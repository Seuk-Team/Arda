# [E3] 면접관 배정 API

> 담당: 팀원4 · 역할 E(인프라·인증) · 브랜치: `feat/e3-interviewer-assignment`
> **PR 단위**: 이 지시서 전체 = PR 1개
>
> **⚠️ 2026-08-31 개정 ([ADR-0017](../03_decision/0017-등급-이분화.md)) — 이 지시서의 전제 두 가지가 바뀌었다. 아래 본문은 착수 당시 기록이다.**
> 1. **A3 는 폐지됐다.** 조회는 로그인한 사람 전체에게 열려 있다. 이 테이블이 남기는 제한은 **평가 작성(배정된 건만)** 하나뿐이다. 배정·해제가 admin 전용인 것은 그대로다 ([ADR-0013](../03_decision/0013-면접관-배정-정책.md)).
> 2. **배정 대상의 role 을 검사하지 않는다.** 역할이 `admin`·`member` 2종이 되면서 `role="interviewer"` 라는 값 자체가 없어졌다 — **누구나 면접관으로 배정될 수 있고, 아래 "422" 완료 조건은 무효다.**

## 배경

**A3(면접관은 본인 배정 지원자만 조회)는 필수 기능인데, 배정 관계가 없으면 강제할 방법이 없다.** [01-erd.md](../00_overview/01-erd.md)가 `interviewer_assignments` 를 둔 이유가 이것이다.

권한 검사 자체는 팀장의 A3 작업이 한다. 이 지시서는 **그 검사가 읽을 데이터를 만든다.** 순서상 이것이 먼저다.

이 프로젝트에서 **유일한 다대다 조인 테이블**이라, 조인 테이블을 다루는 법을 보여주는 자리이기도 하다.

## 선행 조건 — 없으면 중단

아래가 하나라도 아니면 **시작하지 말고 팀 채널에 알린다.** 없는 것을 상상해서 만들지 않는다.

- [ ] [docs/00_overview/01-erd.md](../00_overview/01-erd.md)가 확정 상태다
- [ ] [E2 평가 API](E2-평가-API.md) PR이 머지돼 있다 — 같은 파일 계열을 다룬다

## 가장 중요한 규칙

- **[backend/app/models.py](../../backend/app/models.py)를 수정하지 않는다.** 컬럼이 부족해 보여도 추가하지 않는다. 멈추고 팀 채널에 묻는다.
- **[docs/00_overview/01-erd.md](../00_overview/01-erd.md)·[docs/00_overview/02-api.md](../00_overview/02-api.md)를 수정하지 않는다.** 공용 문서다.
- **인증·권한 코드를 넣지 않는다.** 인증은 팀장 담당(A1~A3)이고 아직 없다. 토큰 검사를 흉내 내면 나중에 팀장 것과 충돌한다. 사용자 id 가 필요한 자리는 `# TODO(A1): 토큰의 사용자로 채운다` 주석만 남긴다.
- **`main.py` 는 `include_router` 한 줄만** 건드린다. 그 파일의 다른 부분은 손대지 않는다.
- **`backend/app/api/assignments.py` 만 만든다.**
- **권한 검사를 여기서 구현하지 않는다.** A3 는 팀장 담당이다. 여기서는 배정 데이터만 만들고 읽는다.
- ~~**`role="interviewer"` 인 사용자만 배정한다.** 아무나 배정되면 이 테이블의 의미가 없다.~~ → **폐지 (ADR-0017)**: 대상 role 을 보지 않는다.

## 완료 조건

- [ ] `backend/app/api/assignments.py` — 라우터
- [ ] `POST /api/v1/applications/{id}/interviewers` — 배정. 본문 `{interviewer_ids: [...]}`
- [ ] `GET /api/v1/applications/{id}/interviewers` — 배정된 면접관 목록
- [ ] `DELETE /api/v1/applications/{id}/interviewers/{user_id}` — 배정 해제. 204
- [ ] `GET /api/v1/interviewers/{user_id}/applications` — **면접관 본인이 볼 목록** (A3 가 쓸 경로)
- [ ] ~~`role != "interviewer"` 인 사용자를 배정하면 **422**~~ → **폐지 (ADR-0017)**: 없는 사용자면 404, 그 외에는 전부 배정된다
- [ ] 이미 배정된 사람을 또 배정하면 **에러가 아니라 무시**한다 (UNIQUE 제약 활용, 멱등)
- [ ] `assigned_by` 는 지금 채울 수 없다 — `None` + `TODO(A1)`
- [ ] 없는 지원자·사용자 → **404**

## 완성 예시

**이 형태를 그대로 따른다.**

```python
# backend/app/api/assignments.py (핵심만)
from sqlalchemy.dialects.postgresql import insert as pg_insert

@router.post("/applications/{application_id}/interviewers")
def assign(application_id: int, body: AssignRequest, db: Session = Depends(get_db)):
    if db.get(Application, application_id) is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원자를 찾을 수 없습니다")

    users = db.scalars(select(User).where(User.id.in_(body.interviewer_ids))).all()
    if len(users) != len(set(body.interviewer_ids)):
        raise HTTPException(http.HTTP_404_NOT_FOUND, "없는 사용자가 있습니다")

    bad = [u.id for u in users if u.role != "interviewer"]
    if bad:
        # 아무나 배정되면 A3 권한 검사가 무의미해진다
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"면접관이 아닌 사용자입니다: {bad}")

    # 같은 사람을 두 번 배정하는 건 실수지 오류가 아니다.
    # UNIQUE(application_id, interviewer_id) 를 이용해 조용히 넘긴다
    db.execute(
        pg_insert(InterviewerAssignment)
        .values([{"application_id": application_id, "interviewer_id": u.id,
                  "assigned_by": None} for u in users])   # TODO(A1): 토큰의 사용자
        .on_conflict_do_nothing(index_elements=["application_id", "interviewer_id"])
    )
    db.commit()
    return {"assigned": [u.id for u in users]}
```

## 참고 문서

- [docs/00_overview/01-erd.md](../00_overview/01-erd.md) — `interviewer_assignments` 표와 A3 설명
- [docs/00_overview/02-api.md](../00_overview/02-api.md) — 권한 규칙 (interviewer 는 본인 배정 지원서만)
- [docs/04_planning/00_summary_ko.md](../04_planning/00_summary_ko.md) — A3 · E3 기능 정의

## Claude에게 시키기

작업 폴더에서 Claude Code를 열고 **아래를 순서대로 하나씩** 붙여넣는다.

```
0단계.
backend/app/models.py 의 InterviewerAssignment 와 User, ROLES,
docs/00_overview/01-erd.md 의 interviewer_assignments 표와 그 위 설명, docs/00_overview/02-api.md 상단의 권한 규칙을 읽어라.

읽은 뒤 아래를 알려줘라. 아직 파일을 만들지 마라.
- A3(면접관은 본인 배정 지원자만 조회)를 강제하려면 어떤 데이터가 필요한지
- 이 테이블에 걸린 UNIQUE 제약이 무엇인지
```

```
1단계.
backend/app/api/assignments.py 에 라우터를 만들어라.
- POST /api/v1/applications/{id}/interviewers : 본문은 interviewer_ids 배열
- GET /api/v1/applications/{id}/interviewers : 배정된 면접관 목록
- DELETE /api/v1/applications/{id}/interviewers/{user_id} : 204
role 이 interviewer 가 아닌 사용자가 섞이면 422 로 거절해라. 왜인지 주석으로 적어라.
이미 배정된 사람은 에러가 아니라 조용히 넘어가라 — on_conflict_do_nothing 을 써라.
assigned_by 는 None 과 TODO(A1) 주석.
```

```
2단계.
GET /api/v1/interviewers/{user_id}/applications 를 추가해라.
그 면접관에게 배정된 지원자 목록을 준다. 나중에 A3 권한 검사가 이 경로를 쓴다.
권한 검사 자체를 구현하지 마라 — 팀장 담당이다.
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
P=localhost:8000/api/v1
psql "$DATABASE_URL" -c "insert into users (email,password_hash,name,role) values ('i1@x.com','x','면접관1','interviewer'),('r1@x.com','x','담당자1','recruiter') on conflict do nothing"
IID=$(psql -t -A "$DATABASE_URL" -c "select id from users where email='i1@x.com'")
RID=$(psql -t -A "$DATABASE_URL" -c "select id from users where email='r1@x.com'")
curl -s -X POST $P/applications/1/interviewers -H 'content-type: application/json' -d "{\"interviewer_ids\":[$IID]}"
curl -s -o /dev/null -w '중복배정 %{http_code}\n' -X POST $P/applications/1/interviewers -H 'content-type: application/json' -d "{\"interviewer_ids\":[$IID]}"
curl -s -o /dev/null -w '면접관아님 %{http_code}\n' -X POST $P/applications/1/interviewers -H 'content-type: application/json' -d "{\"interviewer_ids\":[$RID]}"
curl -s $P/interviewers/$IID/applications | head -c 200; echo
curl -s -o /dev/null -w '해제 %{http_code}\n' -X DELETE $P/applications/1/interviewers/$IID
psql "$DATABASE_URL" -c "select count(*) from interviewer_assignments where application_id=1"
```

기대 결과:

- 면접관 배정 → **200**
- **같은 사람 재배정 → 200** (에러가 아니다). 행이 늘지 않는다
- `recruiter` 를 배정 → **422**
- `/interviewers/{id}/applications` 에 배정된 지원자가 보인다
- 해제 → **204**, 행이 사라진다
- 없는 사용자 id → **404**

## 막히면 · 되돌리기

- **30분 넘게 막히면 혼자 붙들지 말고 팀 채널에 묻는다.**
- **결과가 이상해지면 고치려 들지 말고 버린다.**

```bash
git checkout -- .
```

그래도 이상하면 브랜치째 버리고 처음부터 다시 시작한다.

```bash
git checkout main && git branch -D feat/e3-interviewer-assignment
```

- **`git status`에 `models.py` · `docs/` · 다른 사람 파일이 떠 있으면 범위를 벗어난 것이다.** 되돌리고 팀 채널에 알린다.

## PR 체크리스트

- [ ] PR 본문에 위 검증 결과를 붙였다
- [ ] `models.py` · `docs/` · 다른 사람 파일을 **수정하지 않았다**
- [ ] 스키마 변경 없음
