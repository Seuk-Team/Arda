# 검색 성능 — 인덱스 튜닝 전/후 측정 (H1·H2)

> 작성: woojeongalex · 2026-08-25 · 큐 18번 ([H5 지시서](02_tasks/H5-인덱스-튜닝.md))
>
> **이 문서는 제안이다.** 인덱스 추가는 스키마 변경이라 [CLAUDE.md](../CLAUDE.md) 규칙상
> 팀장 합의가 필요하다. `models.py`·`01-erd.md` 는 고치지 않았다.

## 측정 환경

| | |
|---|---|
| DB | PostgreSQL 16 (alpine, 컨테이너, 기본 설정) |
| 데이터 | `applications` 100,000건 (J7 생성기, `--count 100000`) |
| 테이블 크기 | 162 MB |
| 측정 방법 | `EXPLAIN (ANALYZE, BUFFERS)` 3회 실행 후 **중앙값** |
| 대상 쿼리 | `GET /api/v1/applications` 가 실제로 만드는 SQL 형태 |

측정 전 `ANALYZE applications` 로 통계를 갱신했다. 통계가 낡으면 플래너가 엉뚱한 계획을
고르고, 그러면 인덱스 유무와 무관한 수치를 재게 된다.

## 시작 시점의 인덱스

| 인덱스 | 컬럼 | 크기 | 목적 |
|---|---|---|---|
| `applications_pkey` | `id` | 2.3 MB | PK, 자동 |
| `uq_applications_posting_email` | `(job_posting_id, email)` | 7.6 MB | 중복 지원 방지(C6)의 부산물 |
| `ix_applications_posting_stage` | `(job_posting_id, current_stage)` | 0.8 MB | 칸반·단계 필터(H2) |

`uq_applications_posting_email` 은 선행 컬럼이 `job_posting_id` 라서 **이메일 단독 검색에는
쓰이지 않는다** (B-tree 는 왼쪽 접두사부터 맞아야 탄다).

---

## ① 전체 목록 50건

```sql
SELECT * FROM applications ORDER BY created_at DESC, id DESC LIMIT 50;
```

| | 실행 시간 | 계획 |
|---|---|---|
| 전 | **26.216 ms** | `Parallel Seq Scan` (rows=33333×3) + `Sort Method: top-N heapsort` |
| 후 | **0.253 ms** | `Index Scan using ix_applications_created_id` (actual rows=50) |

**104배.**

**왜 느렸나**: 정렬 기준 컬럼에 인덱스가 없으니 10만 행을 전부 읽어 정렬해야 했다.
`top-N heapsort` 는 상위 50개만 유지하는 최적화지만, **모든 행을 한 번씩 보는 것 자체는
피할 수 없다.** 워커 3개가 나눠 읽어도 총 작업량은 같다.

**무엇을 걸었나**: `(created_at DESC, id DESC)` B-tree. 인덱스가 이미 그 순서로 정렬돼
있으므로 정렬 단계가 사라지고, 앞에서 50개만 읽고 멈춘다 (`actual rows=50`).

---

## ② 이름·이메일 부분 검색

```sql
SELECT * FROM applications
WHERE (name ILIKE '%김%' OR email ILIKE '%김%')
ORDER BY created_at DESC, id DESC LIMIT 50;
```

| | 실행 시간 | 계획 |
|---|---|---|
| 전 | **100.825 ms** | `Seq Scan` (추정 2,022행 / 실제 1,483행) |
| 후 | **7.722 ms** | `Index Scan using ix_applications_created_id` + Filter |

**13배.**

**왜 느렸나**: `%김%` 은 앞이 열려 있어 B-tree 로 좁힐 구간이 없다. 10만 행을 전부 읽고
1,483건을 걸러냈다.

**무엇이 바꿨나**: **trgm 이 아니라 `created_at` 인덱스가 해결했다.**
`LIMIT 50` 덕분에 플래너가 "정렬된 순서로 읽으면서 조건에 맞는 것 50개를 채우면 중단"
전략을 쓸 수 있게 됐다. 1,483건이 10만 건에 고루 퍼져 있어 앞쪽 몇천 행만 봐도 50개가
채워진다.

**추정 vs 실제**: 2,022 추정 / 1,483 실제 — 36% 과대추정. 부분 문자열의 선택도는
통계로 정확히 잡기 어렵다. 다만 이 정도 오차로 계획이 뒤집히지는 않았다.

### pg_trgm GIN 을 시험한 결과 — **추가하지 않기를 권한다**

지시서가 지정한 대로 `pg_trgm` GIN 을 만들어 시험했다.

```sql
CREATE EXTENSION pg_trgm;
CREATE INDEX ix_applications_name_trgm  ON applications USING gin (name  gin_trgm_ops);
CREATE INDEX ix_applications_email_trgm ON applications USING gin (email gin_trgm_ops);
```

| 검색어 | 플래너 선택 | 실행 시간 |
|---|---|---|
| `%김%` (1글자, 1,483건 매칭) | **Seq Scan** — trgm 을 쓰지 않음 | 105.454 ms |
| `%김%` — `enable_seqscan=off` 로 trgm 강제 | `BitmapOr` + 두 trgm 인덱스 | **465.020 ms** |
| `%최영수민%` (4글자, 0건 매칭) | 자율적으로 **trgm 선택** | **0.234 ms** |

**강제로 쓰게 하면 4.4배 느려진다. 플래너 판단이 옳았다.**

강제 실행의 계획을 보면 이유가 드러난다.

```
Bitmap Index Scan on ix_applications_name_trgm  (actual rows=100000)
Bitmap Index Scan on ix_applications_email_trgm (actual rows=100000)
```

**인덱스가 10만 행을 전부 돌려준다.** trgm 은 문자열을 3글자 단위로 쪼개 색인하는데,
한글 **1글자** 검색어는 유의미한 3-gram 이 나오지 않아 사실상 모든 행과 매칭된다.
인덱스가 전혀 걸러주지 못하고, 그 뒤 heap 을 다시 읽어 `ILIKE` 를 재확인하면서
Seq Scan 보다 비싼 일을 한다.

**그런데 한국 이름 검색의 실제 패턴이 1~2글자다** — 담당자는 "김", "이수" 처럼 친다.
바로 그 구간에서 trgm 이 무력하다. 3글자 이상이면 450배 빨라지지만(0.234 ms),
그건 이메일 조각 검색 같은 부수적 경우다.

**비용 대비**: 두 인덱스 합계 **11.8 MB** (name 3.4 MB + email 8.4 MB), 생성에 각각
217 ms · 677 ms. 쓰기마다 GIN 갱신 부담도 진다. **이득이 나는 구간이 실제 사용 패턴과
어긋나므로 지금은 추가하지 않기를 권한다.**

재검토 조건: 검색어 3글자 이상이 주 패턴이 되거나, 자소서 본문 검색(02-api.md 가 유보한
항목)을 열 때. 그때는 이 문서의 수치가 그대로 근거가 된다.

### OR 를 UNION 으로 쪼개는 것도 시험했다 — **더 느리다**

trgm 이 `OR` 때문에 안 걸리는 것이라면 `UNION` 으로 나누면 될까 싶어 재봤다.

| 형태 | 실행 시간 |
|---|---|
| `WHERE name ILIKE ... OR email ILIKE ...` | **7.886 ms** |
| `... UNION ...` 후 정렬 | **71.626 ms** |

**9배 느리다.** `UNION` 은 양쪽 결과를 **전부** 만들고 중복 제거까지 한 뒤에야 정렬·
`LIMIT` 이 적용된다. ①에서 얻은 "50개 채우면 중단" 최적화가 통째로 사라진다.
코드를 바꿀 이유가 없다.

---

## ③ 단계 필터

```sql
SELECT * FROM applications
WHERE current_stage IN ('screening','interview')
ORDER BY created_at DESC, id DESC LIMIT 50;
```

| | 실행 시간 | 계획 |
|---|---|---|
| 전 | **27.953 ms** | `Parallel Seq Scan` (추정 16,565×3 / 실제 13,333×3) + `top-N heapsort` |
| 후 | **0.431 ms** | `Index Scan using ix_applications_created_id` + Filter |

**65배.**

**왜 느렸나**: `ix_applications_posting_stage` 는 선행 컬럼이 `job_posting_id` 다.
`current_stage` 단독 조건으로는 **왼쪽 접두사가 맞지 않아 탈 수 없다.** 정렬 대상도
인덱스가 없어 ①과 같은 상황이 된다.

**무엇이 바꿨나**: 여기서도 `created_at` 인덱스다. 두 단계가 전체의 40%(4만 건)라
정렬 순서로 읽으면 금방 50개가 찬다.

### `(current_stage, created_at DESC)` 복합 인덱스는 필요 없다

지시서 예시에 있던 조합을 만들어 비교했다.

| 인덱스 구성 | ③ 단계 필터 | ④ 공고+단계 |
|---|---|---|
| `created_id` + `stage_created` 둘 다 | 0.473 ms | 1.357 ms |
| `created_id` 만 (`stage_created` 제거) | **0.450 ms** | **1.400 ms** |

**빼는 편이 오히려 미세하게 빠르다.** ③은 어느 쪽이든 `created_id` 를 고르고, ④는 기존
`ix_applications_posting_stage` 로 충분하다. `pg_stat_user_indexes` 에서도 `stage_created`
사용 횟수가 3회에 그쳤고 그마저 `created_id` 로 대체된다.

**컬럼 순서를 왜 그렇게 볼 수 있나**: 복합 인덱스는 **선행 컬럼이 등치(=)로 좁혀질 때**
값어치가 있다. `current_stage` 는 값이 5개뿐이라 한 값이 전체의 15~50%를 차지한다.
그 정도로는 못 좁히고, 뒤따르는 `created_at` 정렬만 얻는데 그건 `created_id` 가 이미 준다.
반면 `job_posting_id` 는 공고 10개로 나뉘어 10%씩 좁히므로 ④에서 제 역할을 한다.

**4.3 MB 를 쓰면서 이득이 0 이므로 추가하지 않기를 권한다.**

---

## ④ 공고 + 단계 복합

```sql
SELECT * FROM applications
WHERE job_posting_id = 3 AND current_stage = 'interview'
ORDER BY created_at DESC, id DESC LIMIT 50;
```

| | 실행 시간 | 계획 |
|---|---|---|
| 전 | **1.315 ms** | `Index Scan using ix_applications_posting_stage` (추정 1,439 / 실제 1,500) |
| 후 | **1.305 ms** | 동일 |

**변화 없음 — 그리고 그게 맞다.**

기존 `ix_applications_posting_stage (job_posting_id, current_stage)` 가 이미 제 역할을
하고 있다. 두 조건 모두 등치라 선행 컬럼부터 정확히 좁혀지고, 1,500건만 읽어 정렬한다.
추정치(1,439)와 실제(1,500)의 차이도 4% 로 통계가 정확하다.

**이 쿼리는 손댈 곳이 없다.** 측정하지 않았으면 "인덱스를 걸었더니 전부 빨라졌다"고
잘못 말할 뻔했다.

---

## 인덱스의 비용

권장 인덱스 하나(`ix_applications_created_id`)만 적용한 상태로 쟀다.

| 항목 | 값 |
|---|---|
| 인덱스 크기 | **3.2 MB** (테이블 162 MB 대비 2%) |
| 생성 시간 | 89.6 ms (10만 건 기준) |
| `INSERT` 1,000건 | 36.116 ms → **42.981 ms** |
| 건당 쓰기 | 0.036 ms → **0.043 ms** (**+19%**) |

쓰기가 19% 느려지지만 절대값이 건당 0.007 ms 다. 지원서 접수는 초당 수백 건이 들어오는
작업이 아니라 **감당할 수 있다.** 읽기 쪽 이득(13~104배)과 견줄 바가 아니다.

추가하지 않기로 한 것들의 비용은 이렇다.

| 인덱스 | 크기 | 판단 |
|---|---|---|
| `ix_applications_email_trgm` | 8.4 MB | 실제 검색 패턴에서 무력 — 보류 |
| `ix_applications_name_trgm` | 3.4 MB | 위와 같음 — 보류 |
| `ix_applications_stage_created` | 4.3 MB | 이득 0 — 보류 |

---

## 인덱스로 풀 수 없는 병목 — API 의 `total`

인덱스 적용 후 API 응답을 쟀더니 SQL 보다 훨씬 느렸다.

| API | `took_ms` | 페이지 조회 SQL | 차이 |
|---|---|---|---|
| 목록 50건 | 9.5 ms | 0.25 ms | 9.2 ms |
| 이름 검색 `q=김` | **109.3 ms** | 7.7 ms | **101.6 ms** |
| 단계 필터 | 5.1 ms | 0.43 ms | 4.7 ms |

원인은 `search.py` 가 **페이지 조회와 별도로 `total` 을 세는 COUNT 를 실행**하기 때문이다.
그 COUNT 에는 `LIMIT` 이 없다 — 조건에 맞는 행을 **전부** 세야 한다.

| COUNT 쿼리 | 실행 시간 | 계획 |
|---|---|---|
| 전체 | 9.677 ms | `Index Only Scan` (pkey) — 10만 행 전부 훑음 |
| 검색 `q=김` | **104.477 ms** | **`Seq Scan`** |
| 단계 필터 | 3.615 ms | `Index Only Scan` (posting_stage) |

검색 API 109.3 ms ≈ COUNT 104.5 ms + 페이지 7.7 ms 로 정확히 설명된다.

**여기에는 인덱스가 답이 아니다.** ①~③이 빨라진 이유가 "50개 채우면 중단" 인데, COUNT 는
중단할 수 없다. 대응은 코드 쪽이다.

1. **커서 페이지네이션에서는 `total` 을 생략한다** — H4(#66)에서 커서를 넣었고, 커서로
   넘기는 화면은 "총 몇 건"이 필요 없다. `with_total=false` 같은 옵션으로 끄면 검색이
   109 ms → 8 ms 가 된다.
2. **근사치를 쓴다** — 필터 없는 전체 건수는 `pg_class.reltuples` 로 0.1 ms 에 얻는다.
   "약 100,000건" 표기면 충분한 화면이 많다.
3. **상한을 둔다** — `LIMIT 1000` 을 씌워 세고 "1000건 이상"으로 표기한다.

**이건 인덱스 제안(이 PR)과 별개의 코드 변경이라 여기서는 측정과 제안까지만 남긴다.**

---

## 후속 — 1번(`with_total`)을 구현한 뒤 (2026-08-26)

위 제안 중 **1번만** 넣었다. `GET /applications` 에 `with_total` 을 추가하고, `false` 면
COUNT 를 건너뛰고 `total` 을 `null` 로 준다. 기본값은 `true` 라 기존 호출은 그대로다.

같은 10만 건 DB, 각 11회 실행 중앙값(괄호는 최소값):

| 케이스 | `with_total=true` | `with_total=false` | 배 | 건수 |
|---|---|---|---|---|
| 필터 없음 | 11.7 ms (7.9) | **2.9 ms** (2.2) | 4.0x | 100,000 |
| 검색 `q=김` | 111.0 ms (103.6) | **7.8 ms** (7.4) | **14.2x** | 1,550 |
| 검색 `q=김민준` | 203.3 ms (197.0) | 102.0 ms (97.8) | 2.0x | 5 |
| 단계 필터 | 4.1 ms (3.9) | **2.6 ms** (2.4) | 1.6x | 15,000 |
| `sort=score` | 181.1 ms (172.2) | 170.0 ms (168.4) | 1.1x | 100,000 |

예측한 대로 `q=김` 이 **111 ms → 7.8 ms** 가 됐다. 다만 재는 김에 **남는 병목 둘이
드러났고, 둘 다 `total` 과 상관없다.**

### 남는 병목 ① — 선택도가 높은 부분 일치 검색 (`q=김민준`, 102 ms)

`total` 을 꺼도 102 ms 다. 위 ①~③이 빨랐던 이유가 "50개 채우면 중단"인데, **10만 건에서
5건만 맞으면 중단할 지점이 없다.** `ILIKE '%김민준%'` 는 끝까지 훑는다. 검색어가 짧을수록
(=많이 맞을수록) 빠르고 구체적일수록 느린, 직관과 반대인 특성이다.

세 글자 이상이면 `pg_trgm` GIN 이 듣는 구간이다. 이 문서 앞쪽에서 pg_trgm 을 물린 이유는
**한글 1글자** 검색에서 플래너가 안 골랐기 때문이라, "짧은 검색어"와 "긴 검색어"의 사정이
서로 다르다. 다시 재볼 값어치가 있다 — 다만 인덱스는 스키마라 측정·제안까지가 이 도메인이다.

### 남는 병목 ② — `sort=score` (170 ms)

`total` 을 꺼도 170 ms 로 거의 안 줄었다. `LIMIT 51` 을 걸어도 소용이 없는데, **정렬 키가
집계값이라 10만 그룹을 전부 만든 뒤에야 순서를 정할 수 있기 때문이다.**

```
GroupAggregate (rows=100000) (actual time=0.069..36.019)
  -> Merge Left Join (rows=100000)
       -> Index Only Scan Backward using applications_pkey (Heap Fetches: 0)
```

인덱스로 풀리는 종류가 아니다. 평균 점수를 `applications` 에 물려 두는(비정규화) 쪽이라야
하는데 그건 스키마 변경이다. **측정만 남긴다.**

---

## 팀장 합의 후 `models.py` 에 반영할 제안

**추가 1건만 권한다.**

```sql
CREATE INDEX ix_applications_created_id
    ON applications (created_at DESC, id DESC);
```

`models.py` 의 `Application.__table_args__` 에는 이렇게 들어간다.

```python
# 목록·검색의 기본 정렬. id 는 커서 페이지네이션(H4)의 tie-breaker 라 함께 건다.
Index("ix_applications_created_id",
      text("created_at DESC"), text("id DESC")),
```

| | |
|---|---|
| 이득 | ① 104배 · ② 13배 · ③ 65배 |
| 비용 | 3.2 MB, 쓰기 +19% (건당 +0.007 ms) |
| 부수 효과 | H4 커서 페이지네이션(`ORDER BY created_at DESC, id DESC`)이 그대로 탄다 |

**보류를 권하는 것** (측정 근거는 위 각 절에).

```sql
-- 실제 검색 패턴(한글 1~2글자)에서 이득이 없다. 3글자 이상이 주 패턴이 되면 재검토.
-- CREATE INDEX ix_applications_name_trgm  ON applications USING gin (name  gin_trgm_ops);
-- CREATE INDEX ix_applications_email_trgm ON applications USING gin (email gin_trgm_ops);

-- current_stage 는 값이 5개뿐이라 선행 컬럼으로 못 좁힌다. 이득 0.
-- CREATE INDEX ix_applications_stage_created ON applications (current_stage, created_at DESC);
```

## 재현 방법

```bash
docker run -d --name arda-perf -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=arda -p 5433:5432 postgres:16-alpine
DATABASE_URL='postgresql+psycopg://postgres:postgres@localhost:5433/arda' \
  uv run python backend/scripts/seed_dummy.py --count 100000
psql "$DATABASE_URL" -c 'ANALYZE applications;'
psql "$DATABASE_URL" -c "EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM applications ORDER BY created_at DESC, id DESC LIMIT 50;"
```
