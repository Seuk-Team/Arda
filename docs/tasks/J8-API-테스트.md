# [J8] 주요 API 테스트 코드

> 담당: 팀원4 · 역할 E(인프라·인증) · 브랜치: `feat/j8-api-tests`
> **PR 단위**: 이 지시서 전체 = PR 1개

## 배경

지금은 API 를 고칠 때마다 curl 을 손으로 친다. 4명이 각자 라우터를 붙이는 중이라 **누군가의 변경이 남의 API 를 깨도 아무도 모른다.**

전부 테스트하지 않는다. **깨지면 데모가 멈추는 경로**만 덮는다 — 공고 CRUD · 지원서 제출 · 검색 · 평가 · 단계 변경.

[J4 CI](../weekly/W1-2.md) 가 붙으면 이 테스트가 PR 마다 자동으로 돈다. 그때 가치가 나온다.

## 선행 조건 — 없으면 중단

아래가 하나라도 아니면 **시작하지 말고 팀 채널에 알린다.** 없는 것을 상상해서 만들지 않는다.

- [ ] **API 가 최소 4개 파트 머지돼 있다** — 공고 · 지원자 · 검색 · 평가
- [ ] [J1 Docker compose](J1-docker-compose.md) PR이 머지돼 있다 — 테스트용 DB 를 컨테이너로 띄운다

## 가장 중요한 규칙

- **[backend/app/models.py](../../backend/app/models.py)를 수정하지 않는다.** 컬럼이 부족해 보여도 추가하지 않는다. 멈추고 팀 채널에 묻는다.
- **[docs/01-erd.md](../01-erd.md)·[docs/02-api.md](../02-api.md)를 수정하지 않는다.** 공용 문서다.
- **인증·권한 코드를 넣지 않는다.** 인증은 팀장 담당(A1~A3)이고 아직 없다. 토큰 검사를 흉내 내면 나중에 팀장 것과 충돌한다. 사용자 id 가 필요한 자리는 `# TODO(A1): 토큰의 사용자로 채운다` 주석만 남긴다.
- **`main.py` 는 `include_router` 한 줄만** 건드린다. 그 파일의 다른 부분은 손대지 않는다.
- **테스트를 통과시키려고 프로덕션 코드를 고치지 않는다.** 실패하면 실패한 대로 PR 에 적는다 ([CLAUDE.md](../../CLAUDE.md) 규칙).
- **개발 DB 를 쓰지 않는다.** 테스트가 남의 데이터를 지우면 안 된다. 별도 DB 를 만들고 매번 초기화한다.
- **`backend/tests/` 밖의 파일을 고치지 않는다.** 단 `pyproject.toml` 에 테스트 의존성 추가는 허용.
- **시간·랜덤에 의존하는 단언을 쓰지 않는다.** 오늘 통과하고 내일 깨진다.

## 완료 조건

- [ ] `uv add --dev pytest httpx`
- [ ] `backend/tests/conftest.py` — 테스트 DB 픽스처. **매 테스트마다 초기화**
- [ ] `backend/tests/test_postings.py` — 공고 CRUD 5개 + 이상한 status 422
- [ ] `backend/tests/test_applications.py` — 지원서 제출 201 · 중복 409 · 미동의 422 · 상세 404
- [ ] `backend/tests/test_search.py` — q 검색 · stage 필터 · limit 초과 422
- [ ] `backend/tests/test_evaluations.py` — 작성 201 · 평균 계산 · 범위 밖 422 · **평가 없을 때 avg 가 null**
- [ ] `pyproject.toml` 에 pytest 설정 (`testpaths` · `DATABASE_URL` 오버라이드)
- [ ] **전체 실행 30초 이내**
- [ ] `uv run pytest` 한 줄로 전부 돈다

## 완성 예시

**이 형태를 그대로 따른다.**

```python
# backend/tests/conftest.py
import os

import pytest
from fastapi.testclient import TestClient

# 개발 DB 를 건드리면 남의 작업 데이터가 날아간다. 반드시 별도 DB 를 쓴다
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/arda_test"
)

from app.db import Base, engine          # noqa: E402 — DATABASE_URL 설정 뒤에 import
from app.main import app                 # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    # 테스트 사이에 데이터가 남으면 실행 순서에 따라 결과가 달라진다
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
```

```python
# backend/tests/test_evaluations.py
def test_평가가_없으면_평균은_null이다(client):
    app_id = _make_application(client)
    r = client.get(f"/api/v1/applications/{app_id}/evaluations")
    assert r.status_code == 200
    # 0 이면 "0점을 받았다"로 읽힌다. 이 구분이 화면 표시를 바꾼다
    assert r.json()["avg_score"] is None


def test_평균은_소수_첫째자리까지(client):
    app_id = _make_application(client)
    for score in (4, 5):
        client.post(f"/api/v1/applications/{app_id}/evaluations", json={"score": score})
    assert client.get(f"/api/v1/applications/{app_id}/evaluations").json()["avg_score"] == 4.5
```

## 참고 문서

- [docs/02-api.md](../02-api.md) — 덮을 엔드포인트 목록
- [J1 Docker compose](J1-docker-compose.md) — 테스트 DB 를 띄우는 방법
- [CLAUDE.md](../../CLAUDE.md) — 테스트를 우회하지 않는다는 규칙

## Claude에게 시키기

작업 폴더에서 Claude Code를 열고 **아래를 순서대로 하나씩** 붙여넣는다.

```
0단계.
backend/app/api/ 아래 라우터 전부와 docs/02-api.md 를 읽어라.

읽은 뒤 아래를 알려줘라. 아직 파일을 만들지 마라.
- 지금 머지돼 있는 엔드포인트 목록
- 그중 깨지면 데모가 멈추는 경로 5개와 그 이유
```

```
1단계.
backend 에서 uv add --dev pytest httpx 를 실행해라.
backend/tests/conftest.py 를 만들어라.
개발 DB 를 쓰지 마라 — TEST_DATABASE_URL 또는 arda_test 를 쓴다. 왜인지 주석으로 적어라.
매 테스트마다 drop_all/create_all 로 초기화하는 autouse 픽스처를 둔다.
```

```
2단계.
test_postings.py 와 test_applications.py 를 만들어라.
공고 CRUD 5개와 이상한 status 422.
지원서 제출 201, 중복 409, 미동의 422, 없는 지원자 상세 404.
테스트 함수 이름은 무엇을 검증하는지 한국어로 읽히게 지어라.
```

```
3단계.
test_search.py 와 test_evaluations.py 를 만들어라.
검색은 q 부분일치, stage 필터, limit 초과 422.
평가는 작성 201, 평균 소수 첫째자리, 범위 밖 422, 평가 없을 때 avg_score 가 null.
시간이나 랜덤에 의존하는 단언을 쓰지 마라.
```

```
4단계.
uv run pytest 를 실행해 전체 결과를 보여줘라.
실패가 있으면 프로덕션 코드를 고치지 말고, 무엇이 왜 실패했는지 그대로 보고해라.
```

```
마지막 단계 — 여기서 멈추지 마라.

위 작업을 끝내고 PR 을 올렸으면, 이어서 다음 할 일을 스스로 찾아 그대로 수행해라.

1. docs/weekly/ 의 이번 주 문서를 전부 읽어라. 번호가 큰 것이 나중에 정해진 것이고 뒤엣것이 우선한다.
2. 거기서 내 다음 작업을 찾아라. 없으면 docs/tasks/J7-더미데이터-생성기.md 의 파트 A 에서
   backend/scripts/seed/ 에 아직 없는 배치를 가져가라.
3. 찾은 작업의 지시서를 docs/tasks/ 에서 열고, 선행 조건을 먼저 확인해라.
   선행 조건이 안 채워졌으면 거기서 멈추고 무엇이 막혔는지 알려줘라.
4. 선행 조건이 채워졌으면 새 브랜치를 만들고 그 지시서의 "Claude에게 시키기" 를
   0단계부터 순서대로 수행해라. 지시서 하나 = PR 하나다.
5. 그 작업도 끝나면 1번으로 돌아가 반복해라.

지키는 것:
- 지시서가 있는 작업만 한다. docs/tasks/ 에 지시서가 없으면 "지시서 없음" 이라고 말하고 멈춘다.
- 지시서에 적힌 산출 파일 밖을 고치지 않는다. 다른 사람 파일과 공용 파일은 건드리지 않는다.
  (공용: frontend/mockups/mockup.html · docs/01-erd.md · docs/02-api.md · backend/app/models.py)
- 작업 사이마다 git status 를 확인해서 지시서에 없는 파일이 있으면 되돌린다.
```

## 검증 방법

```bash
cd backend
psql "$DATABASE_URL" -c "create database arda_test" 2>/dev/null || true
uv run pytest -q
uv run pytest --durations=5
git status --short
```

기대 결과:

- `uv run pytest` 한 줄로 전부 돈다
- 전체 실행이 **30초 이내**
- **두 번 연속 실행해도 같은 결과** (테스트 사이 데이터가 안 남는다)
- `arda_test` 만 쓰이고 **개발 DB 의 데이터가 그대로다**
- 실패가 있으면 PR 본문에 **실패한 채로** 적혀 있다
- `git status` 에 `backend/tests/` 와 `pyproject.toml` 외 변경이 없다

## 막히면 · 되돌리기

- **30분 넘게 막히면 혼자 붙들지 말고 팀 채널에 묻는다.**
- **결과가 이상해지면 고치려 들지 말고 버린다.**

```bash
git checkout -- .
```

그래도 이상하면 브랜치째 버리고 처음부터 다시 시작한다.

```bash
git checkout main && git branch -D feat/j8-api-tests
```

- **`git status`에 `models.py` · `docs/` · 다른 사람 파일이 떠 있으면 범위를 벗어난 것이다.** 되돌리고 팀 채널에 알린다.

## PR 체크리스트

- [ ] PR 본문에 위 검증 결과를 붙였다
- [ ] `models.py` · `docs/` · 다른 사람 파일을 **수정하지 않았다**
- [ ] 스키마 변경 없음
