# [C1·C3·C6] 지원서 제출 API (공개)

> 담당: 팀원1 · 역할 C(파일·알림) · 브랜치: `feat/c2-apply-api`
> **PR 단위**: 이 지시서 전체 = PR 1개

## 배경

지원자는 **로그인 없이** 외부 링크로 지원한다. 그래서 이 API 는 인증 없이 열려 있는 유일한 쓰기 경로이고, 그만큼 입력 검증이 전부다.

[C1 지원 폼 목업](C1-지원-폼-화면.md)이 보내는 값을 그대로 받는다. 목업의 입력 필드와 여기 스키마가 어긋나면 3주차 연동에서 전부 다시 만져야 하므로, **목업을 먼저 열어보고 필드를 맞춘다.**

## 선행 조건 — 없으면 중단

아래가 하나라도 아니면 **시작하지 말고 팀 채널에 알린다.** 없는 것을 상상해서 만들지 않는다.

- [ ] [docs/01-erd.md](../01-erd.md)가 **확정 상태**다 (상단이 `초안`이 아니라 `확정 vX.X · 날짜`)
- [ ] [J0 앱 뼈대](J0-앱-뼈대.md) PR이 머지돼 있다
- [ ] `frontend/mockups/mockup-apply.html`이 `main`에 있다 — 받을 필드의 기준

## 가장 중요한 규칙

- **[backend/app/models.py](../../backend/app/models.py)를 수정하지 않는다.** 컬럼이 부족해 보여도 추가하지 않는다. 멈추고 팀 채널에 묻는다.
- **[docs/01-erd.md](../01-erd.md)·[docs/02-api.md](../02-api.md)를 수정하지 않는다.** 공용 문서다.
- **인증·권한 코드를 넣지 않는다.** 인증은 팀장 담당(A1~A3)이고 아직 없다. 토큰 검사를 흉내 내면 나중에 팀장 것과 충돌한다. 사용자 id 가 필요한 자리는 `# TODO(A1): 토큰의 사용자로 채운다` 주석만 남긴다.
- **`main.py` 는 `include_router` 한 줄만** 건드린다. 그 파일의 다른 부분은 손대지 않는다.
- **파일 업로드를 여기서 처리하지 않는다.** 이력서는 [F1 presigned](F1-S3-presigned.md)가 브라우저 → S3 로 직접 올린다. 이 API 는 업로드가 끝난 뒤 받은 `s3_key` 만 저장한다.
- **`privacy_agreed_at` 은 서버 시각으로 넣는다.** 클라이언트가 보낸 시각을 믿지 않는다.

## 완료 조건

- [ ] `backend/app/schemas/application.py` — `ApplicationCreate` · `ApplicationOut`
- [ ] `backend/app/api/public.py` — 라우터 (`prefix="/api/v1/public"`)
- [ ] `GET /api/v1/public/postings/{id}` — 지원 폼용 공고 정보. **`status="open"` 인 공고만** 준다. 아니면 404
- [ ] `POST /api/v1/public/postings/{id}/applications` — 지원서 저장, 성공 **201**
- [ ] 중복 지원(같은 공고 + 같은 이메일) → **409**. DB UNIQUE 위반을 잡아서 변환한다 (C6)
- [ ] `privacy_agreed` 가 `false` 면 **422**. 저장 시 `privacy_agreed_at` 은 `func.now()` (C3)
- [ ] `source` 는 `"form"` 고정 (담당자 등록 `manual` 과 구분)
- [ ] 접수 시 `stage_history` 에 `from_stage=NULL, to_stage="applied", changed_by=NULL` 1행 기록 (D5)
- [ ] `main.py` 에 `include_router` 한 줄 추가

## 완성 예시

**이 형태를 그대로 따른다.**

```python
# backend/app/api/public.py (핵심만)
from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Application, JobPosting, StageHistory
from app.schemas.application import ApplicationCreate, ApplicationOut

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.post("/postings/{posting_id}/applications",
             response_model=ApplicationOut, status_code=http.HTTP_201_CREATED)
def submit(posting_id: int, body: ApplicationCreate, db: Session = Depends(get_db)):
    posting = db.get(JobPosting, posting_id)
    if posting is None or posting.status != "open":
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원할 수 없는 공고입니다")

    row = Application(
        job_posting_id=posting_id,
        source="form",
        current_stage="applied",
        privacy_agreed_at=func.now(),   # 서버 시각. 클라이언트 값을 믿지 않는다
        **body.model_dump(exclude={"privacy_agreed"}),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:               # C6 — UNIQUE(job_posting_id, email)
        db.rollback()
        raise HTTPException(http.HTTP_409_CONFLICT, "이미 이 공고에 지원했습니다")

    # D5 — 접수도 이력이다. 시스템이 한 것이므로 changed_by 는 NULL
    db.add(StageHistory(application_id=row.id, from_stage=None, to_stage="applied"))
    db.commit()
    return ApplicationOut.model_validate(row)
```

## 참고 문서

- [docs/01-erd.md](../01-erd.md) — `applications` · `stage_history` 표
- [docs/02-api.md](../02-api.md) — "지원 — 공개 (C)" 표
- `frontend/mockups/mockup-apply.html` — 실제로 보내는 필드

## Claude에게 시키기

작업 폴더에서 Claude Code를 열고 **아래를 순서대로 하나씩** 붙여넣는다.

```
0단계.
backend/app/models.py 의 Application·StageHistory, docs/01-erd.md 의 applications 표,
docs/02-api.md 의 "지원 — 공개 (C)" 표, frontend/mockups/mockup-apply.html 을 읽어라.

읽은 뒤, 목업이 입력받는 필드와 applications 테이블 컬럼을 나란히 놓은 표를 보여줘라.
어긋나는 것이 있으면 표시해라. 아직 파일을 만들지 마라.
```

```
1단계.
backend/app/schemas/application.py 를 만들어라.
ApplicationCreate 는 목업이 보내는 필드만 받는다.
privacy_agreed: bool 을 포함하되 True 만 허용해라 (false 면 422).
privacy_agreed_at 은 받지 마라 — 서버가 넣는다.
ApplicationOut 은 model_config = ConfigDict(from_attributes=True) 로 응답용.
```

```
2단계.
backend/app/api/public.py 에 라우터를 만들어라. prefix 는 /api/v1/public.
GET /postings/{id} 는 status 가 "open" 인 공고만 준다. 아니면 404.
POST /postings/{id}/applications 는 지원서를 저장하고 201 을 준다.
- source="form", current_stage="applied", privacy_agreed_at 은 func.now()
- IntegrityError 를 잡아서 409 로 바꾼다 (중복 지원)
- 저장 성공 시 stage_history 에 from_stage=None, to_stage="applied" 한 행을 남긴다
파일 업로드 처리를 넣지 마라. models.py 를 수정하지 마라.
```

```
3단계.
backend/app/main.py 에 include_router 한 줄만 추가하고,
아래 검증 명령을 순서대로 실행해 결과를 보여줘라. 실패하면 고치기 전에 원인을 먼저 설명해라.
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
cd backend && uv run uvicorn app.main:app --reload
# 다른 터미널에서
curl -s -X POST localhost:8000/api/v1/postings -H 'content-type: application/json' -d '{"title":"백엔드","status":"open"}'
curl -s localhost:8000/api/v1/public/postings/1
curl -s -X POST localhost:8000/api/v1/public/postings/1/applications -H 'content-type: application/json' -d '{"name":"홍길동","email":"a@b.com","phone":"010-0000-0000","privacy_agreed":true}'
curl -s -o /dev/null -w '중복 %{http_code}\n' -X POST localhost:8000/api/v1/public/postings/1/applications -H 'content-type: application/json' -d '{"name":"홍길동","email":"a@b.com","phone":"010-0000-0000","privacy_agreed":true}'
curl -s -o /dev/null -w '미동의 %{http_code}\n' -X POST localhost:8000/api/v1/public/postings/1/applications -H 'content-type: application/json' -d '{"name":"김","email":"c@d.com","phone":"010","privacy_agreed":false}'
psql "$DATABASE_URL" -c "select from_stage, to_stage, changed_by from stage_history"
```

기대 결과:

- 첫 제출 → **201**, 응답에 `id` · `current_stage: "applied"` · `source: "form"`
- 같은 이메일 재제출 → **409**
- `privacy_agreed: false` → **422**
- `stage_history` 에 `from_stage=NULL, to_stage=applied, changed_by=NULL` 1행
- `status` 가 `draft` 인 공고로 제출 → **404**
- 서버 로그에 트레이스백이 없다

## 막히면 · 되돌리기

- **30분 넘게 막히면 혼자 붙들지 말고 팀 채널에 묻는다.**
- **결과가 이상해지면 고치려 들지 말고 버린다.**

```bash
git checkout -- .
```

그래도 이상하면 브랜치째 버리고 처음부터 다시 시작한다.

```bash
git checkout main && git branch -D feat/c2-apply-api
```

- **`git status`에 `models.py` · `docs/` · 다른 사람 파일이 떠 있으면 범위를 벗어난 것이다.** 되돌리고 팀 채널에 알린다.

## PR 체크리스트

- [ ] PR 본문에 위 검증 결과를 붙였다
- [ ] `models.py` · `docs/` · 다른 사람 파일을 **수정하지 않았다**
- [ ] 스키마 변경 없음
