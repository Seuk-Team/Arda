"""에이전트 API 라우터 (M2~M4).

M2: 요약 재생성 엔드포인트
M3: 읽기 에이전트 채팅 엔드포인트
M4: 쓰기 도구 (예정)
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status as http
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.backends import get_summary_backend
from app.agent.entity_resolver import resolve_entities
from app.agent.intent_router import DirectAction, classify
from app.company import prompt_context as company_prompt_context
from app.models import AgentTrace
from app.agent.interview_probe import generate_probes, sources_of
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


class ProbeClaim(BaseModel):
    claim: str
    type: str
    questions: list[str]
    # 이 인용이 자기소개서에서 왔는지 이력서에서 왔는지. 면접관이 원문을 찾으러 간다.
    source: str = "자기소개서"


class ProbesOut(BaseModel):
    claims: list[ProbeClaim]


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

_CHOICE_LIMIT = 6


def _stage_label(stage: str | None) -> str | None:
    return STAGE_LABEL_KR.get(stage or "", "") or None


def _choice_for_app(
    app: Application,
    original: str,
    pending: PendingActionOut | None = None,
) -> ChoiceOut:
    return ChoiceOut(
        # label 은 짧게 (이름 + ID). 상세는 카드가 필드별로 그린다.
        label=f"{app.name} (ID {app.id})",
        application_id=app.id,
        message=original,
        email=app.email,
        stage_label=_stage_label(app.current_stage),
        career_years=app.career_years,
        education=app.education,
        pending_action=pending,
    )


def _choices_from_tool_results(reply: str, tool_results: list, original: str) -> list[ChoiceOut]:
    """LLM 경로 — 답변이 동명이인을 알렸고 검색 결과에 실제로 같은 이름이 둘 이상이면
    그 행들을 선택지로 만든다. 답변 본문을 파싱하지 않고 **도구 결과** 만 믿는다
    (LLM 이 id 를 지어내도 카드는 실제 행만 가리킨다).

    LLM 경로는 pending_action 을 아직 안 붙인다 — LLM 답변에서 목표 도구·arguments
    를 안전하게 뽑아내기가 어렵다 (원문에 "면접" 이 있다고 to_stage 를 확정하는 것은
    취약). 이 경로에서는 지금처럼 카드 클릭 = 원 요청 재전송 → 서버가 pending 카드
    반환 → 확인 카드 클릭의 두 단계. 규칙 라우터 (`_handle_direct`) 에서는 원샷.
    """
    if "동명이인" not in (reply or ""):
        return []
    rows: list[dict] = []
    seen: set[int] = set()
    for tr in tool_results or []:
        if not isinstance(tr, dict) or tr.get("name") != "search_applications":
            continue
        out = tr.get("output")
        if not isinstance(out, dict):
            continue
        for r in out.get("results") or []:
            if not isinstance(r, dict) or r.get("id") is None or not r.get("name"):
                continue
            try:
                rid = int(r["id"])
            except (TypeError, ValueError):
                continue
            if rid in seen:
                continue
            seen.add(rid)
            rows.append(r)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["name"]] = counts.get(r["name"], 0) + 1
    dups = [r for r in rows if counts[r["name"]] >= 2]
    return [
        ChoiceOut(
            label=f"{r['name']} (ID {int(r['id'])})",
            application_id=int(r["id"]),
            message=original,
            email=r.get("email"),
            stage_label=_stage_label(r.get("current_stage")),
            career_years=r.get("career_years"),
            education=r.get("education"),
            pending_action=None,
        )
        for r in dups[:_CHOICE_LIMIT]
    ]


def _build_per_choice_pendings(
    intent: DirectAction,
    apps: list[Application],
    db: Session,
) -> dict[int, PendingActionOut]:
    """규칙 라우터가 change_stage 를 잡았고 동명이인이 났을 때 각 후보의 pending 을 미리
    만든다. 도구 하나 (change_stage) 에 후보만 여럿이므로 arguments 는 application_id
    만 다르다. 오늘 UX 개선은 담당자가 가장 자주 쓰는 change_stage 하나로 국한한다 —
    assign_interviewer·draft_email 은 후보별 arguments 계산이 도구마다 다르고, 원샷
    UX 로 부작용이 안 되돌아오는 것 (특히 draft_email → send_email) 이 있어 뒤에 나눠서.

    전환 규칙이 어긋나는 후보엔 pending 을 안 붙인다 (프론트가 폴백으로 chat 재요청 →
    서버가 그때 사람 말로 이유를 답한다). 실행 직전에도 /confirm 에서 다시 검사되므로
    여기 검사는 "카드에 실행 가능 버튼을 안 보이게" 하는 UX 용 (2026-09-02 실측: 카드
    에 눌러도 매번 실패하는 버튼이 남으면 담당자가 헛수고).
    """
    if not intent.is_write or intent.tool_name != "change_stage":
        return {}
    base = dict(intent.args)
    base.pop("_name_lookup", None)
    to_stage = base.get("to_stage")
    if not to_stage:
        return {}
    result: dict[int, PendingActionOut] = {}
    for app in apps:
        try:
            validate_transition(app.current_stage, to_stage)
        except StageTransitionError:
            continue
        args = {**base, "application_id": app.id}
        result[app.id] = PendingActionOut(
            tool_name=intent.tool_name,
            arguments=args,
            description=_describe_action(intent.tool_name, args, db),
        )
    return result


# ── 규칙 라우터 헬퍼 (Phase 1 레버 ②) ──────────────────────────

def _handle_direct(
    intent: DirectAction,
    db: Session,
    user: User,
    original: str = "",
    application_id: int | None = None,
) -> ChatResponse:
    """라우터가 매치한 요청 실행. LLM 안 부름.

    - 읽기 도구 (`is_write=False`): 도구 즉시 실행 → 결과를 사람이 읽는 짧은
      답변으로 렌더 → reply 로 반환
    - 쓰기 도구 (`is_write=True`): `pending_action` 만 만들고 실제 실행은
      담당자가 확인 카드를 승인해 `/confirm` 이 부를 때
    - 이름 → id 조회가 필요한 경우 (`_name_lookup`): DB 에서 검색 후 정확·부분
      일치 순. 0건이면 되묻기, 동명이인이면 **선택지(choices) 를 붙여** 되묻기,
      1건이면 id 채움. 담당자가 선택지를 눌러 `application_id` 가 왔으면 조회 생략.
    """
    args = dict(intent.args)  # 원본 mutate 방지
    app: Application | None = None

    if "_name_lookup" in args:
        name = args.pop("_name_lookup")
        if application_id is not None:
            app = db.get(Application, application_id)
            if app is None:
                return _router_reply(f"ID {application_id} 지원자를 찾지 못했어요. 다시 검색해 주세요.")
        else:
            found = _lookup_applicants_by_name(db, name)
            if not found:
                return _router_reply(f"'{name}' 지원자를 찾지 못했어요. 이름을 다시 확인해 주세요.")
            if len(found) > 1:
                candidates = found[:_CHOICE_LIMIT]
                # change_stage 시나리오에서 각 후보의 pending 을 미리 만들어 카드에
                # 붙인다 (담당자 카드 딸깍 = 확인 = 실행 원샷). 다른 도구는 pending
                # 없이 폴백 흐름 (카드 클릭 → 서버 재요청 → 확인 카드 → 확인).
                per_choice_pendings = _build_per_choice_pendings(intent, candidates, db)
                return _router_response(
                    reply=f"'{name}' 이름으로 {len(found)}명이 있어요. 아래에서 골라 주세요.",
                    tool_calls=[],
                    pending=None,
                    choices=[
                        _choice_for_app(a, original, pending=per_choice_pendings.get(a.id))
                        for a in candidates
                    ],
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
    choices: list[ChoiceOut] | None = None,
) -> ChatResponse:
    """라우터 응답 공통 shape. backend/model 태그로 라우터 힛을 표시."""
    return ChatResponse(
        reply=reply,
        tool_calls=tool_calls,
        pending_action=pending,
        choices=choices or [],
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
