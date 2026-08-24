# [D7] 담당자 메모 API

> 담당: 팀원3 · 역할 A(도메인 백엔드) · 브랜치: `feat/d7-notes-api`
> **PR 단위**: 이 지시서 전체 = PR 1개

## 배경

평가(`evaluations`)는 점수 1~5 가 필수인 행이다. "전화 안 받음", "다음 주 재연락" 같은 **점수 없는 기록이 섞이면 평가 목록과 평균이 오염된다.** 그래서 [01-erd.md](../01-erd.md)가 `application_notes` 를 따로 뒀다.

**한 문서를 여럿이 고치는 구조가 아니라 각자 행을 추가하는 구조**다 ([ADR-0005](../adr/0005-실시간-공동편집-제외.md)). 그래서 동시 편집 충돌 처리가 필요 없다 — 다만 **본인 메모 수정 시에는** 덮어쓰기 감지가 필요하다.

## 선행 조건 — 없으면 중단

아래가 하나라도 아니면 **시작하지 말고 팀 채널에 알린다.** 없는 것을 상상해서 만들지 않는다.

- [ ] [docs/01-erd.md](../01-erd.md)가 확정 상태다
- [ ] [D1 지원자 목록 · 상세 API](D1-지원자-API.md) PR이 머지돼 있다

## 가장 중요한 규칙

- **[backend/app/models.py](../../backend/app/models.py)를 수정하지 않는다.** 컬럼이 부족해 보여도 추가하지 않는다. 멈추고 팀 채널에 묻는다.
- **[docs/01-erd.md](../01-erd.md)·[docs/02-api.md](../02-api.md)를 수정하지 않는다.** 공용 문서다.
- **인증·권한 코드를 넣지 않는다.** 인증은 팀장 담당(A1~A3)이고 아직 없다. 토큰 검사를 흉내 내면 나중에 팀장 것과 충돌한다. 사용자 id 가 필요한 자리는 `# TODO(A1): 토큰의 사용자로 채운다` 주석만 남긴다.
- **`main.py` 는 `include_router` 한 줄만** 건드린다. 그 파일의 다른 부분은 손대지 않는다.
- **`backend/app/api/notes.py` 만 만든다.**
- **메모를 `evaluations` 에 넣지 않는다.** 두 테이블을 나눈 이유가 사라진다.
- **작성자 검사는 코드에서 한다** ([01-erd.md](../01-erd.md) 명시). 인증이 아직 없으므로 지금은 자리만 만들고 `TODO(A1)` 주석을 남긴다.

## 완료 조건

- [ ] `backend/app/schemas/note.py` — `NoteCreate` · `NoteUpdate` · `NoteOut`
- [ ] `backend/app/api/notes.py` — 라우터
- [ ] `GET /api/v1/applications/{id}/notes` — **최신순**. 작성자 이름·시각 포함
- [ ] `POST /api/v1/applications/{id}/notes` — 작성. 성공 201
- [ ] `PATCH /api/v1/notes/{id}` — 수정
- [ ] `body` 가 빈 문자열이거나 공백뿐이면 **422**
- [ ] **덮어쓰기 감지**: `PATCH` 본문에 `updated_at` 을 함께 받아 DB 값과 다르면 **409** ([ADR-0005](../adr/0005-실시간-공동편집-제외.md))
- [ ] 없는 지원자·메모 → **404**
- [ ] `main.py` 에 `include_router` 한 줄

## 완성 예시

**이 형태를 그대로 따른다.**

```python
# backend/app/api/notes.py (핵심만)
@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: int, body: NoteUpdate, db: Session = Depends(get_db)):
    note = db.get(ApplicationNote, note_id)
    if note is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "메모를 찾을 수 없습니다")

    # TODO(A1): 토큰의 사용자와 note.author_id 를 비교해 다르면 403

    # ADR-0005 — 공동 편집을 안 하는 대신, 남의 수정을 모르고 덮어쓰는 것만 막는다.
    # 클라이언트가 읽어 간 시점의 updated_at 과 지금 DB 값이 다르면 그 사이 누가 고친 것이다.
    if body.updated_at != note.updated_at:
        raise HTTPException(http.HTTP_409_CONFLICT,
                            "다른 사람이 먼저 수정했습니다. 새로고침 후 다시 시도하세요")

    note.body = body.body
    db.commit()
    return NoteOut.model_validate(note)
```

빈 메모는 막는다.

```python
class NoteCreate(BaseModel):
    # 공백만 있는 메모가 목록을 채우면 아무도 안 읽게 된다
    body: str = Field(min_length=1)

    @field_validator("body")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("내용을 입력하세요")
        return v
```

## 참고 문서

- [docs/01-erd.md](../01-erd.md) — `application_notes` 표와 그 위 설명
- [docs/02-api.md](../02-api.md) — "메모" 표
- [ADR-0005](../adr/0005-실시간-공동편집-제외.md) — 왜 공동 편집을 안 하는가

## Claude에게 시키기

작업 폴더에서 Claude Code를 열고 **아래를 순서대로 하나씩** 붙여넣는다.

```
0단계.
docs/01-erd.md 의 application_notes 표와 바로 위 설명, docs/02-api.md 의 메모 표,
docs/adr/0005-실시간-공동편집-제외.md 를 읽어라.

읽은 뒤 아래를 알려줘라. 아직 파일을 만들지 마라.
- 메모를 evaluations 와 나눈 이유
- 공동 편집을 안 하는데도 PATCH 에 덮어쓰기 감지가 필요한 이유
```

```
1단계.
backend/app/schemas/note.py 를 만들어라.
NoteCreate 는 body 만 받되 공백만 있는 값을 거절한다(422).
NoteUpdate 는 body 와 updated_at 을 받는다.
NoteOut 은 id, body, author_id, created_at, updated_at 을 준다.
```

```
2단계.
backend/app/api/notes.py 에 라우터를 만들어라.
- GET /api/v1/applications/{id}/notes : 최신순
- POST /api/v1/applications/{id}/notes : 201
- PATCH /api/v1/notes/{id} : 본문의 updated_at 이 DB 값과 다르면 409
없는 지원자/메모는 404.
author_id 는 지금 채울 수 없다 — None 으로 두고 TODO(A1) 주석을 남겨라.
작성자 검사 자리도 TODO(A1) 주석으로 남겨라.
```

```
3단계.
main.py 에 include_router 한 줄을 추가하고 아래 검증을 실행해 결과를 보여줘라.
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
P=localhost:8000/api/v1
curl -s -X POST $P/applications/1/notes -H 'content-type: application/json' -d '{"body":"전화 안 받음. 내일 재시도"}'
curl -s -o /dev/null -w '빈메모 %{http_code}\n' -X POST $P/applications/1/notes -H 'content-type: application/json' -d '{"body":"   "}'
U=$(curl -s $P/applications/1/notes | python -c 'import sys,json;d=json.load(sys.stdin);print(d[0]["updated_at"])')
curl -s -o /dev/null -w '정상수정 %{http_code}\n' -X PATCH $P/notes/1 -H 'content-type: application/json' -d "{\"body\":\"수정됨\",\"updated_at\":\"$U\"}"
curl -s -o /dev/null -w '낡은버전 %{http_code}\n' -X PATCH $P/notes/1 -H 'content-type: application/json' -d "{\"body\":\"또수정\",\"updated_at\":\"$U\"}"
curl -s -o /dev/null -w '없는메모 %{http_code}\n' -X PATCH $P/notes/99999 -H 'content-type: application/json' -d '{"body":"x","updated_at":"2026-01-01T00:00:00Z"}'
```

기대 결과:

- 메모 작성 → **201**, 목록에 **최신순**으로 보인다
- 공백만 있는 메모 → **422**
- 올바른 `updated_at` 으로 수정 → **200**
- **낡은 `updated_at` 으로 다시 수정 → 409** (덮어쓰기 감지가 동작한다)
- 없는 메모 → **404**
- `evaluations` 테이블에 행이 생기지 않았다

## 막히면 · 되돌리기

- **30분 넘게 막히면 혼자 붙들지 말고 팀 채널에 묻는다.**
- **결과가 이상해지면 고치려 들지 말고 버린다.**

```bash
git checkout -- .
```

그래도 이상하면 브랜치째 버리고 처음부터 다시 시작한다.

```bash
git checkout main && git branch -D feat/d7-notes-api
```

- **`git status`에 `models.py` · `docs/` · 다른 사람 파일이 떠 있으면 범위를 벗어난 것이다.** 되돌리고 팀 채널에 알린다.

## PR 체크리스트

- [ ] PR 본문에 위 검증 결과를 붙였다
- [ ] `models.py` · `docs/` · 다른 사람 파일을 **수정하지 않았다**
- [ ] 스키마 변경 없음
