"""에이전트 응답 형식 · 지원자 조회 · 규칙 라우터 도메인 서비스 (ADR-0035 Phase 4).

`application/api/agent.py` 라우터에서 순수 도메인 로직을 이관:
- 형식 함수 (stage_label · format_reply)
- 조회 (lookup_applicants_by_name)
- 규칙 라우터 헬퍼 (handle_direct · stage_rule_reply · build_per_choice_pendings ·
  choices_from_tool_results · choice_for_app · router_reply · router_response)

Pydantic 스키마는 `app/schemas/agent.py` 로 이관 · 서비스도 그것들을 import.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.intent_router import DirectAction
from app.agent.runtime import _describe_action
from app.agent.tools import execute_tool
from app.application.stages import STAGE_ORDER, StageTransitionError, validate_transition
from app.models import Application, User
from app.schemas.agent import (
    ChatResponse,
    ChoiceOut,
    PendingActionOut,
    ToolCallOut,
)
from app.shared.labels import STAGE_LABEL_KR

logger = logging.getLogger(__name__)


CHOICE_LIMIT = 6


def stage_label(stage: str | None) -> str | None:
    return STAGE_LABEL_KR.get(stage or "", "") or None


def lookup_applicants_by_name(db: Session, name: str) -> list[Application]:
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


def format_reply(tool_name: str, result: dict) -> str:
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


def router_response(
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


def router_reply(text: str) -> ChatResponse:
    """짧은 안내만 있는 라우터 응답 (도구 호출 없음, 되묻기 등)."""
    return router_response(reply=text, tool_calls=[], pending=None)


def choice_for_app(
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
        stage_label=stage_label(app.current_stage),
        career_years=app.career_years,
        education=app.education,
        pending_action=pending,
    )


def choices_from_tool_results(reply: str, tool_results: list, original: str) -> list[ChoiceOut]:
    """LLM 경로 — 답변이 동명이인을 알렸고 검색 결과에 실제로 같은 이름이 둘 이상이면
    그 행들을 선택지로 만든다. 답변 본문을 파싱하지 않고 **도구 결과** 만 믿는다
    (LLM 이 id 를 지어내도 카드는 실제 행만 가리킨다).

    LLM 경로는 pending_action 을 아직 안 붙인다 — LLM 답변에서 목표 도구·arguments
    를 안전하게 뽑아내기가 어렵다 (원문에 "면접" 이 있다고 to_stage 를 확정하는 것은
    취약). 이 경로에서는 지금처럼 카드 클릭 = 원 요청 재전송 → 서버가 pending 카드
    반환 → 확인 카드 클릭의 두 단계. 규칙 라우터 (`handle_direct`) 에서는 원샷.
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
            stage_label=stage_label(r.get("current_stage")),
            career_years=r.get("career_years"),
            education=r.get("education"),
            pending_action=None,
        )
        for r in dups[:CHOICE_LIMIT]
    ]


def build_per_choice_pendings(
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


def stage_rule_reply(app: Application, to_stage: str, reason: str, db: Session) -> ChatResponse:
    """전환 규칙에 어긋난 요청에 대한 안내. 가능하면 '다음 단계' 카드를 대신 제안."""
    cur = app.current_stage
    cur_kr = STAGE_LABEL_KR.get(cur, cur)
    to_kr = STAGE_LABEL_KR.get(to_stage, to_stage)

    if cur == to_stage:
        return router_reply(f"{app.name} 님은 이미 {to_kr} 단계예요.")

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
            return router_response(
                reply=(
                    f"{app.name} 님은 지금 {cur_kr} 단계라 {to_kr}(으)로 바로 못 옮겨요 "
                    f"(한 단계씩만 진행). 먼저 {nxt_kr}(으)로 옮길까요?"
                ),
                tool_calls=[ToolCallOut(name="change_stage", input=args)],
                pending=pending,
            )

    return router_reply(f"{app.name} 님: {reason}")


def handle_direct(
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
                return router_reply(f"ID {application_id} 지원자를 찾지 못했어요. 다시 검색해 주세요.")
        else:
            found = lookup_applicants_by_name(db, name)
            if not found:
                return router_reply(f"'{name}' 지원자를 찾지 못했어요. 이름을 다시 확인해 주세요.")
            if len(found) > 1:
                candidates = found[:CHOICE_LIMIT]
                # change_stage 시나리오에서 각 후보의 pending 을 미리 만들어 카드에
                # 붙인다 (담당자 카드 딸깍 = 확인 = 실행 원샷). 다른 도구는 pending
                # 없이 폴백 흐름 (카드 클릭 → 서버 재요청 → 확인 카드 → 확인).
                per_choice_pendings = build_per_choice_pendings(intent, candidates, db)
                return router_response(
                    reply=f"'{name}' 이름으로 {len(found)}명이 있어요. 아래에서 골라 주세요.",
                    tool_calls=[],
                    pending=None,
                    choices=[
                        choice_for_app(a, original, pending=per_choice_pendings.get(a.id))
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
                    return stage_rule_reply(app, to_stage, str(e), db)
        pending = PendingActionOut(
            tool_name=intent.tool_name,
            arguments=args,
            description=_describe_action(intent.tool_name, args, db),
        )
        return router_response(
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
    reply = format_reply(intent.tool_name, result)
    return router_response(
        reply=reply,
        tool_calls=[ToolCallOut(name=intent.tool_name, input=args)],
        pending=None,
    )
