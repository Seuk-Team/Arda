"""회귀 하네스 전용 fixture — 실 백엔드에 실호출하는 마커 스위트.

이 폴더의 test 는 `@pytest.mark.regression` 이 붙어 있고, 기본 pytest 실행
(pytest -q) 에서는 **자동으로 제외**된다. 명시적으로 `-m regression` 을 넘겨야
돈다. 이유:

- 실 백엔드(localhost:8000) 에 실호출 → 시나리오 하나당 5~40초
- 로컬 sLLM 이면 더 오래 걸림
- CI 기본 스위트에 끼면 매 PR 마다 몇 분씩 밀림

**돌리는 법**:

    # backend 안에서, arda-pgvector·백엔드 서버 뜬 상태에서
    uv run pytest -m regression backend/tests/prompt_regression -q

**해석**:

- 성공률·응답 시간 비교는 `results/` 아래 JSON 파일에 append 형태로 저장된다
  (git 에 안 올린다 — .gitignore). 이후 라우터·프롬프트 편집 후 재실행하면
  같은 파일에 새 라인이 붙어 diff 로 개선을 볼 수 있다.
- test 자체는 최소한만 assert 한다 — 회귀 하네스는 "이거 되냐" 아니라 "얼마나
  잘 되냐" 를 보는 도구여서, fallback 만 아니면 통과시키고 숫자는 리포트로.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Callable

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """`regression` 마커 등록 + 기본 실행에서 자동 제외.

    pyproject.toml 을 안 건드리고 conftest 에서 처리 — 이 폴더의 관심사이지
    전체 백엔드 test 설정을 바꿀 일이 아니다.
    """
    config.addinivalue_line(
        "markers",
        "regression: 실 백엔드 실호출 회귀 하네스 (기본 스위트 밖, -m regression 으로만)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """`-m regression` 을 명시하지 않으면 이 폴더 test 를 collection 에서 뺀다.

    `-m "not regression"` 을 매번 붙이는 것과 결과는 같지만, 사람이 잊고 그냥
    `pytest` 만 쳐도 회귀 하네스가 안 걸리게 안전판을 하나 더 둔다.
    """
    if config.getoption("-m") and "regression" in config.getoption("-m"):
        return  # 사용자가 -m regression 을 명시했다
    skip_marker = pytest.mark.skip(reason="회귀 하네스는 -m regression 으로만 실행")
    for item in items:
        if "regression" in item.keywords:
            item.add_marker(skip_marker)


# ── 서버·인증 fixture ─────────────────────────────────────────────

DEFAULT_BASE = "http://localhost:8000"
# `ollama-test` 는 역사적 이름 (2026-08 로컬 sLLM 검증 때 만든 관리자 계정) 이지만
# 서버 백엔드(anthropic/ollama) 와 무관한 그냥 로컬 관리자 계정이다. 계정 이름을
# 갈아엎으면 시드·기존 세팅에서 하네스가 로그인 못 하므로 유지한다. 다른 계정으로
# 돌리고 싶으면 `REGRESSION_EMAIL`·`REGRESSION_PASSWORD` env 로 override.
DEFAULT_EMAIL = "ollama-test@example.com"
DEFAULT_PASSWORD = "testpass123"


@pytest.fixture(scope="session")
def base_url() -> str:
    """실 백엔드 주소. env 로 override 가능."""
    return os.environ.get("REGRESSION_BASE_URL", DEFAULT_BASE)


@pytest.fixture(scope="session", autouse=True)
def _guard_anthropic_backend() -> None:
    """Anthropic 백엔드로 뜬 서버에 하네스가 실호출하면 30~55회 API 콜이 나가 과금된다.

    하네스 기본 실행은 **로컬 Ollama 모드 전제**. 판정 규칙:
    - `backend/.env` 의 `AGENT_CHAT_BACKEND` 가 `ollama` → 통과
    - 비어있거나 `anthropic` → skip (환경 변수 `REGRESSION_ALLOW_ANTHROPIC=1` 로 옵트인)

    Anthropic Haiku 로 기준선을 재측정하려면 명시적으로 옵트인해야 한다:
        REGRESSION_ALLOW_ANTHROPIC=1 uv run pytest -m regression tests/prompt_regression -q

    감지 자체가 API 콜을 쓰지 않도록 `.env` 를 직접 읽는다 (서버 프로세스가 이 `.env`
    를 로드했다는 로컬 개발 전제). 다른 방식(1회 프로브)은 anthropic 이면 그것도
    과금되므로 채택하지 않는다.
    """
    if os.environ.get("REGRESSION_ALLOW_ANTHROPIC"):
        return
    env_path = Path(__file__).resolve().parents[2] / ".env"
    backend_value = ""
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == "AGENT_CHAT_BACKEND":
                backend_value = val.strip().strip('"').strip("'").lower()
                break
    if backend_value != "ollama":
        pytest.skip(
            f"하네스 기본은 Ollama — 지금 AGENT_CHAT_BACKEND={backend_value or '<빈 값=anthropic>'}. "
            "Anthropic 로 정말 재고 싶으면 REGRESSION_ALLOW_ANTHROPIC=1 로 재실행."
        )


@pytest.fixture(scope="session")
def admin_token(base_url: str) -> str:
    """검증 계정으로 로그인해 JWT 를 발급받는다.

    ollama-test 계정 (관리자 승격됨) 이 없으면 skip. 계정 세팅은 튜닝 가이드
    5.4 참고.
    """
    email = os.environ.get("REGRESSION_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("REGRESSION_PASSWORD", DEFAULT_PASSWORD)
    payload = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/v1/auth/login",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        pytest.skip(f"회귀 하네스: 로그인 실패 — 계정·백엔드 상태 확인 ({e})")
    token = data.get("access_token")
    if not token:
        pytest.skip(f"회귀 하네스: 로그인 응답에 access_token 없음 ({data})")
    return token


# ── 호출 헬퍼 ────────────────────────────────────────────────────


CallChat = Callable[[str, list[dict]], "tuple[float, dict]"]
CallConfirm = Callable[[str, dict], "tuple[float, dict]"]


@pytest.fixture()
def call_chat(base_url: str, admin_token: str) -> CallChat:
    """(message, history) → (elapsed_sec, response_json).

    실 /api/v1/agent/chat 호출. history 는 리스트 그대로 body 에 실린다.
    """
    def _call(message: str, history: list[dict]) -> tuple[float, dict]:
        payload = json.dumps({"message": message, "history": history}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/v1/agent/chat",
            data=payload,
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.time()
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return time.time() - started, data

    return _call


@pytest.fixture()
def call_confirm(base_url: str, admin_token: str) -> CallConfirm:
    """(tool_name, arguments) → (elapsed_sec, confirm_response).

    실 /api/v1/agent/confirm 호출. 프론트 확인 응답 라우터(레버 ①) 가
    잡은 뒤 실제로 부르는 엔드포인트. LLM 안 거침.
    """
    def _call(tool_name: str, arguments: dict) -> tuple[float, dict]:
        payload = json.dumps({"tool_name": tool_name, "arguments": arguments}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/v1/agent/confirm",
            data=payload,
            headers={
                "Authorization": f"Bearer {admin_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.time()
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return time.time() - started, data

    return _call


# ── 결과 기록 ────────────────────────────────────────────────────


RESULTS_DIR = Path(__file__).parent / "results"


@pytest.fixture(scope="session")
def results_file() -> Path:
    """세션당 하나의 결과 파일. append 로 라인마다 시나리오 결과 저장.

    파일명 = 실행 시작 시각. 커밋 sha 도 붙이면 좋은데, 이 하네스 실행 시점의
    HEAD 를 여기서 subprocess 로 뽑기보다 사용자가 알아서 태그 파일명에
    포함시키는 편이 유연하다 — env `REGRESSION_TAG` 로 받는다.
    """
    RESULTS_DIR.mkdir(exist_ok=True)
    tag = os.environ.get("REGRESSION_TAG", "run")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"{stamp}_{tag}.jsonl"
    path.touch()
    return path


@pytest.fixture()
def record(results_file: Path):
    """시나리오 결과 한 줄 append."""
    def _record(row: dict) -> None:
        with results_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return _record


# ── 데이터 리셋 (반복 실측 위해) ──────────────────────────────

# 시드 16명 이름. 렌더된 답변에 이 밖의 이름이 나오면 "창작" 으로 본다.
SEED_NAMES = frozenset({
    "김도현", "서지호", "문해린", "오태경", "배수아", "한도윤", "임서연", "곽민재",
    "유하람", "노은재", "진예솔", "백지안", "천유진", "구태윤", "남우빈", "홍서우",
})


@pytest.fixture(scope="session")
def reset_stage():
    """지원자 stage 를 직접 SQL 로 되돌린다.

    Step 0 의 3a→4a 는 실제로 change_stage 를 실행해 DB 를 바꾸므로, 실행 전후에
    되돌려야 반복 실측이 같은 조건에서 돈다 (screening→interview 전환이 매번 유효).
    서버가 쓰는 DB (app.db.DATABASE_URL) 에 직접 붙는다.
    """
    import psycopg
    from dotenv import load_dotenv

    # **서버가 쓰는 .env 를 명시적으로 읽는다.** `app.db` 는 env 에 DATABASE_URL 이
    # 없으면 localhost:5432/postgres 기본값으로 떨어지는데, 하네스 프로세스는 .env 를
    # 안 읽으므로 그 기본값 = 엉뚱한 DB 다. 2026-09-02 실측에서 리셋이 그쪽으로 나가
    # 4a 가 422 (interview→interview) 로 깨졌다. 그래서 여기서 직접 .env 를 로드하고,
    # UPDATE 가 실제로 한 행을 바꿨는지·바뀐 값이 맞는지까지 확인한다.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("회귀 하네스: backend/.env 에 DATABASE_URL 이 없어 리셋 대상 DB 를 모른다")
    dsn = url.replace("postgresql+psycopg://", "postgresql://")

    def _reset(application_id: int, stage: str) -> None:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE applications SET current_stage=%s, updated_at=now() WHERE id=%s",
                (stage, application_id),
            )
            assert cur.rowcount == 1, f"리셋 대상 지원자 id={application_id} 가 {dsn} 에 없다"
            conn.commit()
            cur.execute("SELECT current_stage FROM applications WHERE id=%s", (application_id,))
            got = cur.fetchone()[0]
            assert got == stage, f"리셋 후 stage 가 {got} — 기대 {stage}"

    return _reset
