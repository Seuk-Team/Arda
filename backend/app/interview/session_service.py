"""면접 세션 도메인 서비스 (ADR-0035 Phase 4 · UseCase 분리).

`interview/api/interviews.py` 라우터가 HTTP 파싱·응답만 맡고 세션 라이프사이클의
비즈니스 로직 (질문 자동 생성 · 음성 전사 · 꼬리질문 백그라운드) 은 여기로.

라우터에서 `background.add_task(session_service.seed_questions_bg, session.id)` 형태로
호출. 백그라운드 작업은 자체 SessionLocal 을 열고 실패해도 무해하게 로그만 남긴다.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy import select

from app.adapter.outbound.pg.application_pg_repository import PgApplicationRepository
from app.adapter.outbound.pg.interview_pg_repository import PgInterviewRepository
from app.models import InterviewTurn
from app.shared import s3

logger = logging.getLogger(__name__)

# 자동 생성이 뽑을 게 없거나 실패했을 때 넣는 폴백. 어느 지원자에게든 물을 수
# 있는 안전한 첫 세 개다 (2026-09-10). 담당자가 원하면 편집기로 덮어쓸 수 있다.
DEFAULT_QUESTIONS = (
    "성함과 지원하신 직무를 말씀해 주세요.",
    "가장 자신 있는 기술 하나만 말씀해 주세요.",
    "입사하면 가장 먼저 하고 싶은 일은 무엇인가요?",
)

# 위 발급 경로가 만든 모양만 받는다. 클라이언트가 준 키를 그냥 믿으면
# `applications/<남의 uuid>/resume.pdf` 를 답변이라고 보내 **남의 이력서를 읽어
# 전사**시킬 수 있다 — 서버가 S3 를 대신 읽어 주는 경로라 그대로 유출이 된다.
AUDIO_KEY_RE = re.compile(
    r"^interviews/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    r"answer\.([a-z0-9]{1,10})$"
)

# 끝난 면접에 늦게 도착한 전사를 받아 주는 시간 (2026-09-11). 워커 받아쓰기는
# CPU 한 대에서 줄을 서서 몇 분씩 늦는다 — 세션 59 에서 [면접 종료] 3초 뒤 온
# 전사가 409 로 버려졌다(수택님 로그). 이만큼 지난 뒤 오는 것은 받지 않는다.
LATE_ANSWER_GRACE = timedelta(minutes=10)


def seed_questions_bg(session_id: int) -> None:
    """세션 만든 직후 자동으로 꼬리질문을 뽑아 넣는다 (2026-09-10, 팀장 결정).

    담당자가 매번 수동으로 질문을 넣던 번거로움을 없앤다. 뽑을 게 없으면 폴백
    3개가 들어가므로 지원자는 어느 경우에도 "준비된 질문이 없습니다" 를 안 본다.
    담당자는 이후에도 언제든 편집기로 덮어쓸 수 있다 (`set_questions`).

    실패해도 무해하다 — 로그만 남기고 세션은 그대로 (담당자가 수동으로 넣으면 됨).
    """
    from app.agent.interview_probe import generate_probes, sources_of
    from app.db import SessionLocal

    with SessionLocal() as db:
        session = PgInterviewRepository(db).get_session(session_id)
        if session is None:
            return

        # 이미 질문이 있으면 덮어쓰지 않는다 — 담당자가 수동으로 먼저 넣은 경우
        existing = db.scalar(
            select(InterviewTurn).where(InterviewTurn.session_id == session_id)
        )
        if existing is not None:
            return

        application = PgApplicationRepository(db).get(session.application_id)
        if application is None:
            return

        try:
            sources = sources_of(application, db)
        except Exception:
            logger.exception("면접 질문 자동 생성 실패 (sources_of): session=%s", session_id)
            sources = None

        questions: list[str] = []
        if sources and (sources["cover_letter"].strip() or sources["resume"].strip()):
            try:
                claims = generate_probes(sources)
            except Exception:
                logger.exception(
                    "면접 질문 자동 생성 실패 (generate_probes): session=%s", session_id
                )
                claims = None
            if claims:
                # 주장별로 첫 질문을 먼저 뽑고 (다양한 주장 커버) 그 뒤에 두 번째,
                # 이런 순서로 최대 10개. 같은 주장의 두 질문이 붙어 나가면 흐름이
                # 지루해진다.
                for i in range(2):
                    for c in claims:
                        qs = c.get("questions") or []
                        if i < len(qs):
                            questions.append(qs[i].strip())
                questions = [q for q in questions if q][:10]

        if not questions:
            questions = list(DEFAULT_QUESTIONS)

        # LLM 이 도는 사이 담당자가 세션을 지웠을 수 있다 (2026-09-10 실측:
        # session 48 이 6초만에 삭제됐고, 그 뒤 이 훅이 INSERT 하다 FK 위반).
        # 재확인해 세션이 사라졌으면 조용히 종료 — 담당자가 만든 것을 지운 것이니
        # 그 위에 질문을 남기지 않는 편이 맞다.
        if PgInterviewRepository(db).get_session(session_id) is None:
            logger.info(
                "면접 질문 자동 생성 취소: session=%s (LLM 사이 세션이 삭제됨)",
                session_id,
            )
            return

        for seq, q in enumerate(questions, start=1):
            db.add(
                InterviewTurn(session_id=session_id, seq=seq, question=q)
            )
        try:
            db.commit()
        except Exception:
            # 위 재확인이 지나간 뒤에도 삭제될 수 있다 (그 사이 두 요청이 동시에
            # 왔을 때). 이 자리에서는 FK 위반이 나오므로 롤백 후 조용히 종료.
            logger.info(
                "면접 질문 자동 생성 커밋 실패: session=%s (경합 · 롤백)",
                session_id,
            )
            db.rollback()
            return
        logger.info(
            "면접 질문 자동 생성 완료: session=%s 개수=%s (폴백=%s)",
            session_id, len(questions), questions == list(DEFAULT_QUESTIONS),
        )


def transcribe_answer(turn: InterviewTurn, key: str) -> str:
    """음성을 읽어 전사하고, 회차에 길이·비용까지 적는다 (설계 §5-4).

    **`raw` 를 저장한다 — `resolved` 가 아니다.** 전사에는 엔티티 해석("파이썬
    이년" → "Python 2년")이 같이 나오는데, 면접 답변은 나중에 이력서 주장과
    맞춰 **원문으로 인용**되는 자리다(ADR-0026 결정 3). 다듬은 문장을 인용하면
    지원자가 "그렇게 말한 적 없다"고 할 때 우리가 틀린다.

    실패하면 **아무것도 저장하지 않고 502** 다. 음성은 S3 에 남아 있지만 회차는
    비어 있으므로 지원자에게는 같은 질문이 그대로 보이고 다시 답할 수 있다.
    반쯤 저장해 두면 답을 못 한 채로 다음 질문으로 넘어간다.
    """
    from app.agent import stt

    matched = AUDIO_KEY_RE.match(key)
    if matched is None:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY, "잘못된 음성 파일 키입니다"
        )

    try:
        audio = s3.read_object(key)
    except Exception as exc:
        raise HTTPException(
            HTTPStatus.BAD_GATEWAY, f"음성을 읽지 못했습니다 ({type(exc).__name__})"
        )

    try:
        result = stt.transcribe(audio, filename=f"answer.{matched.group(1)}")
    except Exception as exc:
        raise HTTPException(
            HTTPStatus.BAD_GATEWAY, f"음성을 전사하지 못했습니다 ({type(exc).__name__})"
        )

    text = (result.get("raw") or "").strip()
    if not text:
        # 빈 문자열을 넣으면 "답한 질문"이 되어 다음 질문으로 넘어간다.
        # 말이 안 담긴 녹음은 답변이 아니라 다시 하면 되는 일이다.
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "음성에서 말을 찾지 못했습니다. 다시 답변해 주세요",
        )

    turn.audio_s3_key = key
    turn.audio_duration_sec = result.get("audio_duration_sec")
    turn.stt_cost_usd = result.get("cost_usd")
    return text


def generate_followup_bg(session_id: int, prev_turn_id: int) -> None:
    """직전 답변을 재료로 꼬리질문 하나를 만들어 다음 자리에 삽입한다.

    지원자를 기다리게 하지 않는 자리다 — 답변 저장 뒤 백그라운드로 돈다.
    다음 질문이 이미 나가 있어도 상관없다: 이 새 턴은 그 뒤로 들어가고,
    지원자가 다음다음 질문 필요할 때 자연스럽게 나간다 (2026-09-10, 팀장 결정).

    실패는 무해하다 — 로그만 남기고 사전 질문 흐름이 그대로 굴러간다.
    """
    from app.agent.interview_probe import probe_from_answer
    from app.db import SessionLocal

    with SessionLocal() as db:
        prev = db.get(InterviewTurn, prev_turn_id)
        if prev is None or prev.transcript is None:
            return  # 사라졌거나 아직 전사 안 됨

        # 지원자 요약이 있으면 문맥에 넣는다. 없어도 답변만으로 굴러간다.
        summary = ""
        session = PgInterviewRepository(db).get_session(session_id)
        if session is not None:
            app = PgApplicationRepository(db).get(session.application_id)
            if app is not None and app.ai_summary:
                summary = app.ai_summary

        question = probe_from_answer(
            prev_question=prev.question,
            prev_answer=prev.transcript,
            applicant_summary=summary,
        )
        if question is None:
            return

        # 마지막 번호 다음에 붙인다. 다른 세션은 안 건드리므로 락 없이 안전 —
        # 이 세션 안에서 두 답변이 거의 동시에 도착해도 각각의 배경 태스크가
        # 서로 다른 seq 를 딴다 (uniqueness 는 DB 가 지킨다).
        max_seq = (
            db.query(InterviewTurn.seq)
            .filter(InterviewTurn.session_id == session_id)
            .order_by(InterviewTurn.seq.desc())
            .limit(1)
            .scalar()
            or 0
        )
        new_turn = InterviewTurn(
            session_id=session_id,
            seq=max_seq + 1,
            question=question,
            generated_from_turn_id=prev_turn_id,
        )
        db.add(new_turn)
        db.commit()
