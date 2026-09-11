"""문구 렌더·서명·발송 분기 (G4).

발송은 되돌릴 수 없다. 여기서 잡히지 않는 실수는 지원자 메일함에서 발견된다.
그래서 렌더 층을 DB·SES 없이도 돌 수 있게 떼어 두고, 그 층을 촘촘히 본다.
"""

from __future__ import annotations

import pytest

from app.shared import mail, worker
from app.models import EmailLog


class TestFill:
    def test_모르는_토큰은_그대로_둔다(self):
        """format 이었다면 KeyError 로 워커가 죽고 DLQ 까지 갔을 입력이다."""
        out = mail.fill("{지원자명} 님 {알수없음} {", {"지원자명": "김도현"})
        assert out == "김도현 님 {알수없음} {"

    def test_중괄호가_섞여도_안_죽는다(self):
        assert mail.fill("코드: if x { y }", {"지원자명": "김"}) == "코드: if x { y }"


class TestFillBody:
    """fill_body 의 서명 자동 추가 규칙 (2026-09-08 수정 이후)."""

    _VALUES = {"서명": "Seuk 채용 담당자 관리자 드림"}

    def test_플레이스홀더_있으면_그대로_치환_한_번만(self):
        body = "안녕하세요.\n{서명}"
        out = mail.fill_body(body, self._VALUES)
        assert out.count("Seuk 채용 담당자 관리자 드림") == 1

    def test_렌더된_서명_텍스트가_이미_있으면_재추가_안함(self):
        """담당자 UI 미리보기가 렌더된 서명을 담아 그대로 전송되는 경로 재현.

        수정 전엔 fill_body 가 {서명} 이 없다며 끝에 자동 추가해 서명이 두 번 나갔다.
        """
        body = "안녕하세요.\n본문입니다.\n\nSeuk 채용 담당자 관리자 드림"
        out = mail.fill_body(body, self._VALUES)
        assert out.count("Seuk 채용 담당자 관리자 드림") == 1

    def test_둘_다_없으면_자동_추가(self):
        body = "안녕하세요. 본문만 있음."
        out = mail.fill_body(body, self._VALUES)
        assert out.endswith("Seuk 채용 담당자 관리자 드림")
        assert out.count("Seuk 채용 담당자 관리자 드림") == 1

    def test_서명_값이_비면_자동_추가_안함(self):
        """서명이 빈 값이면 자동 추가 로직에 걸리지 않고 본문 그대로."""
        body = "본문"
        out = mail.fill_body(body, {"서명": ""})
        assert "Seuk" not in out


class TestUnknownVars:
    def test_허용_변수는_통과(self):
        assert mail.unknown_vars("{지원자명} {공고명} {회사명} {면접일시} {서명}") == []

    def test_오타를_잡는다(self):
        assert mail.unknown_vars("{지원자 명} 님") == ["{지원자 명}"]

    def test_없는_변수를_잡는다(self):
        assert mail.unknown_vars("{면접장소}") == ["{면접장소}"]


class TestSignature:
    def test_사람은_이름으로_서명한다(self):
        assert (
            mail.build_signature("interview", "human", "김채용")
            == f"{mail.COMPANY_NAME} 채용 담당자 김채용 드림"
        )

    def test_에이전트는_아르로_서명한다(self):
        assert (
            mail.build_signature("interview", "agent", "김채용")
            == f"{mail.COMPANY_NAME} 채용 에이전트 아르 드림"
        )

    def test_시스템은_팀_서명(self):
        """접수 확인·일정 확정은 지원자 본인의 행동이 트리거다 — 담당자가 없다."""
        assert (
            mail.build_signature("applied", "system")
            == f"{mail.COMPANY_NAME} 채용팀 드림"
        )

    @pytest.mark.parametrize("stage", ["accepted", "rejected"])
    def test_합불_통보는_에이전트여도_사람_이름(self, stage):
        """AI 가 심사했다는 오해를 만들지 않는다 (G4 결정 6)."""
        assert mail.build_signature(stage, "agent", "김채용").endswith(
            "채용 담당자 김채용 드림"
        )

    def test_이름을_모르면_팀_서명으로_내려간다(self):
        assert mail.build_signature("interview", "human", None).endswith("채용팀 드림")


class TestRender:
    def test_기본_문구에_값이_채워진다(self, db, admin_user):
        subject, body = mail.render(
            db, "interview", "김도현", "백엔드 개발자", actor_kind="human",
            actor_name=admin_user.name,
        )
        assert "김도현" in body
        assert "백엔드 개발자" in subject
        assert "{지원자명}" not in body  # 남은 변수가 없다
        assert body.rstrip().endswith(f"채용 담당자 {admin_user.name} 드림")

    def test_오버라이드가_기본값을_이긴다(self, db, admin_user):
        from app.models import EmailTemplate

        db.add(
            EmailTemplate(
                stage="applied",
                subject="바뀐 제목",
                body="{지원자명} 님\n\n{서명}",
                updated_by=admin_user.id,
            )
        )
        db.flush()
        subject, body = mail.render(db, "applied", "김도현", "백엔드")
        assert subject == "바뀐 제목"
        assert body.startswith("김도현 님")

    def test_문구가_없는_단계는_예외(self, db):
        with pytest.raises(mail.UnknownStageTemplate):
            mail.render(db, "screening", "김도현", "백엔드")

    def test_db_없이도_기본값으로_렌더된다(self):
        """오버라이드 조회가 불가능한 상황에서도 메일은 나가야 한다."""
        subject, _ = mail.render(None, "applied", "김도현", "백엔드")
        assert "김도현" not in subject  # 제목에는 이름이 없다
        assert "백엔드" in subject


class TestReplyTo:
    def test_사람이_보내면_그_사람에게_회신된다(self):
        log = EmailLog(actor_kind="human")
        assert worker._reply_to(log, "recruiter@arda.com") == "recruiter@arda.com"

    def test_에이전트는_팀_주소로(self, monkeypatch):
        monkeypatch.setattr(worker, "MAIL_REPLY_TO", "team@arda.com")
        log = EmailLog(actor_kind="agent")
        assert worker._reply_to(log, "someone@arda.com") == "team@arda.com"

    def test_시스템도_팀_주소로(self, monkeypatch):
        monkeypatch.setattr(worker, "MAIL_REPLY_TO", "team@arda.com")
        assert worker._reply_to(EmailLog(actor_kind="system"), None) == "team@arda.com"

    def test_팀_주소가_없으면_None(self, monkeypatch):
        """빈 문자열을 SES 에 넘기면 거절당한다 — 키를 아예 빼야 한다."""
        monkeypatch.setattr(worker, "MAIL_REPLY_TO", "")
        assert worker._reply_to(EmailLog(actor_kind="system"), None) is None


class TestSenderName:
    """From 표시 이름 (G4). 본문 서명과 **같은 문자열**이어야 한다 —
    받은편지함의 이름과 서명이 다르면 누구에게 연락할지 헷갈린다."""

    def test_서명과_같은_이름을_쓴다(self):
        for kind, name in (("human", "김채용"), ("agent", None), ("system", None)):
            assert (
                mail.build_signature("interview", kind, name)
                == mail.sender_name("interview", kind, name) + " 드림"
            )

    def test_사람_이름이_들어간다(self):
        assert mail.sender_name("interview", "human", "김채용").endswith("김채용")

    def test_에이전트는_아르(self):
        assert mail.sender_name("interview", "agent").endswith("아르")

    def test_시스템은_팀_이름(self):
        assert mail.sender_name("applied", "system") == f"{mail.COMPANY_NAME} 채용팀"


class TestSource:
    """From 헤더 조립. 주소는 그대로 두고 표시 이름만 붙인다."""

    def test_한글_이름은_MIME_인코딩된다(self, monkeypatch):
        """헤더에 한글을 날것으로 넣으면 SES 가 거절하거나 깨져서 도착한다."""
        monkeypatch.setenv("SES_FROM_EMAIL", "no-reply@arda.seuk.cloud")
        out = worker._source("Arda 채용 담당자 김채용")
        assert out.endswith("<no-reply@arda.seuk.cloud>")
        assert "=?utf-8?" in out.lower()
        assert "김채용" not in out  # 날것으로 새어나가지 않는다

    def test_이름이_없으면_주소만(self, monkeypatch):
        monkeypatch.setenv("SES_FROM_EMAIL", "no-reply@arda.seuk.cloud")
        assert worker._source(None) == "no-reply@arda.seuk.cloud"


class TestHandleBranch:
    """워커가 저장된 본문과 발송 시점 렌더를 어떻게 가르는가."""

    def _sent(self, monkeypatch) -> list:
        calls: list = []
        monkeypatch.setattr(
            worker,
            "_send_via_ses",
            lambda to, subject, body, reply_to=None, from_name=None: calls.append(
                (to, subject, body, reply_to, from_name)
            ),
        )
        return calls

    def test_저장된_본문은_다시_렌더하지_않는다(
        self, db, monkeypatch, application, member_user
    ):
        calls = self._sent(monkeypatch)
        log = mail.create_custom_log(
            db,
            application_id=application.id,
            to_email=application.email,
            subject="그대로 나갈 제목",
            body="그대로 나갈 본문",
            actor_kind="human",
            actor_id=member_user.id,
        )
        db.flush()
        worker.handle(db, log.id)

        assert calls[0][1] == "그대로 나갈 제목"
        assert calls[0][2] == "그대로 나갈 본문"
        assert calls[0][3] == member_user.email  # 보낸 사람에게 회신
        assert calls[0][4].endswith(member_user.name)  # 받은편지함에 뜰 이름
        assert log.status == "sent"

    def test_저장된_본문이_없으면_단계로_렌더한다(
        self, db, monkeypatch, application, admin_user
    ):
        calls = self._sent(monkeypatch)
        log = mail.create_log(
            db,
            application_id=application.id,
            to_email=application.email,
            stage="applied",
            actor_kind="human",
            actor_id=admin_user.id,
        )
        db.flush()
        worker.handle(db, log.id)

        assert application.name in calls[0][2]
        assert calls[0][2].rstrip().endswith(f"채용 담당자 {admin_user.name} 드림")

    def test_주체가_없으면_팀_서명으로_나간다(
        self, db, monkeypatch, application
    ):
        calls = self._sent(monkeypatch)
        log = mail.create_log(
            db,
            application_id=application.id,
            to_email=application.email,
            stage="applied",
        )
        db.flush()
        worker.handle(db, log.id)
        assert calls[0][2].rstrip().endswith("채용팀 드림")

    def test_custom_인데_본문이_없으면_실패로_남는다(
        self, db, monkeypatch, application
    ):
        """렌더할 문구가 없는 조합이다. 조용히 빈 메일을 보내지 않는다."""
        self._sent(monkeypatch)
        log = mail.create_log(
            db,
            application_id=application.id,
            to_email=application.email,
            stage="custom",
        )
        db.flush()
        with pytest.raises(mail.UnknownStageTemplate):
            worker.handle(db, log.id, receive_count=worker.MAX_RECEIVE)
        assert log.status == "failed"

    def test_이미_보낸_건은_두_번_안_보낸다(
        self, db, monkeypatch, application
    ):
        calls = self._sent(monkeypatch)
        log = mail.create_log(
            db,
            application_id=application.id,
            to_email=application.email,
            stage="applied",
        )
        log.status = "sent"
        db.flush()
        worker.handle(db, log.id)
        assert calls == []


class TestProviderMessageId:
    """SES MessageId 를 행에 남긴다 (2026-09-07).

    **`status='sent'` 는 "SES 가 받아줬다"까지만 뜻한다.** `MAIL_DRY_RUN` 이면
    SES 를 아예 안 부르고도 sent 가 되고, 받은 뒤 반송될 수도 있다. 그래서
    "보냈다는데 안 왔다"를 확인하려면 이 값이 있어야 한다 — 로그로만 갖고
    있었더니 서버 셸이 없는 사람은 확인할 방법이 없었다.
    """

    def _log(self, db, application):
        log = mail.create_log(
            db,
            application_id=application.id,
            to_email=application.email,
            stage="applied",
        )
        db.flush()
        return log

    def test_MessageId_를_행에_남긴다(self, db, monkeypatch, application):
        monkeypatch.setattr(
            worker,
            "_send_via_ses",
            lambda *a, **k: "0100018f-ses-message-id",
        )
        log = self._log(db, application)
        worker.handle(db, log.id)

        assert log.status == "sent"
        assert log.provider_message_id == "0100018f-ses-message-id"

    def test_DRY_RUN_이면_sent_인데_MessageId_가_없다(
        self, db, monkeypatch, application
    ):
        """이 조합 자체가 '실제로는 안 나갔다' 는 표시다."""
        monkeypatch.setattr(worker, "_send_via_ses", lambda *a, **k: None)
        log = self._log(db, application)
        worker.handle(db, log.id)

        assert log.status == "sent"
        assert log.provider_message_id is None

    def test_DRY_RUN_은_SES_를_부르지_않고_None_을_돌려준다(self, monkeypatch):
        monkeypatch.setattr(worker, "DRY_RUN", True)
        called = []
        monkeypatch.setattr(worker, "_ses", lambda: called.append(1))

        assert worker._send_via_ses("a@b.c", "제목", "본문") is None
        assert called == []  # SES 를 만들지도 않는다
