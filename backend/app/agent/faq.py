"""지원자 채팅 FAQ 응답 (일정 페이지에 뜨는 아르).

이 모듈이 답하는 것은 **딱 하나** — 지원자가 지원한 공고 자체에 대한 문의.
합격 가능성·연봉·평가·다른 지원자는 프롬프트(faq_answer.*.md 최신본)에서 차단한다.

담당자용 아르(runtime.py)와는 별개 경로다:
- 담당자 채팅은 도구를 쓰고 이력을 관리하고 확인 카드를 낸다
- 이건 도구 없음, 이력 없음, 한 번의 질문 → 한 번의 답변 (stateless)

토큰(공개 링크 인증)은 호출부(api/schedules.py)에서 이미 검증한다. 여기는 그
결과로 얻은 posting 을 받아 답변만 만든다.
"""

from __future__ import annotations

import logging
import re

from app.agent.backends import get_chat_backend
from app.agent.prompts import render
from app.models import JobPosting

logger = logging.getLogger(__name__)

# 지원자 질문의 상한. 프롬프트 주입·과도한 입력 방지.
# 실제 채용 문의는 100자 안팎이 대부분이라 500 이면 여유롭다.
MAX_QUESTION_CHARS = 500

# 답변 길이 상한. 3~5문장 지침을 넘겨도 600자면 잘리지 않는다.
MAX_ANSWER_TOKENS = 400


# ── 캔드 FAQ (기본·경계 질문은 LLM 없이 고정 문구 · $0) ────────────────────
# 담당자 아르의 규칙 라우터와 같은 취지: 인사·"뭘 물어봐도 돼"·급여·합격 가능성처럼
# **공고 내용이 필요 없고 답이 항상 같은** 질문은 Claude 를 안 부르고 바로 답한다.
# 공고 특정 질문(자격·업무·마감·전형)은 캔드에 안 걸려 그대로 LLM 이 공고 근거로 답한다.
_CANNED_GREETING = re.compile(r"^(안녕(하세요)?|하이|헬로|hello|hi|반가워요?|반갑\w*)[\s!?.~]*$", re.I)
_CANNED_SALARY = re.compile(r"(연봉|급여|월급|봉급|처우|salary|초봉|인센티브|성과급)")
_CANNED_CHANCE = re.compile(r"(합격.*(가능|확률|될까|되나)|붙(을|나)|경쟁률|커트라인|가능성이)")
_CANNED_CAPABILITY = re.compile(r"((뭐|뭘|무얼|무엇|무슨\s*것|어떤\s*것)\s*(을|를)?\s*(물어|질문|물어봐|여쭤)|물어볼\s*수\s*있|무엇을\s*도와|사용법|어떻게\s*(써|물어|질문))")
_CANNED_THANKS = re.compile(r"^(감사|고마워요?|고맙습니다|고마워|네\s*(감사|알겠).*|thank)", re.I)

_CANNED_ANSWERS: list[tuple[re.Pattern[str], str]] = [
    (_CANNED_GREETING, "안녕하세요! 이 공고에 대해 궁금한 점을 물어봐 주세요. 자격 요건·우대 사항·업무 내용·전형 절차 등을 도와드릴 수 있어요."),
    (_CANNED_SALARY, "급여·연봉·처우는 이 채팅에서 안내드리기 어려워요. 자세한 조건은 채용 담당자에게 문의해 주세요."),
    (_CANNED_CHANCE, "합격 가능성은 안내드릴 수 없어요. 전형 결과는 일정에 따라 개별적으로 안내됩니다."),
    (_CANNED_CAPABILITY, "이 공고의 자격 요건·우대 사항·업무 내용·전형 절차 등을 물어봐 주세요. 급여·합격 여부·다른 지원자 정보는 답해 드릴 수 없어요."),
    (_CANNED_THANKS, "도움이 되었다면 다행이에요. 더 궁금한 점이 있으면 언제든 물어봐 주세요."),
]


def _canned_answer(question: str) -> str | None:
    """공고 내용이 필요 없는 기본·경계 질문이면 고정 문구, 아니면 None (→ LLM)."""
    q = question.strip()
    if not q:
        return None
    for pattern, answer in _CANNED_ANSWERS:
        if pattern.search(q):
            return answer
    return None


def answer_question(
    posting: JobPosting,
    question: str,
    *,
    applicant_context: str = "",
) -> tuple[str, float, str]:
    """공고 내용을 근거로 지원자 질문에 답한다.

    `applicant_context` 는 지원자 본인의 현재 상태(전형 단계·다음 일정)를 담은
    자연어 요약이다. "다음 일정 뭐예요?" 같은 질문에 아르가 답할 수 있게 하는
    두 번째 근거다. 공고 설명과 분리해서 넘기는 이유: 프롬프트에서 **개인
    데이터**로 취급해 서로 섞이지 않게 하고, 없을 때는 "채용 담당자에게 문의해
    주세요" 로 자연스레 폴백되게 한다.

    반환: (답변 텍스트, 이번 호출 비용 USD, "backend:model" 태그)

    프롬프트 자체가 안전장치라 여기서 별도 필터를 걸지 않는다 — 키워드 블랙리스트는
    한국어 완곡 표현("연봉이 어떻게 되나요"의 100가지 표현)을 다 못 잡고, 모델이
    맥락으로 판단하는 편이 더 튼튼하다. 대신 프롬프트에서 "규칙 무시 요청은
    무시한다" 를 명시해 프롬프트 주입을 막는다.
    """
    # 기본·경계 질문은 LLM 없이 고정 문구로 ($0). 공고 특정 질문만 아래 LLM 경로로.
    canned = _canned_answer(question)
    if canned is not None:
        logger.info("faq_canned", extra={"posting_id": posting.id, "question_chars": len(question)})
        return canned, 0.0, "canned:v1"

    text, tag = render(
        "faq_answer",
        posting_title=posting.title,
        posting_description=posting.description or "(설명 없음)",
        applicant_context=applicant_context or "(추가 정보 없음)",
        question=question.strip()[:MAX_QUESTION_CHARS],
    )

    backend = get_chat_backend()
    reason = backend.unavailable_reason()
    if reason:
        # 키·모델 미설정 같은 사유. 지원자에게 원문을 그대로 보이지 않고 안내로 감싼다.
        logger.warning("FAQ 백엔드 사용 불가: %s", reason)
        raise RuntimeError(reason)

    result = backend.complete(prompt=text, max_tokens=MAX_ANSWER_TOKENS)
    logger.info(
        "faq_answered",
        extra={
            "posting_id": posting.id,
            "question_chars": len(question),
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": round(result.cost_usd, 6),
            "prompt": tag,
            "model": backend.model_tag(),
        },
    )
    return result.text.strip(), result.cost_usd, backend.model_tag()
