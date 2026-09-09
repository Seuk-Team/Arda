"""지원자 앱 로그인 요청·응답 (ADR-0033)."""

from datetime import datetime

from pydantic import BaseModel, Field


class ApplicantLoginRequest(BaseModel):
    """아이디는 지원할 때 쓴 이메일, 비밀번호는 생년월일 8자리다.

    `birth_date` 를 `date` 로 받지 않고 문자열로 받는 이유: 형식이 틀렸을 때
    **422 가 아니라 401 로 답하려는 것**이다. 422 는 "형식은 맞지만 값이
    틀렸다"와 "형식부터 틀렸다"를 구별해 주는데, 그 차이가 이메일 존재 여부를
    떠보는 데 쓰인다.
    """

    email: str = Field(min_length=3, max_length=255)
    birth_date: str = Field(min_length=8, max_length=8, description="YYYYMMDD")


class ApplicantLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MyApplicationOut(BaseModel):
    """지원자가 보는 자기 지원 한 건.

    **단계를 내부값이 아니라 사람이 읽을 말로 내린다.** 특히 `rejected` 를
    "불합격"으로 쓰지 않는다 — 담당자가 통보하기 전에 앱이 먼저 말하면 안 된다
    (portal.STAGE_LABEL 과 같은 규칙).
    """

    id: int
    posting_title: str
    stage_label: str
    applied_at: datetime
    # 지금 들어갈 수 있는 것들. 없으면 빈 목록이다.
    #
    # **로그인이 유일한 문이면 이것들이 여기 없을 때 갈 길이 없다.** 앱에는
    # 메일함이 없고, 그러면 ADR-0033 이 없애려던 "앱인데 메일을 거쳐야 한다"가
    # 그대로 남는다. 셋 다 본인 토큰으로 조회한 자기 것이라 근거가 같다.
    interviews: list["MyInterviewOut"] = []
    aptitudes: list["MyTokenLinkOut"] = []
    schedules: list["MyTokenLinkOut"] = []


class MyTokenLinkOut(BaseModel):
    """지원자가 지금 들어갈 수 있는 토큰 경로 하나 — 인적성·일정에 쓴다.

    면접(`MyInterviewOut`)과 모양이 같다. 셋 다 `application_id` + `token` +
    `status` + `expires_at` 구조라 따로 만들 이유가 없다.
    """

    token: str
    status: str
    expires_at: datetime | None


class MyInterviewOut(BaseModel):
    """지원자가 들어갈 수 있는 면접 하나.

    **토큰을 내려준다.** 지원자 본인 토큰으로 조회한 자기 면접이라 새로 여는
    비밀이 아니고, 이 값이 없으면 메일을 못 찾은 지원자는 면접에 못 들어간다 —
    "메일함을 뒤지세요"가 유일한 길이 되는 것을 막는다.

    **만료된 면접은 목록에 없다** — 지원자가 놓친 것이라 할 수 있는 일이 없다.
    끝난 면접(`done`)은 **있다**(2026-09-09): 없으면 방금 면접을 마친 사람의
    화면에서 면접이 통째로 사라져 "완료"와 "아직 안 잡힘"이 같아진다.
    화면은 `status` 를 보고 끝난 줄에는 들어가는 문을 그리지 않는다.
    """

    token: str
    status: str
    expires_at: datetime | None


class ApplicantMeOut(BaseModel):
    """**담당자 이름·평가·메모·AI 요약·불합격 사유가 없다.**

    지원자에게 필요한 것은 "내 지원이 지금 어디까지 왔는가" 하나다.
    """

    email: str
    name: str
    applications: list[MyApplicationOut]
