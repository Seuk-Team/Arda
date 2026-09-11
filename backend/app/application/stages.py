"""단계 전환 규칙 (D3).

01-erd.md 의 "단계(stage)" 절을 코드로 옮긴 것이다.

    applied → screening → interview → accepted / rejected

- `rejected` 는 어느 단계에서든 진입 가능하다.
- 그 외 전진은 순서대로만 — 건너뛰기 금지.
- 뒤로 이동은 담당자 권한이다.

**규칙을 DB 제약이 아니라 여기에 둔 이유**: 체크 제약은 "값이 5개 중 하나"까지만
막을 수 있다. "지금 값이 무엇이냐에 따라 다음 값이 정해진다"는 전이 규칙은 이전 행
값을 알아야 해서 컬럼 제약으로 표현되지 않는다. 트리거로 넣으면 표현은 되지만
규칙이 마이그레이션 안으로 숨어 테스트도 어려워진다. 그래서 서비스 레이어다
(01-erd.md 가 지정한 위치이기도 하다).
"""

from app.models import STAGES

# 전진 경로. rejected 는 순서 밖이라 여기 없다.
STAGE_ORDER = ("applied", "screening", "interview", "accepted")

REJECTED = "rejected"

# 지원자에게 알릴 단계 (G1 템플릿이 있는 것). screening 은 내부 검토 단계라
# 지원자에게 보낼 문구가 없고, applied 는 C4 접수 확인 메일이 따로 있다.
NOTIFY_STAGES = frozenset({"interview", "accepted", REJECTED})


class StageTransitionError(ValueError):
    """규칙에 어긋나는 전환. 호출부가 409 로 바꾼다."""


def validate_transition(from_stage: str, to_stage: str) -> None:
    """전환이 규칙에 맞는지 본다. 어긋나면 StageTransitionError."""
    if to_stage not in STAGES:
        raise StageTransitionError(
            f"알 수 없는 단계입니다: {to_stage} (가능: {', '.join(STAGES)})"
        )

    if from_stage == to_stage:
        raise StageTransitionError(f"이미 '{to_stage}' 단계입니다")

    # 불합격은 어느 단계에서든 가능
    if to_stage == REJECTED:
        return

    # 불합격에서 되돌리는 것은 뒤로 이동 — 담당자 권한으로 허용한다
    if from_stage == REJECTED:
        return

    here = STAGE_ORDER.index(from_stage)
    there = STAGE_ORDER.index(to_stage)

    # 뒤로 이동은 허용 (담당자가 되돌리는 경우)
    if there < here:
        return

    # 전진은 한 칸씩만
    if there - here > 1:
        raise StageTransitionError(
            f"단계를 건너뛸 수 없습니다: {from_stage} → {to_stage}"
            f" (다음 단계는 '{STAGE_ORDER[here + 1]}')"
        )
