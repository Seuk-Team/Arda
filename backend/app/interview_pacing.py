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

둘이다.

1. **답이 아주 짧다** — 전사된 글자 수
2. **말이 유난히 느리다** — 글자 수 ÷ 답변 길이(초). 설계 §5-4 가 붙어
   `audio_duration_sec` 이 채워지면서 볼 수 있게 됐다 (2026-09-07)

**답변 전 침묵은 아직 못 본다.** 재는 곳이 없다 — 브라우저가 녹음 시작부터
첫 발화까지를 재서 보내야 한다. 프론트가 붙을 때 이 파일의 같은 자리에 얹는다.

## 왜 짧은 답·느린 말을 신호로 보나

**둘 다 거짓의 신호가 아니다.** 질문을 못 알아들었거나, 긴장했거나, 그냥
말수가 적거나 천천히 말하는 사람일 수 있다. 어느 쪽이든 면접관이 원하는 것은
같다 — **한 번 더 묻거나, 질문을 바꾸거나, 쉬어가게 하는 것.** 이유를
추론하지 않고 행동만 제안하는 이유다.

말이 느린 것을 **"긴장했다"로 적지 않는다.** 그렇게 적는 순간 그건 심리 추론이
되고 ADR-0026 결정 2 를 넘는다. 우리가 말할 수 있는 것은 "말이 느렸다"까지고,
할 수 있는 것은 "질문을 바꿔 보자"까지다.
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

# 공백 뺀 글자 수 ÷ 초. 이보다 느리면 "유난히 느리다"로 본다.
#
# ⚠️ **이 숫자는 임시다.** 한국어 말하기는 보통 초당 4~6자쯤인데, 우리 지원자
# 녹음으로 실제로 재 본 적이 없다. 그래서 평균 근처가 아니라 **한참 아래**로
# 잡았다 — 어지간해서는 안 걸리고, 말이 끊기다시피 한 답변만 걸린다.
#
# 처음에 2.0 으로 뒀다가 내렸다. 24자를 12.5초에 말한 답변(1.9자/초)이 걸렸는데,
# 그건 중간에 한두 번 생각하며 말한 **평범한 답변**이다. 그런 데까지 말을 걸면
# 지원자는 계속 채근당한다. **오탐 하나가 놓친 것 열보다 나쁘다** — 놓쳐도
# 면접은 그대로 흘러가지만, 잘못 걸면 사람을 방해한다.
#
# 실제 녹음이 쌓이면 분포를 보고 다시 정한다. 올릴 때는 오탐이 늘어난다는 것을
# 알고 올려야 한다.
SLOW_CHARS_PER_SEC = 1.5

# 이보다 짧은 녹음으로는 속도를 재지 않는다.
#
# 2초짜리 답변은 첫 한마디 뜸들이는 것만으로도 속도가 반토막 난다. 재 봐야
# 사람에 대한 정보가 아니라 잡음이다.
MIN_DURATION_FOR_RATE = 3.0


@dataclass(frozen=True)
class PacingHint:
    """다음에 할 행동 하나. **판정이 아니라 제안이다.**

    `action` 은 화면이 분기할 값이고, `message` 는 지원자에게 그대로 보여줄
    문장이다. 점수·확률·등급에 해당하는 값은 일부러 두지 않았다.
    """

    action: str  # follow_up | offer_break | rephrase
    message: str


def _visible_length(text: str) -> int:
    """공백을 뺀 글자 수. 줄바꿈만 넣은 답이 길어 보이지 않게."""
    return len("".join(text.split()))


def suggest(
    transcript: str,
    earlier: Sequence[str] = (),
    *,
    audio_duration_sec: float | None = None,
) -> PacingHint | None:
    """이번 답변을 보고 다음 행동을 제안한다. 제안할 것이 없으면 `None`.

    `earlier` 는 같은 면접에서 **앞서 답한 것들**을 순서대로 준 것이다.
    바로 앞 답변만 보므로 전부 줘도 되고 마지막 하나만 줘도 된다.

    `audio_duration_sec` 은 음성으로 답했을 때만 온다. 텍스트로 답하면 `None`
    이고, 그때는 길이만 본다.

    **아무 문제가 없으면 아무 말도 하지 않는다** — 매 답변마다 무언가를
    제안하면 지원자는 계속 지적받는 느낌을 받는다.
    """
    length = _visible_length(transcript)

    # 길이가 먼저다. 답이 짧으면 속도를 재도 의미가 없다 — 두 글자짜리
    # 답변의 초당 글자 수는 사람에 대한 정보가 아니다.
    if length < SHORT_CHARS:
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

    if _is_slow(length, audio_duration_sec):
        # **"긴장했다"고 적지 않는다.** 우리가 아는 것은 말이 느렸다는 것뿐이고,
        # 이유는 질문이 어려웠을 수도 있다. 그래서 질문을 바꿔 보자고 한다.
        return PacingHint(
            action="rephrase",
            message="질문이 어려우셨을까요? 다르게 여쭤볼까요?",
        )

    return None


def _is_slow(length: int, audio_duration_sec: float | None) -> bool:
    """말이 유난히 느렸나. 잴 수 없으면 `False` — 모르는 것을 신호로 쓰지 않는다."""
    if audio_duration_sec is None or audio_duration_sec < MIN_DURATION_FOR_RATE:
        return False
    return (length / audio_duration_sec) < SLOW_CHARS_PER_SEC
