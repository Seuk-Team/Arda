"""서류 주장 ↔ 면접 발언 대조 (AI면접 설계 §5-6 · ADR-0026 결정 3).

여기서 지킬 것은 **인용이 진짜인가** 하나다. 주장은 서류에, 답변은 전사에 그대로
있어야 한다. 없는 문장을 인용하면 면접관은 서류에서 그 대목을 못 찾고, 지원자는
하지도 않은 말로 대조당한다 — 그건 이 기능이 하려는 일의 정반대다.

모델은 부르지 않는다. 프롬프트가 부탁이라면 이쪽은 보증이라, 보증만 시험한다.
"""

from __future__ import annotations

import json

import pytest

from app.agent.interview_findings import (
    KOREAN,
    MAX_FINDINGS,
    _parse_findings,
    enabled_backend,
    generate_findings,
    generate_findings_bg,
    transcript_of,
)

COVER = "응답이 820ms에서 240ms로 줄었습니다. 좋은 개발자가 되고 싶습니다."
RESUME = "[경력] 3년\n[기술] Python, FastAPI\nKafka를 도입해 정산 파이프라인을 재작성했습니다."
SAID = (
    "[질문 1] 응답 속도는 어떻게 줄이셨어요?\n"
    "[답변 1] 외부 API 호출을 비동기로 바꾸고 캐시를 넣었습니다.\n\n"
    "[질문 2] Kafka는 어떻게 쓰셨나요?\n"
    "[답변 2] Kafka는 써 본 적 없습니다."
)


def _raw(*findings) -> str:
    return json.dumps({"findings": list(findings)}, ensure_ascii=False)


def _one(**kw) -> dict:
    base = {
        "claim_source": "self_intro",
        "claim_text": "응답이 820ms에서 240ms로 줄었습니다.",
        "answer_text": "외부 API 호출을 비동기로 바꾸고 캐시를 넣었습니다.",
        "verdict": "consistent",
    }
    return {**base, **kw}


def _parse(*findings):
    return _parse_findings(_raw(*findings), cover=COVER, resume=RESUME, transcript=SAID)


class TestCitations:
    def test_양쪽_다_원문이면_통과한다(self):
        got = _parse(_one())
        assert len(got) == 1
        assert got[0]["verdict"] == "consistent"

    def test_서류에_없는_주장은_버린다(self):
        """모델이 지어낸 주장. 면접관이 서류에서 못 찾으면 대조가 성립하지 않는다."""
        assert _parse(_one(claim_text="응답이 900ms에서 100ms로 줄었습니다.")) == []

    def test_전사에_없는_답변은_버린다(self):
        """**지원자가 하지 않은 말이다.** 이걸 통과시키면 없는 발언으로 대조당한다."""
        assert _parse(_one(answer_text="한 300ms 정도로 줄었어요.")) == []

    def test_공고나_질문_문장은_주장이_아니다(self):
        """질문은 우리가 쓴 글이다 — 지원자의 주장이 될 수 없다."""
        assert _parse(_one(claim_text="응답 속도는 어떻게 줄이셨어요?")) == []

    def test_끝의_마침표까지_같기를_요구하지_않는다(self):
        got = _parse(_one(claim_text="응답이 820ms에서 240ms로 줄었습니다"))
        assert len(got) == 1

    def test_줄바꿈이_섞여도_찾는다(self):
        """PDF 추출 텍스트는 문장 한가운데서 줄이 바뀐다."""
        got = _parse(_one(claim_text="응답이 820ms에서\n240ms로 줄었습니다."))
        assert len(got) == 1


class TestLabels:
    """모델이 인용 앞에 `[답변 2]` 같은 표지를 붙인다 — 전사를 그 형식으로 넘겨
    주니 따라 적는다(exaone 3.5 실측). 표지 때문에 멀쩡한 대조를 버리지 않는다."""

    def test_표지가_붙어도_찾는다(self):
        got = _parse(
            _one(answer_text="[답변 1] 외부 API 호출을 비동기로 바꾸고 캐시를 넣었습니다.")
        )
        assert len(got) == 1

    def test_저장할_때는_표지를_뗀다(self):
        """담당자 화면에 `[답변 1]` 이 보일 이유가 없다."""
        got = _parse(
            _one(answer_text="[답변 1] 외부 API 호출을 비동기로 바꾸고 캐시를 넣었습니다.")
        )
        assert got[0]["answer_text"].startswith("외부 API")

    def test_표지를_떼도_원문이_아니면_버린다(self):
        """표지만 봐주는 것이지 의역을 봐주는 것이 아니다."""
        assert _parse(_one(answer_text="[답변 1] 비동기로 바꿔서 빨라졌어요")) == []


class TestSource:
    def test_어느_서류인지는_원문으로_정한다(self):
        """모델이 자소서 문장을 이력서라고 적어 보내도 원문이 정답이다 —
        틀린 채로 두면 면접관이 엉뚱한 서류를 뒤진다."""
        got = _parse(_one(claim_source="resume"))
        assert got[0]["claim_source"] == "self_intro"

    def test_이력서_문장은_이력서로_붙는다(self):
        got = _parse(
            _one(
                claim_source="self_intro",
                claim_text="Kafka를 도입해 정산 파이프라인을 재작성했습니다.",
                answer_text="Kafka는 써 본 적 없습니다.",
                verdict="inconsistent",
            )
        )
        assert got[0]["claim_source"] == "resume"
        assert got[0]["verdict"] == "inconsistent"


class TestUnverified:
    def test_답변을_지어내지_않는다(self):
        """면접에서 안 다뤄진 주장. **빈 칸이 곧 '이건 못 물어봤다' 는 정보다.**"""
        got = _parse(_one(verdict="unverified", answer_text="아마 이렇게 말했을 겁니다"))
        assert got[0]["answer_text"] == ""

    def test_전사에_없어도_버리지_않는다(self):
        got = _parse(_one(verdict="unverified", answer_text=""))
        assert len(got) == 1


class TestShape:
    def test_모르는_판정은_버린다(self):
        assert _parse(_one(verdict="의심스러움")) == []

    def test_같은_주장을_두_번_내지_않는다(self):
        assert len(_parse(_one(), _one())) == 1

    def test_상한을_넘기지_않는다(self):
        """프롬프트에도 적혀 있지만 여기서 다시 자른다 — 저쪽은 부탁이다."""
        many = [
            _one(claim_text=t, answer_text="")
            for t in ["응답이 820ms에서 240ms로 줄었습니다."] * (MAX_FINDINGS + 5)
        ]
        assert len(_parse(*many)) <= MAX_FINDINGS

    def test_JSON_이_아니면_None(self):
        """빈 리스트와 다르다 — 전자는 '맞춰 볼 게 없었다', 이건 '못 돌렸다'."""
        assert _parse_findings("음... 잘 모르겠습니다", COVER, RESUME, SAID) is None

    def test_코드펜스를_벗겨_읽는다(self):
        raw = "```json\n" + _raw(_one()) + "\n```"
        assert len(_parse_findings(raw, COVER, RESUME, SAID)) == 1


class TestKorean:
    def test_판정마다_화면_문구가_있다(self):
        """빠지면 담당자 화면에 `unverified` 가 영어로 그대로 뜬다."""
        from app.agent.interview_findings import VERDICTS

        assert set(KOREAN) == set(VERDICTS)


class TestTranscriptOf:
    def test_답_안_한_회차는_빼고_센다(self):
        class T:
            def __init__(self, seq, q, a):
                self.seq, self.question, self.transcript = seq, q, a

        text = transcript_of([T(1, "질문1", "답1"), T(2, "질문2", None), T(3, "질문3", "  ")])
        assert "질문1" in text and "질문2" not in text and "질문3" not in text


class TestSwitch:
    """**기본은 꺼짐.** 머지만으로 과금이 시작되면 안 된다."""

    def test_스위치가_비면_모델을_안_부른다(self, monkeypatch):
        monkeypatch.delenv("AGENT_FINDINGS_BACKEND", raising=False)

        def boom(*a, **kw):
            raise AssertionError("꺼져 있는데 모델을 불렀다")

        monkeypatch.setattr("app.agent.backends.build_backend", boom)
        assert generate_findings({"cover_letter": COVER, "resume": RESUME}, SAID) == []

    def test_스위치가_비면_DB_도_안_건드린다(self, monkeypatch):
        """앞서 만들어 둔 대조가 있으면 그대로 남아야 한다."""
        monkeypatch.delenv("AGENT_FINDINGS_BACKEND", raising=False)

        def boom(*a, **kw):
            raise AssertionError("꺼져 있는데 DB 를 열었다")

        monkeypatch.setattr("app.db.SessionLocal", boom)
        generate_findings_bg(1)  # 조용히 끝나야 한다

    def test_켜면_그_백엔드를_쓴다(self, monkeypatch):
        monkeypatch.setenv("AGENT_FINDINGS_BACKEND", "ollama")
        assert type(enabled_backend()).__name__ == "OllamaBackend"


class TestNoBackendCall:
    """**부를 것이 없으면 토큰을 쓰지 않는다.** 스위치가 켜져 있어도 그렇다."""

    @pytest.mark.parametrize(
        "sources,transcript",
        [
            ({"cover_letter": "", "resume": ""}, SAID),
            ({"cover_letter": COVER, "resume": ""}, ""),
            ({"cover_letter": "", "resume": ""}, ""),
        ],
    )
    def test_서류나_답변이_없으면_빈_리스트(self, sources, transcript, monkeypatch):
        monkeypatch.setenv("AGENT_FINDINGS_BACKEND", "ollama")

        def boom(*a, **kw):
            raise AssertionError("모델을 부르면 안 된다")

        monkeypatch.setattr("app.agent.backends.build_backend", boom)
        assert generate_findings(sources, transcript) == []
