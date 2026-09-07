import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import PageHead from '../components/PageHead'
import { ApiError } from '../api/client'
import { assignments, postings as postingsApi, schedules } from '../api/endpoints'
import type { Interview, Posting, Stage } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import styles from './Dashboard.module.css'

/* ── 대시보드 = 현황판 ────────────────────────────────────────────
   지원자 목록은 여기서 뺐다 (2026-09-07). 사람을 훑는 일은 '지원자' 탭이
   이미 하고, 대시보드는 "회사가 지금 어떻게 돌아가나"에만 답한다.
   위에서 아래로 얼마나 → 어디가 → 언제 순이다.

   부르는 API 는 셋뿐이고 전부 이미 열려 있다:
     GET /postings                      → status · d_day · stage_counts
     GET /schedules?from&to             → 확정 면접
     GET /interviewers/{me}/applications → 내 배정 수
   백엔드 변경 없음. */

/* 심사 중 3단. 같은 색상의 밝기 계단이라 이 순서가 곧 단계다 (05-design §1).
   합격·불합격은 여기 넣지 않는다 — 아래 DONE 참고. */
const LIVE: { stage: Stage; label: string; color: string }[] = [
  { stage: 'applied', label: '접수', color: 'var(--stage-1)' },
  { stage: 'screening', label: '서류', color: 'var(--stage-2)' },
  { stage: 'interview', label: '면접', color: 'var(--stage-3)' },
]

/* 심사가 끝난 두 갈래. 막대를 그리지 않는다 —
   한번 되면 영원히 쌓이는 누적값이라 심사 중 세 칸과 같은 자를 쓰면
   시간이 갈수록 앞 세 칸이 실오라기가 된다. 견줄 대상이 아니다.
   덤으로 --ok 와 --danger 는 적록색약에서 ΔE 3.5 라 나란히 두면 경계가 안 보인다. */
const DONE: { stage: Stage; label: string; color: string }[] = [
  { stage: 'accepted', label: '합격', color: 'var(--ok-text)' },
  { stage: 'rejected', label: '불합격', color: 'var(--danger)' },
]

/* 표에 싣는 진행 중 공고 수. 넘치면 잘라내고 "외 n개" 를 단다 —
   스크롤을 만들면 현황판이 목록이 된다 */
const TABLE_LIMIT = 6

/* 면접은 한국에서 열린다 — 캘린더 화면(Interviews.tsx)과 같은 규칙 */
const timeFmt = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false,
})
const dayFmt = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
})

function hhmm(iso: string): string {
  return timeFmt.format(new Date(iso))
}

function isoDayKey(iso: string): string {
  const p = dayFmt.formatToParts(new Date(iso))
  const g = (t: string) => p.find((x) => x.type === t)?.value ?? ''
  return `${g('year')}-${g('month')}-${g('day')}`
}

function dayKey(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

function addDays(d: Date, n: number): Date {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

/* 주 시작은 일요일 — 캘린더 화면이 이미 그렇게 잡고 있다(국내 관행).
   여기서만 월요일로 두면 같은 주가 두 화면에서 다르게 보인다. */
const DOW = ['일', '월', '화', '수', '목', '금', '토']

function startOfWeek(d: Date): Date {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return addDays(x, -x.getDay())
}

/* d_day 는 서버가 응답 시점에 계산해 준다(PostingOut.d_day) — 양수가 남은 일수다.
   음수(마감 지남)는 진행 중 공고에는 안 나온다: 백엔드가 조회할 때 자동으로
   닫는다(postings.py _expire). 그래도 방어적으로 그려 둔다. */
function ddayOf(v: number | null): { text: string; tone: string } {
  if (v === null) return { text: '상시', tone: styles.ddayCalm }
  if (v < 0) return { text: `D+${-v}`, tone: styles.ddayHot }
  if (v === 0) return { text: 'D-DAY', tone: styles.ddayHot }
  if (v <= 3) return { text: `D-${v}`, tone: styles.ddayWarn }
  return { text: `D-${v}`, tone: styles.ddayCalm }
}

interface Data {
  /* 나에게 배정된 지원자 수. assignments.mine().count 는 배정 전체라
     내가 이미 평가한 건도 들어간다 — 그래서 '리뷰 대기'가 아니라 '배정'이다 */
  mine: number
  open: Posting[]
  /* 이번 주 확정 면접. mine 을 안 붙였으므로 회사 전체다 (ADR-0017) */
  week: Interview[]
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!user) return
    const ac = new AbortController()

    const from = startOfWeek(new Date())
    const to = addDays(from, 7)

    Promise.all([
      assignments.mine(user.id, ac.signal),
      postingsApi.list(ac.signal),
      schedules.interviews({ from: from.toISOString(), to: to.toISOString() }, ac.signal),
    ])
      .then(([assigned, all, ivs]) => {
        setError(null)
        setData({
          mine: assigned.count,
          /* 진행 중 공고만 싣는다. 마감·초안의 지원자는 더 이상 움직이지 않아서
             현황에 섞으면 숫자만 부푼다 */
          open: all.filter((p) => p.status === 'open'),
          week: ivs.items,
        })
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '대시보드를 불러오지 못했습니다')
      })

    return () => ac.abort()
  }, [user])

  /* ── 회사 합계 — 아래 표의 롤업이다. 두 블록의 합은 항상 같아야 한다 ── */
  const totals = useMemo(() => {
    const sum = (s: Stage) =>
      (data?.open ?? []).reduce((t, p) => t + (p.stage_counts?.[s] ?? 0), 0)
    const live = LIVE.map((x) => ({ ...x, n: sum(x.stage) }))
    const done = DONE.map((x) => ({ ...x, n: sum(x.stage) }))
    /* 막대는 심사 중 세 칸끼리만 견준다 */
    const max = Math.max(...live.map((x) => x.n), 1)
    return {
      live: live.map((x) => ({ ...x, pct: `${Math.round((x.n / max) * 100)}%` })),
      done,
    }
  }, [data])

  /* ── 공고별 — 막대 길이를 공고끼리 하나의 자에 맞춘다.
       각 공고를 100% 로 채우면 34명짜리와 5명짜리가 같은 길이가 되어 비교가 죽는다 ── */
  const rows = useMemo(() => {
    const list = (data?.open ?? []).map((p) => {
      const c = p.stage_counts ?? {}
      const live = LIVE.map((x) => c[x.stage] ?? 0)
      return {
        p,
        live,
        liveSum: live.reduce((a, b) => a + b, 0),
        accepted: c.accepted ?? 0,
        rejected: c.rejected ?? 0,
        total: p.application_count,
      }
    })
    const max = Math.max(...list.map((r) => r.liveSum), 1)
    return list.map((r) => ({ ...r, width: `${Math.round((r.liveSum / max) * 100)}%` }))
  }, [data])

  /* ── 이번 주 면접 — 요일별 확정 건수. 지금 백엔드로 그릴 수 있는 유일한 시계열 ── */
  const week = useMemo(() => {
    const from = startOfWeek(new Date())
    const counts = new Map<string, number>()
    for (const iv of data?.week ?? []) {
      const k = isoDayKey(iv.start_at)
      counts.set(k, (counts.get(k) ?? 0) + 1)
    }
    const todayKey = dayKey(new Date())
    const days = Array.from({ length: 7 }, (_, i) => {
      const d = addDays(from, i)
      const k = dayKey(d)
      return { key: k, dow: DOW[d.getDay()], n: counts.get(k) ?? 0, today: k === todayKey }
    })
    const max = Math.max(...days.map((d) => d.n), 1)
    /* 0 건인 날은 막대를 그리지 않는다 — 높이 0 짜리를 억지로 남기면
       "아주 적음" 으로 읽힌다. 없는 것과 적은 것은 다르다 */
    return days.map((d) => ({ ...d, h: d.n === 0 ? 0 : Math.round((d.n / max) * 100) }))
  }, [data])

  const today = useMemo(() => {
    const k = dayKey(new Date())
    return (data?.week ?? [])
      .filter((iv) => isoDayKey(iv.start_at) === k)
      .sort((a, b) => a.start_at.localeCompare(b.start_at))
  }, [data])

  const shown = rows.slice(0, TABLE_LIMIT)
  const hidden = rows.length - shown.length

  return (
    <>
      <PageHead
        title="대시보드"
        meta={
          <div className={styles.meta}>
            {/* 이 화면에서 유일하게 '나' 인 숫자라 앞에 세우고 선으로 회사 숫자와 가른다 */}
            <Link to="/evaluations" className={styles.mine}>
              <span className={styles.metaLabel}>내 배정</span>
              <b className={styles.metaVal}>{data?.mine ?? '—'}</b>
              <span className={styles.metaUnit}>명</span>
            </Link>
            <span className={styles.metaBar} aria-hidden="true" />
            <span className={styles.metaItem}>
              <span className={styles.metaLabel}>진행 중 공고</span>
              <b className={styles.metaVal}>{data?.open.length ?? '—'}</b>
              <span className={styles.metaUnit}>개</span>
            </span>
            <span className={styles.metaItem}>
              <span className={styles.metaLabel}>이번 주 면접</span>
              <b className={styles.metaVal}>{data?.week.length ?? '—'}</b>
              <span className={styles.metaUnit}>건</span>
            </span>
          </div>
        }
      />

      <main className={`page-content ${styles.page}`}>
        {error !== null && <p className={styles.state} role="alert">{error}</p>}

        {/* 좁은 화면 전용 — 제목 띠의 요약 숫자가 폰 폭에 안 들어가 감춰진다.
            그중 '내 배정' 만 여기로 내린다: 나머지 둘은 아래 카드가 이미 말한다 */}
        <Link to="/evaluations" className={styles.mobileMine}>
          <span className={styles.mobileMineLabel}>내 배정</span>
          <b className={styles.mobileMineVal}>{data?.mine ?? '—'}<span className={styles.metaUnit}>명</span></b>
          <span className={styles.mobileMineGo}>평가하러 가기 →</span>
        </Link>

        {/* ── 1. 전체 현황 ───────────────────────────────────── */}
        <section className={styles.card} aria-labelledby="dash-total">
          <div className={styles.cardHead}>
            <h2 id="dash-total" className={styles.cap}>전체 현황</h2>
          </div>

          <div className={styles.totals}>
            {totals.live.map((t) => (
              <div key={t.stage} className={styles.tot}>
                <span className={styles.totLabel}>
                  <span className={styles.dot} style={{ background: t.color }} />
                  {t.label}
                </span>
                <span className={styles.totVal}>
                  {data === null ? '—' : t.n}<span className={styles.totUnit}>명</span>
                </span>
                <span className={styles.totTrack}>
                  <span className={styles.totBar} style={{ width: t.pct, background: t.color }} />
                </span>
              </div>
            ))}

            {/* 심사가 끝난 사람은 파이프라인 밖이다. 그냥 이으면 "5단계" 로 읽힌다 */}
            <span className={styles.totSplit} aria-hidden="true" />

            {totals.done.map((t) => (
              <div key={t.stage} className={styles.tot}>
                <span className={styles.totLabel} style={{ color: t.color }}>
                  <span className={styles.dot} style={{ background: t.color }} />
                  {t.label}
                </span>
                <span className={styles.totVal} style={{ color: t.color }}>
                  {data === null ? '—' : t.n}<span className={styles.totUnit}>명</span>
                </span>
                {/* 막대 없음 — 위 DONE 주석 참고. 자리는 남겨 세 칸과 밑선을 맞춘다 */}
                <span className={styles.totCum}>누적</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── 2. 공고별 현황 ─────────────────────────────────── */}
        <section className={styles.card} aria-labelledby="dash-postings">
          <div className={styles.cardHead}>
            <h2 id="dash-postings" className={styles.cap}>공고별 현황</h2>
            <Link to="/postings" className={styles.go}>공고 전체 →</Link>
          </div>

          {data === null && error === null && <p className={styles.state}>불러오는 중…</p>}
          {data !== null && rows.length === 0 && (
            <p className={styles.state}>진행 중인 공고가 없습니다.</p>
          )}

          {shown.length > 0 && (
            <div className={styles.table} role="table">
              <div className={`${styles.tr} ${styles.th}`} role="row">
                <span role="columnheader">공고</span>
                <span role="columnheader" className={styles.right}>마감</span>
                <span role="columnheader">심사 중 — 어디에 쌓였나</span>
                {/* 색 점이 곧 범례다 — 막대 옆에 범례를 또 달지 않는다 */}
                {LIVE.map((x) => (
                  <span key={x.stage} role="columnheader" className={styles.right}>
                    <span className={styles.dot} style={{ background: x.color }} />
                    {x.label}
                  </span>
                ))}
                {DONE.map((x) => (
                  <span key={x.stage} role="columnheader" className={styles.right} style={{ color: x.color }}>
                    {x.label}
                  </span>
                ))}
                <span role="columnheader" className={styles.right}>총</span>
              </div>

              {shown.map((r) => {
                const dd = ddayOf(r.p.d_day)
                return (
                  <button
                    key={r.p.id}
                    type="button"
                    className={styles.tr}
                    role="row"
                    onClick={() => navigate(`/postings/${r.p.id}`)}
                  >
                    <span className={styles.pname} role="cell">{r.p.title}</span>
                    <span className={`${styles.right} ${styles.dday} ${dd.tone}`} role="cell">{dd.text}</span>
                    <span className={styles.track} role="cell">
                      {/* 칸 사이 2px 은 배경색 틈 — 램프가 밝기 계단이라 틈이 없으면 경계가 뭉갠다 */}
                      <span className={styles.fill} style={{ width: r.width }}>
                        {LIVE.map((x, i) =>
                          r.live[i] > 0 ? (
                            <span key={x.stage} style={{ flex: r.live[i], background: x.color }} />
                          ) : null,
                        )}
                      </span>
                    </span>
                    {/* data-label 은 좁은 화면에서 열 이름 줄이 사라진 뒤 ::before 로 되살아난다 —
                        이름표 없는 숫자는 어느 단계인지 알 수 없어 표가 아니라 낙서가 된다 */}
                    {r.live.map((n, i) => (
                      <span
                        key={LIVE[i].stage}
                        className={`${styles.num} ${n === 0 ? styles.zero : ''}`}
                        data-label={LIVE[i].label}
                        role="cell"
                      >
                        {n}
                      </span>
                    ))}
                    <span
                      className={`${styles.num} ${r.accepted === 0 ? styles.zero : ''}`}
                      style={r.accepted === 0 ? undefined : { color: 'var(--ok-text)' }}
                      data-label="합격"
                      role="cell"
                    >
                      {r.accepted}
                    </span>
                    <span
                      className={`${styles.num} ${r.rejected === 0 ? styles.zero : ''}`}
                      style={r.rejected === 0 ? undefined : { color: 'var(--danger)' }}
                      data-label="불합격"
                      role="cell"
                    >
                      {r.rejected}
                    </span>
                    <span className={`${styles.num} ${styles.numTotal}`} data-label="총" role="cell">{r.total}</span>
                  </button>
                )
              })}
            </div>
          )}

          {hidden > 0 && (
            <Link to="/postings" className={styles.moreLink}>외 {hidden}개 →</Link>
          )}
        </section>

        {/* ── 3. 면접 ────────────────────────────────────────── */}
        <div className={styles.duo}>
          <section className={styles.card} aria-labelledby="dash-week">
            <div className={styles.cardHead}>
              <h2 id="dash-week" className={styles.cap}>이번 주 면접</h2>
              <p className={styles.note}>확정된 것만 · {data?.week.length ?? 0}건</p>
              <Link to="/calendar" className={styles.go}>캘린더 →</Link>
            </div>

            <div className={styles.chart}>
              {week.map((d) => (
                <div key={d.key} className={styles.col}>
                  <span className={`${styles.colVal} ${d.n === 0 ? styles.zero : ''} ${d.today ? styles.colToday : ''}`}>
                    {d.n}
                  </span>
                  <span className={styles.colBarBox}>
                    <span
                      className={`${styles.colBar} ${d.today ? styles.colBarToday : ''}`}
                      style={{ height: `${d.h}%` }}
                    />
                  </span>
                  <span className={`${styles.colDow} ${d.today ? styles.colToday : ''}`}>{d.dow}</span>
                </div>
              ))}
            </div>
          </section>

          <section className={styles.card} aria-labelledby="dash-today">
            <div className={styles.cardHead}>
              <h2 id="dash-today" className={styles.cap}>오늘 면접</h2>
              <p className={`${styles.note} ${styles.noteOn}`}>{today.length}건</p>
            </div>

            {data !== null && today.length === 0 && (
              <p className={styles.state}>오늘 잡힌 면접이 없습니다. 확정된 일정만 표시됩니다.</p>
            )}

            <div className={styles.ivList}>
              {today.map((iv, i) => (
                <button
                  key={iv.proposal_id}
                  type="button"
                  className={styles.iv}
                  onClick={() => navigate('/calendar')}
                >
                  {/* 다음 차례 한 건만 강조한다. 넷 다 강조하면 강조가 아니다 */}
                  <span className={`${styles.ivTime} ${i === 0 ? styles.ivNext : ''}`}>{hhmm(iv.start_at)}</span>
                  <span className={styles.ivName}>{iv.applicant_name}</span>
                  <span className={styles.ivPosting}>{iv.posting_title}</span>
                  <span className={styles.ivWho}>{iv.interviewer_name}</span>
                </button>
              ))}
            </div>
          </section>
        </div>
      </main>
    </>
  )
}
