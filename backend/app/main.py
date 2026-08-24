"""Arda ATS API — 앱 진입점.

라우터는 각 기능 지시서에서 include_router 한 줄로 등록한다.
여기에 비즈니스 로직을 두지 않는다.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401 — 테이블을 메타데이터에 등록하려면 import 가 필요하다
from app.db import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 스키마가 굳기 전까지는 마이그레이션 없이 create_all 로 만든다 (app/db.py 참고)
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Arda ATS API", version="0.1.0", lifespan=lifespan)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


# 라우터는 여기에 한 줄씩 추가한다. 각 라우터가 자기 prefix 를 갖는다.
# 예: from app.api.postings import router as postings_router
#     app.include_router(postings_router)
