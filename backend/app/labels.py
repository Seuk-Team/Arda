"""사람이 보는 이름 (Korean display labels).

같은 단계 코드를 서로 다른 문자열로 그리면 담당자·지원자가 같은 화면에서
두 표기를 보게 된다 — runtime.py 의 "서류심사" 와 프론트 STAGE_LABEL 의
"서류 검토" 가 실제로 그렇게 갈라져 있었다 (2026-09-01 감사).

- **STAGE_LABEL_KR** — 프론트 `frontend/app/src/lib/stage.ts:STAGE_LABEL` 과
  값이 같다. 프론트가 화면의 정본이라 그것에 맞춘다.
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

EMAIL_PURPOSE_KR = {
    "interview": "면접 안내",
    "accepted": "합격 안내",
    "rejected": "불합격 안내",
    "general": "일반 안내",
}
