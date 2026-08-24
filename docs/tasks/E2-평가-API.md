# [E1·E2] 평가 작성 · 목록 · 평균 API

> 담당: 팀원4 · 역할 E(인프라·인증) · 브랜치: `feat/e2-evaluations-api`
> **PR 단위**: 이 지시서 전체 = PR 1개

## 배경

면접관이 점수와 코멘트를 남기고, 담당자가 평균을 본다. [E1 평가 현황 화면](E1-평가-현황-화면.md)이 읽고 쓰는 API 다.

점수는 **1~5 체크 제약**이 DB 에 이미 걸려 있다([01-erd.md](../01-erd.md)). API 도 같은 범위로 막아 **DB 예외가 500 으로 새어 나가지 않게** 한다 — 422 로 돌려줘야 화면이 사용자에게 설명할 수 있다.

## 선행 조건 — 없으면 중단

아래가 하나라도 아니면 **시작하지 말고 팀 채널에 알린다.** 없는 것을 상상해서 만들지 않는다.

- [ ] [docs/01-erd.md](../01-erd.md)가 확정 상태다
- [ ] [J0 앱 뼈대](J0-앱-뼈대.md) PR이 머지돼 있다
- [ ] [D1 지원자 API](D1-지원자-API.md) PR이 머지돼 있다 — 상세 응답에 평가가 이미 들어간다. 형식을 맞춘다

## 가장 중요한 규칙

- **[backend/app/models.py](../../backend/app/models.py)를 수정하지 않는다.** 컬럼이 부족해 보여도 추가하지 않는다. 멈추고 팀 채널에 묻는다.
- **[docs/01-erd.md](../01-erd.md)·[docs/02-api.md](../02-api.md)를 수정하지 않는다.** 공용 문서다.
- **인증·권한 코드를 넣지 않는다.** 인증은 팀장 담당(A1~A3)이고 아직 없다. 토큰 검사를 흉내 내면 나중에 팀장 것과 충돌한다. 사용자 id 가 필요한 자리는 `# TODO(A1): 토큰의 사용자로 채운다` 주석만 남긴다.
- **`main.py` 는 `include_router` 한 줄만** 건드린다. 그 파일의 다른 부분은 손대지 않는다.
- **`backend/app/api/evaluations.py` 만 만든다.**
- **점수 범위를 코드에도 건다.** DB 제약만 믿으면 `IntegrityError` 가 500 으로 나간다.
- **본인 평가만 수정(E5)은 코드에서 검사한다** ([01-erd.md](../01-erd.md) 명시). 인증이 없으므로 자리만 만들고 `TODO(A1)`.

## 완료 조건

- [ ] `backend/app/schemas/evaluation.py` — `EvaluationCreate` · `EvaluationUpdate` · `EvaluationOut` · `EvaluationSummary`
- [ ] `backend/app/api/evaluations.py` — 라우터
- [ ] `POST /api/v1/applications/{id}/evaluations` — 작성. 성공 **201**
- [ ] `GET /api/v1/applications/{id}/evaluations` — 목록 + **평균**. 최신순
- [ ] `PATCH /api/v1/evaluations/{id}` — 수정 (E5 자리)
- [ ] `score` 가 1~5 밖이면 **422** (DB 예외가 아니라 검증으로)
- [ ] 평균은 **소수 첫째 자리**. 평가가 없으면 `null` — `0` 이 아니다
- [ ] 응답에 작성자 이름 포함 (`users` 조인). 지금은 `author_id` 가 없으므로 `null` 허용
- [ ] 없는 지원자 → **404**
- [ ] `main.py` 에 `include_router` 한 줄

## 완성 예시

**이 형태를 그대로 따른다.**

```python
# backend/app/schemas/evaluation.py
class EvaluationCreate(BaseModel):
    # DB 에 체크 제약이 있지만 여기서도 막는다.
    # 제약만 믿으면 IntegrityError 가 500 으로 나가고 화면이 사용자에게 설명할 수 없다
    score: int = Field(ge=1, le=5)
    comment: str | None = None
```

```python
# backend/app/api/evaluations.py (핵심만)
@router.get("/applications/{application_id}/evaluations", response_model=EvaluationSummary)
def list_evaluations(application_id: int, db: Session = Depends(get_db)):
    if db.get(Application, application_id) is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원자를 찾을 수 없습니다")

    rows = db.scalars(
        select(Evaluation)
        .where(Evaluation.application_id == application_id)
        .order_by(Evaluation.created_at.desc())
    ).all()

    # 평가가 없을 때 0 을 주면 "0점을 받았다"로 읽힌다. null 이어야 "아직 없음"이다
    avg = round(sum(e.score for e in rows) / len(rows), 1) if rows else None
    return EvaluationSummary(items=rows, count=len(rows), avg_score=avg)
```

## 참고 문서

- [docs/01-erd.md](../01-erd.md) — `evaluations` 표와 비고(E4·E5)
- [docs/02-api.md](../02-api.md) — "평가 (E)" 표
- `frontend/mockups/mockup-evaluations.html` — 화면이 쓰는 항목
- [D1 지원자 API](D1-지원자-API.md) — 상세 응답의 평가 형식

## Claude에게 시키기

작업 폴더에서 Claude Code를 열고 **아래를 순서대로 하나씩** 붙여넣는다.

```
0단계.
backend/app/models.py 의 Evaluation, docs/01-erd.md 의 evaluations 표와 비고,
docs/02-api.md 의 평가 표, frontend/mockups/mockup-evaluations.html,
backend/app/schemas/application_detail.py 를 읽어라.

읽은 뒤 아래를 알려줘라. 아직 파일을 만들지 마라.
- 점수 범위 제약이 DB 어디에 걸려 있는지
- 상세 API 가 이미 평가를 어떤 형식으로 주고 있는지
```

```
1단계.
backend/app/schemas/evaluation.py 를 만들어라.
score 는 Field(ge=1, le=5) 로 코드에서도 막아라. 왜 DB 제약만 믿으면 안 되는지 주석으로 적어라.
EvaluationSummary 는 items, count, avg_score 를 담고 avg_score 는 float | None 이다.
```

```
2단계.
backend/app/api/evaluations.py 에 라우터를 만들어라.
- POST /api/v1/applications/{id}/evaluations : 201
- GET /api/v1/applications/{id}/evaluations : 최신순 목록 + 평균
- PATCH /api/v1/evaluations/{id} : 수정
평균은 소수 첫째 자리. 평가가 없으면 null 이다. 0 을 주지 마라 — 왜인지 주석으로 적어라.
없는 지원자는 404.
evaluator_id 는 지금 채울 수 없다 — None 과 TODO(A1) 주석.
본인 평가만 수정 가능한 검사 자리도 TODO(A1) 주석으로 남겨라.
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
curl -s $P/applications/1/evaluations | python -c 'import sys,json;print("평가없을때 avg:",json.load(sys.stdin)["avg_score"])'
curl -s -X POST $P/applications/1/evaluations -H 'content-type: application/json' -d '{"score":4,"comment":"기술 스택 적합"}' -o /dev/null -w '작성 %{http_code}\n'
curl -s -X POST $P/applications/1/evaluations -H 'content-type: application/json' -d '{"score":5,"comment":"좋음"}' >/dev/null
curl -s $P/applications/1/evaluations | python -c 'import sys,json;d=json.load(sys.stdin);print("count",d["count"],"avg",d["avg_score"])'
curl -s -o /dev/null -w '점수0 %{http_code}\n' -X POST $P/applications/1/evaluations -H 'content-type: application/json' -d '{"score":0}'
curl -s -o /dev/null -w '점수6 %{http_code}\n' -X POST $P/applications/1/evaluations -H 'content-type: application/json' -d '{"score":6}'
curl -s -o /dev/null -w '없는지원자 %{http_code}\n' $P/applications/999999/evaluations
```

기대 결과:

- 평가가 없을 때 `avg_score` 가 **`null`** (0 이 아니다)
- 작성 → **201**
- 4점·5점 두 건 → `count: 2`, `avg_score: 4.5`
- `score: 0` → **422**, `score: 6` → **422** (500 이 아니다)
- 없는 지원자 → **404**
- 목록이 최신순이다

## 막히면 · 되돌리기

- **30분 넘게 막히면 혼자 붙들지 말고 팀 채널에 묻는다.**
- **결과가 이상해지면 고치려 들지 말고 버린다.**

```bash
git checkout -- .
```

그래도 이상하면 브랜치째 버리고 처음부터 다시 시작한다.

```bash
git checkout main && git branch -D feat/e2-evaluations-api
```

- **`git status`에 `models.py` · `docs/` · 다른 사람 파일이 떠 있으면 범위를 벗어난 것이다.** 되돌리고 팀 채널에 알린다.

## PR 체크리스트

- [ ] PR 본문에 위 검증 결과를 붙였다
- [ ] `models.py` · `docs/` · 다른 사람 파일을 **수정하지 않았다**
- [ ] 스키마 변경 없음
