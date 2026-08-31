import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import PageHead from '../components/PageHead'
import { ApiError } from '../api/client'
import { applications, assignments, postings as postingsApi, schedules } from '../api/endpoints'
import type { ApplicationListItem, Posting, ScheduleStatus, Stage } from '../api/types'
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

/* 공고 카드의 3단 레일. 왼쪽부터 검토 → 진행 → 완료 */
const RAIL_STAGES: Stage[] = ['screening', 'interview', 'accepted']

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
              RAIL_STAGES.map((s) => applications.countByStage(s, p.id, ac.signal)),
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
      <main className="page-content">
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

        <div className={styles.sectionTitle}>진행중 공고</div>
        {data === null && error === null && <p className={styles.state}>불러오는 중…</p>}
        {data !== null && data.openPostings.length === 0 && (
          <p className={styles.state}>진행중인 공고가 없습니다.</p>
        )}
        <div className={styles.postingList}>
          {data?.openPostings.map((p) => {
            const counts = rails[p.id] ?? [0, 0, 0]
            const total = counts.reduce((a, b) => a + b, 0)
            const pct = (n: number) => (total === 0 ? 0 : Math.round((n / total) * 100))
            return (
              <button key={p.id} className={styles.postingCard} onClick={() => navigate(`/postings/${p.id}`)}>
                <div className={styles.postingLeft}>
                  <div className={styles.postingName}>{p.title}</div>
                  <div className={styles.postingRail}>
                    <div className={styles.railSeg} style={{ width: `${pct(counts[0])}%`, background: 'var(--border)' }} />
                    <div className={styles.railSeg} style={{ width: `${pct(counts[1])}%`, background: 'var(--neutral)' }} />
                    <div className={styles.railSeg} style={{ width: `${pct(counts[2])}%`, background: 'var(--sprout)' }} />
                  </div>
                </div>
                {/* 마감일이 없는 공고(상시)는 D-day 를 그리지 않는다 */}
                {p.d_day !== null && (
                  <div className={styles.postingDday}>
                    {p.d_day >= 0 ? `D-${p.d_day}` : `D+${-p.d_day}`}
                  </div>
                )}
              </button>
            )
          })}
        </div>
      </main>
    </>
  )
}
