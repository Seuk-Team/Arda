import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import PageHead from '../components/PageHead'
import { ApiError } from '../api/client'
import { applications, assignments, postings as postingsApi, schedules } from '../api/endpoints'
import type { ApplicationListItem, Interview, Posting, ScheduleStatus, Stage } from '../api/types'
import { STAGE_LABEL, fmtDate } from '../lib/stage'
import { useAuth } from '../auth/AuthContext'
import styles from './Dashboard.module.css'

/* ── 지원자 현황 (리스트 ↔ 칸반) ─────────────────────────────────
   면접 일정·전형 현황 두 카드를 지원자 단위 데이터 하나로 합쳤다 (2026-08-31).
   두 뷰는 같은 데이터의 다른 모양일 뿐이다 — 숫자가 어긋나면 버그다.
   불합격은 대시보드에서 뺀다: 여기는 "지금 움직이는 사람"의 요약이고,
   불합격 목록은 통합검색에서 필터로 본다. */
const PIPE_STAGES: { stage: Stage; pass?: boolean }[] = [
  { stage: 'applied' },
  { stage: 'screening' },
  { stage: 'interview' },
  { stage: 'accepted', pass: true },
]

/* 단계당 표시 인원. 대시보드는 요약이라 전부 그리지 않는다 — 넘치면 "외 n명 →" */
const GROUP_LIMIT = 5

interface PipeGroup {
  stage: Stage
  pass?: boolean
  total: number
  items: ApplicationListItem[]
}

interface DashboardData {
  reviewWaiting: number
  openPostings: Posting[]
  /* 행에 공고명을 붙일 때 쓴다. 목록 API 가 id 만 주므로 여기서 잇는다 */
  postingTitles: Record<number, string>
  pipe: PipeGroup[]
  /* 면접 단계 표시 인원의 일정 상태. 제안이 없으면 null (404) */
  schedules: Record<number, ScheduleStatus | null>
}

/* 면접은 한국에서 열린다 — 지원자 페이지(Schedule.tsx)와 같은 이유로 KST 고정 */
const slotFmt = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', weekday: 'short',
  hour: '2-digit', minute: '2-digit', hour12: false,
})

function fmtSlot(iso: string): string {
  const parts = slotFmt.formatToParts(new Date(iso))
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  return `${get('month')}.${get('day')} (${get('weekday')}) ${get('hour')}:${get('minute')}`
}

/* 공고 카드의 퍼널 레일. 공고의 지원자 화면(PostingApplicants)의 FUNNEL 과 같은
   무채 램프 + 합격 연두 (§1 — 흐름 그래프 한정 허용). 불합격은 대시보드 범위 밖. */
const RAIL: { stage: Stage; color: string }[] = [
  { stage: 'applied', color: '#C9CFC3' },
  { stage: 'screening', color: '#AEB6A8' },
  { stage: 'interview', color: 'var(--neutral)' },
  { stage: 'accepted', color: 'var(--sprout)' },
]

/* ── 면접 일정 축소판 ─────────────────────────────────────────────
   캘린더 화면(Interviews.tsx)과 같은 소스(GET /schedules)를 같은 규칙으로 읽는다 —
   확정된 일정만, 주 시작은 일요일(국내 관행), 칸 배정은 KST 기준.
   여기서 등록·수정은 없다. 넘치는 건 캘린더 화면이 받는다. */
const DOW = ['일', '월', '화', '수', '목', '금', '토']

/* 목록에 그리는 최대 건수. 대시보드는 요약이라 하루치를 다 펴지 않는다 */
const CAL_LIMIT = 4

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
  const parts = dayFmt.formatToParts(new Date(iso))
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  return `${get('year')}-${get('month')}-${get('day')}`
}

function startOfToday(): Date {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

function addDays(d: Date, n: number): Date {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

function startOfWeek(d: Date): Date {
  return addDays(d, -d.getDay())
}

function dayKey(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

function fmtMonth(d: Date): string {
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}`
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { user } = useAuth()

  const [data, setData] = useState<DashboardData | null>(null)
  const [rails, setRails] = useState<Record<number, number[]>>({})
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'list' | 'kanban'>('list')

  useEffect(() => {
    if (!user) return
    const ac = new AbortController()
    setError(null)

    async function load(userId: number) {
      const [assigned, allPostings, pipe] = await Promise.all([
        assignments.mine(userId, ac.signal),
        postingsApi.list(ac.signal),
        Promise.all(
          PIPE_STAGES.map(async (p): Promise<PipeGroup> => {
            const res = await applications.search(
              { stage: p.stage, limit: GROUP_LIMIT, with_total: true },
              ac.signal,
            )
            return { ...p, total: res.total ?? res.items.length, items: res.items }
          }),
        ),
      ])

      /* 면접 단계 표시 인원만 일정 상태를 묻는다 (최대 GROUP_LIMIT 번).
         404 = 아직 제안이 없다 — 에러가 아니라 "일정 없음" 상태다 */
      const ivItems = pipe.find((g) => g.stage === 'interview')?.items ?? []
      const schedulePairs = await Promise.all(
        ivItems.map(async (a) => {
          try {
            return [a.id, await schedules.latest(a.id, ac.signal)] as const
          } catch (err) {
            if (err instanceof ApiError && err.code === 'NOT_FOUND') return [a.id, null] as const
            throw err
          }
        }),
      )

      const open = allPostings.filter((p) => p.status === 'open')
      return {
        data: {
          reviewWaiting: assigned.count,
          openPostings: open,
          postingTitles: Object.fromEntries(allPostings.map((p) => [p.id, p.title])),
          pipe,
          schedules: Object.fromEntries(schedulePairs),
        },
        open,
      }
    }

    load(user.id)
      .then(({ data, open }) => {
        setData(data)
        /* 공고 레일은 공고 수 × 3 호출이라 본 블록 뒤에 따로 채운다 —
           레일이 늦어도 지원자 현황은 먼저 뜬다 */
        return Promise.all(
          open.map(async (p) => {
            const counts = await Promise.all(
              RAIL.map((r) => applications.countByStage(r.stage, p.id, ac.signal)),
            )
            return [p.id, counts] as const
          }),
        ).then((pairs) => setRails(Object.fromEntries(pairs)))
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '대시보드를 불러오지 못했습니다')
      })

    return () => ac.abort()
  }, [user])

  /* 축소판이 보는 날. 주(스트립)는 이 날에서 파생된다 — 상태를 둘로 두면 어긋난다 */
  const [calSel, setCalSel] = useState(startOfToday)
  const [ivs, setIvs] = useState<Interview[] | null>(null)
  const [ivError, setIvError] = useState<string | null>(null)

  const calWeek = useMemo(() => startOfWeek(calSel), [calSel])

  useEffect(() => {
    const ac = new AbortController()
    setIvs(null)

    schedules
      .interviews({ from: calWeek.toISOString(), to: addDays(calWeek, 7).toISOString() }, ac.signal)
      .then((res) => { setIvs(res.items); setIvError(null) })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setIvs([])
        setIvError(err instanceof ApiError ? err.message : '면접 일정을 불러오지 못했습니다')
      })

    return () => ac.abort()
  }, [calWeek])

  const calByDay = useMemo(() => {
    const map = new Map<string, Interview[]>()
    for (const iv of ivs ?? []) {
      const bucket = map.get(isoDayKey(iv.start_at))
      if (bucket) bucket.push(iv)
      else map.set(isoDayKey(iv.start_at), [iv])
    }
    for (const bucket of map.values()) bucket.sort((a, b) => a.start_at.localeCompare(b.start_at))
    return map
  }, [ivs])

  const calDays = useMemo(
    () => Array.from({ length: 7 }, (_, i) => addDays(calWeek, i)),
    [calWeek],
  )
  const calItems = calByDay.get(dayKey(calSel)) ?? []
  const todayKey = dayKey(startOfToday())

  /* 축소판 → 캘린더 화면. 2026-09-01 확대 전환을 뺐다 — 그냥 이동한다 */
  function goCalendar() {
    navigate('/calendar')
  }

  /* 카드 안 빈자리를 눌러도 캘린더로 간다. 카드 안의 조작(주 이동·날짜 선택)은 제자리 */
  function onCalCardClick(e: React.MouseEvent<HTMLElement>) {
    if (e.target instanceof Element && e.target.closest('button, a') !== null) return
    goCalendar()
  }

  const interviewTotal = data?.pipe.find((g) => g.stage === 'interview')?.total

  const stats = [
    { label: '내 리뷰 대기', value: data?.reviewWaiting, unit: '명' },
    { label: '면접 진행', value: interviewTotal, unit: '명' },
    { label: '진행중 공고', value: data?.openPostings.length, unit: '개' },
  ]

  /* 행·카드는 그 공고의 지원자 화면으로 간다 (05-design §0.5 진입점) */
  const goPosting = (a: ApplicationListItem) => navigate(`/postings/${a.job_posting_id}`)

  function scheduleChip(a: ApplicationListItem) {
    if (a.current_stage !== 'interview' || data === null) return null
    const s = data.schedules[a.id]
    if (s === undefined) return null
    if (s !== null && s.status === 'confirmed' && s.confirmed_slot !== null) {
      return <span className={`${styles.chip} ${styles.chipConfirmed}`}>{fmtSlot(s.confirmed_slot.start_at)}</span>
    }
    if (s !== null && s.status === 'proposed') {
      return <span className={`${styles.chip} ${styles.chipNeutral}`}>일정 제안 중</span>
    }
    if (s !== null && s.status === 'expired') {
      return <span className={`${styles.chip} ${styles.chipNeutral}`}>제안 만료</span>
    }
    return <span className={`${styles.chip} ${styles.chipNeutral}`}>일정 없음</span>
  }

  return (
    <>
      <PageHead title="대시보드" />
      <main className={`page-content ${styles.page}`}>
        {error !== null && <p className={styles.state} role="alert">{error}</p>}

        <div className={styles.stats}>
          {stats.map((s) => (
            <div key={s.label} className={styles.stat}>
              <div className={styles.statLabel}>{s.label}</div>
              <div className={styles.statVal}>
                {s.value ?? '—'}<span className={styles.statUnit}>{s.unit}</span>
              </div>
            </div>
          ))}
        </div>

        {/* ── 캘린더 축소판(절반) + 진행중 공고(절반) — 2026-08-31 2열 개편.
            1100px 아래에선 1열로 스택 (§9 확정 브레이크포인트 재사용) */}
        <div className={styles.topGrid}>
        {/* ── 면접 일정 축소판 — 누르면 캘린더 화면으로 이어진다 ────────── */}
        <section
          className={`${styles.card} ${styles.calCard}`}
          onClick={onCalCardClick}
        >
          <div className={styles.calHead}>
            <h2 className={styles.calTitle}>캘린더</h2>
            <span className={styles.calMonth}>{fmtMonth(calSel)}</span>
            {/* 주 이동·오늘 버튼은 뺐다 (2026-08-31 절반 너비 개편) — 축소판은 이번 주만,
                다른 주·달은 캘린더 화면이 받는다 */}
            {/* 키보드로도 캘린더에 닿는 길 (§10) — 전환은 여기서도 같은 것을 탄다 */}
            <Link
              to="/calendar"
              className={styles.go}
              onClick={(e) => {
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
                e.preventDefault()
                goCalendar()
              }}
            >
              캘린더 →
            </Link>
          </div>

          <div className={styles.dow} aria-hidden="true">
            {DOW.map((d) => <span key={d} className={styles.dowCell}>{d}</span>)}
          </div>

          <div className={styles.strip}>
            {calDays.map((d) => {
              const key = dayKey(d)
              const n = calByDay.get(key)?.length ?? 0
              const cls = [
                styles.stripCell,
                key === todayKey ? styles.stripToday : '',
                key === dayKey(calSel) ? styles.stripSel : '',
              ].filter(Boolean).join(' ')
              return (
                <button
                  key={key}
                  type="button"
                  className={cls}
                  aria-pressed={key === dayKey(calSel)}
                  aria-current={key === todayKey ? 'date' : undefined}
                  aria-label={`${key.replaceAll('-', '.')} ${DOW[d.getDay()]}요일, ${n ? `면접 ${n}건` : '면접 없음'}`}
                  onClick={() => setCalSel(d)}
                >
                  <span className={styles.stripDate}>{d.getDate()}</span>
                  {/* 면접이 잡힌 날 표식. 건수는 aria-label 과 아래 목록이 말한다 */}
                  {n > 0 && <span className={styles.stripDot} aria-hidden="true" />}
                </button>
              )
            })}
          </div>

          <div className={styles.calList}>
            {ivError !== null && <p className={styles.calState} role="alert">{ivError}</p>}

            {ivError === null && ivs === null && [0, 1, 2].map((i) => (
              <span key={i} className={styles.calSkel} />
            ))}

            {ivError === null && ivs !== null && calItems.length === 0 && (
              <p className={styles.calState}>이 날짜에 잡힌 면접이 없습니다. 확정된 일정만 표시됩니다.</p>
            )}

            {calItems.length > 0 && (
              /* 컬럼 머리 — 캘린더 화면의 그날 목록과 같은 구성(시각·지원자·공고·면접관) */
              <div className={styles.calCols} aria-hidden="true">
                <span className={styles.calTime}>시각</span>
                <span className={styles.calName}>지원자</span>
                <span className={styles.calPosting}>공고</span>
                <span className={styles.calWho}>면접관</span>
              </div>
            )}

            {calItems.slice(0, CAL_LIMIT).map((iv) => (
              <div key={iv.proposal_id} className={styles.calRow}>
                <span className={styles.calTime}>{hhmm(iv.start_at)}</span>
                <span className={styles.calName}>{iv.applicant_name}</span>
                <span className={styles.calPosting}>{iv.posting_title}</span>
                <span className={styles.calWho}>{iv.interviewer_name}</span>
              </div>
            ))}

            {calItems.length > CAL_LIMIT && (
              <button type="button" className={styles.moreLink} onClick={goCalendar}>
                외 {calItems.length - CAL_LIMIT}건 →
              </button>
            )}
          </div>
        </section>

        {/* 섹션 라벨은 두지 않는다 — 왼쪽 캘린더 카드와 같은 위계라 같은 자리에서 시작해야 한다.
            공고 카드 하나하나가 캘린더 카드와 같은 규격(.card)의 흰 블록이고, 공고 제목이 "캘린더"에 대응한다 */}
        <div className={styles.postingCol}>
          {data === null && error === null && <p className={`${styles.card} ${styles.state}`}>불러오는 중…</p>}
          {data !== null && data.openPostings.length === 0 && (
            <p className={`${styles.card} ${styles.state}`}>진행중인 공고가 없습니다.</p>
          )}
          <div className={styles.postingList}>
            {data?.openPostings.map((p) => {
              const counts = rails[p.id] ?? RAIL.map(() => 0)
              const total = counts.reduce((a, b) => a + b, 0)
              /* 0 건도 6px 남긴다 — 폭이 0 이면 단계가 통째로 사라져 레일이 몇 단인지 안 보인다.
                 fr 은 공고 규모와 무관하게 비율을 맞추므로 최소 폭은 px 로 따로 준다 */
              const cols = counts.map((n) => `minmax(6px, ${n}fr)`).join(' ')
              return (
                <button
                  key={p.id}
                  className={`${styles.card} ${styles.postingCard}`}
                  onClick={() => navigate(`/postings/${p.id}`)}
                >
                  <div className={styles.postingTop}>
                    <span className={styles.postingName}>{p.title}</span>
                    {/* 레일이 아직 안 왔으면 총 인원도 쓰지 않는다 — 0 명으로 잠깐 보이면 그게 실제 값처럼 읽힌다.
                        마감일이 없는 공고(상시)는 D-day 를 그리지 않는다 */}
                    {(rails[p.id] !== undefined || p.d_day !== null) && (
                      <span className={styles.postingDday}>
                        {[
                          rails[p.id] !== undefined ? `총 ${total}명` : null,
                          p.d_day === null ? null : p.d_day >= 0 ? `D-${p.d_day}` : `D+${-p.d_day}`,
                        ].filter(Boolean).join(' · ')}
                      </span>
                    )}
                  </div>
                  <div className={styles.postingRail} style={{ gridTemplateColumns: cols }}>
                    {RAIL.map((r) => (
                      <div key={r.stage} className={styles.railSeg} style={{ background: r.color }} />
                    ))}
                  </div>
                  {/* 눈금이 아니라 범례다 — 색 점이 라벨을 자기 구간에 잇는다.
                      한 줄 고정: 폭이 모자라면 넘치는 쪽을 자른다 (§7 ellipsis 원칙) */}
                  <div className={styles.postingCounts}>
                    {RAIL.map((r, i) => (
                      <span
                        key={r.stage}
                        className={`${styles.countItem} ${r.stage === 'accepted' ? styles.countPass : ''}`}
                      >
                        <span className={styles.countDot} style={{ background: r.color }} />
                        {STAGE_LABEL[r.stage]} <b>{counts[i]}</b>
                      </span>
                    ))}
                  </div>
                </button>
              )
            })}
          </div>
        </div>
        </div>

        <div className={styles.card}>
          <div className={styles.pipeHead}>
            <div className={styles.vtoggle} role="group" aria-label="보기 방식">
              <button
                type="button"
                className={view === 'list' ? styles.vOn : undefined}
                aria-pressed={view === 'list'}
                onClick={() => setView('list')}
              >
                리스트
              </button>
              <button
                type="button"
                className={view === 'kanban' ? styles.vOn : undefined}
                aria-pressed={view === 'kanban'}
                onClick={() => setView('kanban')}
              >
                칸반
              </button>
            </div>
            <Link to="/applicants" className={styles.go}>전체 지원자 →</Link>
          </div>

          {data === null && error === null && <p className={styles.state}>불러오는 중…</p>}

          {data !== null && (
            <>
              {/* 모바일(≤768px)은 칸반 금지(05-design §9) — CSS 가 칸반을 숨기고
                  리스트를 다시 보여주므로 두 뷰를 모두 그려 둔다 */}
              <div className={view === 'kanban' ? styles.listHiddenOnDesktop : undefined}>
                {data.pipe.map((g) => (
                  <div key={g.stage} className={styles.group}>
                    <div className={styles.groupHead}>
                      <span className={g.pass ? `${styles.dot} ${styles.dotPass}` : styles.dot} />
                      <span className={g.pass ? `${styles.groupLabel} ${styles.groupLabelPass}` : styles.groupLabel}>
                        {STAGE_LABEL[g.stage]}
                      </span>
                      <span className={styles.groupCount}>{g.total}명</span>
                    </div>
                    {g.items.map((a) => (
                      <button key={a.id} type="button" className={styles.row} onClick={() => goPosting(a)}>
                        <span className={styles.rowName}>{a.name}</span>
                        <span className={styles.rowPosting}>{data.postingTitles[a.job_posting_id] ?? ''}</span>
                        {scheduleChip(a)}
                        <span className={styles.rowDate}>{fmtDate(a.created_at)}</span>
                      </button>
                    ))}
                    {g.items.length === 0 && <p className={styles.groupEmpty}>없음</p>}
                    {g.total > g.items.length && (
                      <button type="button" className={styles.moreLink} onClick={() => navigate('/applicants')}>
                        외 {g.total - g.items.length}명 →
                      </button>
                    )}
                  </div>
                ))}
              </div>

              {view === 'kanban' && (
                <div className={styles.board}>
                  {data.pipe.map((g) => (
                    <div key={g.stage} className={styles.col}>
                      <div className={styles.groupHead}>
                        <span className={g.pass ? `${styles.dot} ${styles.dotPass}` : styles.dot} />
                        <span className={g.pass ? `${styles.groupLabel} ${styles.groupLabelPass}` : styles.groupLabel}>
                          {STAGE_LABEL[g.stage]}
                        </span>
                        <span className={styles.groupCount}>{g.total}</span>
                      </div>
                      {g.items.map((a) => (
                        <button key={a.id} type="button" className={styles.kcard} onClick={() => goPosting(a)}>
                          <span className={styles.kcardName}>{a.name}</span>
                          <span className={styles.kcardPosting}>{data.postingTitles[a.job_posting_id] ?? ''}</span>
                          {scheduleChip(a)}
                        </button>
                      ))}
                      {g.items.length === 0 && <p className={styles.groupEmpty}>없음</p>}
                      {g.total > g.items.length && (
                        <button type="button" className={styles.colMore} onClick={() => navigate('/applicants')}>
                          외 {g.total - g.items.length}명 →
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

      </main>
    </>
  )
}
