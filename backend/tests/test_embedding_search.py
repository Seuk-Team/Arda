"""시맨틱 검색 테스트 (ADR-0021).

DB·임베딩 모델 없이 도는 테스트다. 벡터 검색은 가짜로 바꿔 끼우고, 검증하는 것은
**검색이 어떻게 조합되고 실패했을 때 무엇을 알리는가** 다.

핵심은 마지막 클래스다: 벡터 검색이 죽어도 "지원자가 없습니다" 로 끝나면 안 된다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.agent import embedder
from app.agent.embedder import EmbeddingUnavailable
from app.agent.tools import execute_tool
from app.agent.tools import read as read_tools


class FakeApplication:
    """DB 없이 쓰는 지원자 스텁. _app_to_dict 가 읽는 속성만 갖는다."""

    def __init__(
        self,
        id: int,
        name: str = "홍길동",
        email: str = "a@b.c",
        skills=None,
        self_intro: str = "",
        education: str = "",
        career_years: int | None = 3,
        current_stage: str = "applied",
        job_posting_id: int = 1,
    ):
        self.id = id
        self.name = name
        self.email = email
        self.skills = skills or []
        self.self_intro = self_intro
        self.education = education
        self.career_years = career_years
        self.current_stage = current_stage
        self.job_posting_id = job_posting_id
        self.created_at = datetime(2026, 8, 31, tzinfo=UTC)


def fake_db(apps: list[FakeApplication]) -> MagicMock:
    db = MagicMock()
    db.scalars.return_value.all.return_value = apps
    return db


class TestKeywordExtraction:
    """벡터가 없어도 'Python 경험자' 가 걸리려면 여기서 Python 이 나와야 한다."""

    def test_영문_기술어를_뽑는다(self):
        assert read_tools._keywords("Python 경험자 찾아줘") == ["Python"]

    def test_한글_명사를_뽑는다(self):
        assert read_tools._keywords("클라우드 인프라 경험 있는 사람") == [
            "클라우드",
            "인프라",
        ]

    def test_상투어는_버린다(self):
        # 이것들이 남으면 자기소개서 전건이 걸려 검색이 무의미해진다.
        assert read_tools._keywords("경험 있는 사람 찾아줘") == []

    def test_점_포함_기술어를_통째로_본다(self):
        assert "Node.js" in read_tools._keywords("Node.js 다루는 개발자")

    def test_중복은_한_번만(self):
        assert read_tools._keywords("Python python PYTHON") == ["Python"]

    def test_한_글자는_버린다(self):
        assert read_tools._keywords("C 언어") == ["언어"]


class TestKeywordHits:
    def test_스킬_배열에서_찾는다(self):
        app = FakeApplication(1, skills=["Python", "AWS"])
        assert read_tools._keyword_hits(app, ["Python"]) == 1

    def test_자기소개서에서_찾는다(self):
        app = FakeApplication(1, self_intro="파이썬과 Django 로 서비스를 만들었습니다")
        assert read_tools._keyword_hits(app, ["Django"]) == 1

    def test_여러_키워드_적중을_센다(self):
        app = FakeApplication(1, skills=["Python", "AWS"], self_intro="Kubernetes 운영")
        assert read_tools._keyword_hits(app, ["Python", "AWS", "Kubernetes"]) == 3

    def test_대소문자를_가리지_않는다(self):
        app = FakeApplication(1, skills=["python"])
        assert read_tools._keyword_hits(app, ["Python"]) == 1


class TestLexicalPayload:
    def test_결과가_있으면_note_없이_돌려준다(self):
        payload = read_tools._lexical_payload([{"id": 1}], limit=50, q="김")
        assert payload["count"] == 1
        assert payload["search_mode"] == "lexical"
        assert "note" not in payload

    def test_limit_에_걸리면_잘렸다고_알린다(self):
        payload = read_tools._lexical_payload([{"id": 1}], limit=1, q=None)
        assert "잘렸" in payload["note"]

    def test_0건이면_semantic_을_권한다(self):
        payload = read_tools._lexical_payload([], limit=50, q="파이썬")
        assert "semantic" in payload["note"]


class TestSemanticMerge:
    """ADR-0021 의 '결과 병합' — 벡터와 키워드를 합치고 중복을 제거한다."""

    def test_스킬_exact_match_가_최상위(self, monkeypatch):
        """직무 어휘는 skills exact match 가 semantic 만인 결과를 이긴다.

        2026-09-02 실측: "Kubernetes 경험" 질의에 벡터가 React 개발자를 상위에
        올리고 정작 skills 에 "Kubernetes" 를 가진 지원자는 뒤로 밀렸다. 이
        정렬은 그 상황을 뒤집는다.
        """
        skill_and_semantic = FakeApplication(1, name="스킬+벡터", skills=["Python"])
        semantic_only = FakeApplication(2, name="벡터만", skills=["Django"])
        skill_only = FakeApplication(3, name="스킬만", skills=["Python"])

        monkeypatch.setattr(
            embedder, "search_similar", lambda *a, **k: [(1, 0.2), (2, 0.3)]
        )
        payload = read_tools._semantic_search(
            fake_db([skill_and_semantic, semantic_only, skill_only]),
            MagicMock(),
            {"semantic": "Python 경험"},
            limit=10,
        )

        # rank 0(스킬+벡터) → rank 0(스킬만) → rank 2(벡터만)
        assert [r["id"] for r in payload["results"]] == [1, 3, 2]
        assert payload["results"][0]["matched_by"] == "skill+semantic"
        assert payload["results"][1]["matched_by"] == "skill_exact"
        assert payload["results"][2]["matched_by"] == "semantic"
        # skill_hits 는 exact 매치가 몇 개인지, keyword_hits 는 substring 몇 개인지
        assert payload["results"][0]["skill_hits"] == 1
        assert payload["search_mode"] == "semantic+keyword"

    def test_스킬_없이_벡터와_키워드만이면_기존_순서(self, monkeypatch):
        """스킬 exact 가 없을 때는 both → semantic → keyword 그대로."""
        both = FakeApplication(1, name="양쪽", skills=["Django"], self_intro="Python 3년")
        vector_only = FakeApplication(2, name="벡터만", skills=["Ruby"])
        keyword_only = FakeApplication(3, name="키워드만", skills=["Java"], self_intro="Python 강의")

        monkeypatch.setattr(
            embedder, "search_similar", lambda *a, **k: [(1, 0.2), (2, 0.3)]
        )
        payload = read_tools._semantic_search(
            fake_db([both, vector_only, keyword_only]),
            MagicMock(),
            {"semantic": "Python 경험"},
            limit=10,
        )

        assert [r["id"] for r in payload["results"]] == [1, 2, 3]
        assert payload["results"][0]["matched_by"] == "both"
        assert payload["results"][1]["matched_by"] == "semantic"
        assert payload["results"][2]["matched_by"] == "keyword"

    def test_kubernetes_는_semantic_top_을_넘어선다(self, monkeypatch):
        """실측 재현: 벡터는 Kubernetes 를 놓치는데, 실제 소유자를 앞으로 올린다."""
        react_dev_top = FakeApplication(
            1, name="React 개발자", skills=["React", "TypeScript"]
        )
        vue_dev = FakeApplication(2, name="Vue 개발자", skills=["Vue", "JavaScript"])
        k8s_dev = FakeApplication(
            3, name="Kubernetes 소유자", skills=["Kubernetes", "Docker", "Go"]
        )

        # 벡터는 프론트 개발자 두 명을 앞에, k8s 소유자는 아예 못 잡음
        monkeypatch.setattr(
            embedder, "search_similar", lambda *a, **k: [(1, 0.35), (2, 0.42)]
        )
        payload = read_tools._semantic_search(
            fake_db([react_dev_top, vue_dev, k8s_dev]),
            MagicMock(),
            {"semantic": "Kubernetes 경험"},
            limit=10,
        )

        # k8s 소유자가 반드시 첫 번째
        assert payload["results"][0]["id"] == 3
        assert payload["results"][0]["matched_by"] == "skill_exact"

    def test_같은_지원자가_두_번_나오지_않는다(self, monkeypatch):
        app = FakeApplication(1, skills=["Python"])
        monkeypatch.setattr(embedder, "search_similar", lambda *a, **k: [(1, 0.2)])
        payload = read_tools._semantic_search(
            fake_db([app]), MagicMock(), {"semantic": "Python"}, limit=10
        )
        assert payload["count"] == 1

    def test_유사도를_결과에_담는다(self, monkeypatch):
        monkeypatch.setattr(embedder, "search_similar", lambda *a, **k: [(1, 0.25)])
        payload = read_tools._semantic_search(
            fake_db([FakeApplication(1)]), MagicMock(), {"semantic": "백엔드"}, limit=10
        )
        assert payload["results"][0]["similarity"] == 0.75

    def test_가까운_순으로_정렬한다(self, monkeypatch):
        monkeypatch.setattr(
            embedder, "search_similar", lambda *a, **k: [(2, 0.1), (1, 0.6)]
        )
        payload = read_tools._semantic_search(
            fake_db([FakeApplication(1), FakeApplication(2)]),
            MagicMock(),
            {"semantic": "백엔드"},
            limit=10,
        )
        assert [r["id"] for r in payload["results"]] == [2, 1]

    def test_limit_을_넘기지_않는다(self, monkeypatch):
        apps = [FakeApplication(i, skills=["Python"]) for i in range(1, 6)]
        monkeypatch.setattr(embedder, "search_similar", lambda *a, **k: [])
        payload = read_tools._semantic_search(
            fake_db(apps), MagicMock(), {"semantic": "Python"}, limit=2
        )
        assert payload["count"] == 2

    def test_어느_쪽에도_안_걸린_행은_버린다(self, monkeypatch):
        """DB 가 돌려준 행이라도 벡터·키워드 근거가 없으면 결과에 넣지 않는다."""
        monkeypatch.setattr(embedder, "search_similar", lambda *a, **k: [(1, 0.2)])
        payload = read_tools._semantic_search(
            fake_db([FakeApplication(1), FakeApplication(99, name="무관")]),
            MagicMock(),
            {"semantic": "Python"},
            limit=10,
        )
        assert [r["id"] for r in payload["results"]] == [1]


class TestSemanticFallback:
    """빈 결과로 조용히 죽지 않는다 — 데모 파괴급 결함의 회귀 방지."""

    def _unavailable(self, reason: str):
        def raise_it(*args, **kwargs):
            raise EmbeddingUnavailable(reason)

        return raise_it

    def test_임베딩이_없으면_키워드로_내려앉는다(self, monkeypatch):
        monkeypatch.setattr(
            embedder, "search_similar", self._unavailable("아직 생성된 임베딩이 없습니다")
        )
        payload = read_tools._semantic_search(
            fake_db([FakeApplication(1, name="김파이", skills=["Python", "AWS"])]),
            MagicMock(),
            {"semantic": "Python 경험자"},
            limit=10,
        )
        # 여기서 0건이 나오면 아르가 "지원자가 없습니다" 라고 답한다.
        assert payload["count"] == 1
        # skills 에 "Python" 이 정확히 있어 skill_exact 로 잡힌다. 벡터가 없어도
        # 정답을 놓치지 않는다는 것이 핵심 — 라벨은 그 결과의 근거를 말할 뿐.
        assert payload["results"][0]["matched_by"] in ("skill_exact", "keyword")
        assert payload["search_mode"] == "keyword_fallback"
        assert "임베딩" in payload["note"]

    def test_pgvector_가_없어도_찾는다(self, monkeypatch):
        monkeypatch.setattr(
            embedder, "search_similar", self._unavailable("pgvector 확장이 없어")
        )
        payload = read_tools._semantic_search(
            fake_db([FakeApplication(1, skills=["Python"])]),
            MagicMock(),
            {"semantic": "Python"},
            limit=10,
        )
        assert payload["count"] == 1
        assert payload["search_mode"] == "keyword_fallback"

    def test_벡터_검색이_터져도_검색_자체는_산다(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("연결 끊김")

        monkeypatch.setattr(embedder, "search_similar", boom)
        payload = read_tools._semantic_search(
            fake_db([FakeApplication(1, skills=["Python"])]),
            MagicMock(),
            {"semantic": "Python"},
            limit=10,
        )
        assert payload["count"] == 1
        assert payload["search_mode"] == "keyword_fallback"
        assert "note" in payload

    def test_벡터_검색이_터지면_트랜잭션을_되돌린다(self, monkeypatch):
        """rollback 이 없으면 폴백 쿼리가 InFailedSqlTransaction 으로 죽어 도구가 500 이 된다.

        pgvector 파이썬 패키지는 깔렸는데 DB 확장이 없는 상태(= 2026-08-31 운영)에서
        application_embeddings SELECT 가 실패하며 PG 트랜잭션이 abort 되는 경로다.
        """

        def boom(*args, **kwargs):
            raise RuntimeError("relation application_embeddings does not exist")

        monkeypatch.setattr(embedder, "search_similar", boom)
        db = fake_db([FakeApplication(1, skills=["Python"])])
        read_tools._semantic_search(db, MagicMock(), {"semantic": "Python"}, limit=10)
        db.rollback.assert_called_once()

    def test_임베딩_불가는_rollback_이_필요없다(self, monkeypatch):
        """EmbeddingUnavailable 은 SQL 실패가 아니다 — 멀쩡한 트랜잭션을 끊지 않는다."""
        monkeypatch.setattr(
            embedder, "search_similar", self._unavailable("임베딩 없음")
        )
        db = fake_db([FakeApplication(1, skills=["Python"])])
        read_tools._semantic_search(db, MagicMock(), {"semantic": "Python"}, limit=10)
        db.rollback.assert_not_called()

    def test_임계값_밖이면_그렇다고_알린다(self, monkeypatch):
        """벡터는 살아 있는데 임계값 안에 아무것도 없는 경우."""
        monkeypatch.setattr(embedder, "search_similar", lambda *a, **k: [])
        payload = read_tools._semantic_search(
            fake_db([FakeApplication(1, skills=["Python"])]),
            MagicMock(),
            {"semantic": "Python"},
            limit=10,
        )
        assert payload["search_mode"] == "keyword_fallback"
        assert "임계값" in payload["note"]

    def test_결과가_0건이어도_이유가_붙는다(self, monkeypatch):
        monkeypatch.setattr(embedder, "search_similar", lambda *a, **k: [])
        payload = read_tools._semantic_search(
            fake_db([]), MagicMock(), {"semantic": "Rust"}, limit=10
        )
        assert payload["count"] == 0
        assert payload["note"]

    def test_키워드를_못_뽑으면_되묻게_한다(self, monkeypatch):
        monkeypatch.setattr(
            embedder, "search_similar", self._unavailable("임베딩 없음")
        )
        payload = read_tools._semantic_search(
            fake_db([]), MagicMock(), {"semantic": "있는 사람 찾아줘"}, limit=10
        )
        assert payload["count"] == 0
        assert "키워드" in payload["note"]


class AbortingSession:
    """PG 트랜잭션 의미를 흉내 내는 가짜 세션.

    문장 하나가 실패하면 트랜잭션이 abort 되고, rollback 전까지 뒤따르는 모든
    쿼리가 InFailedSqlTransaction 으로 죽는다 — 실제 psycopg 동작 그대로다.
    """

    class InFailedSqlTransaction(RuntimeError):
        pass

    def __init__(self, apps):
        self.apps = apps
        self.aborted = False
        self.rollbacks = 0

    def _guard(self):
        if self.aborted:
            raise self.InFailedSqlTransaction(
                "current transaction is aborted, commands ignored until rollback"
            )

    def scalars(self, stmt):
        self._guard()
        result = MagicMock()
        result.all.return_value = self.apps
        return result

    def rollback(self):
        self.rollbacks += 1
        self.aborted = False


class TestAbortedTransactionRecovery:
    """벡터 쿼리가 트랜잭션을 죽인 뒤에도 도구가 답을 내는지 (500 방지)."""

    def test_폴백이_500_이_되지_않는다(self, monkeypatch):
        db = AbortingSession([FakeApplication(1, name="김파이", skills=["Python"])])

        def vector_query_kills_transaction(*args, **kwargs):
            db.aborted = True
            raise RuntimeError("relation application_embeddings does not exist")

        monkeypatch.setattr(embedder, "search_similar", vector_query_kills_transaction)

        result = json.loads(
            execute_tool(
                "search_applications",
                {"semantic": "Python 경험자 찾아줘"},
                db,
                MagicMock(),
            )
        )
        assert db.rollbacks == 1
        assert result["count"] == 1
        assert result["results"][0]["name"] == "김파이"
        assert result["search_mode"] == "keyword_fallback"


class TestSearchApplicationsContract:
    """도구 반환 형태 — 아르가 '검색이 온전했는지' 를 알 수 있어야 한다."""

    def test_semantic_은_dict_를_돌려준다(self, monkeypatch):
        monkeypatch.setattr(embedder, "search_similar", lambda *a, **k: [(1, 0.1)])
        result = read_tools.search_applications(
            fake_db([FakeApplication(1)]), MagicMock(), {"semantic": "백엔드"}
        )
        assert set(result) >= {"results", "count", "search_mode"}

    def test_이름_검색도_같은_형태다(self):
        result = read_tools.search_applications(
            fake_db([FakeApplication(1, name="김도현")]), MagicMock(), {"q": "김"}
        )
        assert set(result) >= {"results", "count", "search_mode"}
        assert result["search_mode"] == "lexical"


class TestEmbedderUnavailable:
    """모듈이 '못 쓴다' 를 빈 리스트가 아니라 예외로 말하는지."""

    def test_모델_패키지가_없으면_예외(self, monkeypatch):
        monkeypatch.setattr(embedder, "_model", None)
        import builtins

        real_import = builtins.__import__

        def no_st(name, *args, **kwargs):
            if name == "sentence_transformers":
                raise ImportError("없음")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_st)
        with pytest.raises(EmbeddingUnavailable):
            embedder._get_model()

    def test_임베딩이_한_건도_없으면_예외(self, monkeypatch):
        monkeypatch.setattr(embedder, "_embedding_table", lambda: MagicMock())
        monkeypatch.setattr(embedder, "embeddings_exist", lambda db: False)
        with pytest.raises(EmbeddingUnavailable) as exc:
            embedder.search_similar(MagicMock(), "Python")
        assert "임베딩" in exc.value.reason

    def test_기본_임계값이_설정돼_있다(self):
        assert 0 < embedder.MAX_DISTANCE <= 2.0
        assert 0 < embedder.RELATIVE_WINDOW <= 1.0


class TestThreshold:
    """절대 임계값 + 1등 기준 상대 창 (실측 근거는 embedder.py 주석)."""

    def _db_returning(self, rows):
        db = MagicMock()
        db.execute.return_value.all.return_value = rows
        return db

    def _patch(self, monkeypatch):
        # 쿼리는 진짜 모델로 세우고, 실행 결과만 목으로 갈아 끼운다.
        pytest.importorskip("pgvector")
        monkeypatch.setattr(embedder, "embeddings_exist", lambda db: True)
        monkeypatch.setattr(embedder, "encode", lambda text: [0.1] * 768)

    def test_1등과_멀리_떨어진_결과는_버린다(self, monkeypatch):
        self._patch(monkeypatch)
        # 0.30 이 1등이면 창은 0.50 까지 — 0.68 은 "같은 업계지만 무관" 자리다.
        db = self._db_returning([(1, 0.30), (2, 0.45), (3, 0.68)])
        hits = embedder.search_similar(db, "Python", relative_window=0.20)
        assert [aid for aid, _ in hits] == [1, 2]

    def test_상대_창을_넓히면_다_남는다(self, monkeypatch):
        self._patch(monkeypatch)
        db = self._db_returning([(1, 0.30), (2, 0.45), (3, 0.68)])
        hits = embedder.search_similar(db, "Python", relative_window=1.0)
        assert len(hits) == 3

    def test_결과가_없으면_빈_리스트(self, monkeypatch):
        self._patch(monkeypatch)
        hits = embedder.search_similar(self._db_returning([]), "Rust")
        assert hits == []

    def test_절대_임계값이_SQL_에_실린다(self, monkeypatch):
        """거리 필터는 서브쿼리 바깥에 있어야 HNSW 인덱스를 탄다."""
        pytest.importorskip("pgvector")
        from sqlalchemy.dialects import postgresql

        monkeypatch.setattr(embedder, "embeddings_exist", lambda db: True)
        monkeypatch.setattr(embedder, "encode", lambda text: [0.1] * 768)

        captured = {}

        def capture(stmt):
            captured["sql"] = str(stmt.compile(dialect=postgresql.dialect()))
            result = MagicMock()
            result.all.return_value = []
            return result

        db = MagicMock()
        db.execute = capture
        embedder.search_similar(db, "Python")

        sql = captured["sql"]
        # ORDER BY + LIMIT 이 안쪽, 거리 필터가 바깥쪽
        assert "<=>" in sql
        inner = sql[sql.index("(SELECT") : sql.index("WHERE")]
        assert "ORDER BY" in inner and "LIMIT" in inner


class TestBuildText:
    def test_스킬과_경력을_담는다(self):
        app = FakeApplication(
            1, skills=["Python", "AWS"], education="서울대", career_years=3
        )
        text = embedder.build_text(app)
        assert "Python" in text and "AWS" in text
        assert "3년" in text
        assert "서울대" in text

    def test_빈_지원서는_빈_문자열(self):
        app = FakeApplication(1, skills=[], education="", career_years=None)
        assert embedder.build_text(app).strip() == ""

    def test_자기소개서는_넣지_않는다(self, monkeypatch):
        """모델 max_seq_length 가 128 이라 자소서를 넣으면 상투구가 벡터를 지배한다.

        더미 15명 실측에서 자소서를 넣은 쪽은 "Python 경험자" 상위 5명에 React·Java
        개발자가 끼었고, 뺀 쪽은 전원 정답이었다. 근거는 build_text 독스트링.
        """
        monkeypatch.setattr(embedder, "INCLUDE_INTRO", False)
        app = FakeApplication(
            1, skills=["Python"], self_intro="저는 성실한 개발자입니다" * 20
        )
        text = embedder.build_text(app)
        assert "성실한" not in text
        assert "Python" in text

    def test_환경변수로_되돌릴_수_있다(self, monkeypatch):
        monkeypatch.setattr(embedder, "INCLUDE_INTRO", True)
        app = FakeApplication(1, skills=["Python"], self_intro="쿠버네티스 운영 경험")
        assert "쿠버네티스" in embedder.build_text(app)

    def test_자소서는_키워드_쪽에서_여전히_검색된다(self, monkeypatch):
        """임베딩에서 빠져도 하이브리드의 키워드 절반이 self_intro 를 훑는다."""
        monkeypatch.setattr(embedder, "search_similar", lambda *a, **k: [])
        app = FakeApplication(1, skills=["Java"], self_intro="Kubernetes 로 배포 자동화")
        payload = read_tools._semantic_search(
            fake_db([app]), MagicMock(), {"semantic": "Kubernetes 경험"}, limit=10
        )
        assert payload["count"] == 1


class TestModelTag:
    """입력 규칙이 바뀌면 낡은 벡터를 골라낼 수 있어야 한다."""

    def test_모델과_입력규칙을_함께_적는다(self):
        tag = embedder.model_tag()
        assert embedder.DEFAULT_MODEL in tag
        assert embedder.TEXT_RECIPE in tag

    def test_자소서_포함_여부가_태그를_가른다(self, monkeypatch):
        monkeypatch.setattr(embedder, "TEXT_RECIPE", "text-v1")
        v1 = embedder.model_tag()
        monkeypatch.setattr(embedder, "TEXT_RECIPE", "text-v2")
        assert v1 != embedder.model_tag()


class TestHnswIndex:
    """ADR-0021 이 확정한 인덱스가 실제로 선언돼 있는지."""

    def test_hnsw_코사인_인덱스가_선언된다(self):
        pytest.importorskip("pgvector")
        from app.models import ApplicationEmbedding

        indexes = [
            arg
            for arg in ApplicationEmbedding.__table_args__
            if getattr(arg, "name", None) == "ix_application_embeddings_hnsw"
        ]
        assert indexes, "HNSW 인덱스 선언이 없다"
        assert indexes[0].dialect_options["postgresql"]["using"] == "hnsw"
        assert (
            indexes[0].dialect_options["postgresql"]["ops"]["embedding"]
            == "vector_cosine_ops"
        )
