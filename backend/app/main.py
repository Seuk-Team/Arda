"""Arda ATS API — 앱 진입점.

라우터는 각 기능 지시서에서 include_router 한 줄로 등록한다.
여기에 비즈니스 로직을 두지 않는다.
"""

#파이썬 기본 도구
import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

#.env
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

#FastAPI
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

#프로젝트 내부모듈
from app import mail
from app import models  # noqa: F401 — 테이블을 메타데이터에 등록하려면 import 가 필요하다
from app.db import Base, engine, pgvector_ready
from app.errors import ErrorCode, ErrorResponse
from app.logging_conf import setup_logging
from app.security import APP_ENV

logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 스키마가 굳기 전까지는 마이그레이션 없이 create_all 로 만든다 (app/db.py 참고)
    # 임베딩 테이블은 vector 타입을 쓰므로 확장이 없는 서버에서는 건너뛴다 —
    # 안 그러면 CREATE TABLE 이 실패해 나머지 테이블까지 못 만든다.
    tables = list(Base.metadata.sorted_tables)
    if not pgvector_ready():
        tables = [t for t in tables if t.name != "application_embeddings"]
    Base.metadata.create_all(engine, tables=tables)

    # APP_ENV 하나가 보안 게이트 두 개(공개 가입 차단·JWT_SECRET 필수)를 함께 켜고 끈다.
    # 기본값이 dev 라 서버에서 빠뜨리면 아무 에러 없이 꺼진 채로 뜬다 (#122).
    # 어느 모드로 떴는지 기동 로그에 남겨, 배포 후 로그만 봐도 알 수 있게 한다.
    if APP_ENV == "production":
        logger.info("startup: APP_ENV=production — 보안 게이트 켜짐")
    else:
        logger.warning(
            f"startup: APP_ENV={APP_ENV} — 보안 게이트 꺼짐. 공개 가입이 열려 있고 "
            "기본 JWT 시크릿으로 서명한다. 로컬이 아니면 APP_ENV=production 을 설정해야 한다"
        )

    # G2 — SQS 클라이언트 예열. 별도 스레드로 돌려 부팅을 막지 않는다
    # (--reload 개발 중에는 저장할 때마다 재기동한다). 이유는 mail.warm_up 참고.
    threading.Thread(target=mail.warm_up, daemon=True).start()

    yield


app = FastAPI(title="Arda ATS API", version="0.1.0", lifespan=lifespan)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """요청마다 request_id를 부여하고 로그에 남긴다."""

    async def dispatch(self, request: Request, call_next):
        # 클라이언트가 보낸 X-Request-ID가 있으면 쓰고, 없으면 생성
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 1)

        response.headers["X-Request-ID"] = request_id

        # 요청 로그
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        return response


app.add_middleware(RequestContextMiddleware)

if APP_ENV != "production":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


if APP_ENV != "production":
    _chat_test_path = Path(__file__).resolve().parent.parent / "chat_test.html"

    @app.get("/chat-test", response_class=HTMLResponse, include_in_schema=False)
    def chat_test():
        return _chat_test_path.read_text(encoding="utf-8")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 예외 — 상태 코드에 따라 에러 코드를 매핑."""
    request_id = getattr(request.state, "request_id", "unknown")

    # 상태 코드별 에러 코드 매핑
    code_map = {
        400: ErrorCode.VALIDATION_FAILED,
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
        410: ErrorCode.GONE,  # B4 마감 — 안 넣으면 INTERNAL 로 나간다
        413: ErrorCode.VALIDATION_FAILED,  # 파일 용량 초과 (F3)
        422: ErrorCode.VALIDATION_FAILED,
    }
    error_code = code_map.get(exc.status_code, ErrorCode.INTERNAL)

    logger.warning(
        f"http_exception_{error_code}",
        extra={
            "request_id": request_id,
            "status": exc.status_code,
            "error_code": error_code,
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": error_code,
            "message": exc.detail,
            "request_id": request_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """입력 검증 실패 — 422."""
    request_id = getattr(request.state, "request_id", "unknown")

    logger.warning(
        "validation_error",
        extra={
            "request_id": request_id,
            "status": 422,
        },
    )

    return JSONResponse(
        status_code=422,
        content={
            "code": ErrorCode.VALIDATION_FAILED,
            "message": "입력 형식이 잘못되었습니다",
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """처리되지 않은 예외 — 500. 스택트레이스는 로그에만 남긴다."""
    request_id = getattr(request.state, "request_id", "unknown")

    logger.exception(
        "unhandled_exception",
        extra={
            "request_id": request_id,
            "status": 500,
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "code": ErrorCode.INTERNAL,
            "message": "서버 오류가 발생했습니다",
            "request_id": request_id,
        },
    )


# 라우터는 여기에 한 줄씩 추가한다. 각 라우터가 자기 prefix 를 갖는다.
from app.api.applications import router as applications_router  # noqa: E402
from app.api.assignments import router as assignments_router  # noqa: E402
from app.api.auth import router as auth_router  # noqa: E402
from app.api.availability import router as availability_router  # noqa: E402
from app.api.evaluations import router as evaluations_router  # noqa: E402
from app.api.files import router as files_router  # noqa: E402
from app.api.notes import router as notes_router  # noqa: E402
from app.api.postings import router as postings_router  # noqa: E402
from app.api.public import router as public_router  # noqa: E402
from app.api.schedules import router as schedules_router  # noqa: E402
from app.api.agent import router as agent_router  # noqa: E402
from app.api.search import router as search_router  # noqa: E402

app.include_router(agent_router)
app.include_router(applications_router)
app.include_router(assignments_router)
app.include_router(auth_router)
app.include_router(availability_router)
app.include_router(evaluations_router)
app.include_router(files_router)
app.include_router(notes_router)
app.include_router(postings_router)
app.include_router(public_router)
app.include_router(schedules_router)
app.include_router(search_router)
