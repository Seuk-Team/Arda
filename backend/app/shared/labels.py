"""사람이 보는 이름 (Korean display labels).

같은 단계 코드를 서로 다른 문자열로 그리면 담당자·지원자가 같은 화면에서
두 표기를 보게 된다 — runtime.py 의 "서류심사" 와 프론트 STAGE_LABEL 의
"서류 검토" 가 실제로 그렇게 갈라져 있었다 (2026-09-01 감사).

- **STAGE_LABEL_KR** — 프론트 `frontend/app/src/lib/stage.ts:STAGE_LABEL` 과
  값이 같다. 프론트가 화면의 정본이라 그것에 맞춘다. **담당자용 표기**다.
- **STAGE_LABEL_APPLICANT_KR** — **지원자에게 보이는 표기**. 담당자용과 일부러
  다르다 ("불합격" → "전형 종료" 처럼 통보 맥락에 맞춘 완곡한 문구). 지원자 포털과
  지원자 로그인 화면이 같은 문구를 써야 해서 여기 둔다 — 원래 `application/api/portal.py`
  안에 있었고 `talent/api/applicant_auth.py` 가 그 **라우터 모듈을 import** 해서
  쓰고 있었다 (2026-09-12 감사에서 컨텍스트 경계 위반으로 잡아 옮겼다).
- **EMAIL_PURPOSE_KR** — 확인 카드·메일 로그의 목적 표시.

**중복 지점을 여기 하나로 모은다.** 새 화면·문구를 추가할 때 여기 없는 표기를
지어내면 즉시 갈라지므로, 표기가 필요하면 먼저 이 파일을 확장한다.
"""

STAGE_LABEL_KR = {
    "applied": "지원 접수",
    "screening": "서류 검토",
    "interview": "면접",
    "accepted": "최종 합격",
    "rejected": "불합격",
}

# 지원자에게 보이는 단계 표기. 담당자용(STAGE_LABEL_KR) 과 문구가 다른 것이 의도다.
#
# **`rejected` 를 그대로 "불합격"이라고 쓰지 않는다.** 담당자가 통보 메일을 보내기
# 전에 지원자가 이 화면으로 먼저 알게 되면, 사람이 전할 말을 화면이 앞질러 전하게
# 된다. 여기서는 "전형이 끝났다"까지만 말하고, 사유는 어디에도 싣지 않는다 —
# 불합격 사유는 담당자 화면의 기록이지 지원자에게 자동으로 나가는 값이 아니다.
STAGE_LABEL_APPLICANT_KR = {
    "applied": "접수 완료",
    "screening": "서류 검토 중",
    "interview": "면접 전형 진행 중",
    "accepted": "최종 합격",
    "rejected": "전형 종료",
}

EMAIL_PURPOSE_KR = {
    "interview": "면접 안내",
    "accepted": "합격 안내",
    "rejected": "불합격 안내",
    "general": "일반 안내",
}
