"""임베딩 생성 모듈 (ADR-0021).

sentence-transformers 의 ko-sroberta-multitask 로 텍스트를 768차원 벡터로 변환한다.
모델은 첫 호출 시 1회 로드하고 이후 재사용한다. CPU 환경에서도 ~50ms/건.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
EMBEDDING_DIM = 768

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("임베딩 모델 로딩: %s", DEFAULT_MODEL)
        _model = SentenceTransformer(DEFAULT_MODEL)
    return _model


def encode(text: str) -> list[float]:
    """텍스트를 벡터로 변환한다."""
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def build_text(application) -> str:
    """Application 객체에서 임베딩 입력 텍스트를 조합한다."""
    parts = []
    if application.skills:
        parts.append("스킬: " + ", ".join(application.skills))
    if application.education:
        parts.append("학력: " + application.education)
    if application.career_years is not None:
        parts.append(f"경력: {application.career_years}년")
    if application.self_intro:
        parts.append(application.self_intro)
    return "\n".join(parts)


def embed_application(db: Session, application_id: int) -> None:
    """지원서 1건의 임베딩을 생성하고 DB에 저장한다."""
    from app.models import Application

    try:
        from app.models import ApplicationEmbedding
    except ImportError:
        logger.warning("pgvector 미설치 — 임베딩 건너뜀")
        return

    app = db.get(Application, application_id)
    if app is None:
        return

    text = build_text(app)
    if not text.strip():
        return

    vec = encode(text)

    existing = db.scalar(
        select(ApplicationEmbedding).where(
            ApplicationEmbedding.application_id == application_id
        )
    )
    if existing:
        existing.embedding = vec
        existing.model_name = DEFAULT_MODEL
    else:
        db.add(
            ApplicationEmbedding(
                application_id=application_id,
                embedding=vec,
                model_name=DEFAULT_MODEL,
            )
        )
    db.commit()


def search_similar(db: Session, query: str, limit: int = 20) -> list[int]:
    """쿼리 텍스트와 유사한 지원서 ID 목록을 반환한다."""
    try:
        from app.models import ApplicationEmbedding
    except ImportError:
        return []

    query_vec = encode(query)
    rows = db.execute(
        select(ApplicationEmbedding.application_id)
        .order_by(ApplicationEmbedding.embedding.cosine_distance(query_vec))
        .limit(limit)
    ).all()
    return [r[0] for r in rows]
