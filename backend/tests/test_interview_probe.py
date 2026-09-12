"""꼬리 질문 생성 — 파싱과 경계 (AI면접 설계 §5-5).

LLM 호출은 목으로 막는다. 여기서 보는 것은 **모델이 뭘 돌려주든 화면에
줄 수 있는 모양으로 정제되는가**다.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.agent.backends.base import CompletionResult
from app.agent.interview_probe import generate_probes


def _backend(text: str, unavailable: str | None = None):
    b = MagicMock()
    b.unavailable_reason.return_value = unavailable
    b.supports_structured_output = False
    b.model_tag.return_value = "anthropic:claude-haiku-4-5-20251001"
    b.complete.return_value = CompletionResult(text=text, input_tokens=900, output_tokens=200)
    return b


# 인용 검증이 걸리므로, 테스트가 쓰는 주장은 이 자소서 안에 있어야 한다.
COVER = (
    "FastAPI로 재작성해 820ms → 240ms 로 줄였습니다. "
    "주장 0 주장 1 주장 2 주장 3 주장 4 주장 5 주장 6 주장 7 주장 8 "
    "질문 없음 질문 있음 주장"
)


def _run(text: str, cover_letter: str = COVER):
    with patch("app.agent.backends.get_summary_backend", return_value=_backend(text)):
        return generate_probes(cover_letter)


_ONE_CLAIM = json.dumps(
    {
        "claims": [
            {
                "claim": "FastAPI로 재작성해 820ms → 240ms",
                "type": "수치",
                "questions": ["820ms 중 어느 구간이 병목이었나요?", "240ms는 어떻게 측정했나요?"],
            }
        ]
    },
    ensure_ascii=False,
)


class TestGenerateProbes:
    def test_주장과_질문을_뽑는다(self):
        claims = _run(_ONE_CLAIM)
        assert len(claims) == 1
        assert claims[0]["type"] == "수치"
        assert len(claims[0]["questions"]) == 2

    def test_코드펜스로_감싸도_읽는다(self):
        """클라우드 모델은 형식 강제가 없어 ```json 을 붙여 오는 일이 있다."""
        assert len(_run(f"```json\n{_ONE_CLAIM}\n```")) == 1

    def test_빈_자소서는_호출하지_않고_빈_리스트(self):
        """백엔드를 부르기 전에 끝난다 — 빈 입력에 토큰을 쓰지 않는다."""
        assert generate_probes("   ") == []

    def test_주장이_없으면_빈_리스트(self):
        """감상만 쓴 자소서. 실패가 아니라 '뽑을 게 없음' 이다."""
        assert _run('{"claims": []}') == []

    def test_파싱_실패는_None(self):
        """빈 리스트와 구분된다 — 화면이 '없음' 과 '못 만듦' 을 갈라 써야 한다."""
        assert _run("모델이 그냥 문장으로 답했다") is None

    def test_백엔드_불가는_None(self):
        with patch(
            "app.agent.backends.get_summary_backend",
            return_value=_backend("", unavailable="ANTHROPIC_API_KEY 미설정"),
        ):
            assert generate_probes("아무 자소서") is None


class TestNormalize:
    def test_주장은_5개까지만(self):
        many = {
            "claims": [
                {"claim": f"주장 {i}", "type": "수치", "questions": ["질문"]} for i in range(9)
            ]
        }
        assert len(_run(json.dumps(many, ensure_ascii=False))) == 5

    def test_질문은_2개까지만(self):
        four = {
            "claims": [
                {"claim": "주장", "type": "기술", "questions": ["q1", "q2", "q3", "q4"]}
            ]
        }
        assert len(_run(json.dumps(four, ensure_ascii=False))[0]["questions"]) == 2

    def test_질문_없는_주장은_버린다(self):
        """면접관에게 줄 것이 없는 행이다."""
        payload = {
            "claims": [
                {"claim": "질문 없음", "type": "수치", "questions": []},
                {"claim": "질문 있음", "type": "수치", "questions": ["왜 그렇게 했나요?"]},
            ]
        }
        claims = _run(json.dumps(payload, ensure_ascii=False))
        assert [c["claim"] for c in claims] == ["질문 있음"]

    def test_모르는_유형은_기타로(self):
        payload = {"claims": [{"claim": "주장", "type": "느낌", "questions": ["질문"]}]}
        assert _run(json.dumps(payload, ensure_ascii=False))[0]["type"] == "기타"


class TestQuoteMustExist:
    """인용은 자소서에서 찾을 수 있어야 한다 — 못 찾으면 대조가 성립하지 않는다."""

    def _one(self, claim: str, cover: str = COVER):
        payload = {"claims": [{"claim": claim, "type": "수치", "questions": ["왜요?"]}]}
        return _run(json.dumps(payload, ensure_ascii=False), cover)

    def test_원문에_없으면_버린다(self):
        """실제로 모델이 '목록이'를 '목lists이'로 깨뜨린 적이 있다."""
        assert self._one("목lists이 멈췄습니다", "데이터가 1만 행을 넘자 목록이 멈췄습니다") == []

    def test_원문에_있으면_남긴다(self):
        assert len(self._one("목록이 멈췄습니다", "데이터가 1만 행을 넘자 목록이 멈췄습니다")) == 1

    def test_줄바꿈이_단어를_갈라도_통과한다(self):
        """PDF 추출은 단어 한가운데서 줄을 바꾼다 — 공백을 지우고 대조한다."""
        cover = "평균 응답이 820ms였고 월말에는 3초를 넘겼습니\n다."
        assert len(self._one("월말에는 3초를 넘겼습니다", cover)) == 1

    def test_끝의_마침표는_눈감아_준다(self):
        """모델이 인용 끝에 마침표를 붙이는 일이 흔하다. 그것까지 버릴 이유는 없다."""
        assert len(self._one("목록이 멈췄습니다.", "데이터가 1만 행을 넘자 목록이 멈췄습니다")) == 1

    def test_굽은_따옴표와_곧은_따옴표를_같게_본다(self):
        """자소서는 굽은 따옴표를 쓰는데 모델이 곧은 것으로 바꿔 오는 일이 있다."""
        cover = "반년 넘게 “가끔 나는 일”로 남아 있었습니다"
        assert len(self._one('"가끔 나는 일"로 남아 있었습니다', cover)) == 1


# ── 이력서까지 본다 (2026-09-09) ──────────────────────────────

RESUME = "[경력]\n카카오에서 결제 API 를 맡았습니다.\n\n[기술]\nKafka, PostgreSQL"
REQUIREMENTS = "대용량 트래픽 경험자를 찾습니다."


def _run3(text: str, cover: str = COVER, resume: str = RESUME):
    sources = {"cover_letter": cover, "resume": resume, "requirements": REQUIREMENTS}
    with patch("app.agent.backends.get_summary_backend", return_value=_backend(text)):
        return generate_probes(sources)


def _claims(*pairs):
    return json.dumps(
        {"claims": [{"claim": c, "type": "역할", "questions": ["가", "나"]} for c in pairs]},
        ensure_ascii=False,
    )


class TestResumeSource:
    """자기소개서만 보던 것을 이력서까지 넓혔다. **인용 보장은 그대로다.**"""

    def test_이력서에서_인용해도_통과한다(self):
        claims = _run3(_claims("카카오에서 결제 API 를 맡았습니다"))
        assert len(claims) == 1
        assert claims[0]["source"] == "이력서"

    def test_자기소개서_인용은_자기소개서로_표시된다(self):
        claims = _run3(_claims("FastAPI로 재작성해 820ms → 240ms"))
        assert claims[0]["source"] == "자기소개서"

    def test_공고_요건은_인용할_수_없다(self):
        """공고는 **회사가 쓴 글**이다. 지원자의 주장이 될 수 없다."""
        assert _run3(_claims("대용량 트래픽 경험자를 찾습니다")) == []

    def test_어느_쪽에도_없는_인용은_버린다(self):
        assert _run3(_claims("지어낸 문장입니다")) == []

    def test_자기소개서가_없어도_이력서만으로_돈다(self):
        claims = _run3(_claims("카카오에서 결제 API 를 맡았습니다"), cover="")
        assert len(claims) == 1

    def test_둘_다_비면_부르지_않고_빈_리스트(self):
        with patch("app.agent.backends.get_summary_backend") as g:
            assert generate_probes({"cover_letter": "", "resume": "", "requirements": REQUIREMENTS}) == []
            g.assert_not_called()

    def test_옛_호출_방식도_그대로_돈다(self):
        """문자열 하나만 넘기던 호출부가 남아 있어도 깨지지 않는다."""
        claims = _run(_ONE_CLAIM)
        assert len(claims) == 1
        assert claims[0]["source"] == "자기소개서"


class TestTruncatedResponse:
    """`max_tokens` 로 잘린 응답 — **완성된 주장만 건져 쓴다.**

    2026-09-12 프로덕션: 이력서가 촘촘한 지원자에서 응답이 상한(당시 1200)에 걸려
    잘렸고, 잘린 JSON 은 파싱이 안 되니 개인화 질문이 통째로 날아가 폴백 3개
    ("성함과 지원하신 직무를…") 로 떨어졌다. **같은 지원자인데 실행마다 갈렸다** —
    세션 63은 10개(개인화), 19분 뒤 세션 64는 3개(폴백). 상한 근처에서는 응답 길이
    편차가 곧 동전 던지기가 된다.

    상한을 올렸고(2400), 그래도 잘리면 건져 쓴다 — 5개 중 3개가 멀쩡하면 그 3개로
    면접을 볼 수 있고, 그게 일반 질문 3개보다 낫다.
    """

    def _cut(self, text: str, tail: int) -> str:
        return text[: len(text) - tail]

    def test_잘린_응답에서_완성된_주장을_건진다(self):
        full = _claims("주장 0", "주장 1", "주장 2")
        got = _run3(self._cut(full, 40))  # 마지막 주장을 도중에 자른다

        assert got is not None, "건질 수 있는데 None 을 냈다 — 폴백으로 떨어진다"
        assert len(got) >= 1
        assert got[0]["claim"] == "주장 0"

    def test_첫_주장도_못_끝냈으면_None(self):
        """진짜로 못 읽은 것은 None 이어야 한다 — 빈 리스트와 구분된다."""
        full = _claims("주장 0")
        assert _run3(self._cut(full, 60)) is None

    def test_인용문_속_중괄호에_속지_않는다(self):
        """중괄호를 세는 방식이면 여기서 깨진다."""
        cover = COVER + " 설정은 {json} 형식입니다"
        full = json.dumps(
            {
                "claims": [
                    {"claim": "설정은 {json} 형식입니다", "type": "기술", "questions": ["가", "나"]},
                    {"claim": "주장 1", "type": "역할", "questions": ["다", "라"]},
                ]
            },
            ensure_ascii=False,
        )
        got = _run3(self._cut(full, 35), cover=cover)

        assert got is not None
        assert got[0]["claim"] == "설정은 {json} 형식입니다"

    def test_멀쩡한_응답은_그대로_간다(self):
        got = _run3(_claims("주장 0", "주장 1"))
        assert got is not None and len(got) == 2

    def test_상한이_충분히_높다(self):
        """상한이 다시 내려가면 같은 사고가 난다."""
        from app.agent.interview_probe import PROBE_MAX_TOKENS

        assert PROBE_MAX_TOKENS >= 2000, "주장 5개 × 질문 2개 + 인용이 들어갈 여유가 필요하다"
