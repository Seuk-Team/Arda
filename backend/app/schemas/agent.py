"""에이전트 API 스키마 (ADR-0035 Phase 4).

`application/api/agent.py` 라우터에서 분리 · 서비스 함수 (agent_service) 와 라우터가
같은 스키마를 참조하기 위한 공통 자리.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SttResponse(BaseModel):
    raw: str
    resolved: str
    duration_ms: int
    audio_duration_sec: float
    cost_usd: float


class SummaryOut(BaseModel):
    summary: str
    model: str | None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list)
    # 담당자가 동명이인 선택지(ChatResponse.choices) 버튼으로 고른 지원자. 있으면
    # 이름 조회를 건너뛰고 이 id 로 확정한다 (2026-09-08 팀장 요청 — "ID 를 손으로
    # 치지 않고 직접 고르게").
    application_id: int | None = None
    # 대화 스레드 식별자. 프론트가 창을 열 때 발급해 여러 턴에 걸쳐 보낸다.
    # 없어도 되고, 있으면 agent_traces 에 같은 값으로 묶여 다중 턴 학습에 쓸 수 있다.
    session_id: str | None = None


class ToolCallOut(BaseModel):
    name: str
    input: dict


class PendingActionOut(BaseModel):
    tool_name: str
    arguments: dict
    description: str


class ChoiceOut(BaseModel):
    """사람이 골라야 하는 갈림길 하나 (동명이인). 프론트가 카드로 그린다.

    pending_action 이 붙어 오면 카드 안 확인 버튼 클릭 = agent.confirm 직접 실행
    (담당자가 원래 요청 → 이름 목록 → id 재입력 → 확인 카드 → 확인, 네 걸음이던
    것을 카드 딸깍 한 번으로 줄인다). 없으면 폴백으로 message + application_id
    를 다시 chat 에 보내 서버가 pending 을 만드는 두 단계 흐름을 탄다.
    """
    label: str
    application_id: int
    message: str
    # 카드 안에서 사람이 고를 만한 만큼의 상세를 함께 준다 — label 하나로 이어붙이던
    # 형식은 프론트가 정렬·강조를 잡을 수 없어 카드에 안 맞는다.
    email: str | None = None
    stage_label: str | None = None
    career_years: int | None = None
    education: str | None = None
    # 규칙 라우터가 change_stage 를 잡았고 동명이인이 났을 때 각 후보의 pending 을 미리
    # 만들어 붙인다. 도구 하나에 후보만 여러이므로 arguments 는 application_id 만 다르다.
    pending_action: PendingActionOut | None = None


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallOut]
    pending_action: PendingActionOut | None = None
    input_tokens: int
    output_tokens: int
    # 캐시로 처리된 몫. cache_read_tokens 가 계속 0이면 캐시가 안 걸린 것이다
    cache_write_tokens: int
    cache_read_tokens: int
    # 모델명이 아니라 `backend:model` 태그다 (예: anthropic:claude-haiku-4-5-20251001,
    # ollama:qwen3:8b). 토크나이저가 달라 백엔드 간 토큰 수를 비교할 수 없으므로
    # 어느 백엔드가 낸 숫자인지 함께 남긴다.
    model: str
    cost_usd: float
    # 백엔드 식별자. 로컬은 프롬프트 캐싱 개념 자체가 없어서 cache_* 가 0 인데,
    # 이 필드가 "캐시 미적중"과 "캐시 개념 없음"을 구분해 준다.
    backend: str = ""
    # 동명이인 등 담당자가 골라야 답이 이어지는 경우의 선택지. 비면 버튼 없음.
    choices: list[ChoiceOut] = Field(default_factory=list)


class ConfirmRequest(BaseModel):
    tool_name: str
    arguments: dict


class ConfirmResponse(BaseModel):
    ok: bool
    result: dict


class ProbeClaim(BaseModel):
    claim: str
    type: str
    questions: list[str]
    # 이 인용이 자기소개서에서 왔는지 이력서에서 왔는지. 면접관이 원문을 찾으러 간다.
    source: str = "자기소개서"


class ProbesOut(BaseModel):
    claims: list[ProbeClaim]
