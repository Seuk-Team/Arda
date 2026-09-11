import json
import logging
from datetime import UTC, datetime

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
            # `utcnow()` 는 폐기 예정이고 tz 없는 값을 준다. 출력 모양("...Z")은
            # 그대로 두고 tz-aware 로 바꿨다 — 루트 로거까지 설정한 뒤로는 이
            # 포맷터가 모든 로그를 처리해서, 경고가 레코드마다 한 번씩 났다
            # (2026-09-12 전체 테스트에서 경고 381건 증가로 드러났다).
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
    """로깅 설정 — JSON 한 줄 포맷.

    **루트 로거까지 덮는 이유** (2026-09-12): `python -m app.shared.worker` 처럼
    `-m` 으로 띄우면 그 모듈의 `__name__` 이 `"__main__"` 이 된다. 그래서
    `logging.getLogger(__name__)` 로 만든 로거가 `app` 트리 **밖**에 놓이고,
    여기서 `app` 만 설정하면 그 로거의 INFO 는 아무 핸들러도 받지 못해 사라진다.
    WARNING 이상만 logging 의 lastResort 핸들러로 **평문**으로 새어 나온다.

    실제로 프로덕션 메일 워커가 그 상태였다 — `docker logs arda-worker-1` 이
    0바이트였고 (시작 로그·발송 완료 로그 전부 소실), 크래시 트레이스만 보였다.
    그래서 워커가 죽어 있어도 "Up" 외에 볼 신호가 없었다.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    # 루트 — `-m` 진입점(`__main__`)·서드파티 로거까지 같은 JSON 포맷으로 받는다.
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # uvicorn 액세스 로그는 **핸들러를 직접 붙인다** (루트 전파에 맡기지 않는다).
    # uvicorn 이 자기 `dictConfig` 를 우리 설정 뒤에 다시 적용하는 경우가 있어
    # (실측: `--log-level` 을 주고 띄우면 평문 포맷으로 되돌아간다), 전파에만
    # 맡기면 JSON 이던 액세스 로그가 조용히 평문으로 바뀐다. 붙여 두고
    # `propagate=False` 로 두면 포맷이 고정되고 이중 출력도 없다.
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.addHandler(handler)
    access.propagate = False
    access.setLevel(logging.INFO)

    # 비즈니스 로직 로거 — 루트로 전파시켜 한 번만 찍는다.
    app_logger = logging.getLogger("app")
    app_logger.handlers.clear()
    app_logger.propagate = True
    app_logger.setLevel(logging.INFO)

    # 루트를 INFO 로 열면 서드파티 INFO 까지 들어온다. 쓸모보다 양이 많은 것만
    # 눌러 둔다 — 로그 파일은 20MB × 3 으로 돌려쓰기 때문에(compose logging),
    # 소음이 많으면 **정작 필요한 줄이 먼저 밀려 나간다**.
    for noisy in ("botocore", "boto3", "urllib3", "s3transfer", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return app_logger
