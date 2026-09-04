"""제출물 무결성 응답 스키마 (ADR-0028)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AnchorItem(BaseModel):
    """고리 하나 + 지금 원본과 맞춰 본 결과."""

    model_config = ConfigDict(from_attributes=True)

    seq: int
    doc_type: str
    file_id: int | None = None
    filename: str | None = None  # 첨부일 때만. 담당자가 어느 파일인지 알아야 한다
    content_sha256: str
    chain_hash: str
    anchored_at: datetime
    # ok | mismatch | unreadable — 뜻은 anchoring.verify_anchor 참고
    status: str
    reason: str | None = None


class ApplicationIntegrityOut(BaseModel):
    """지원서 하나의 제출물 무결성.

    `verdict` 는 항목들을 한 줄로 요약한 것이다. 화면에서 배지 하나로 보여줄 값이라
    **나쁜 쪽이 이긴다** — 하나라도 어긋나면 전체가 `mismatch` 다. 셋 중 무엇이
    걸렸는지는 `items` 를 펼쳐 본다.

    `none` 은 앵커가 아직 없다는 뜻이다 — ADR-0028 이전에 접수된 지원서가 그렇다.
    "깨끗하다"가 아니라 **"증명할 근거가 없다"** 이므로 ok 와 섞지 않는다.
    """

    application_id: int
    anchored: bool
    verdict: str  # ok | mismatch | unreadable | none
    items: list[AnchorItem]


class PublicationOut(BaseModel):
    """사슬 머리를 공개 체인에 올린 거래 한 건 (ADR-0028 2단계)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    network: str
    covered_through_seq: int
    chain_hash: str
    tx_hash: str | None = None
    block_number: int | None = None
    status: str  # pending | confirmed | failed
    error: str | None = None
    created_at: datetime
    confirmed_at: datetime | None = None
    # 탐색기 링크. 발표에서 이걸 그대로 연다.
    explorer_url: str | None = None


class ChainIntegrityOut(BaseModel):
    """사슬 전체 검증 결과. `broken_at` 은 처음 어긋난 자리의 seq.

    `published` 는 **가장 최근에 공개 체인에 못 박은 거래**다. 이게 있어야
    "우리 DB 안의 주장"이 "밖에서 확인되는 사실"이 된다. 없으면 아직 1단계다.
    """

    intact: bool
    length: int
    broken_at: int | None = None
    reason: str | None = None
    published: PublicationOut | None = None
    # 못 박은 뒤에 쌓인 고리 수. 이만큼이 아직 외부 증명이 없는 구간이다.
    unpublished_count: int = 0
