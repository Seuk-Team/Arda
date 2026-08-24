# [B1·B2·B3] 채용 공고 CRUD API

> 담당: 팀원3 · 역할 A(도메인 백엔드) · 브랜치: `feat/b2-postings-api`
> **PR 단위**: 이 지시서 전체 = PR 1개

## 배경

공고는 이 시스템에서 **가장 위에 있는 도메인**이다. 지원서가 공고에 붙고, 지원자·평가·메일이 전부 그 아래로 딸려온다. 그래서 백엔드 중 가장 먼저 만든다.

구조가 단순한 CRUD라 **FastAPI + SQLAlchemy로 API를 만드는 방식을 팀에 정착시키는 자리**이기도 하다. 여기서 정한 파일 배치·응답 형태를 이후 API가 전부 따라 쓴다. 그래서 화려하게 만들지 말고 **가장 평범하게** 만든다.

## 선행 조건 — 없으면 중단

아래가 하나라도 아니면 **시작하지 말고 팀 채널에 알린다.** 없는 것을 상상해서 만들지 않는다.

- [ ] [docs/01-erd.md](../01-erd.md)가 **확정 상태**다 (문서 상단이 `초안`이 아니라 `확정 vX.X · 날짜`)
- [ ] `backend/app/main.py`가 있고 FastAPI 앱이 뜬다 — [J0 앱 뼈대](J0-앱-뼈대.md) **PR이 머지돼 있다.** 아직이면 기다린다
- [ ] `backend/pyproject.toml`에 `fastapi`가 들어 있다
- [ ] Postgres가 로컬에 떠 있고 `backend/.env`의 `DATABASE_URL`로 붙는다

## 가장 중요한 규칙 — 스키마를 건드리지 않는다

- **[backend/app/models.py](../../backend/app/models.py)를 수정하지 않는다.** 컬럼이 부족해 보여도 추가하지 않는다. 필요하면 멈추고 팀 채널에 묻는다.
- **인증·권한은 이번 범위가 아니다.** 02-api.md에 `recruiter+`라 적혀 있지만 인증은 팀장 담당이고 아직 없다. **토큰 검사를 흉내 내지 마라.** `created_by`는 지금 `None`으로 두고 `# TODO(A1): 토큰의 사용자로 채운다` 주석만 남긴다.
- **상태값은 직접 쓰지 않는다.** `models.POSTING_STATUSES`(`draft` / `open` / `closed`)를 import 해서 쓴다.
- **B3 지원자 수는 컬럼이 아니라 집계 쿼리다** ([01-erd.md](../01-erd.md) job_postings 비고). 테이블에 컬럼을 추가하지 마라.
- 이번엔 페이지네이션·정렬을 만들지 않는다. 공고는 많아야 수십 건이다.

## 완료 조건

- [ ] `backend/app/schemas/posting.py` — Pydantic 모델 3개: `PostingCreate` · `PostingUpdate` · `PostingOut`
- [ ] `backend/app/api/postings.py` — 라우터 1개, 엔드포인트 5개
- [ ] `backend/app/main.py`에 **`include_router` 한 줄만** 추가 (이 파일에서 그 외는 건드리지 않는다)

| 메서드 | 경로 | 동작 |
|---|---|---|
| GET | `/api/v1/postings` | 목록 + **각 건의 지원자 수**(B3). 최신순 |
| POST | `/api/v1/postings` | 생성. `status` 기본값 `draft` |
| GET | `/api/v1/postings/{id}` | 상세. 없으면 404 |
| PATCH | `/api/v1/postings/{id}` | 수정 · 상태 변경. 보낸 필드만 바뀐다 |
| DELETE | `/api/v1/postings/{id}` | 삭제. 성공 시 204 |

- [ ] `status`에 `draft`/`open`/`closed` 외의 값이 오면 **422**로 거절한다 (Pydantic이 처리)
- [ ] 없는 id로 GET·PATCH·DELETE 하면 **404**, 본문은 `{"detail": "..."}`
- [ ] `PATCH`에 필드를 하나만 보내도 나머지가 지워지지 않는다 (`exclude_unset=True`)
- [ ] `/docs`(Swagger)에서 5개가 다 보이고 **Try it out으로 실행된다** (J3)
- [ ] [docs/02-api.md](../02-api.md)의 공고 표와 경로·메서드가 정확히 일치한다 (문서를 고치지 말고 코드를 맞춘다)

## 완성 예시

**아래가 이 작업의 정답 형태다. 파일 배치와 응답 형태를 그대로 따른다.**

```python
# backend/app/schemas/posting.py
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import POSTING_STATUSES

PostingStatus = Literal[POSTING_STATUSES]  # ("draft", "open", "closed")


class PostingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: PostingStatus = "draft"


class PostingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: PostingStatus | None = None


class PostingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: str
    created_by: int | None
    created_at: datetime
    updated_at: datetime
    application_count: int = 0  # B3 — 집계 쿼리로 채운다. 컬럼이 아니다
```

```python
# backend/app/api/postings.py
from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Application, JobPosting
from app.schemas.posting import PostingCreate, PostingOut, PostingUpdate

router = APIRouter(prefix="/api/v1/postings", tags=["postings"])


def _get_or_404(db: Session, posting_id: int) -> JobPosting:
    posting = db.get(JobPosting, posting_id)
    if posting is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "공고를 찾을 수 없습니다")
    return posting


@router.get("", response_model=list[PostingOut])
def list_postings(db: Session = Depends(get_db)):
    # B3 지원자 수 — 컬럼을 두지 않고 LEFT JOIN 집계로 낸다
    rows = db.execute(
        select(JobPosting, func.count(Application.id))
        .outerjoin(Application, Application.job_posting_id == JobPosting.id)
        .group_by(JobPosting.id)
        .order_by(JobPosting.created_at.desc())
    ).all()
    return [
        PostingOut.model_validate(p).model_copy(update={"application_count": n})
        for p, n in rows
    ]


@router.post("", response_model=PostingOut, status_code=http.HTTP_201_CREATED)
def create_posting(body: PostingCreate, db: Session = Depends(get_db)):
    posting = JobPosting(**body.model_dump())
    # TODO(A1): created_by 를 토큰의 사용자로 채운다. 인증은 팀장 담당
    db.add(posting)
    db.commit()
    return PostingOut.model_validate(posting)


@router.get("/{posting_id}", response_model=PostingOut)
def get_posting(posting_id: int, db: Session = Depends(get_db)):
    return PostingOut.model_validate(_get_or_404(db, posting_id))


@router.patch("/{posting_id}", response_model=PostingOut)
def update_posting(posting_id: int, body: PostingUpdate, db: Session = Depends(get_db)):
    posting = _get_or_404(db, posting_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(posting, field, value)
    db.commit()
    return PostingOut.model_validate(posting)


@router.delete("/{posting_id}", status_code=http.HTTP_204_NO_CONTENT)
def delete_posting(posting_id: int, db: Session = Depends(get_db)):
    db.delete(_get_or_404(db, posting_id))
    db.commit()
```

`main.py`에는 **이 한 줄만** 더한다.

```python
from app.api.postings import router as postings_router
app.include_router(postings_router)
```

## 참고 문서

- [docs/01-erd.md](../01-erd.md) — `job_postings` 표. 컬럼과 타입의 기준
- [docs/02-api.md](../02-api.md) — "채용 공고 (B)" 표. 경로·메서드의 기준
- [backend/app/models.py](../../backend/app/models.py) — `JobPosting` 클래스, `POSTING_STATUSES` 상수

## Claude에게 시키기

작업 폴더에서 Claude Code를 열고 아래를 **하나씩 순서대로** 붙여넣는다.

```
0단계.
backend/app/models.py, backend/app/db.py, docs/01-erd.md 의 job_postings 표,
docs/02-api.md 의 "채용 공고 (B)" 표를 읽어라.
읽은 뒤, 만들 엔드포인트 5개와 각각의 성공·실패 응답 코드를 표로 보여줘라.
아직 파일을 만들지 마라.

1단계.
backend/app/schemas/posting.py 를 만들어라.
PostingCreate / PostingUpdate / PostingOut 세 개.
status 는 app.models.POSTING_STATUSES 를 그대로 Literal 로 쓴다 — 문자열을 직접 나열하지 마라.
PostingOut 에 application_count: int = 0 을 둔다 (B3, 집계로 채운다).

2단계.
backend/app/api/postings.py 에 라우터를 만들어라. prefix 는 /api/v1/postings.
GET 목록 · POST 생성 · GET 상세 · PATCH 수정 · DELETE 삭제.
목록의 지원자 수는 Application 과 LEFT JOIN 해서 count 로 낸다 — 컬럼을 추가하지 마라.
없는 id 는 404, PATCH 는 exclude_unset=True 로 보낸 필드만 반영한다.
backend/app/models.py 를 수정하지 마라. 인증·권한 코드를 넣지 마라.

3단계.
backend/app/main.py 에 include_router 한 줄만 추가해라. 그 파일의 다른 부분은 건드리지 마라.
```

```
마지막 단계 — 여기서 멈추지 마라.

위 작업을 끝내고 PR 을 올렸으면, 이어서 다음 할 일을 스스로 찾아 그대로 수행해라.

1. docs/weekly/ 의 이번 주 문서를 전부 읽어라.
   W1.md 가 본 계획이고 W1-2 · W1-3 … 번호가 큰 것이 나중에 정해진 것이다. 뒤엣것이 우선한다.
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

**주의**: Claude가 `models.py` 수정, 컬럼 추가, 마이그레이션 생성, 인증 코드 추가, 라이브러리 설치를 제안하면 **수락하지 말고** 팀 채널에 물어본다.

## 검증 방법

```bash
cd backend && uv run uvicorn app.main:app --reload
```

브라우저에서 `http://localhost:8000/docs`를 열고 Try it out으로 확인한다. 또는:

```bash
curl -s -X POST localhost:8000/api/v1/postings -H 'content-type: application/json' -d '{"title":"백엔드 개발자"}'
curl -s localhost:8000/api/v1/postings
curl -s -X PATCH localhost:8000/api/v1/postings/1 -H 'content-type: application/json' -d '{"status":"open"}'
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/v1/postings/99999
curl -s -X POST localhost:8000/api/v1/postings -H 'content-type: application/json' -d '{"title":"x","status":"이상한값"}' -o /dev/null -w '%{http_code}\n'
```

기대 결과:

- 생성 시 **201**, 응답에 `id` · `status: "draft"` · `created_at`이 있다
- 목록에 방금 만든 공고가 있고 **`application_count: 0`**이 함께 온다
- PATCH로 `status`만 보냈는데 **`title`이 그대로 남아 있다**
- 없는 id 조회 → **404**
- 이상한 `status` → **422**
- `/docs`에 5개가 전부 보이고 실행된다
- 서버 로그에 트레이스백이 없다

## 막히면 · 되돌리기

- **30분 넘게 막히면 혼자 붙들지 말고 팀 채널에 묻는다.**
- **결과가 이상해지면 고치려 들지 말고 버린다.**

```bash
git checkout -- .
```

그래도 이상하면 브랜치째 버리고 처음부터 다시 시작한다.

```bash
git checkout main && git branch -D feat/b2-postings-api
```

- **`git status`에 `models.py`나 `docs/`가 떠 있으면 범위를 벗어난 것이다.** 되돌리고 팀 채널에 알린다.

## PR 체크리스트

- [ ] PR 본문에 위 검증 결과를 붙였다 (curl 출력 또는 `/docs` 스크린샷)
- [ ] `models.py` · `docs/` · 다른 사람 파일을 **수정하지 않았다**
- [ ] `main.py` 변경은 `include_router` 한 줄뿐이다
- [ ] 스키마 변경 없음
