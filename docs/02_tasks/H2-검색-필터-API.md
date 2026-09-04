# [H1·H2] 지원자 검색 · 필터 API

> 담당: 팀원2 · 역할 B(검색·데이터) · 브랜치: `feat/h2-search-api`
> **PR 단위**: 이 지시서 전체 = PR 1개

## 배경

[H1 통합검색 화면](H1-지원자-통합검색-화면.md)은 **전 공고를 가로지르는** 지원자 테이블이다. 그런데 [docs/00_overview/02-api.md](../00_overview/02-api.md)에는 공고에 매인 `GET /postings/{id}/applications` 밖에 없다. **전역 검색 엔드포인트가 문서에 빠져 있다.**

이 지시서는 전역 `GET /api/v1/applications` 를 만든다. 공고별 목록(D1)은 [팀원3의 지원자 API](D1-지원자-API.md)가 따로 만든다 — **두 사람이 같은 파일을 건드리지 않게 라우터 파일을 나눈다.**

10만 건 위에서 이 쿼리가 몇 ms 인지가 [인덱스 튜닝](H5-인덱스-튜닝.md)의 출발점이다.

## 선행 조건 — 없으면 중단

아래가 하나라도 아니면 **시작하지 말고 팀 채널에 알린다.** 없는 것을 상상해서 만들지 않는다.

- [ ] [docs/00_overview/01-erd.md](../00_overview/01-erd.md)가 확정 상태다
- [ ] [J0 앱 뼈대](J0-앱-뼈대.md) PR이 머지돼 있다
- [ ] **전역 검색 경로가 [docs/00_overview/02-api.md](../00_overview/02-api.md)에 추가되어 있다** — 공용 문서는 백엔드 오너가 갱신하고 팀 채널 사후 공지 (2026-09-04 자율제)

## 가장 중요한 규칙

- **[backend/app/models.py](../../backend/app/models.py)를 수정하지 않는다.** 컬럼이 부족해 보여도 추가하지 않는다. 멈추고 팀 채널에 묻는다.
- **[docs/00_overview/01-erd.md](../00_overview/01-erd.md)·[docs/00_overview/02-api.md](../00_overview/02-api.md)를 수정하지 않는다.** 공용 문서다.
- **인증·권한 코드를 넣지 않는다.** 인증은 팀장 담당(A1~A3)이고 아직 없다. 토큰 검사를 흉내 내면 나중에 팀장 것과 충돌한다. 사용자 id 가 필요한 자리는 `# TODO(A1): 토큰의 사용자로 채운다` 주석만 남긴다.
- **`main.py` 는 `include_router` 한 줄만** 건드린다. 그 파일의 다른 부분은 손대지 않는다.
- **파일은 `backend/app/api/search.py` 하나만 만든다.** `applications.py` 는 팀원3 것이다. 건드리면 충돌한다.
- **검색 범위는 이름·이메일로 확정돼 있다** ([docs/00_overview/02-api.md](../00_overview/02-api.md) 아래 설명). 자기소개서 전문 검색은 범위 밖이다 — 한국어 형태소 분석 문제와 인덱스 비용 때문에 미뤄둔 것이다.
- **여기서 인덱스를 추가하지 않는다.** 인덱스는 [H5 튜닝](H5-인덱스-튜닝.md)에서 측정한 뒤 팀장 합의를 거쳐 넣는다.

## 완료 조건

- [ ] `backend/app/schemas/search.py` — `ApplicationListItem` · `SearchResult`
- [ ] `backend/app/api/search.py` — 라우터
- [ ] `GET /api/v1/applications` — 전 공고 지원자 검색
- [ ] 쿼리 `q` — 이름 **또는** 이메일 부분 일치. 대소문자 무시 (`ilike`)
- [ ] 쿼리 `stage` — 단계 필터. 여러 개 허용 (`?stage=applied&stage=screening`)
- [ ] 쿼리 `posting_id` — 특정 공고로 좁히기 (선택)
- [ ] 쿼리 `limit` 기본 50 · 최대 200. 넘으면 **422**
- [ ] 응답에 `items` · `total` · **`took_ms`**(서버 측정 소요 시간) 포함 — 화면이 응답 시간을 표시한다
- [ ] `q` 가 비었으면 필터만 적용한다. 전체 조회가 막히면 안 된다
- [ ] 이상한 `stage` 값 → **422** (`models.STAGES` 로 검증)
- [ ] `main.py` 에 `include_router` 한 줄

## 완성 예시

**이 형태를 그대로 따른다.**

```python
# backend/app/api/search.py (핵심만)
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import STAGES, Application, JobPosting

router = APIRouter(prefix="/api/v1/applications", tags=["search"])


@router.get("", response_model=SearchResult)
def search(
    db: Session = Depends(get_db),
    q: str | None = None,
    stage: Annotated[list[str] | None, Query()] = None,
    posting_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    started = time.perf_counter()

    stmt = select(Application).join(JobPosting)
    if q:
        # 이름 또는 이메일 부분 일치. 검색 범위는 02-api.md 에서 이 둘로 확정돼 있다
        like = f"%{q}%"
        stmt = stmt.where(or_(Application.name.ilike(like), Application.email.ilike(like)))
    if stage:
        stmt = stmt.where(Application.current_stage.in_(stage))
    if posting_id:
        stmt = stmt.where(Application.job_posting_id == posting_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(Application.created_at.desc()).limit(limit).offset(offset)
    ).all()

    # 화면이 "0.12초" 처럼 응답 시간을 보여준다. 튜닝 전/후 비교의 기준값이기도 하다
    took_ms = round((time.perf_counter() - started) * 1000, 1)
    return SearchResult(items=rows, total=total, took_ms=took_ms)
```

## 참고 문서

- [docs/00_overview/02-api.md](../00_overview/02-api.md) — 검색 범위가 이름·이메일로 확정된 근거
- [docs/00_overview/01-erd.md](../00_overview/01-erd.md) — `applications` 표와 기존 인덱스
- `frontend/mockups/mockup-applicants.html` — 화면이 쓰는 컬럼과 응답 시간 표기
- [H5 인덱스 튜닝](H5-인덱스-튜닝.md) — 이 API 를 측정 대상으로 쓴다

## Claude에게 시키기

작업 폴더에서 Claude Code를 열고 **아래를 순서대로 하나씩** 붙여넣는다.

```
0단계.
backend/app/models.py 의 Application 과 STAGES, docs/00_overview/01-erd.md 의 applications 표,
docs/00_overview/02-api.md 의 "지원자 관리 (D·H)" 절 전체(검색 범위 설명 포함),
frontend/mockups/mockup-applicants.html 을 읽어라.

읽은 뒤 아래를 알려줘라. 아직 파일을 만들지 마라.
- 화면이 테이블에 실제로 보여주는 컬럼 목록
- 검색 범위가 이름·이메일로 한정된 이유와 그 근거가 적힌 위치
```

```
1단계.
backend/app/schemas/search.py 를 만들어라.
ApplicationListItem 은 화면이 실제로 쓰는 컬럼만 담는다. 자기소개서 전문 같은 큰 필드를 넣지 마라.
SearchResult 는 items, total, took_ms 세 개.
```

```
2단계.
backend/app/api/search.py 에 GET /api/v1/applications 를 만들어라.
- q 는 이름 또는 이메일 부분 일치, ilike 로 대소문자 무시
- stage 는 여러 개 받는다. models.STAGES 에 없는 값이면 422
- posting_id 로 좁힐 수 있다
- limit 기본 50, 최대 200. offset 으로 넘긴다
- 응답에 total 과 took_ms 를 넣는다. took_ms 는 time.perf_counter 로 서버에서 잰다
backend/app/api/applications.py 를 만들거나 고치지 마라 — 팀원3 담당이다.
인덱스를 추가하지 마라. models.py 를 수정하지 마라.
```

```
3단계.
main.py 에 include_router 한 줄을 추가하고 아래 검증을 실행해 결과를 보여줘라.
```

```
마지막 단계 — 여기서 멈추지 마라.

위 작업을 끝내고 PR 을 올렸으면, 이어서 다음 할 일을 스스로 찾아 그대로 수행해라.

1. docs/00_overview/04-team.md 에서 내 도메인을 확인하고, docs/01_role/<내 도메인>.md 의 작업 큐를 읽어라.
   (작업 큐는 로드맵에만 있다. docs/00_overview/06-weekly.md 는 주 마감 게이트·도메인 간 일정용이다)
2. 큐에서 선행이 풀린 다음 작업을 찾아라. 큐가 비었거나 전부 막혀 있으면
   멈추고 무엇이 막혔는지 팀 채널에 알려라.
3. 찾은 작업의 지시서가 docs/02_tasks/ 에 링크돼 있으면 열고, 선행 조건을 먼저 확인해라.
   선행 조건이 안 채워졌으면 거기서 멈추고 무엇이 막혔는지 알려줘라.
4. 선행 조건이 채워졌으면 새 브랜치를 만들고 그 지시서의 "Claude에게 시키기" 를
   0단계부터 순서대로 수행해라. 지시서 하나 = PR 하나다.
5. 그 작업도 끝나면 1번으로 돌아가 반복해라.

지키는 것:
- 지시서가 있는 작업만 한다. 큐 항목에 지시서가 없으면 "지시서 없음 — 오너가 직접 쪼갤 것"
  이라고 말하고 멈춘다.
- 지시서에 적힌 산출 파일 밖을 고치지 않는다. 다른 도메인 파일과 공용 파일은 건드리지 않는다.
  (공용: frontend/mockups/mockup.html · docs/00_overview/01-erd.md · docs/00_overview/02-api.md · backend/app/models.py)
- 작업 사이마다 git status 를 확인해서 지시서에 없는 파일이 있으면 되돌린다.
```

## 검증 방법

```bash
A=localhost:8000/api/v1/applications
curl -s "$A?limit=5" | head -c 400; echo
curl -s "$A?q=홍" | python -c 'import sys,json;d=json.load(sys.stdin);print("q검색",d["total"],d["took_ms"],"ms")'
curl -s "$A?stage=applied&stage=screening" | python -c 'import sys,json;d=json.load(sys.stdin);print("단계필터",d["total"])'
curl -s -o /dev/null -w 'limit초과 %{http_code}\n' "$A?limit=500"
curl -s -o /dev/null -w '이상한단계 %{http_code}\n' "$A?stage=없는단계"
curl -s -o /dev/null -w '빈검색 %{http_code}\n' "$A"
```

기대 결과:

- `q` 검색이 이름·이메일 양쪽에서 걸린다 (대소문자 무시)
- `stage` 를 두 개 주면 **둘 다** 포함된다
- 응답에 `total` 과 `took_ms` 가 있다
- `limit=500` → **422**
- `stage=없는단계` → **422**
- 쿼리 없이 호출해도 **200** (전체 조회가 막히지 않는다)

## 막히면 · 되돌리기

- **30분 넘게 막히면 혼자 붙들지 말고 팀 채널에 묻는다.**
- **결과가 이상해지면 고치려 들지 말고 버린다.**

```bash
git checkout -- .
```

그래도 이상하면 브랜치째 버리고 처음부터 다시 시작한다.

```bash
git checkout main && git branch -D feat/h2-search-api
```

- **`git status`에 `models.py` · `docs/` · 다른 사람 파일이 떠 있으면 범위를 벗어난 것이다.** 되돌리고 팀 채널에 알린다.

## PR 체크리스트

- [ ] PR 본문에 위 검증 결과를 붙였다
- [ ] `models.py` · `docs/` · 다른 사람 파일을 **수정하지 않았다**
- [ ] 스키마 변경 없음
