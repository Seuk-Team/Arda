"""STT 모듈 테스트 — OpenAI Whisper 를 mock 해서 단위 검증."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from app.agent.stt import _estimate_stt_cost, transcribe


@dataclass
class FakeTranscription:
    text: str = ""
    duration: float = 10.0


class TestTranscribeNoKey:
    """OPENAI_API_KEY 가 없으면 RuntimeError."""

    def test_raises_without_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                transcribe(b"dummy_audio")


class TestTranscribeWithMock:
    """OpenAI 클라이언트를 mock 해서 정상 동작 검증."""

    def _run(self, raw_text: str, filename: str = "audio.webm") -> dict:
        fake_resp = FakeTranscription(text=raw_text)
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = fake_resp

        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch("openai.OpenAI", return_value=mock_client),
        ):
            return transcribe(b"fake_audio_bytes", filename)

    def test_return_keys(self):
        result = self._run("안녕하세요")
        assert "raw" in result
        assert "resolved" in result
        assert "duration_ms" in result
        assert "audio_duration_sec" in result
        assert "cost_usd" in result

    def test_raw_matches_whisper_output(self):
        result = self._run("  김도현 파이썬 이년 경력  ")
        assert result["raw"] == "김도현 파이썬 이년 경력"

    def test_entity_resolution_applied(self):
        result = self._run("파이썬 이년 이상")
        assert "Python" in result["resolved"]
        assert "2년" in result["resolved"]

    def test_tech_term_resolved(self):
        result = self._run("리액트 개발자")
        assert "React" in result["resolved"]

    def test_duration_is_non_negative(self):
        result = self._run("테스트")
        assert result["duration_ms"] >= 0

    def test_custom_filename_passed(self):
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = FakeTranscription(text="ok")

        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch("openai.OpenAI", return_value=mock_client),
        ):
            transcribe(b"audio", filename="recording.wav")

        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["file"] == ("recording.wav", b"audio")

    def test_korean_language_used(self):
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = FakeTranscription(text="ok")

        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch("openai.OpenAI", return_value=mock_client),
        ):
            transcribe(b"audio")

        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["language"] == "ko"

    def test_verbose_json_format(self):
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = FakeTranscription(text="ok")

        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch("openai.OpenAI", return_value=mock_client),
        ):
            transcribe(b"audio")

        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["response_format"] == "verbose_json"

    def test_empty_text(self):
        result = self._run("   ")
        assert result["raw"] == ""
        assert result["resolved"] == ""


class TestSttCost:
    """STT 비용 추정 검증."""

    def test_one_minute(self):
        assert _estimate_stt_cost(60.0) == pytest.approx(0.006)

    def test_ten_seconds(self):
        assert _estimate_stt_cost(10.0) == pytest.approx(0.001)

    def test_zero(self):
        assert _estimate_stt_cost(0.0) == 0.0

    def test_cost_in_result(self):
        fake_resp = FakeTranscription(text="테스트", duration=30.0)
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = fake_resp

        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
            patch("openai.OpenAI", return_value=mock_client),
        ):
            result = transcribe(b"audio")

        assert result["audio_duration_sec"] == 30.0
        assert result["cost_usd"] == pytest.approx(0.003)


class TestTranscribeKeyPresent:
    """키가 있을 때 임포트-레벨 동작."""

    def test_openai_client_created_with_key(self):
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = FakeTranscription(text="ok")

        with (
            patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}),
            patch("openai.OpenAI", return_value=mock_client) as mock_cls,
        ):
            transcribe(b"audio")

        mock_cls.assert_called_once_with(api_key="sk-test123")
