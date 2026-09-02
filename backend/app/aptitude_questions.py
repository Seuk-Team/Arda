"""사전 성향 설문 문항 — 코드 상수 (ADR-0027 결정 2).

문항 편집 UI 는 만들지 않는다. 문구를 고치면 key 를 유지한 채 text 만 바꾸되,
이미 저장된 응답은 `aptitude_answers.question_text` 스냅샷이 지킨다.

**직무 관련 행동 성향만 묻는다.** MBTI·DISC 같은 상표 검사를 쓰지 않고 흉내
내지도 않는다. 좋고 나쁨이 있는 문장을 두지 않는다 — "혼자 집중할 때 성과가
잘 나온다"는 선호이지 결함이 아니다.
"""

LIKERT_MIN = 1
LIKERT_MAX = 5

# 지원자 화면·요약 프롬프트가 같은 라벨을 쓴다 — 두 벌이면 반드시 갈린다
LIKERT_LABELS = {
    1: "전혀 그렇지 않다",
    2: "그렇지 않은 편이다",
    3: "보통이다",
    4: "그런 편이다",
    5: "매우 그렇다",
}

# category → 화면·통계 라벨
CATEGORY_LABELS = {
    "collaboration": "협업",
    "workstyle": "업무 방식",
    "stress": "스트레스 대처",
    "communication": "소통",
    "growth": "성장",
}

QUESTIONS: list[dict] = [
    {
        "key": "collab_help",
        "category": "collaboration",
        "text": "동료가 어려움을 겪고 있으면 내 일정을 조정해서라도 돕는 편이다.",
    },
    {
        "key": "collab_feedback",
        "category": "collaboration",
        "text": "내 결과물에 대한 비판적인 피드백을 편하게 받아들이는 편이다.",
    },
    {
        "key": "work_plan",
        "category": "workstyle",
        "text": "일을 시작하기 전에 계획을 세우고 우선순위를 정리하는 편이다.",
    },
    {
        "key": "work_focus",
        "category": "workstyle",
        "text": "여럿이 함께 일할 때보다 혼자 집중할 때 성과가 더 잘 나오는 편이다.",
    },
    {
        "key": "stress_deadline",
        "category": "stress",
        "text": "마감이 촉박해도 평소와 비슷한 품질을 유지하는 편이다.",
    },
    {
        "key": "stress_recover",
        "category": "stress",
        "text": "실수한 뒤에도 감정에 오래 머물지 않고 다음 일로 넘어가는 편이다.",
    },
    {
        "key": "comm_disagree",
        "category": "communication",
        "text": "의견이 다를 때 상대와 직접 이야기해서 조율하는 편이다.",
    },
    {
        "key": "comm_share",
        "category": "communication",
        "text": "진행 상황을 누가 묻기 전에 먼저 공유하는 편이다.",
    },
    {
        "key": "growth_learn",
        "category": "growth",
        "text": "새로운 도구나 방법을 스스로 찾아서 익히는 편이다.",
    },
    {
        "key": "growth_challenge",
        "category": "growth",
        "text": "익숙한 일보다 해 본 적 없는 일을 맡는 쪽을 선호하는 편이다.",
    },
]

QUESTION_KEYS = tuple(q["key"] for q in QUESTIONS)
QUESTIONS_BY_KEY = {q["key"]: q for q in QUESTIONS}
