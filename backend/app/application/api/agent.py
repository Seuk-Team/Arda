"""에이전트 API 라우터 (M2~M4).

M2: 요약 재생성 엔드포인트
M3: 읽기 에이전트 채팅 엔드포인트
M4: 쓰기 도구 (예정)
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status as http
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.backends import get_summary_backend
from app.agent.entity_resolver import resolve_entities
from app.agent.intent_router import DirectAction, classify
from app.hiring.company import prompt_context as company_prompt_context
from app.models import AgentTrace
from app.agent.interview_probe import generate_probes, sources_of
from app.agent.prompts import render
from app.agent.runtime import _describe_action, run_agent
from app.agent.summarizer import generate_summary
from app.agent.tools import WRITE_TOOL_NAMES, execute_tool
from app.db import get_db
from app.deps import get_current_user
from app.shared.labels import STAGE_LABEL_KR
from app.models import Application, User
from app.application.stages import STAGE_ORDER, StageTransitionError, validate_transition

# Pydantic 스키마 (ADR-0035 Phase 4 · schemas/agent.py 로 이관)
from app.schemas.agent import (
    ChatRequest,
    ChatResponse,
    ChoiceOut,
    ConfirmRequest,
    ConfirmResponse,
    PendingActionOut,
    SttResponse,
    SummaryOut,
    ToolCallOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post(
    "/applications/{application_id}/summarize",
    response_model=SummaryOut,
)
def regenerate_summary(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """AI 요약 재생성. 로그인한 사람이면 누구나. 기존 요약을 덮어쓴다.

    실패 사유를 분리해서 돌려준다. 이전에는 "API 키 또는 프로필 정보를 확인하세요"
    한 문구로 뭉쳐서, 09/02 실측에서 김데모(프로필 빈 테스트 행)로 시험했을 때
    원인이 키 폐기인지 데이터인지 갈리지 않았다. 이제는:
    - 백엔드 사용 불가(키 미설정 등) → **503** + `backend.unavailable_reason()` 원문
    - 그 외 실패(LLM 응답 파싱 실패·중간 예외) → **422** + 재시도 안내
    프로필이 정말 비어 있는 경우는 실패가 아니라 `insufficient=True` 요약이
    저장되므로 여기까지 오지 않는다.
    """
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원자를 찾을 수 없습니다")

    reason = get_summary_backend().unavailable_reason()
    if reason:
        raise HTTPException(
            http.HTTP_503_SERVICE_UNAVAILABLE,
            f"요약 백엔드를 사용할 수 없습니다: {reason}",
        )

    summary = generate_summary(db, application_id)
    if summary is None:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            "요약 생성에 실패했습니다. LLM 응답을 처리하지 못했습니다 — 잠시 후 다시 시도해 주세요.",
        )

    return SummaryOut(summary=summary, model=app.ai_summary_model)


from app.schemas.agent import ProbeClaim, ProbesOut  # noqa: F401,E402


@router.post(
    "/applications/{application_id}/interview-probes",
    response_model=ProbesOut,
)
def interview_probes(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """자기소개서·이력서에서 확인할 주장과 면접 꼬리 질문을 뽑는다 (AI면접 설계 §5-5).

    공고 요건도 함께 넘기지만 **인용하지는 않는다** — 회사가 쓴 글이라 지원자의
    주장이 될 수 없다. 무엇을 먼저 물을지 고르는 데만 쓴다.

    **저장하지 않는다.** 부를 때마다 새로 만든다 — 아직 화면도 붙지 않았고,
    저장 위치(`interview_turns`)는 면접 세션이 있을 때 정해진다. 재생성이
    사람 손에 달려 있다는 점은 요약과 같다(ADR-0011 §3-4).

    **참·거짓을 판정하지 않는다.** 질문만 돌려주고 대조는 면접관이 한다
    (ADR-0003 · ADR-0026 결정 3).
    """
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원자를 찾을 수 없습니다")

    # 요약과 같은 이유로 여기서 먼저 본다 — 이 검사를 빼면 키 미설정이
    # "생성 실패(422)" 로 둔갑해 원인이 안 보인다
    reason = get_summary_backend().unavailable_reason()
    if reason:
        raise HTTPException(
            http.HTTP_503_SERVICE_UNAVAILABLE,
            f"질문 생성 백엔드를 사용할 수 없습니다: {reason}",
        )

    sources = sources_of(app, db)
    if not (sources["cover_letter"].strip() or sources["resume"].strip()):
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            "자기소개서와 이력서가 모두 없어 확인할 주장을 뽑을 수 없습니다",
        )

    claims = generate_probes(sources)
    if claims is None:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            "질문 생성에 실패했습니다. LLM 응답을 처리하지 못했습니다 — 잠시 후 다시 시도해 주세요.",
        )

    # 빈 목록은 실패가 아니다 — 감상·다짐만 쓴 자기소개서가 있고,
    # 그때 억지로 뽑은 질문은 면접관에게 해롭다
    return ProbesOut(claims=[ProbeClaim(**c) for c in claims])


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """에이전트 채팅 (M3). 읽기 도구로 지원자 검색·조회를 돕는다.

    빈출 요청은 `intent_router.classify` 로 먼저 잡아 LLM 을 우회한다 (Phase 1
    레버 ②). 확신도 높은 것만 라우팅하고 애매하면 그대로 LLM 흐름으로 이어감.
    """
    system_prompt, _ = render("agent", user_name=user.name, user_role=user.role)
    # 회사 절 — company_profile 이 채워져 있으면 시스템 프롬프트 뒤에 붙는다.
    # 아르가 회사 관련 질문에 이 절만 근거로 답한다 (지어내지 않는다).
    system_prompt = system_prompt + company_prompt_context(db)
    message = resolve_entities(body.message)

    # 레버 ② — 규칙 라우터 먼저. 매치되면 LLM 안 부르고 즉시 응답
    intent = classify(message)
    if intent is not None:
        logger.info(
            "intent_router_hit",
            extra={
                "rule": intent.rule,
                "tool": intent.tool_name,
                "is_write": intent.is_write,
            },
        )
        return _handle_direct(
            intent, db, user, original=body.message, application_id=body.application_id
        )

    # 선택지 버튼으로 온 요청 — LLM 에게도 어느 지원자인지 못 박아 준다. 이력에는
    # 동명이인 목록이 이미 있으므로 id 한 줄이면 충분하다.
    if body.application_id is not None:
        message = f"{message}\n(담당자가 선택한 지원자 ID: {body.application_id} — 이 지원자로 진행)"

    result = run_agent(
        message=message,
        history=body.history,
        db=db,
        user=user,
        system_prompt=system_prompt,
        request_id=getattr(request.state, "request_id", None),
    )

    pending = None
    if result.pending_action:
        pending = PendingActionOut(
            tool_name=result.pending_action.tool_name,
            arguments=result.pending_action.arguments,
            description=result.pending_action.description,
        )

    # 비용은 백엔드가 계산해서 실어 보낸다. 여기서 PRICING 표를 다시 조회하면
    # 로컬 모델명이 haiku 단가로 폴백해 있지도 않은 요금이 찍힌다.
    cost = result.cost_usd

    # 학습 데이터 원본으로 남긴다 (ADR-0024 Qwen QLoRA · agent_traces).
    # 실패해도 대화는 계속되어야 하므로 예외를 삼킨다 — 회고성 저장이 실서비스를
    # 막지 않는다.
    try:
        tool_results = getattr(result, "tool_results", []) or []
        merged_tools = []
        for i, tc in enumerate(result.tool_calls):
            out = tool_results[i].get("output") if i < len(tool_results) and isinstance(tool_results[i], dict) else None
            merged_tools.append({"name": tc.get("name"), "input": tc.get("input"), "output": out})
        db.add(AgentTrace(
            request_id=getattr(request.state, "request_id", None),
            session_id=body.session_id,
            turn_index=len(body.history) // 2,
            user_id=user.id,
            user_message=body.message,
            assistant_reply=result.reply or "",
            history=body.history,
            tool_calls=merged_tools,
            pending_action=(pending.model_dump() if pending else None),
            backend=result.backend or "",
            model_tag=result.model or "",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=round(cost, 6),
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()

    return ChatResponse(
        reply=result.reply,
        tool_calls=[ToolCallOut(**tc) for tc in result.tool_calls],
        pending_action=pending,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cache_write_tokens=result.cache_write_tokens,
        cache_read_tokens=result.cache_read_tokens,
        model=result.model,
        cost_usd=round(cost, 6),
        backend=result.backend,
        choices=_choices_from_tool_results(
            result.reply, getattr(result, "tool_results", []), body.message
        ),
    )


# ── 동명이인 선택지 ──────────────────────────────────────────



from app.application.agent_service import (
    CHOICE_LIMIT as _CHOICE_LIMIT,
    build_per_choice_pendings as _build_per_choice_pendings,
    choice_for_app as _choice_for_app,
    choices_from_tool_results as _choices_from_tool_results,
    format_reply as _format_reply,
    handle_direct as _handle_direct,
    lookup_applicants_by_name as _lookup_applicants_by_name,
    router_reply as _router_reply,
    router_response as _router_response,
    stage_label as _stage_label,
    stage_rule_reply as _stage_rule_reply,
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
