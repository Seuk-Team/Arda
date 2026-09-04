"""사슬 머리를 공개 블록체인에 못 박는다 (ADR-0028 2단계).

**한 문장 정의**: 원장의 맨 끝 해시 하나를 폴리곤에 거래로 실어 보낸다. 그 거래는
우리가 회수할 수 없으므로, 나중에 원본을 고치면 안 맞는다는 것이 밖에서 증명된다.

옛날에 문서의 존재 시각을 증명하려고 **신문 광고란에 해시를 실었다.** 신문은
이미 뿌려져 회수할 수 없다. 여기서는 블록체인이 그 신문이다.

## 왜 값 하나만 올리는가

`document_anchors` 의 각 고리는 **앞 고리의 해시를 재료로** 쓴다. 그래서 seq=20
의 `chain_hash` 는 1~20 전체에 대한 약속이다. 머리 하나를 올리면 그 앞이 전부
덮인다 — 머클 트리도, 고리마다의 증명 파일도 필요 없다.

## 왜 스마트 컨트랙트를 안 쓰는가

배포할 것이 없으면 틀릴 것도 없다. **자기 자신에게 보내는 0원짜리 거래의
`data` 칸에 해시를 넣는다.** 탐색기에서 그대로 읽히고, 컨트랙트 배포·검증·
업그레이드 같은 표면이 하나도 안 생긴다. 컨트랙트가 필요해지는 것은 체인 위에서
**조회**를 하고 싶을 때인데, 조회는 우리 DB 가 한다.

## 설정 (전부 환경변수. 하나라도 없으면 이 기능은 꺼진다)

- `CHAIN_RPC_URL`     — 폴리곤 RPC 주소
- `CHAIN_PRIVATE_KEY` — 서명용 개인키. **테스트넷 전용 지갑의 것만 넣는다**
- `CHAIN_NETWORK`     — 기록용 이름 (기본 `polygon-amoy`)

**개인키를 코드·로그·응답 어디에도 남기지 않는다.** 이 모듈은 개인키에서 뽑은
주소만 밖으로 낸다. 테스트넷 키라 값이 없지만, 습관이 무너지면 메인넷으로
갈아탈 때 그대로 사고가 된다.
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 기본값은 폴리곤 테스트넷(Amoy)이다. 메인넷을 기본으로 두지 않는다 —
# 설정을 덜 한 채 배포했을 때 진짜 돈이 나가는 쪽으로 기울면 안 된다.
DEFAULT_NETWORK = "polygon-amoy"

# 거래 하나가 쓸 수 있는 가스 상한. data 32바이트짜리 단순 전송이라 21,000 +
# 데이터 비용이면 끝나지만, 체인마다 계산이 조금씩 달라 여유를 둔다.
GAS_LIMIT = 100_000

# 블록 확정을 기다리는 시간. 폴리곤은 보통 몇 초다. 여기서 오래 붙잡으면
# 요청이 타임아웃되므로 짧게 두고, 못 받으면 pending 으로 남긴다.
RECEIPT_TIMEOUT_SEC = 30


@dataclass(frozen=True)
class ChainConfig:
    rpc_url: str
    private_key: str
    network: str

    @property
    def is_testnet(self) -> bool:
        """이름에 mainnet 이 없으면 테스트넷으로 본다.

        보수적으로 판단한다 — 확실히 메인넷일 때만 메인넷이라고 한다.
        """
        return "mainnet" not in self.network.lower()


def load_config() -> ChainConfig | None:
    """환경변수에서 설정을 읽는다. 하나라도 없으면 `None` — 기능이 꺼진 것이다.

    꺼진 상태가 정상 상태다. 설정이 없다고 서버가 안 뜨거나 접수가 막히면
    안 된다 — 못 박기는 **있으면 좋은 것**이지 접수의 전제가 아니다.
    """
    rpc = (os.getenv("CHAIN_RPC_URL") or "").strip()
    key = (os.getenv("CHAIN_PRIVATE_KEY") or "").strip()
    if not rpc or not key:
        return None
    return ChainConfig(
        rpc_url=rpc,
        private_key=key,
        network=(os.getenv("CHAIN_NETWORK") or DEFAULT_NETWORK).strip(),
    )


def unavailable_reason() -> str | None:
    """왜 못 쓰는지 한 줄로. 쓸 수 있으면 `None`.

    요약 백엔드(`agent/backends.py`)와 같은 모양이다 — 화면에 "안 됩니다"만
    뜨고 이유를 모르는 상황을 09/02 에 한 번 겪었다.
    """
    if not (os.getenv("CHAIN_RPC_URL") or "").strip():
        return "CHAIN_RPC_URL 미설정"
    if not (os.getenv("CHAIN_PRIVATE_KEY") or "").strip():
        return "CHAIN_PRIVATE_KEY 미설정"
    try:
        _account_address(load_config())  # 키 모양이 틀렸으면 여기서 걸린다
    except Exception as exc:
        return f"CHAIN_PRIVATE_KEY 를 읽을 수 없습니다 ({type(exc).__name__})"
    return None


def _account_address(config: ChainConfig) -> str:
    from eth_account import Account

    return Account.from_key(config.private_key).address


@dataclass(frozen=True)
class SentTx:
    tx_hash: str
    from_address: str
    block_number: int | None  # 확정 전이면 None
    confirmed: bool


def publish_hash(config: ChainConfig, chain_hash: str) -> SentTx:
    """해시 하나를 체인에 실어 보낸다.

    **자기 자신에게 보내는 0 값 거래**다. 받는 사람이 우리라서 남의 지갑을
    건드리지 않고, 값이 0 이라 옮겨지는 자산도 없다. 남는 것은 `data` 칸에
    적힌 해시와 그 거래가 실린 블록의 시각뿐 — 우리가 원한 것이 정확히 그것이다.

    영수증(블록 확정)을 잠깐 기다려 보고, 시간 안에 안 오면 `confirmed=False`
    로 돌려준다. **거래는 이미 보내졌으므로 실패가 아니다** — 나중에 상태만
    다시 확인하면 된다.
    """
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(config.rpc_url))
    account = _account_address(config)

    tx = {
        "from": account,
        "to": account,  # 자기 자신에게
        "value": 0,
        "nonce": w3.eth.get_transaction_count(account),
        "gas": GAS_LIMIT,
        "chainId": w3.eth.chain_id,
        # 해시 64자를 그대로 바이트로 넣는다. 탐색기에서 읽힌다.
        "data": "0x" + chain_hash,
    }
    # 가스 값은 체인이 알려주는 현재 시세를 쓴다. 직접 정하면 너무 낮을 때
    # 거래가 영영 안 실린다.
    tx["maxFeePerGas"] = w3.eth.gas_price * 2
    tx["maxPriorityFeePerGas"] = w3.eth.max_priority_fee

    signed = w3.eth.account.sign_transaction(tx, private_key=config.private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hex = tx_hash.hex()
    if not tx_hex.startswith("0x"):
        tx_hex = "0x" + tx_hex

    try:
        receipt = w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=RECEIPT_TIMEOUT_SEC
        )
        return SentTx(
            tx_hash=tx_hex,
            from_address=account,
            block_number=receipt["blockNumber"],
            confirmed=receipt["status"] == 1,
        )
    except Exception:
        # 확정을 못 봤을 뿐 보낸 것은 보낸 것이다. 여기서 실패로 적으면
        # 같은 값을 두 번 보내게 된다.
        logger.info("거래는 보냈으나 확정을 못 봤다: %s", tx_hex)
        return SentTx(
            tx_hash=tx_hex, from_address=account, block_number=None, confirmed=False
        )


def fetch_status(config: ChainConfig, tx_hash: str) -> SentTx | None:
    """보냈던 거래가 블록에 실렸는지 다시 본다. 아직이면 `None`."""
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(config.rpc_url))
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
    except Exception:
        return None
    if receipt is None:
        return None
    return SentTx(
        tx_hash=tx_hash,
        from_address=receipt.get("from") or "",
        block_number=receipt["blockNumber"],
        confirmed=receipt["status"] == 1,
    )


def explorer_url(network: str, tx_hash: str) -> str | None:
    """탐색기 주소. 발표에서 이 링크를 그대로 연다."""
    bases = {
        "polygon-amoy": "https://amoy.polygonscan.com/tx/",
        "polygon-mainnet": "https://polygonscan.com/tx/",
    }
    base = bases.get(network)
    return base + tx_hash if base else None
