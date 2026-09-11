"""파이프라인 종단 점검 — 컨텍스트 **사이의 배선**만 본다 (ADR-0035).

각 조각의 규칙은 다른 테스트들이 이미 본다. 여기서 지키는 것은 하나다:
**경계를 넘는 호출이 실제로 이어져 있는가.** 헥사고날로 쪼갠 뒤 생기는 사고는
거의 전부 "모듈은 멀쩡한데 부르는 쪽이 옛 경로를 본다" 형태였다 —

- 2026-09-12: 프로덕션 워커가 `python -m app.worker` 로 떠 있어 컨테이너가
  재시작을 반복했다 (모듈은 `app.shared.worker` 로 옮겼다). 단위 테스트는 전부
  초록이었다. 발송 자체는 `MAIL_DISPATCH=n8n` 경로라 막히지 않았지만, 바로 그래서
  **아무 신호도 없었다** — 살아 있는 경로 밖의 고장은 누가 들여다보지 않으면 안 보인다.
- 같은 날: `app/interview/api/schedules.py` 의 `timedelta` 미import,
  `assignments.py` 의 `PgTalentRepository` 범위 밖 참조 — 둘 다 라우터를 한 번이라도
  태우면 잡혔을 NameError 였다.

그래서 이 파일은 "부팅되는가 · 한 줄로 흐르는가 · 포트가 갈아끼워지는가" 만 본다.
빠르게 유지한다 (DB 왕복 20회 미만).
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app as fastapi_app
from app.models import Application, EmailLog, EmailTemplate, InterviewSession, StageHistory, User


class TestPortsAndAdapters:
    """포트 4개가 각자 어댑터로 실제 조회를 한다 (ADR-0035 Phase 3)."""

    def test_each_repository_satisfies_its_port(self, db: Session, application: Application, admin_user: User):
        from app.adapter.outbound.pg.application_pg_repository import PgApplicationRepository
        from app.adapter.outbound.pg.hiring_pg_repository import PgHiringRepository
        from app.adapter.outbound.pg.interview_pg_repository import PgInterviewRepository
        from app.adapter.outbound.pg.talent_pg_repository import PgTalentRepository
        from app.ports.output.application_repository import ApplicationRepository
        from app.ports.output.hiring_repository import HiringRepository
        from app.ports.output.interview_repository import InterviewRepository
        from app.ports.output.talent_repository import TalentRepository

        assert issubclass(PgApplicationRepository, ApplicationRepository)
        assert issubclass(PgHiringRepository, HiringRepository)
        assert issubclass(PgInterviewRepository, InterviewRepository)
        assert issubclass(PgTalentRepository, TalentRepository)

        assert PgApplicationRepository(db).get(application.id) is not None
        assert PgHiringRepository(db).get_posting(application.job_posting_id) is not None
        assert len(PgHiringRepository(db).find_postings_by_ids([application.job_posting_id])) == 1
        assert PgTalentRepository(db).get_user(admin_user.id) is not None
        assert len(PgTalentRepository(db).find_users_by_ids([admin_user.id])) == 1

    def test_injected_repository_replaces_db_access(self, db: Session, application: Application):
        """주입한 가짜가 실제로 쓰인다 — 이게 안 되면 Repository 주입은 장식이다."""
        from app.interview.scoring import latest_interview_score
        from app.ports.output.interview_repository import InterviewRepository

        fake = MagicMock(spec=InterviewRepository)
        fake.latest_ai_score_for_application.return_value = 42

        assert latest_interview_score(db, application.id, interview_repo=fake) == 42
        fake.latest_ai_score_for_application.assert_called_once_with(application.id)

    def test_real_repository_reads_finished_interview_only(self, db: Session, application: Application, admin_user: User):
        from app.interview.scoring import latest_interview_score

        session = InterviewSession(
            application_id=application.id,
            token=f"e2e-{datetime.now(UTC).timestamp():.0f}",
            status="in_progress",
            started_at=datetime.now(UTC) - timedelta(minutes=10),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            created_by=admin_user.id,
            ai_score=77,
            scored_at=datetime.now(UTC),
        )
        db.add(session)
        db.flush()
        # 아직 안 끝난 면접은 점수 조회 대상이 아니다
        assert latest_interview_score(db, application.id) is None

        session.status = "done"
        session.ended_at = datetime.now(UTC)
        db.flush()
        assert latest_interview_score(db, application.id) == 77


class TestStageChangeToMailQueue:
    """application → shared 경계: 단계 전환이 이력과 메일 큐를 만든다."""

    def _template(self, db: Session, stage: str, actor: User) -> None:
        if db.query(EmailTemplate).filter(EmailTemplate.stage == stage).first() is None:
            db.add(EmailTemplate(
                stage=stage, subject="[{회사명}] 안내",
                body="{이름} 님께 안내드립니다.", updated_by=actor.id,
            ))
            db.flush()

    def test_notify_stage_creates_log_and_publishes(self, db: Session, application: Application, admin_user: User):
        from app.application import stage_service
        from app.application.stages import validate_transition

        self._template(db, "interview", admin_user)

        # 알림 대상이 아닌 단계에서는 메일이 생기지 않는다
        validate_transition("applied", "screening")
        assert stage_service.apply_stage_change(
            db, application, "screening",
            changed_by=admin_user.id, reason=None, now=datetime.now(UTC),
        ) is None

        # 알림 대상 단계에서는 생긴다
        validate_transition("screening", "interview")
        log_id = stage_service.apply_stage_change(
            db, application, "interview",
            changed_by=admin_user.id, reason=None, now=datetime.now(UTC),
        )
        db.flush()

        assert application.current_stage == "interview"
        assert log_id is not None
        assert db.get(EmailLog, log_id) is not None
        assert db.query(StageHistory).filter(
            StageHistory.application_id == application.id
        ).count() == 2

        sent: list[int] = []
        with patch("app.shared.mail.publish", side_effect=lambda i, **k: sent.append(i)):
            assert stage_service.publish_all([log_id]) == 1
        assert sent == [log_id]


class TestMailDispatcherPort:
    """shared → adapter 경계: 큐 어댑터를 코드 수정 없이 갈아끼운다."""

    def test_sqs_adapter_sends_to_queue(self, db: Session, application: Application, admin_user: User):
        from app.adapter.outbound.mail.sqs_dispatcher import SqsMailDispatcher

        log = EmailLog(
            application_id=application.id,
            to_email=application.email,
            subject="제목",
            body="본문",
            stage="interview",
            status="queued",
            actor_kind="human",
            actor_id=admin_user.id,
        )
        db.add(log)
        db.flush()

        fake_sqs = MagicMock()
        with patch("app.adapter.outbound.mail.sqs_dispatcher._sqs_client", return_value=fake_sqs), \
             patch.dict(os.environ, {"SQS_QUEUE_URL": "https://sqs.local/q"}):
            SqsMailDispatcher().publish(log.id)

        assert fake_sqs.send_message.called

    def test_switch_selects_adapter(self):
        from app.adapter.outbound.mail.n8n_dispatcher import N8nMailDispatcher
        from app.adapter.outbound.mail.sqs_dispatcher import SqsMailDispatcher
        from app.ports.output.mail_dispatcher_port import MailDispatcher
        from app.shared.mail import _get_dispatcher

        assert issubclass(SqsMailDispatcher, MailDispatcher)
        assert issubclass(N8nMailDispatcher, MailDispatcher)

        with patch.dict(os.environ, {"MAIL_DISPATCH": "n8n"}):
            assert isinstance(_get_dispatcher(), N8nMailDispatcher)
        with patch.dict(os.environ, {"MAIL_DISPATCH": "sqs"}):
            assert isinstance(_get_dispatcher(), SqsMailDispatcher)


class TestScoringChain:
    """서류 → 면접 → 최종 → 등급이 한 줄로 이어진다 (가중치는 hiring 에서 온다)."""

    def test_weights_to_grade(self, db: Session):
        from app.application.screening import (
            DEFAULT_WEIGHTS,
            doc_score_from,
            final_score,
            grade,
            interview_score_from,
            truth_consistency,
            weights,
        )

        w = weights(db)
        assert set(w) == set(DEFAULT_WEIGHTS)

        doc = doc_score_from({"requirements": 80, "preferred": 40, "culture": 45}, w)
        itv = interview_score_from(75, truth_consistency({"true": 8, "false": 2}), w)
        final = final_score(doc, itv, w)

        assert doc is not None and 0 <= doc <= 100
        assert itv is not None and 0 <= itv <= 100
        assert final is not None and 0 <= final <= 100
        assert grade(final) in {"S", "A", "B", "C", None}


class TestAppBoots:
    """라우터 전체가 등록되고, 한 번이라도 태워 본다.

    이 클래스가 없으면 라우터 파일의 import 누락(NameError) 이 그 라우터를 부르는
    테스트가 없는 한 통과해 버린다 — 2026-09-12 에 실제로 두 건 있었다.
    """

    def test_openapi_covers_all_routers(self):
        # 이 FastAPI 버전은 include_router 를 지연 확장하므로 OpenAPI 로 센다.
        paths = fastapi_app.openapi()["paths"]
        ops = sum(len(v) for v in paths.values())
        assert ops > 80, f"라우트가 갑자기 줄었다: {ops}"

    def test_every_router_module_imports(self):
        """등록된 모든 라우터 모듈을 실제로 import 한다 (모듈 레벨 NameError 검출)."""
        import importlib
        import pkgutil

        import app as app_pkg

        failed: list[str] = []
        for mod in pkgutil.walk_packages(app_pkg.__path__, prefix="app."):
            if ".api." not in mod.name and not mod.name.endswith(".api"):
                continue
            try:
                importlib.import_module(mod.name)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{mod.name}: {exc}")
        assert not failed, failed

    def test_every_lazy_import_resolves(self):
        """**함수 안 import** 를 전부 실제로 해석한다.

        지연 import 는 그 함수를 부르는 테스트가 없으면 영원히 검증되지 않는다.
        `ruff F821` 도 못 잡는다 — 이름이 import 문에 있으니 정의된 것으로 본다.
        2026-09-12 에 실제로 `agent/tools/write.py` 가 `schedules._build_candidates`
        (#198 에서 `schedule_service.build_candidates` 로 옮겨 없어진 이름) 를 불러
        아르의 "면접 일정 제안" 도구가 ImportError 로 죽어 있었다.
        """
        import ast
        import importlib
        import pathlib

        problems: list[str] = []
        for path in sorted(pathlib.Path("app").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            toplevel = {id(n) for n in tree.body}
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or id(node) in toplevel:
                    continue  # 모듈 레벨 import 는 import 자체로 검증된다
                if node.level or not node.module or not node.module.startswith("app"):
                    continue
                try:
                    mod = importlib.import_module(node.module)
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"{path}:{node.lineno} {node.module} import 실패: {exc}")
                    continue
                for alias in node.names:
                    if hasattr(mod, alias.name):
                        continue
                    # `from 패키지 import 서브모듈` 은 hasattr 로 안 보인다
                    try:
                        importlib.import_module(f"{node.module}.{alias.name}")
                    except Exception:  # noqa: BLE001
                        problems.append(
                            f"{path}:{node.lineno} {node.module} 에 '{alias.name}' 없음"
                        )
        assert not problems, problems

    def test_health_open_and_api_guarded(self):
        with TestClient(fastapi_app, raise_server_exceptions=False) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/api/v1/applications").status_code in (401, 403)
