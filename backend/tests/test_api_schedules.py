"""면접 일정 자동화 API (ADR-0016) — 가용 시간 3종 + 제안·공개 조회·확정 3종.

이 기능은 **틀렸을 때 지원자가 잘못된 시간에 면접을 보러 온다.** 규칙이 여러 곳에
흩어져 있어서(조회 시점 만료 판정 · 확정 시점 겹침 재검증 · 재제안 시 이전 제안
취소) 각각을 눈으로 확인하기 어렵다. 그래서 규칙 하나에 테스트 하나를 붙인다.

권한은 `get_current_user` 만 바꿔 끼우고 `require_roles` 는 진짜를 돌린다 —
require_roles 는 호출할 때마다 새 함수를 만들어서 dependency_overrides 키로
잡히지 않고, 무엇보다 403 이 실제로 나는지가 이 테스트의 관심사다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import (
    Application,
    InterviewerAssignment,
    InterviewerAvailability,
    JobPosting,
    ScheduleProposal,
    ScheduleSlot,
    User,
)

NOW = datetime.now(UTC)


@pytest.fixture(autouse=True)
def no_sqs(monkeypatch):
    """메일 큐 발행은 AWS 로 나간다 — 테스트에서는 막는다.

    발행 실패는 코드가 이미 삼키지만(제안·확정이 메일 때문에 무너지면 안 된다),
    막지 않으면 boto3 가 매번 클라이언트를 만들고 재시도하느라 느려진다.
    """
    monkeypatch.setattr("app.mail.publish", lambda _id: None)


@pytest.fixture()
def as_user(db: Session):
    """주어진 사용자로 인증된 TestClient 를 만든다."""

    def make(user: User) -> TestClient:
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    yield make
    app.dependency_overrides.clear()


@pytest.fixture()
def public(db: Session):
    """토큰만으로 접근하는 공개 라우트용. 인증을 걸지 않는다."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def assigned(db: Session, application: Application, interviewer_user: User, admin_user: User):
    """지원자에게 면접관을 배정한다 (E3) — 제안 생성의 재료다."""
    db.add(
        InterviewerAssignment(
            application_id=application.id,
            interviewer_id=interviewer_user.id,
            assigned_by=admin_user.id,
        )
    )
    db.flush()
    return application


def add_window(db: Session, interviewer: User, *, from_hours: int, hours: int):
    row = InterviewerAvailability(
        interviewer_id=interviewer.id,
        start_at=NOW + timedelta(hours=from_hours),
        end_at=NOW + timedelta(hours=from_hours + hours),
    )
    db.add(row)
    db.flush()
    return row


def make_proposal(
    db: Session, application: Application, creator: User, **over
) -> ScheduleProposal:
    values = dict(
        application_id=application.id,
        token=f"tok-{datetime.now(UTC).timestamp()}-{over.pop('n', 0)}",
        status="proposed",
        created_by=creator.id,
    )
    values.update(over)
    row = ScheduleProposal(**values)
    db.add(row)
    db.flush()
    return row


def add_slot(db: Session, proposal: ScheduleProposal, interviewer: User, *, from_hours: int):
    row = ScheduleSlot(
        proposal_id=proposal.id,
        interviewer_id=interviewer.id,
        start_at=NOW + timedelta(hours=from_hours),
        end_at=NOW + timedelta(hours=from_hours + 1),
    )
    db.add(row)
    db.flush()
    return row


# ── 가용 시간 (3종) ─────────────────────────────────────────────────


class TestAvailabilityWrite:
    def test_본인은_등록할_수_있다(self, as_user, interviewer_user: User):
        res = as_user(interviewer_user).post(
            f"/api/v1/interviewers/{interviewer_user.id}/availability",
            json={
                "start_at": (NOW + timedelta(days=1)).isoformat(),
                "end_at": (NOW + timedelta(days=1, hours=4)).isoformat(),
            },
        )
        assert res.status_code == 201

    def test_남의_가용_시간은_등록할_수_없다(self, as_user, recruiter_user: User, interviewer_user: User):
        # 담당자라도 면접관 일정을 대신 넣지 않는다 — 본인 또는 admin 만.
        res = as_user(recruiter_user).post(
            f"/api/v1/interviewers/{interviewer_user.id}/availability",
            json={
                "start_at": (NOW + timedelta(days=1)).isoformat(),
                "end_at": (NOW + timedelta(days=1, hours=4)).isoformat(),
            },
        )
        assert res.status_code == 403

    def test_admin_은_대신_등록할_수_있다(self, as_user, admin_user: User, interviewer_user: User):
        res = as_user(admin_user).post(
            f"/api/v1/interviewers/{interviewer_user.id}/availability",
            json={
                "start_at": (NOW + timedelta(days=2)).isoformat(),
                "end_at": (NOW + timedelta(days=2, hours=2)).isoformat(),
            },
        )
        assert res.status_code == 201

    def test_지난_시간은_등록할_수_없다(self, as_user, interviewer_user: User):
        # 후보 슬롯이 될 수 없는 데이터라 받아 두면 오염만 된다.
        res = as_user(interviewer_user).post(
            f"/api/v1/interviewers/{interviewer_user.id}/availability",
            json={
                "start_at": (NOW - timedelta(days=2)).isoformat(),
                "end_at": (NOW - timedelta(days=1)).isoformat(),
            },
        )
        assert res.status_code == 422

    def test_면접관이_아닌_사용자에게는_등록할_수_없다(self, as_user, admin_user: User, recruiter_user: User):
        res = as_user(admin_user).post(
            f"/api/v1/interviewers/{recruiter_user.id}/availability",
            json={
                "start_at": (NOW + timedelta(days=1)).isoformat(),
                "end_at": (NOW + timedelta(days=1, hours=2)).isoformat(),
            },
        )
        assert res.status_code == 422


class TestAvailabilityRead:
    def test_담당자는_볼_수_있다(self, as_user, db: Session, recruiter_user: User, interviewer_user: User):
        # 제안을 만들려면 봐야 한다.
        add_window(db, interviewer_user, from_hours=24, hours=4)
        res = as_user(recruiter_user).get(f"/api/v1/interviewers/{interviewer_user.id}/availability")
        assert res.status_code == 200
        assert res.json()["count"] == 1

    def test_다른_면접관_것은_볼_수_없다(self, as_user, db: Session, interviewer_user: User):
        other = User(
            email="other-interviewer@fixture.local",
            password_hash="hashed",
            name="다른 면접관",
            role="interviewer",
        )
        db.add(other)
        db.flush()
        res = as_user(other).get(f"/api/v1/interviewers/{interviewer_user.id}/availability")
        assert res.status_code == 403

    def test_기간_필터는_걸친_구간도_포함한다(
        self, as_user, db: Session, recruiter_user: User, interviewer_user: User
    ):
        # 24~28시 구간을 26~30시로 조회하면 걸쳐 있으므로 나와야 한다.
        add_window(db, interviewer_user, from_hours=24, hours=4)
        res = as_user(recruiter_user).get(
            f"/api/v1/interviewers/{interviewer_user.id}/availability",
            params={
                "from": (NOW + timedelta(hours=26)).isoformat(),
                "to": (NOW + timedelta(hours=30)).isoformat(),
            },
        )
        assert res.json()["count"] == 1


class TestAvailabilityDelete:
    def test_본인은_지울_수_있다(self, as_user, db: Session, interviewer_user: User):
        row = add_window(db, interviewer_user, from_hours=24, hours=2)
        res = as_user(interviewer_user).delete(f"/api/v1/availability/{row.id}")
        assert res.status_code == 204

    def test_남의_것은_지울_수_없다(self, as_user, db: Session, recruiter_user: User, interviewer_user: User):
        row = add_window(db, interviewer_user, from_hours=24, hours=2)
        res = as_user(recruiter_user).delete(f"/api/v1/availability/{row.id}")
        assert res.status_code == 403

    def test_없으면_404(self, as_user, interviewer_user: User):
        assert as_user(interviewer_user).delete("/api/v1/availability/99999999").status_code == 404


# ── 제안 생성 ────────────────────────────────────────────────────────


class TestProposalCreate:
    def test_배정된_면접관이_없으면_422(self, as_user, recruiter_user: User, application: Application):
        res = as_user(recruiter_user).post(
            f"/api/v1/applications/{application.id}/schedule-proposals", json={}
        )
        assert res.status_code == 422

    def test_가용_시간이_없으면_422(self, as_user, recruiter_user: User, assigned: Application):
        res = as_user(recruiter_user).post(
            f"/api/v1/applications/{assigned.id}/schedule-proposals", json={}
        )
        assert res.status_code == 422

    def test_면접관은_제안을_만들_수_없다(self, as_user, db: Session, interviewer_user: User, assigned: Application):
        add_window(db, interviewer_user, from_hours=24, hours=4)
        res = as_user(interviewer_user).post(
            f"/api/v1/applications/{assigned.id}/schedule-proposals", json={}
        )
        assert res.status_code == 403

    def test_가용_시간을_슬롯으로_자른다(
        self, as_user, db: Session, recruiter_user: User, interviewer_user: User, assigned: Application
    ):
        add_window(db, interviewer_user, from_hours=24, hours=3)  # 3시간 → 60분 슬롯 3개
        res = as_user(recruiter_user).post(
            f"/api/v1/applications/{assigned.id}/schedule-proposals",
            json={"slot_minutes": 60, "max_slots": 5},
        )
        assert res.status_code == 201
        body = res.json()
        assert len(body["slots"]) == 3
        assert body["status"] == "proposed"
        assert body["token"]
        assert body["url"].endswith(body["token"])

    def test_max_slots_를_넘지_않는다(
        self, as_user, db: Session, recruiter_user: User, interviewer_user: User, assigned: Application
    ):
        add_window(db, interviewer_user, from_hours=24, hours=10)
        res = as_user(recruiter_user).post(
            f"/api/v1/applications/{assigned.id}/schedule-proposals",
            json={"slot_minutes": 60, "max_slots": 2},
        )
        assert len(res.json()["slots"]) == 2

    def test_재제안하면_이전_제안은_canceled(
        self, as_user, db: Session, recruiter_user: User, interviewer_user: User, assigned: Application
    ):
        # 라이브 제안은 항상 최대 1건이어야 한다 — 옛 링크가 살아 있으면
        # 지원자가 두 링크에서 다른 시간을 고를 수 있다.
        add_window(db, interviewer_user, from_hours=24, hours=3)
        client = as_user(recruiter_user)
        first = client.post(f"/api/v1/applications/{assigned.id}/schedule-proposals", json={}).json()
        second = client.post(f"/api/v1/applications/{assigned.id}/schedule-proposals", json={}).json()

        statuses = {
            p.token: p.status
            for p in db.scalars(
                select(ScheduleProposal).where(ScheduleProposal.application_id == assigned.id)
            )
        }
        assert statuses[first["token"]] == "canceled"
        assert statuses[second["token"]] == "proposed"

    def test_이미_확정된_면접과_겹치는_시간은_후보에서_빠진다(
        self,
        as_user,
        db: Session,
        recruiter_user: User,
        interviewer_user: User,
        assigned: Application,
        posting: JobPosting,
    ):
        # 같은 면접관이 다른 지원자와 이미 확정한 시간이다. 그 시간을 또 제안하면
        # 지원자가 고를 수 있는 것처럼 보이다가 확정 단계에서 거절당한다.
        other = Application(
            job_posting_id=posting.id,
            name="다른 지원자",
            email="other-applicant@fixture.local",
            phone="010-0000-0000",
            current_stage="interview",
            source="form",
            privacy_agreed_at=NOW,
        )
        db.add(other)
        db.flush()
        booked = make_proposal(db, other, recruiter_user, n=1, status="confirmed")
        slot = add_slot(db, booked, interviewer_user, from_hours=24)
        booked.confirmed_slot_id = slot.id
        db.flush()

        add_window(db, interviewer_user, from_hours=24, hours=2)  # 24~25 는 이미 찼다
        res = as_user(recruiter_user).post(
            f"/api/v1/applications/{assigned.id}/schedule-proposals",
            json={"slot_minutes": 60, "max_slots": 5},
        )
        starts = [s["start_at"] for s in res.json()["slots"]]
        assert len(starts) == 1  # 25~26 하나만 남는다


# ── 지원자용 공개 조회 ───────────────────────────────────────────────


class TestPublicRead:
    def test_없는_토큰은_404(self, public: TestClient):
        assert public.get("/api/v1/public/schedule/nope").status_code == 404

    def test_취소된_제안은_410(
        self, public: TestClient, db: Session, application: Application, recruiter_user: User
    ):
        # 404 면 지원자가 "링크가 틀렸나" 하고 헤맨다. 새 링크가 메일로 나갔다는
        # 뜻이 전달돼야 한다.
        p = make_proposal(db, application, recruiter_user, status="canceled")
        res = public.get(f"/api/v1/public/schedule/{p.token}")
        assert res.status_code == 410

    def test_기한이_지나면_조회_시점에_expired_로_바뀐다(
        self, public: TestClient, db: Session, application: Application, recruiter_user: User
    ):
        # 스케줄러가 없다 — B4 마감과 같은 조회 시점 판정이다.
        p = make_proposal(db, application, recruiter_user, expires_at=NOW - timedelta(hours=1))
        res = public.get(f"/api/v1/public/schedule/{p.token}")
        assert res.status_code == 200
        assert res.json()["status"] == "expired"
        db.refresh(p)
        assert p.status == "expired"  # 저장까지 된다

    def test_전형_현황을_함께_준다(
        self, public: TestClient, db: Session, application: Application, recruiter_user: User
    ):
        p = make_proposal(db, application, recruiter_user)
        body = public.get(f"/api/v1/public/schedule/{p.token}").json()
        assert body["applicant_name"] == application.name
        assert body["current_stage"] == application.current_stage
        assert body["posting_title"]


# ── 지원자 확정 ──────────────────────────────────────────────────────


class TestPublicConfirm:
    def test_슬롯을_고르면_확정된다(
        self,
        public: TestClient,
        db: Session,
        application: Application,
        interviewer_user: User,
        recruiter_user: User,
    ):
        p = make_proposal(db, application, recruiter_user)
        slot = add_slot(db, p, interviewer_user, from_hours=24)
        res = public.post(f"/api/v1/public/schedule/{p.token}/confirm", json={"slot_id": slot.id})
        assert res.status_code == 200
        assert res.json()["status"] == "confirmed"
        assert res.json()["confirmed_slot"]["start_at"]
        db.refresh(p)
        assert p.confirmed_slot_id == slot.id

    def test_두_번째_확정은_409(
        self,
        public: TestClient,
        db: Session,
        application: Application,
        interviewer_user: User,
        recruiter_user: User,
    ):
        # 더블클릭·중복 탭이 정상 사용이다.
        p = make_proposal(db, application, recruiter_user)
        slot = add_slot(db, p, interviewer_user, from_hours=24)
        public.post(f"/api/v1/public/schedule/{p.token}/confirm", json={"slot_id": slot.id})
        again = public.post(f"/api/v1/public/schedule/{p.token}/confirm", json={"slot_id": slot.id})
        assert again.status_code == 409

    def test_기한이_지났으면_409(
        self,
        public: TestClient,
        db: Session,
        application: Application,
        interviewer_user: User,
        recruiter_user: User,
    ):
        p = make_proposal(db, application, recruiter_user, expires_at=NOW - timedelta(hours=1))
        slot = add_slot(db, p, interviewer_user, from_hours=24)
        res = public.post(f"/api/v1/public/schedule/{p.token}/confirm", json={"slot_id": slot.id})
        assert res.status_code == 409

    def test_다른_제안의_슬롯은_고를_수_없다(
        self,
        public: TestClient,
        db: Session,
        application: Application,
        interviewer_user: User,
        recruiter_user: User,
    ):
        mine = make_proposal(db, application, recruiter_user, n=1)
        theirs = make_proposal(db, application, recruiter_user, n=2)
        other_slot = add_slot(db, theirs, interviewer_user, from_hours=48)
        res = public.post(
            f"/api/v1/public/schedule/{mine.token}/confirm", json={"slot_id": other_slot.id}
        )
        assert res.status_code == 404

    def test_그_사이_찬_시간이면_409(
        self,
        public: TestClient,
        db: Session,
        application: Application,
        interviewer_user: User,
        recruiter_user: User,
        posting: JobPosting,
    ):
        # 슬롯은 제안 생성 시점 스냅샷이라, 제안이 나간 뒤 같은 면접관의 다른
        # 면접이 먼저 확정될 수 있다. 확정 시점에 다시 봐야 하는 이유다.
        other = Application(
            job_posting_id=posting.id,
            name="먼저 확정한 지원자",
            email="earlier@fixture.local",
            phone="010-0000-0000",
            current_stage="interview",
            source="form",
            privacy_agreed_at=NOW,
        )
        db.add(other)
        db.flush()
        booked = make_proposal(db, other, recruiter_user, n=3, status="confirmed")
        taken = add_slot(db, booked, interviewer_user, from_hours=24)
        booked.confirmed_slot_id = taken.id

        mine = make_proposal(db, application, recruiter_user, n=4)
        same_time = add_slot(db, mine, interviewer_user, from_hours=24)
        db.flush()

        res = public.post(
            f"/api/v1/public/schedule/{mine.token}/confirm", json={"slot_id": same_time.id}
        )
        assert res.status_code == 409
