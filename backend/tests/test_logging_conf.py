"""로깅 설정 — `-m` 진입점의 로그가 사라지지 않는지.

**왜 이 파일이 있나** (2026-09-12): 프로덕션 메일 워커의 `docker logs` 가 0바이트였다.
`python -m app.shared.worker` 로 띄우면 그 모듈의 `__name__` 이 `"__main__"` 이라
`logging.getLogger(__name__)` 이 `app` 트리 **밖**에 놓인다. `setup_logging()` 이
`app` 로거만 설정하던 동안 그 로거의 INFO 는 받을 핸들러가 없어 전부 사라지고,
WARNING 이상만 logging 의 lastResort 핸들러로 평문으로 새어 나왔다.

결과: 워커가 몇 시간 죽어 있어도 `docker ps` 의 "Up" 말고는 볼 신호가 없었다.
같은 형태의 진입점이 하나 더 있다 (`python -m app.agent.embedder`).
"""
from __future__ import annotations

import json
import logging

from app.logging_conf import setup_logging


def _capture(caplog, logger_name: str, level: int = logging.INFO) -> list[logging.LogRecord]:
    with caplog.at_level(level):
        logging.getLogger(logger_name).log(level, "테스트 메시지")
    return list(caplog.records)


class TestSetupLogging:
    def test_main_logger_is_configured(self):
        """`-m` 진입점(`__main__`) 의 INFO 가 핸들러에 닿는다."""
        setup_logging()
        logger = logging.getLogger("__main__")

        # 루트에 핸들러가 있고, __main__ 로거가 그 핸들러까지 전파된다
        assert logging.getLogger().handlers, "루트 핸들러가 없다 — -m 진입점 로그가 사라진다"
        assert logger.isEnabledFor(logging.INFO), "__main__ 로거의 INFO 가 꺼져 있다"

    def test_app_logger_still_configured(self):
        setup_logging()
        assert logging.getLogger("app").isEnabledFor(logging.INFO)

    def test_repeated_setup_does_not_duplicate_handlers(self):
        """부팅 경로가 두 번 불러도 로그가 두 줄로 찍히지 않는다."""
        setup_logging()
        first = len(logging.getLogger().handlers)
        setup_logging()
        assert len(logging.getLogger().handlers) == first == 1

    def test_output_is_json_one_line(self, capsys):
        """포맷은 JSON 한 줄 — 로그 수집이 그걸 전제한다."""
        setup_logging()
        logging.getLogger("__main__").info("모의 워커 시작", extra={"queue": "test"})

        err = capsys.readouterr().err.strip().splitlines()
        assert len(err) == 1, err
        payload = json.loads(err[0])
        assert payload["level"] == "INFO"
        assert payload["message"] == "모의 워커 시작"
        assert payload["queue"] == "test"


class TestEntrypointLoggers:
    def test_m_entrypoints_do_not_rely_on_dunder_name(self):
        """`-m` 으로 띄우는 모듈은 로거 이름을 명시하거나 루트 설정에 의존해야 한다.

        루트를 설정하므로 `__name__` 을 써도 이제는 보인다 — 이 테스트는 진입점
        목록이 늘었을 때 사람이 한 번 보게 하는 표시다.
        """
        import pathlib

        entrypoints = [
            p
            for p in pathlib.Path("app").rglob("*.py")
            if "__pycache__" not in p.parts
            and 'if __name__ == "__main__":' in p.read_text(encoding="utf-8")
        ]
        # 2026-09-12 기준 2개: shared/worker.py · agent/embedder.py
        assert len(entrypoints) <= 2, (
            f"`-m` 진입점이 늘었다: {[p.as_posix() for p in entrypoints]} — "
            "로그가 보이는지 확인하고 이 기대값을 갱신해라"
        )
