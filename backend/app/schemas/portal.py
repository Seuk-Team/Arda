"""지원 현황 조회 (신-1 지원자 포털) 요청·응답."""

from datetime import datetime

from pydantic import BaseModel, Field


class PortalLookupRequest(BaseModel):
    """조회 링크 요청. 이메일 하나뿐이다.

    `EmailStr` 을 쓰지 않는다 — 저장소 어디에서도 안 쓰고 있고(회원가입도 `str`),
    그것만을 위해 `email-validator` 를 새로 넣을 이유가 없다. 모양이 틀린 주소는
    어차피 아무 지원서와도 안 맞아서 **없는 주소와 같은 응답**으로 끝난다.
    """

    email: str = Field(min_length=3, max_length=255)


class PortalLookupResponse(BaseModel):
    """**찾았든 못 찾았든 같은 응답이다.**

    건수를 돌려주면 그것만으로 "이 사람이 여기 지원했는가"를 확인하는 도구가
    된다. 지원 사실 자체가 알려지면 안 되는 정보라 숫자를 싣지 않는다.
    """

    message: str


class PortalStatusOut(BaseModel):
    """지원자가 보는 현황.

    **담당자 이름·평가·메모·불합격 사유가 없다.** 지원자에게 필요한 것은
    "내 지원이 지금 어디까지 왔는가" 하나다.

    `stage_label` 은 내부 단계값(`applied`·`rejected` …)이 아니라 **사람이 읽을
    말**이다. 특히 `rejected` 를 "불합격"으로 그대로 내리지 않는다 — 담당자가
    통보하기 전에 화면이 먼저 말하게 되기 때문이다.
    """

    applicant_name: str
    posting_title: str
    stage_label: str
    submitted_at: datetime
