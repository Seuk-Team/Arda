"""면접 진행 보조 — 답변을 보고 **다음에 뭘 할지**만 제안한다 (ADR-0026 결정 4).

## 이 파일이 하지 않는 것부터

**점수를 만들지 않는다. 저장하지 않는다. 평가에 닿지 않는다.**

ADR-0026 은 목소리로 긴장도·거짓말을 판별하는 것을 명시적으로 잘랐고(결정 2),
대신 이 길만 열어 뒀다:

> **4. 긴장 신호를 쓴다면 평가가 아니라 면접 진행에만 쓴다.** 답변이 길게
> 끊기면 질문을 바꾸거나 쉬어가기를 제안하는 식. 점수에 넣지 않는다.

그래서 여기서 나오는 값은 **지원자에게 그대로 보여줄 한 문장**뿐이다. 숫자가
없고, DB 에 남지 않고, `evaluations` 로 가는 길이 아예 없다. 나중에 누가
"이 신호도 평가에 반영하면 좋겠다"고 할 때 **고칠 코드가 없어야** 한다 —
저장을 안 하는 것이 그 방어다.

## 지금 무엇을 보고 있나

**전사된 글자 수뿐이다.** 음성이 아직 안 들어온다 — 설계 §5 의 4번(음성 업로드
→ STT)이 붙기 전이라 `interview_turns.audio_duration_sec` 이 비어 있고,
답변 전 침묵은 애초에 재는 곳이 없다.

그래서 v1 은 "답이 아주 짧다"만 본다. 침묵 길이·발화 속도는 §5-4 가 붙은 뒤
이 파일의 같은 자리에 얹는다 — 규칙을 여기 모아 둔 이유가 그것이다.

## 왜 짧은 답을 신호로 보나

짧은 답은 **거짓의 신호가 아니다.** 질문을 못 알아들었거나, 긴장했거나, 그냥
말수가 적은 사람일 수 있다. 어느 쪽이든 면접관이 원하는 것은 같다 —
**한 번 더 물어보는 것.** 이유를 추론하지 않고 행동만 제안하는 이유다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

# 공백을 뺀 글자 수가 이보다 적으면 "아주 짧다"로 본다.
#
# 15자는 한국어에서 "네 그렇습니다" 정도까지가 걸리고 한 문장짜리 설명은
# 안 걸리는 선이다. 낮추면 진짜 짧은 답을 놓치고, 올리면 멀쩡한 한 문장에
# 자꾸 되묻게 된다 — 되묻는 쪽이 지원자를 더 불편하게 만든다.
SHORT_CHARS = 15

# 연속으로 이만큼 짧으면 되묻는 대신 쉬어가기를 권한다.
#
# 두 번 연속 짧다는 것은 그 질문 하나의 문제가 아닐 가능성이 높다. 계속
# 되물으면 추궁이 된다.
CONSECUTIVE_FOR_BREAK = 2


@dataclass(frozen=True)
class PacingHint:
    """다음에 할 행동 하나. **판정이 아니라 제안이다.**

    `action` 은 화면이 분기할 값이고, `message` 는 지원자에게 그대로 보여줄
    문장이다. 점수·확률·등급에 해당하는 값은 일부러 두지 않았다.
    """

    action: str  # follow_up | offer_break
    message: str


def _visible_length(text: str) -> int:
    """공백을 뺀 글자 수. 줄바꿈만 넣은 답이 길어 보이지 않게."""
    return len("".join(text.split()))


def suggest(transcript: str, earlier: Sequence[str] = ()) -> PacingHint | None:
    """이번 답변을 보고 다음 행동을 제안한다. 제안할 것이 없으면 `None`.

    `earlier` 는 같은 면접에서 **앞서 답한 것들**을 순서대로 준 것이다.
    바로 앞 답변만 보므로 전부 줘도 되고 마지막 하나만 줘도 된다.

    **아무 문제가 없으면 아무 말도 하지 않는다** — 매 답변마다 무언가를
    제안하면 지원자는 계속 지적받는 느낌을 받는다.
    """
    if _visible_length(transcript) >= SHORT_CHARS:
        return None

    recent_short = 1
    if earlier and _visible_length(earlier[-1]) < SHORT_CHARS:
        recent_short += 1

    if recent_short >= CONSECUTIVE_FOR_BREAK:
        return PacingHint(
            action="offer_break",
            message="천천히 하셔도 괜찮습니다. 잠시 쉬었다 이어가시겠어요?",
        )

    return PacingHint(
        action="follow_up",
        message="조금만 더 자세히 말씀해 주시겠어요?",
    )
