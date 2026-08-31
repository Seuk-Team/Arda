"""에이전트 API 라우터 (M2~M4).

M2: 요약 재생성 엔드포인트
M3: 읽기 에이전트 채팅 엔드포인트
M4: 쓰기 도구 (예정)
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status as http
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.entity_resolver import resolve_entities
from app.agent.prompts import render
from app.agent.runtime import run_agent
from app.agent.summarizer import generate_summary
from app.agent.tools import WRITE_TOOL_NAMES, execute_tool
from app.db import get_db
from app.deps import get_current_user
from app.models import Application, User

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


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


class ToolCallOut(BaseModel):
    name: str
    input: dict


class PendingActionOut(BaseModel):
    tool_name: str
    arguments: dict
    description: str


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallOut]
    pending_action: PendingActionOut | None = None
    input_tokens: int
    output_tokens: int
    model: str
    cost_usd: float


class ConfirmRequest(BaseModel):
    tool_name: str
    arguments: dict


class ConfirmResponse(BaseModel):
    ok: bool
    result: dict


@router.post(
    "/applications/{application_id}/summarize",
    response_model=SummaryOut,
)
def regenerate_summary(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """AI 요약 재생성. 로그인한 사람이면 누구나. 기존 요약을 덮어쓴다."""
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원자를 찾을 수 없습니다")

    summary = generate_summary(db, application_id)
    if summary is None:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            "요약을 생성할 수 없습니다 (API 키 또는 프로필 정보를 확인하세요)",
        )

    return SummaryOut(summary=summary, model=app.ai_summary_model)


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """에이전트 채팅 (M3). 읽기 도구로 지원자 검색·조회를 돕는다."""
    system_prompt, _ = render("agent", user_name=user.name, user_role=user.role)
    message = resolve_entities(body.message)

    result = run_agent(
        message=message,
        history=body.history,
        db=db,
        user=user,
        system_prompt=system_prompt,
    )

    pending = None
    if result.pending_action:
        pending = PendingActionOut(
            tool_name=result.pending_action.tool_name,
            arguments=result.pending_action.arguments,
            description=result.pending_action.description,
        )

    from app.agent.runtime import _estimate_cost, AGENT_MODEL
    cost = _estimate_cost(AGENT_MODEL, result.input_tokens, result.output_tokens)

    return ChatResponse(
        reply=result.reply,
        tool_calls=[ToolCallOut(**tc) for tc in result.tool_calls],
        pending_action=pending,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        model=result.model,
        cost_usd=round(cost, 6),
    )


@router.post("/confirm", response_model=ConfirmResponse)
def confirm_action(
    body: ConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """쓰기 도구 확인 실행 (M4). 사용자가 확인 카드를 승인한 뒤 호출한다."""
    if body.tool_name not in WRITE_TOOL_NAMES:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, f"확인 대상이 아닌 도구입니다: {body.tool_name}")

    import json
    raw = execute_tool(body.tool_name, body.arguments, db, user)
    result = json.loads(raw)

    if "error" in result:
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, result["error"])

    return ConfirmResponse(ok=True, result=result)


_STT_MAX_SIZE = 25 * 1024 * 1024  # Whisper 제한: 25 MB
_STT_ALLOWED_TYPES = {
    "audio/webm", "audio/wav", "audio/mpeg", "audio/mp4",
    "audio/ogg", "audio/flac", "audio/x-m4a",
}


@router.post("/stt", response_model=SttResponse)
async def speech_to_text(
    file: UploadFile,
    user: User = Depends(get_current_user),
):
    """음성 파일을 텍스트로 변환 (Whisper + 엔티티 해석)."""
    if file.content_type and file.content_type not in _STT_ALLOWED_TYPES:
        raise HTTPException(
            http.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"지원하지 않는 오디오 형식입니다: {file.content_type}",
        )

    audio_bytes = await file.read()
    if len(audio_bytes) > _STT_MAX_SIZE:
        raise HTTPException(
            http.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "파일 크기가 25 MB를 초과합니다",
        )

    from app.agent.stt import transcribe

    try:
        result = transcribe(audio_bytes, filename=file.filename or "audio.webm")
    except RuntimeError as e:
        raise HTTPException(http.HTTP_503_SERVICE_UNAVAILABLE, str(e))

    return SttResponse(**result)
