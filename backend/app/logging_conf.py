import json
import logging
from datetime import datetime

# LogRecord 가 스스로 채우는 표준 속성. extra 로 넘어온 것만 남기려면 이걸 빼야 한다.
_RESERVED = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "taskName", "thread", "threadName",
})


class JSONFormatter(logging.Formatter):
    """JSON 한 줄 로깅 포맷터 — ts·level + extra 로 넘긴 필드 전부.

    이전에는 request_id·method·path·status·duration_ms 만 화이트리스트로 골라
    담았다. 그래서 토큰·비용처럼 나중에 추가된 extra 필드가 로그에 아예 찍히지
    않았다 (ADR-0011 §3-2 "호출마다 토큰 사용량을 로깅한다" 가 출력 단계에서
    무효화돼 있었다). 이제 표준 속성을 뺀 나머지를 그대로 싣는다.

    **extra 에 개인정보를 넣지 않는다** — 화이트리스트가 사라졌으므로 넘긴 것은
    전부 남는다. 지원자 식별은 application_id 로 한다 (J5).

    **extra 키에 아래 _RESERVED 이름을 쓰지 않는다** — logging 이 makeRecord 에서
    KeyError 를 던진다. 예: `args`, `module`, `name`, `message`.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_dict = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
        }

        # extra 로 넘어온 필드 전부 (request_id, method, path, status,
        # duration_ms, input_tokens, cost_usd, user_id …)
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            log_dict[key] = value

        # 메인 메시지
        if record.msg:
            log_dict["message"] = record.getMessage()

        # 예외 정보 (스택트레이스)
        if record.exc_info:
            log_dict["exception"] = self.formatException(record.exc_info)

        # 직렬화 못 하는 값이 섞여도 로그 한 줄 때문에 요청이 죽으면 안 된다
        return json.dumps(log_dict, ensure_ascii=False, default=str)


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
