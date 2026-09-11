"""AI 면접 스키마 (ADR-0026).

설계는 docs/02_tasks/AI면접-설계.md.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SessionCreate(BaseModel):
    """담당자가 면접을 만들 때. 전부 선택값이다 — 기본값으로 충분하다."""

    # 링크 유효 기간. 비우면 서버 기본값(7일)
    expires_in_days: int | None = Field(default=None, ge=1, le=30)


class SessionOut(BaseModel):
    """담당자용. 토큰과 링크를 함께 준다 — 링크를 화면이 조립하지 않는다.

    치환을 화면에 맡기면 미리보기와 실제가 갈린다 (메일 프리필과 같은 판단).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    status: str
    token: str
    url: str
    expires_at: datetime | None
    consented_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime


class ActiveSessionOut(BaseModel):
    """지금 진행 중인 면접 하나 — 대시보드가 바로 들어가는 데 쓴다.

    **이름과 공고를 같이 준다.** 담당자가 면접 중에 볼 화면이라 "누구의 면접인가"
    없이 세션 번호만 있으면 못 고른다. 화면이 지원서·공고를 따로 두 번 더 부르게
    하지 않는다 — `InterviewRoom` 이 그렇게 하고 있고, 대시보드에서 그러면
    면접 수만큼 요청이 는다.
    """

    id: int
    application_id: int
    applicant_name: str
    posting_title: str
    started_at: datetime | None


class TurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    question: str
    transcript: str | None
    audio_duration_sec: float | None
    # 아르가 어느 답변에서 이 질문을 만들었나. 값이 있으면 자동생성이고 화면이
    # 배지를 그린다 (2026-09-10, 0017 마이그레이션).
    generated_from_turn_id: int | None = None


class FindingOut(BaseModel):
    """서류 주장 ↔ 면접 발언 대조 한 건.

    **점수가 없다.** 갈래는 셋뿐이고 판단은 사람이 한다 (ADR-0026 · ADR-0003).
    양쪽 원문을 그대로 내려주는 이유는 지원자가 반박할 수 있어야 하기 때문이다.
    """

    model_config = ConfigDict(from_attributes=True)

    claim_source: str
    claim_text: str
    answer_text: str
    verdict: str
    # 어느 답변에서 나온 대조인가 (2026-09-11). 화상 방이 그 답변 밑에 붙인다.
    # None 이면 면접이 끝난 뒤 전체 전사로 만든 것이다.
    turn_seq: int | None = None


class SessionDetailOut(SessionOut):
    """담당자용 상세 — 전사와 대조 결과, 아르의 면접 점수(ADR-0034)까지."""

    turns: list[TurnOut] = []
    findings: list[FindingOut] = []
    # 서류 대조 스위치(`AGENT_FINDINGS_BACKEND`)가 켜져 있는가. **꺼진 것과 아직
    # 없는 것을 화면이 가를 수 있게** 내려준다 — 둘 다 `findings` 가 비어 보인다
    # (2026-09-11: 운영에서 꺼져 있는 줄 모르고 기능이 안 되는 줄 알 뻔했다).
    findings_enabled: bool = False
    ai_score: int | None = None
    ai_score_detail: dict | None = None
    scored_at: datetime | None = None


class PacingHintOut(BaseModel):
    """진행 보조 제안 하나 (ADR-0026 결정 4).

    **판정이 아니라 제안이다.** 점수·확률·등급에 해당하는 값이 없고, DB 에도
    남지 않는다 — 답변을 저장한 그 응답에만 실려 나간다. 규칙은
    `app/interview_pacing.py` 에 모여 있다.
    """

    action: str  # follow_up | offer_break | rephrase
    message: str


class InterviewPublicOut(BaseModel):
    """지원자용. **토큰과 URL 을 되돌려주지 않는다** — 이미 가진 사람만 본다.

    지원자에게 필요한 것은 "내가 누구의 어느 면접에 와 있는가"와 "지금 뭘 하면
    되는가"뿐이다. 담당자 이름·평가·다른 지원자는 내려주지 않는다.
    """

    status: str
    applicant_name: str
    posting_title: str
    expires_at: datetime | None
    consent_required: bool
    # 진행 중일 때 현재 질문. pending 이면 None
    current_question: str | None = None
    question_seq: int | None = None
    # 답변을 낸 직후에만 붙는다. 조회(GET)에는 항상 None —
    # 지원자가 새로고침할 때마다 같은 말을 반복하지 않게.
    pacing: PacingHintOut | None = None


class ConsentRequest(BaseModel):
    """녹음·전사·보관 동의. 지원 폼의 개인정보 동의와 별개다."""

    agreed: bool


class QuestionsSet(BaseModel):
    """담당자가 질문 목록을 넣는다.

    설계 §5 의 5번(요약에서 자동 생성)이 붙기 전까지의 입구다. 자동 생성이 들어와도
    이 경로는 남는다 — 담당자가 질문을 고쳐 넣을 수 있어야 한다.
    """

    questions: list[str] = Field(min_length=1, max_length=20)


class AudioUploadRequest(BaseModel):
    """답변 음성 업로드 URL 요청 (설계 §5-4).

    이력서 업로드(`/public/files/presign-upload`)와 **다른 경로**다. 그쪽은
    토큰 없이 누구나 부를 수 있어서, 거기에 음성 형식을 얹으면 아무나 우리
    버킷에 미디어를 올릴 수 있게 된다. 여기는 **진행 중인 면접 토큰**이 있어야
    발급된다.
    """

    filename: str = Field(min_length=1, max_length=200)
    content_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(gt=0)


class AudioUploadResponse(BaseModel):
    upload_url: str
    s3_key: str
    expires_in: int


class AnswerRequest(BaseModel):
    """답변 제출. **텍스트 또는 음성 하나**를 보낸다.

    - `transcript` — 텍스트로 바로 답한다
    - `audio_s3_key` — 음성을 올린 뒤 그 키를 준다. 서버가 읽어 전사한다 (§5-4)

    **둘 다 보내면 거절한다.** 어느 쪽을 진짜 답으로 볼지 서버가 고르게 두면,
    보낸 쪽은 자기가 낸 답이 저장됐다고 믿는데 실제로는 다른 것이 저장될 수 있다.
    """

    transcript: str | None = Field(default=None, min_length=1)
    audio_s3_key: str | None = Field(default=None, min_length=1, max_length=200)
    # 어느 질문의 답인가. **안 보내면 지금까지와 같다** — "아직 답 안 한 가장 앞
    # 질문"에 붙는다.
    #
    # 워커가 전사를 뒤에서 돌리기 시작하면서 필요해졌다. 지원자를 기다리게 하지
    # 않으려고 다음 질문을 먼저 보내는데, 그러면 답변이 도착하는 순서와 질문
    # 순서가 어긋날 수 있다. "가장 앞 빈칸" 규칙은 그때 **남의 칸에 답을 넣는다**.
    seq: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _exactly_one(self) -> "AnswerRequest":
        if bool(self.transcript) == bool(self.audio_s3_key):
            raise ValueError("transcript 와 audio_s3_key 중 하나만 보내야 합니다")
        return self
