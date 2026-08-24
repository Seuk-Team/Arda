# [D1·D4] 지원자 목록 · 상세 API

> 담당: 팀원3 · 역할 A(도메인 백엔드) · 브랜치: `feat/d1-applications-api`
> **PR 단위**: 이 지시서 전체 = PR 1개

## 배경

칸반과 상세 패널이 읽는 API 다. **화면에서 가장 자주 호출되는 경로**라 여기가 느리면 전체가 느리게 느껴진다.

상세는 지원서 한 건에 딸린 것을 전부 모아서 준다 — 단계 이력(D5) · 평가(E1) · 메모 · 파일. **화면이 상세 패널을 열 때 API 를 네 번 부르게 하지 않는다.**

공고에 매인 목록(`/postings/{id}/applications`)을 만든다. **전 공고 가로지르는 검색은 [팀원2의 H2](H2-검색-필터-API.md)가 따로 만든다** — 라우터 파일을 나눠 충돌을 막는다.

## 선행 조건 — 없으면 중단

아래가 하나라도 아니면 **시작하지 말고 팀 채널에 알린다.** 없는 것을 상상해서 만들지 않는다.

- [ ] [docs/00_overview/01-erd.md](../00_overview/01-erd.md)가 확정 상태다
- [ ] [J0 앱 뼈대](J0-앱-뼈대.md) PR이 머지돼 있다
- [ ] [B2 공고 CRUD API](B2-공고-CRUD-API.md) PR이 머지돼 있다 — 같은 패턴을 따른다

## 가장 중요한 규칙

- **[backend/app/models.py](../../backend/app/models.py)를 수정하지 않는다.** 컬럼이 부족해 보여도 추가하지 않는다. 멈추고 팀 채널에 묻는다.
- **[docs/00_overview/01-erd.md](../00_overview/01-erd.md)·[docs/00_overview/02-api.md](../00_overview/02-api.md)를 수정하지 않는다.** 공용 문서다.
- **인증·권한 코드를 넣지 않는다.** 인증은 팀장 담당(A1~A3)이고 아직 없다. 토큰 검사를 흉내 내면 나중에 팀장 것과 충돌한다. 사용자 id 가 필요한 자리는 `# TODO(A1): 토큰의 사용자로 채운다` 주석만 남긴다.
- **`main.py` 는 `include_router` 한 줄만** 건드린다. 그 파일의 다른 부분은 손대지 않는다.
- **파일은 `backend/app/api/applications.py` 하나만 만든다.** `search.py` 는 팀원2 것이다.
- **상세 응답에 `self_intro` 전문을 넣되 목록에는 넣지 않는다.** 목록에 5천 자 자소서가 100건 실리면 응답이 수 MB 가 된다.
- **단계 변경(D3)은 만들지 않는다.** 팀장 담당이다. 여기서는 읽기만 한다.

## 완료 조건

- [ ] `backend/app/schemas/application_detail.py` — `ApplicationDetail` · `StageHistoryOut` 등
- [ ] `backend/app/api/applications.py` — 라우터
- [ ] `GET /api/v1/postings/{id}/applications` — 공고별 지원자 목록. **자소서 전문 제외**
- [ ] `GET /api/v1/applications/{id}` — 상세. 없으면 404
- [ ] 상세 응답에 **한 번에** 포함: 지원서 본문 · `stage_history`(최신순) · `evaluations`(+평균) · `application_notes`(최신순) · `files`
- [ ] `GET /api/v1/applications/{id}/history` — 단계 이력만 (D5)
- [ ] **N+1 쿼리를 만들지 않는다** — `selectinload` 로 한 번에 읽는다
- [ ] 평가 평균은 소수 첫째 자리까지. 평가가 없으면 `null`
- [ ] `main.py` 에 `include_router` 한 줄

## 완성 예시

**이 형태를 그대로 따른다.**

```python
# backend/app/api/applications.py (핵심만)
from sqlalchemy.orm import Session, selectinload

@router.get("/applications/{application_id}", response_model=ApplicationDetail)
def detail(application_id: int, db: Session = Depends(get_db)):
    # selectinload 를 안 쓰면 관계마다 쿼리가 따로 나간다(N+1).
    # 상세 패널은 자주 열리므로 한 번에 읽는다.
    row = db.scalar(
        select(Application)
        .options(
            selectinload(Application.stage_history),
            selectinload(Application.evaluations),
            selectinload(Application.notes),
            selectinload(Application.files),
        )
        .where(Application.id == application_id)
    )
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원자를 찾을 수 없습니다")

    scores = [e.score for e in row.evaluations]
    return ApplicationDetail.model_validate(row).model_copy(
        update={"avg_score": round(sum(scores) / len(scores), 1) if scores else None}
    )
```

목록은 가볍게 준다.

```python
# 목록에는 self_intro 를 넣지 않는다. 5천 자 × 100건이면 응답이 수 MB 가 된다
class ApplicationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    current_stage: str
    career_years: int | None
    created_at: datetime
```

## 참고 문서

- [docs/00_overview/01-erd.md](../00_overview/01-erd.md) — `applications` · `stage_history` · `evaluations` · `application_notes` · `files`
- [docs/00_overview/02-api.md](../00_overview/02-api.md) — "지원자 관리 (D·H)" 표
- [B2 공고 CRUD API](B2-공고-CRUD-API.md) — 따라 할 파일 배치·응답 형태
- `frontend/mockups/mockup.html` — 상세 패널이 실제로 보여주는 항목

## Claude에게 시키기

작업 폴더에서 Claude Code를 열고 **아래를 순서대로 하나씩** 붙여넣는다.

```
0단계.
backend/app/models.py 전체, docs/00_overview/01-erd.md 의 applications 와 그 자식 테이블들,
docs/00_overview/02-api.md 의 "지원자 관리 (D·H)" 표, frontend/mockups/mockup.html 의 상세 패널을 읽어라.

읽은 뒤 아래를 알려줘라. 아직 파일을 만들지 마라.
- 상세 패널이 화면에 보여주는 항목 목록
- 그것을 다 채우려면 어떤 테이블을 함께 읽어야 하는지
```

```
1단계.
backend/app/schemas/application_detail.py 를 만들어라.
목록용 ApplicationListItem 은 화면 테이블이 쓰는 컬럼만 담는다. self_intro 를 넣지 마라.
상세용 ApplicationDetail 은 지원서 본문 + stage_history + evaluations + notes + files 를 담고
avg_score: float | None 을 포함한다.
```

```
2단계.
backend/app/api/applications.py 에 라우터를 만들어라.
- GET /api/v1/postings/{id}/applications : 공고별 목록. 최신순
- GET /api/v1/applications/{id} : 상세. selectinload 로 관계를 한 번에 읽는다
- GET /api/v1/applications/{id}/history : 단계 이력만, 최신순
없는 id 는 404. 평가 평균은 소수 첫째 자리, 평가가 없으면 null.
단계 변경 엔드포인트를 만들지 마라 — 팀장 담당이다.
backend/app/api/search.py 를 만들거나 고치지 마라 — 팀원2 담당이다.
```

```
3단계.
main.py 에 include_router 한 줄을 추가하고, 아래 검증을 실행해 결과를 보여줘라.
상세 API 를 한 번 호출할 때 SQL 이 몇 번 나가는지 echo=True 로 세어 보고해라.
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
curl -s localhost:8000/api/v1/postings/1/applications | head -c 300; echo
curl -s localhost:8000/api/v1/applications/1 | python -c 'import sys,json;d=json.load(sys.stdin);print("키:",sorted(d.keys()));print("평균:",d.get("avg_score"))'
curl -s localhost:8000/api/v1/applications/1/history
curl -s -o /dev/null -w '없는id %{http_code}\n' localhost:8000/api/v1/applications/999999
curl -s localhost:8000/api/v1/postings/1/applications | python -c 'import sys,json;d=json.load(sys.stdin);print("목록에 self_intro 있나:", any("self_intro" in i for i in d))'
```

기대 결과:

- 목록에 **`self_intro` 가 없다**
- 상세에 `stage_history` · `evaluations` · `notes` · `files` 가 **한 번에** 들어온다
- 평가가 있으면 `avg_score` 가 소수 첫째 자리, 없으면 `null`
- 없는 id → **404**
- 상세 1회 호출에 나가는 SQL 이 **관계 수 + 1 이하** (N+1 이 아니다)
- `history` 가 최신순으로 온다

## 막히면 · 되돌리기

- **30분 넘게 막히면 혼자 붙들지 말고 팀 채널에 묻는다.**
- **결과가 이상해지면 고치려 들지 말고 버린다.**

```bash
git checkout -- .
```

그래도 이상하면 브랜치째 버리고 처음부터 다시 시작한다.

```bash
git checkout main && git branch -D feat/d1-applications-api
```

- **`git status`에 `models.py` · `docs/` · 다른 사람 파일이 떠 있으면 범위를 벗어난 것이다.** 되돌리고 팀 채널에 알린다.

## PR 체크리스트

- [ ] PR 본문에 위 검증 결과를 붙였다
- [ ] `models.py` · `docs/` · 다른 사람 파일을 **수정하지 않았다**
- [ ] 스키마 변경 없음
