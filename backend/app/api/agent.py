"""에이전트 API 라우터 (M2~M4).

M2: 요약 재생성 엔드포인트
M3: 읽기 에이전트 채팅 엔드포인트
M4: 쓰기 도구 (예정)
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status as http
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.backends import get_summary_backend
from app.agent.entity_resolver import resolve_entities
from app.agent.intent_router import DirectAction, classify
from app.agent.prompts import render
from app.agent.runtime import _describe_action, run_agent
from app.agent.summarizer import generate_summary
from app.agent.tools import WRITE_TOOL_NAMES, execute_tool
from app.db import get_db
from app.deps import get_current_user
from app.labels import STAGE_LABEL_KR
from app.models import Application, User
from app.stages import STAGE_ORDER, StageTransitionError, validate_transition

logger = logging.getLogger(__name__)

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
        return _handle_direct(intent, db, user)

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
    )


# ── 규칙 라우터 헬퍼 (Phase 1 레버 ②) ──────────────────────────

def _handle_direct(intent: DirectAction, db: Session, user: User) -> ChatResponse:
    """라우터가 매치한 요청 실행. LLM 안 부름.

    - 읽기 도구 (`is_write=False`): 도구 즉시 실행 → 결과를 사람이 읽는 짧은
      답변으로 렌더 → reply 로 반환
    - 쓰기 도구 (`is_write=True`): `pending_action` 만 만들고 실제 실행은
      담당자가 확인 카드를 승인해 `/confirm` 이 부를 때
    - 이름 → id 조회가 필요한 경우 (`_name_lookup`): DB 에서 검색 후 정확·부분
      일치 순. 0건이면 되묻기, 동명이인이면 이름 나열해 되묻기, 1건이면 id 채움
    """
    args = dict(intent.args)  # 원본 mutate 방지
    app: Application | None = None

    if "_name_lookup" in args:
        name = args.pop("_name_lookup")
        found = _lookup_applicants_by_name(db, name)
        if not found:
            return _router_reply(f"'{name}' 지원자를 찾지 못했어요. 이름을 다시 확인해 주세요.")
        if len(found) > 1:
            names = ", ".join(a.name for a in found[:5])
            return _router_reply(
                f"'{name}' 이름으로 여러 명이 있어요: {names}. 어떤 분인지 더 알려 주세요."
            )
        app = found[0]
        args["application_id"] = app.id

    if intent.is_write:
        if intent.tool_name == "change_stage":
            # 카드를 만들기 **전에** 전환 규칙을 검사한다. 실행 단계(/confirm)에서 422 로
            # 튀면 카드가 화면에 남아 누를 때마다 같은 오류가 쌓인다 (2026-09-02 실측:
            # 한도윤 applied→interview, 빨간 박스 5개). 어긋나면 이유를 말하고, 한 칸
            # 건너뛴 경우엔 '다음 단계' 카드를 대신 제안한다 — 담당자가 원한 방향은 맞으니.
            if app is None and args.get("application_id") is not None:
                app = db.get(Application, int(args["application_id"]))
            to_stage = args.get("to_stage")
            if app is not None and to_stage:
                try:
                    validate_transition(app.current_stage, to_stage)
                except StageTransitionError as e:
                    return _stage_rule_reply(app, to_stage, str(e), db)
        pending = PendingActionOut(
            tool_name=intent.tool_name,
            arguments=args,
            description=_describe_action(intent.tool_name, args, db),
        )
        return _router_response(
            reply="",
            tool_calls=[ToolCallOut(name=intent.tool_name, input=args)],
            pending=pending,
        )

    # 읽기 도구 — 즉시 실행 + 템플릿 렌더
    output = execute_tool(intent.tool_name, args, db, user, compact=False)
    try:
        result = json.loads(output)
    except json.JSONDecodeError:
        result = {}
    reply = _format_reply(intent.tool_name, result)
    return _router_response(
        reply=reply,
        tool_calls=[ToolCallOut(name=intent.tool_name, input=args)],
        pending=None,
    )


def _stage_rule_reply(app: Application, to_stage: str, reason: str, db: Session) -> ChatResponse:
    """전환 규칙에 어긋난 요청에 대한 안내. 가능하면 '다음 단계' 카드를 대신 제안."""
    cur = app.current_stage
    cur_kr = STAGE_LABEL_KR.get(cur, cur)
    to_kr = STAGE_LABEL_KR.get(to_stage, to_stage)

    if cur == to_stage:
        return _router_reply(f"{app.name} 님은 이미 {to_kr} 단계예요.")

    # 전진 두 칸 이상 → 바로 다음 단계를 대신 제안
    if cur in STAGE_ORDER and to_stage in STAGE_ORDER:
        here, there = STAGE_ORDER.index(cur), STAGE_ORDER.index(to_stage)
        if there - here > 1:
            nxt = STAGE_ORDER[here + 1]
            nxt_kr = STAGE_LABEL_KR.get(nxt, nxt)
            args = {"application_id": app.id, "to_stage": nxt}
            pending = PendingActionOut(
                tool_name="change_stage",
                arguments=args,
                description=_describe_action("change_stage", args, db),
            )
            return _router_response(
                reply=(
                    f"{app.name} 님은 지금 {cur_kr} 단계라 {to_kr}(으)로 바로 못 옮겨요 "
                    f"(한 단계씩만 진행). 먼저 {nxt_kr}(으)로 옮길까요?"
                ),
                tool_calls=[ToolCallOut(name="change_stage", input=args)],
                pending=pending,
            )

    return _router_reply(f"{app.name} 님: {reason}")


def _lookup_applicants_by_name(db: Session, name: str) -> list[Application]:
    """정확 일치 우선, 없으면 부분 일치. 동명이인 감지 위해 다 반환."""
    exact = db.execute(
        select(Application).where(Application.name == name).limit(5)
    ).scalars().all()
    if exact:
        return list(exact)
    partial = db.execute(
        select(Application).where(Application.name.like(f"%{name}%")).limit(5)
    ).scalars().all()
    return list(partial)


def _router_reply(text: str) -> ChatResponse:
    """짧은 안내만 있는 라우터 응답 (도구 호출 없음, 되묻기 등)."""
    return _router_response(reply=text, tool_calls=[], pending=None)


def _router_response(
    reply: str,
    tool_calls: list[ToolCallOut],
    pending: PendingActionOut | None,
) -> ChatResponse:
    """라우터 응답 공통 shape. backend/model 태그로 라우터 힛을 표시."""
    return ChatResponse(
        reply=reply,
        tool_calls=tool_calls,
        pending_action=pending,
        input_tokens=0,
        output_tokens=0,
        cache_write_tokens=0,
        cache_read_tokens=0,
        model="router:v1",
        cost_usd=0.0,
        backend="router",
    )


def _format_reply(tool_name: str, result: dict) -> str:
    """도구 결과 → 담당자용 짧은 한국어 답변. LLM 없이 코드로 렌더.

    복잡한 요약이 필요 없는 뻔한 결과에 쓴다 — 지원자 목록·상세 등. 이메일
    본문 같은 자연어 생성은 여기 못 잡으니 라우터가 아예 안 낚아채고 LLM 로.
    """
    if tool_name == "search_applications":
        results = result.get("results") or []
        count = result.get("count", len(results))
        if count == 0:
            return "검색 결과가 없어요. 다른 조건으로 찾아볼까요?"
        header = f"지원자 {count}명이 검색됐어요."
        lines = []
        for a in results[:5]:
            name = a.get("name", "?")
            years = a.get("career_years")
            years_str = f" ({years}년)" if isinstance(years, int) else ""
            skills = a.get("skills") or []
            skills_str = ", ".join(skills[:3]) if skills else ""
            stage_kr = STAGE_LABEL_KR.get(a.get("current_stage", ""), "")
            parts = [f"- **{name}**{years_str}"]
            if stage_kr:
                parts.append(f"— {stage_kr}")
            if skills_str:
                parts.append(f"— {skills_str}")
            lines.append(" ".join(parts))
        tail = f"\n\n(총 {count}명 중 상위 5명 표시)" if count > 5 else ""
        return "\n".join([header, *lines]) + tail
    # 다른 읽기 도구 확장 대비 — 원시 JSON 잘라서 폴백
    return f"{tool_name} 결과: {json.dumps(result, ensure_ascii=False)[:200]}"


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
