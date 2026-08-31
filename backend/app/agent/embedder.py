"""임베딩 생성·검색 모듈 (ADR-0021).

sentence-transformers 의 ko-sroberta-multitask 로 텍스트를 768차원 벡터로 변환한다.
모델은 첫 호출 시 1회 로드하고 이후 재사용한다. CPU 환경에서도 ~50ms/건.

**이 모듈은 "쓸 수 없으면 조용히 빈 결과" 를 내지 않는다.** 모델·pgvector·임베딩
데이터 중 하나라도 없으면 `EmbeddingUnavailable` 을 던진다 — 호출부(read.py)가
그것을 잡아 키워드 검색으로 내려앉고, 그 사실을 사용자에게 알린다.
빈 리스트로 뭉개면 아르가 "지원자가 없습니다" 라고 단정해 버린다.

백필: `python -m app.agent.embedder` (옵션은 --help)
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
EMBEDDING_DIM = 768

# 임베딩 입력 텍스트의 조합 규칙 버전. model_name 에 함께 적어 두면 "모델은 같은데
# 입력 규칙이 바뀐" 낡은 벡터를 골라낼 수 있다 — backfill 이 자동으로 다시 만든다.
# v1 = 스킬+학력+경력+자소서, v2 = 자소서 제외 (근거는 build_text 주석)
INCLUDE_INTRO = os.getenv("EMBEDDING_INCLUDE_INTRO", "0") == "1"
TEXT_RECIPE = "text-v1" if INCLUDE_INTRO else "text-v2"


def model_tag() -> str:
    """벡터를 만든 조건. 모델과 입력 규칙을 함께 적는다."""
    return f"{DEFAULT_MODEL}/{TEXT_RECIPE}"


# ── 유사도 임계값 ───────────────────────────────────────────────────
# normalize_embeddings=True 라 코사인 거리 = 1 - 유사도.
#
# **절대 임계값 하나로는 안 된다**는 것이 두 번의 독립 실측에서 같이 나왔다.
# 더미 15건(2026-08-31) — 거리 0.7 상한을 12~15명이 그냥 통과했다.
# 합성 6건(2026-08-31, 이 모듈 작성 중) — 자소서를 뺀 build_text 기준:
#   "Python 경험자 찾아줘" → 파이썬 0.38·0.47 / 자바 0.60 / 프론트 0.60 / 요리사 0.84
#   "요리사"              → 요리사 0.44 / 나머지 0.64~0.70
#   "클라우드 인프라 경험"  → 인프라 0.55 / 나머지 IT 0.66~0.72 / 요리사 0.81
# 정답과 오답의 거리 차가 0.1~0.2 뿐이고, **1등의 절대값 자체가 질의마다
# 0.38~0.66 으로 흔들린다.** 고정 상한이 필터 노릇을 못 하는 이유가 이것이다.
#
# 그래서 두 겹으로 자른다.
#   1) 절대 상한 — 명백히 무관한 꼬리를 자른다 (요리사 0.84 류). 10만 건에서 필수.
#   2) 상대 창 — 1등과의 거리 차가 이보다 크면 버린다. 흔들리는 기준선을 흡수한다.
#      실제로 거르는 일은 대부분 이쪽이 한다.
# 창을 0.20 → 0.15 로 좁히면 위 실측에서 "Python 경험" 3명→2명(프론트 탈락),
# "요리사" 2명→1명으로 정확해지고 잃는 정답은 없었다.
#
# 코퍼스가 작으니 더미 지원서 전량으로 재측정이 필요하다. 둘 다 환경변수다.
MAX_DISTANCE = float(os.getenv("SEMANTIC_MAX_DISTANCE", "0.70"))
RELATIVE_WINDOW = float(os.getenv("SEMANTIC_RELATIVE_WINDOW", "0.15"))

_model: SentenceTransformer | None = None


class EmbeddingUnavailable(RuntimeError):
    """임베딩을 쓸 수 없는 상태. 이유(reason)를 사용자에게 그대로 전달한다."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # 패키지 미설치 환경 (경량 컨테이너·초기 배포)
            raise EmbeddingUnavailable(
                "임베딩 모델 패키지(sentence-transformers)가 설치되지 않았습니다"
            ) from exc

        logger.info("임베딩 모델 로딩: %s", DEFAULT_MODEL)
        try:
            _model = SentenceTransformer(DEFAULT_MODEL)
        except Exception as exc:  # 모델 다운로드 실패·오프라인
            raise EmbeddingUnavailable(
                f"임베딩 모델({DEFAULT_MODEL})을 불러오지 못했습니다"
            ) from exc
    return _model


def _embedding_table():
    """ApplicationEmbedding 모델. pgvector 가 없으면 존재하지 않는다."""
    try:
        from app.models import ApplicationEmbedding
    except ImportError as exc:
        raise EmbeddingUnavailable(
            "pgvector 확장이 없어 시맨틱 검색이 꺼져 있습니다"
        ) from exc
    return ApplicationEmbedding


def encode(text: str) -> list[float]:
    """텍스트를 벡터로 변환한다."""
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def encode_many(texts: list[str]) -> list[list[float]]:
    """여러 텍스트를 한 번에 변환한다. 백필에서 배치로 쓴다."""
    model = _get_model()
    vecs = model.encode(texts, normalize_embeddings=True)
    return [list(v) for v in vecs]


def build_text(application) -> str:
    """Application 객체에서 임베딩 입력 텍스트를 조합한다.

    **자기소개서를 넣지 않는다.** ADR-0021 은 "self_intro 전체 + skills" 로 적었지만,
    실측 결과 자소서를 넣으면 순위가 오히려 망가진다 (보고서의 ADR 차이 항목):

    - 이 모델의 `max_seq_length` 는 **128 토큰**이다. 스킬·학력·경력은 35토큰인데
      자소서를 붙이면 245~550토큰이 되어 **절반~4분의 3이 잘린다.**
    - 잘리고 남는 것은 자소서 앞부분, 즉 "저는 ~한 개발자입니다" 류의 상투구다.
      이 상투구는 지원자마다 거의 같아서 벡터를 서로 닮게 만든다 — 무관한 사람이
      위로 올라오는 원인이다. 더미 15명 실측에서 "Python 경험자" 상위 5명에
      React·Java 개발자가 끼고 정작 적합자가 10위로 밀렸다.
    - 스킬·학력·경력만 넣으면 같은 질의에서 상위 5명이 전원 정답이었다.

    자소서 내용이 검색에서 통째로 사라지는 것은 아니다 — 하이브리드 검색의
    키워드 쪽(`read.py: _keyword_filter`)이 self_intro 를 그대로 훑는다.

    되돌리려면 EMBEDDING_INCLUDE_INTRO=1. 재측정 없이 기본값을 바꾸지 않는다.
    """
    parts = []
    if application.skills:
        parts.append("스킬: " + ", ".join(application.skills))
    if application.education:
        parts.append("학력: " + application.education)
    if application.career_years is not None:
        parts.append(f"경력: {application.career_years}년")
    if INCLUDE_INTRO and application.self_intro:
        parts.append(application.self_intro)
    return "\n".join(parts)


def _upsert(db: Session, application_id: int, vec: list[float]) -> None:
    ApplicationEmbedding = _embedding_table()
    existing = db.scalar(
        select(ApplicationEmbedding).where(
            ApplicationEmbedding.application_id == application_id
        )
    )
    if existing:
        existing.embedding = vec
        existing.model_name = model_tag()
    else:
        db.add(
            ApplicationEmbedding(
                application_id=application_id,
                embedding=vec,
                model_name=model_tag(),
            )
        )


def embed_application(db: Session, application_id: int) -> None:
    """지원서 1건의 임베딩을 생성하고 DB에 저장한다."""
    from app.models import Application

    try:
        _embedding_table()
    except EmbeddingUnavailable as exc:
        logger.warning("임베딩 건너뜀: %s", exc.reason)
        return

    app = db.get(Application, application_id)
    if app is None:
        return

    text = build_text(app)
    if not text.strip():
        return

    _upsert(db, application_id, encode(text))
    db.commit()


def embeddings_exist(db: Session) -> bool:
    """임베딩이 한 건이라도 있는지. 0건과 '검색해도 안 걸림' 을 구분하는 데 쓴다."""
    ApplicationEmbedding = _embedding_table()
    return db.scalar(select(ApplicationEmbedding.id).limit(1)) is not None


def search_similar(
    db: Session,
    query: str,
    limit: int = 20,
    max_distance: float | None = None,
    relative_window: float | None = None,
) -> list[tuple[int, float]]:
    """쿼리와 유사한 (지원서 ID, 코사인 거리) 목록. 가까운 순.

    절대 임계값(max_distance)과 1등 기준 상대 창(relative_window)을 둘 다 적용한다.
    쓸 수 없는 상태면 EmbeddingUnavailable 을 던진다 — 빈 리스트로 뭉개지 않는다.
    """
    ApplicationEmbedding = _embedding_table()
    if not embeddings_exist(db):
        raise EmbeddingUnavailable(
            "아직 생성된 임베딩이 없습니다 (백필: python -m app.agent.embedder)"
        )

    threshold = MAX_DISTANCE if max_distance is None else max_distance
    query_vec = encode(query)
    distance = ApplicationEmbedding.embedding.cosine_distance(query_vec).label(
        "distance"
    )

    # 임계값 필터를 **바깥 쿼리**에 둔다. 같은 쿼리의 WHERE 에 거리 조건을 넣으면
    # 플래너가 HNSW 인덱스 대신 전건 스캔을 고르는 경우가 있다 (pgvector 권장 형태).
    nearest = (
        select(ApplicationEmbedding.application_id, distance)
        .order_by(distance)
        .limit(limit)
        .subquery()
    )
    rows = db.execute(
        select(nearest.c.application_id, nearest.c.distance)
        .where(nearest.c.distance <= threshold)
        # 바깥에서 다시 정렬한다 — 서브쿼리의 순서는 보장되는 값이 아니다.
        .order_by(nearest.c.distance)
    ).all()
    hits = [(row[0], float(row[1])) for row in rows]
    if not hits:
        return []

    # 상대 창은 1등이 정해진 뒤에야 계산되므로 SQL 이 아니라 여기서 자른다.
    window = RELATIVE_WINDOW if relative_window is None else relative_window
    cutoff = hits[0][1] + window
    return [(aid, dist) for aid, dist in hits if dist <= cutoff]


# ── 백필 ────────────────────────────────────────────────────────────
# ADR-0021 은 백필을 "별도 스크립트" 로 뒀지만, 임베딩은 에이전트 도메인의 것이라
# 모듈 CLI 로 여기 둔다. 서버 기동 시 자동 실행하지 않는 것(ADR-0011 비용 가드)은
# 그대로다 — 사람이 명령을 쳐야 돈다.


def backfill(
    db: Session,
    batch_size: int = 64,
    limit: int | None = None,
    force: bool = False,
    progress=None,
) -> dict:
    """임베딩이 없는 지원서를 찾아 일괄 생성한다.

    force=True 면 이미 있는 것도 다시 만든다 (모델·입력 텍스트가 바뀌었을 때).
    반환: {"total": 대상 수, "embedded": 생성 수, "skipped": 텍스트가 비어 건너뜀}
    """
    from app.models import Application

    ApplicationEmbedding = _embedding_table()

    stmt = select(Application).order_by(Application.id)
    if not force:
        # 만든 조건(모델 + 입력 규칙)이 지금과 같은 것만 "끝난 것" 으로 친다.
        # 그래야 build_text 규칙을 바꿔도 낚은 벡터가 조용히 남지 않는다.
        done = select(ApplicationEmbedding.application_id).where(
            ApplicationEmbedding.model_name == model_tag()
        )
        stmt = stmt.where(Application.id.notin_(done))
    if limit:
        stmt = stmt.limit(limit)

    targets = db.scalars(stmt).all()
    total = len(targets)
    embedded = 0
    skipped = 0

    for start in range(0, total, batch_size):
        chunk = targets[start : start + batch_size]
        pairs = [(a.id, build_text(a)) for a in chunk]
        usable = [(aid, text) for aid, text in pairs if text.strip()]
        skipped += len(pairs) - len(usable)
        if usable:
            vectors = encode_many([text for _, text in usable])
            for (aid, _), vec in zip(usable, vectors, strict=True):
                _upsert(db, aid, vec)
            embedded += len(usable)
        db.commit()
        if progress:
            progress(min(start + batch_size, total), total)

    return {"total": total, "embedded": embedded, "skipped": skipped}


def pending_count(db: Session) -> int:
    """다시 만들어야 하는 지원서 수 (없거나, 낚은 규칙으로 만든 것)."""
    from app.models import Application

    ApplicationEmbedding = _embedding_table()
    done = select(ApplicationEmbedding.application_id).where(
        ApplicationEmbedding.model_name == model_tag()
    )
    return (
        db.scalar(
            select(func.count(Application.id)).where(Application.id.notin_(done))
        )
        or 0
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.agent.embedder",
        description="지원서 임베딩 백필 (ADR-0021)",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--limit", type=int, default=None, help="이 건수만 처리")
    parser.add_argument(
        "--force", action="store_true", help="이미 임베딩이 있어도 다시 만든다"
    )
    parser.add_argument("--dry-run", action="store_true", help="대상 건수만 센다")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from app.db import SessionLocal

    db = SessionLocal()
    try:
        try:
            _embedding_table()
        except EmbeddingUnavailable as exc:
            print(f"중단: {exc.reason}")
            return 1

        if args.dry_run:
            print(f"임베딩 없는 지원서: {pending_count(db)}건")
            return 0

        def show(done: int, total: int) -> None:
            print(f"  {done}/{total}", flush=True)

        try:
            result = backfill(
                db,
                batch_size=args.batch_size,
                limit=args.limit,
                force=args.force,
                progress=show,
            )
        except EmbeddingUnavailable as exc:
            print(f"중단: {exc.reason}")
            return 1

        print(
            f"완료: 대상 {result['total']}건 · 생성 {result['embedded']}건 "
            f"· 건너뜀 {result['skipped']}건"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
