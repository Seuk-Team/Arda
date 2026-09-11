"""OpenTimestamps — 사슬 머리를 비트코인에 못 박는다 (ADR-0028 3단계).

**한 문장 정의**: 해시 하나를 공개 캘린더에 맡기면, 그쪽이 전 세계 요청을 모아
비트코인 거래 하나에 새기고, 우리는 "그 뭉치 어디에 우리 것이 있다"는 증명
파일을 받는다.

## 왜 폴리곤과 같이 쓰나

둘은 서로를 보완한다.

| | 폴리곤 Amoy | OpenTimestamps |
|---|---|---|
| 보여주기 | 탐색기 링크 ✅ | 없음 |
| 영구성 | 테스트넷이라 리셋될 수 있음 | 비트코인이라 영구 |
| 개인키 | 필요 | **불필요** |
| 비용 | 가스 (테스트넷이라 0) | **0** |
| 확정까지 | 몇 초 | **몇 시간** |

폴리곤은 *보여주는* 쪽, OTS 는 *남기는* 쪽이다.

## 개인키가 없다는 것의 의미

우리가 거래를 만들지 않는다. 캘린더에 해시만 던지고 영수증을 받는다. 그래서
**이 모듈은 서버에서 그냥 돌려도 된다** — 폴리곤 서명을 GitHub Actions 로
옮긴 이유(서버에 키를 두지 않는다)가 여기에는 해당하지 않는다.

## 두 단계다

1. **stamp** — 캘린더에 제출. 즉시 증명을 받지만 아직 `pending` 이다.
   비트코인 블록에 안 실렸다는 뜻이고, 이 단계의 증명은 "캘린더가 봤다"까지만
   보증한다.
2. **upgrade** — 몇 시간 뒤 다시 물어보면 비트코인 첨부(attestation)가 붙은
   완전한 증명으로 바뀐다. 이때부터 우리 손을 떠난 증거가 된다.

`stamp` 만 하고 `upgrade` 를 안 하면 **비트코인에 실렸는지 영영 모른다.**
주기 실행이 필요한 이유가 그것이다.
"""

import base64
import logging

logger = logging.getLogger(__name__)

NETWORK = "opentimestamps"

# 공개 캘린더. 여러 곳에 내는 이유는 한 곳이 죽어도 증명이 남게 하기 위해서다 —
# 하나만 쓰면 그 운영자가 사라지는 순간 그 기간의 증명이 통째로 뜬다.
# 2026-09-04 실측: b.pool 은 이 개발 환경에서 응답, 나머지는 막혀 있었다.
# 운영·CI 에서는 셋 다 뚫릴 수 있으므로 전부 시도하고 **하나라도 되면 성공**이다.
CALENDARS = (
    "https://b.pool.opentimestamps.org",
    "https://a.pool.opentimestamps.org",
    "https://finney.calendar.eternitywall.com",
)

SUBMIT_TIMEOUT_SEC = 20


def _digest(chain_hash: str) -> bytes:
    """사슬 머리(16진수 64자)를 바이트로. 이 값 자체를 도장 대상으로 쓴다.

    한 번 더 해시하지 않는다 — `chain_hash` 가 이미 SHA-256 결과이고,
    검증하는 쪽이 우리 DB 의 값과 그대로 맞춰볼 수 있어야 하기 때문이다.
    """
    return bytes.fromhex(chain_hash)


def stamp(chain_hash: str) -> str:
    """캘린더에 도장을 찍고 증명을 base64 로 돌려준다.

    캘린더 하나가 죽어도 나머지로 간다. **전부 실패해야 실패**다.
    """
    from opentimestamps.calendar import RemoteCalendar
    from opentimestamps.core.op import OpSHA256
    from opentimestamps.core.serialize import BytesSerializationContext
    from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

    digest = _digest(chain_hash)
    timestamp = Timestamp(digest)

    merged = 0
    errors: list[str] = []
    for url in CALENDARS:
        try:
            timestamp.merge(RemoteCalendar(url).submit(digest, timeout=SUBMIT_TIMEOUT_SEC))
            merged += 1
        except Exception as exc:  # 한 곳이 죽는 것은 정상 범주다
            errors.append(f"{url}: {type(exc).__name__}")
            logger.info("OTS 캘린더 실패 %s (%s)", url, type(exc).__name__)

    if merged == 0:
        raise RuntimeError("모든 OTS 캘린더가 실패했습니다 — " + ", ".join(errors))

    ctx = BytesSerializationContext()
    DetachedTimestampFile(OpSHA256(), timestamp).serialize(ctx)
    return base64.b64encode(ctx.getbytes()).decode()


def is_confirmed(proof_b64: str) -> bool:
    """증명이 **비트코인 블록에 실렸는지**. 아직 캘린더 접수 단계면 False.

    `pending` 첨부만 있는 증명은 "캘린더가 봤다"까지만 보증한다. 그것을
    확정으로 세면 우리가 가진 것보다 강한 주장을 하게 된다.
    """
    from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
    from opentimestamps.core.serialize import BytesDeserializationContext
    from opentimestamps.core.timestamp import DetachedTimestampFile

    raw = base64.b64decode(proof_b64)
    dtf = DetachedTimestampFile.deserialize(BytesDeserializationContext(raw))
    return any(
        isinstance(att, BitcoinBlockHeaderAttestation)
        for _, att in dtf.timestamp.all_attestations()
    )


def bitcoin_height(proof_b64: str) -> int | None:
    """확정된 증명이 걸린 비트코인 블록 높이. 아직이면 None."""
    from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
    from opentimestamps.core.serialize import BytesDeserializationContext
    from opentimestamps.core.timestamp import DetachedTimestampFile

    raw = base64.b64decode(proof_b64)
    dtf = DetachedTimestampFile.deserialize(BytesDeserializationContext(raw))
    for _, att in dtf.timestamp.all_attestations():
        if isinstance(att, BitcoinBlockHeaderAttestation):
            return att.height
    return None


def upgrade(proof_b64: str) -> tuple[str, bool]:
    """캘린더에 다시 물어 증명을 완전한 것으로 갱신한다.

    `(새 증명, 확정됐나)` 를 돌려준다. 아직 블록에 안 실렸으면 원래 증명을
    그대로 돌려주고 `False` — **실패가 아니라 아직인 것**이다. 비트코인 블록은
    10분에 하나씩 나오고 캘린더는 그것을 모아 올리므로 몇 시간이 정상이다.
    """
    from opentimestamps.calendar import RemoteCalendar
    from opentimestamps.core.serialize import (
        BytesDeserializationContext,
        BytesSerializationContext,
    )
    from opentimestamps.core.timestamp import DetachedTimestampFile

    raw = base64.b64decode(proof_b64)
    dtf = DetachedTimestampFile.deserialize(BytesDeserializationContext(raw))

    for url in CALENDARS:
        try:
            calendar = RemoteCalendar(url)
            for msg, attestation in list(dtf.timestamp.all_attestations()):
                # pending 첨부만 갱신 대상이다. 이미 비트코인 것이면 건드리지 않는다.
                if type(attestation).__name__ != "PendingAttestation":
                    continue
                dtf.timestamp.merge(calendar.get_timestamp(msg))
        except Exception as exc:
            logger.info("OTS 갱신 실패 %s (%s)", url, type(exc).__name__)

    ctx = BytesSerializationContext()
    dtf.serialize(ctx)
    updated = base64.b64encode(ctx.getbytes()).decode()
    return updated, is_confirmed(updated)


def explorer_url(proof_b64: str) -> str | None:
    """확정된 증명이 걸린 블록의 탐색기 주소. 아직이면 None."""
    height = bitcoin_height(proof_b64)
    return f"https://mempool.space/block/{height}" if height else None
