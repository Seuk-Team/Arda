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


def _run(text: str, cover_letter: str = "FastAPI로 재작성해 820ms → 240ms 로 줄였습니다."):
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
