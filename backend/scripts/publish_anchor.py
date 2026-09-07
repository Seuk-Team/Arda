"""사슬 머리를 폴리곤에 올린다 — **GitHub Actions 에서 돈다** (ADR-0028 2단계).

## 왜 서버가 아니라 여기인가

폴리곤에 거래를 쓰려면 **지갑 개인키로 서명**해야 한다. 그 키를 서버에 두면
서버 셸에 들어갈 수 있는 사람이 곧 서명 권한을 갖는다. 인프라 오너 판단으로
**키를 서버 밖(Actions secret)에 두기로** 했다 (2026-09-04 팀장 검토 Q2·Q3).

그래서 일이 이렇게 갈린다:

    서버   — 무엇을 올려야 하는지 알려주고(`publications/start`),
             결과를 기록받는다(`publications/{id}/result`). **키 없음**
    Actions — 키를 쥐고 서명·전송한다. **DB 접근 없음**

둘 다 상대를 못 믿어도 된다. 서버는 Actions 가 보낸 `tx_hash` 를 검증하지
못하지만, 그 해시가 가리키는 **체인의 값이 진실**이라 거짓으로 적으면
탐색기에서 대조할 때 드러난다.

## 실패해도 기록은 남는다

`publications/start` 로 자리를 먼저 잡고 시작한다. 전송에 실패하면 그 행을
`failed` 로 닫는다 — 조용히 사라지면 다음에 왜 안 됐는지 알 수 없다.

## 필요한 것 (전부 Actions secret)

    ARDA_API_BASE      https://api.seuk.suvisdev.cloud/api/v1
    ARDA_API_TOKEN     admin JWT — **secret 이 아니라 워크플로가 매 실행마다
                       로그인해서 넣어 준다.** JWT 는 12시간이면 만료돼서
                       (security.py `JWT_EXPIRES_MINUTES`) secret 에 박아 두면
                       하루 만에 401 로 죽는다
    CHAIN_RPC_URL      https://polygon-amoy-bor-rpc.publicnode.com
    CHAIN_PRIVATE_KEY  테스트넷 전용 지갑 개인키
    CHAIN_NETWORK      polygon-amoy (기본값)

**개인키를 찍지 않는다.** 로그에 나가는 것은 주소뿐이다 — Actions 로그는
저장소 권한이 있는 사람 모두가 본다.
"""

from __future__ import annotations

import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import chain  # noqa: E402  — sys.path 를 먼저 세워야 한다

TIMEOUT = 30


def _api(method: str, path: str, token: str, base: str, **kwargs):
    url = base.rstrip("/") + path
    resp = requests.request(
        method,
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
        **kwargs,
    )
    return resp


def main() -> int:
    base = os.environ["ARDA_API_BASE"]
    token = os.environ["ARDA_API_TOKEN"]

    config = chain.load_config()
    if config is None:
        print(f"::error::체인 설정이 없습니다 — {chain.unavailable_reason()}")
        return 1

    if not config.is_testnet:
        # 메인넷은 진짜 돈이 나간다. 자동 실행이 사람 모르게 그쪽으로 가면 안 된다.
        print(f"::error::메인넷({config.network})은 자동 게시 대상이 아닙니다")
        return 1

    # 1) 자리를 먼저 잡는다 — 올릴 것이 없으면 409 이고 그건 실패가 아니다.
    started = _api(
        "POST", f"/integrity/publications/start?network={config.network}", token, base
    )
    if started.status_code == 409:
        print(f"올릴 것이 없습니다: {started.json().get('message')}")
        return 0
    if started.status_code >= 400:
        print(f"::error::자리 잡기 실패 {started.status_code}: {started.text[:200]}")
        return 1

    row = started.json()
    publication_id, chain_hash = row["id"], row["chain_hash"]
    print(f"게시 대상 seq={row['covered_through_seq']} hash={chain_hash[:16]}…")

    # 2) 서명·전송. 키는 이 프로세스 밖으로 나가지 않는다.
    try:
        sent = chain.publish_hash(config, chain_hash)
    except Exception as exc:
        print(f"::error::전송 실패 {type(exc).__name__}: {str(exc)[:200]}")
        _api(
            "POST",
            f"/integrity/publications/{publication_id}/result",
            token,
            base,
            json={"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:2000]},
        )
        return 1

    print(f"보냄 tx={sent.tx_hash}  from={sent.from_address}")

    # 3) 결과를 되돌려 준다. 확정을 못 봤어도 pending 이지 실패가 아니다 —
    #    실패로 적으면 같은 값을 다음 실행에서 또 보낸다.
    recorded = _api(
        "POST",
        f"/integrity/publications/{publication_id}/result",
        token,
        base,
        json={
            "status": "confirmed" if sent.confirmed else "pending",
            "tx_hash": sent.tx_hash,
            "block_number": sent.block_number,
            "from_address": sent.from_address,
        },
    )
    if recorded.status_code >= 400:
        # 체인에는 올라갔는데 기록이 안 된 상태다. 사람이 봐야 한다.
        print(f"::error::결과 기록 실패 {recorded.status_code} — tx={sent.tx_hash}")
        return 1

    url = chain.explorer_url(config.network, sent.tx_hash)
    print(f"완료: {url or sent.tx_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
