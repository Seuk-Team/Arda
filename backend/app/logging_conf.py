import json
import logging
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """JSON 한 줄 로깅 포맷터 — ts, level, request_id, method, path, status, duration_ms."""

    def format(self, record: logging.LogRecord) -> str:
        log_dict = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
        }

        # extra 필드가 있으면 추가 (request_id, method, path, status, duration_ms 등)
        if hasattr(record, "request_id"):
            log_dict["request_id"] = record.request_id
        if hasattr(record, "method"):
            log_dict["method"] = record.method
        if hasattr(record, "path"):
            log_dict["path"] = record.path
        if hasattr(record, "status"):
            log_dict["status"] = record.status
        if hasattr(record, "duration_ms"):
            log_dict["duration_ms"] = record.duration_ms

        # 메인 메시지
        if record.msg:
            log_dict["message"] = record.getMessage()

        # 예외 정보 (스택트레이스)
        if record.exc_info:
            log_dict["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_dict, ensure_ascii=False)


def setup_logging():
    """로깅 설정 — JSON 한 줄 포맷."""
    logger = logging.getLogger("uvicorn.access")
    logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # 비즈니스 로직 로거
    app_logger = logging.getLogger("app")
    app_logger.handlers.clear()
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)

    return app_logger
