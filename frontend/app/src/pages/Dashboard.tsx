import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import PageHead from '../components/PageHead'
import { ApiError } from '../api/client'
import { applications, assignments, postings as postingsApi } from '../api/endpoints'
import type { Posting, Stage } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import styles from './Dashboard.module.css'

/* ── 면접 일정 (아직 목데이터) ──────────────────────────────────────
   면접 일정을 담는 테이블이 아직 없다. 01-erd.md 에 interviewer_assignments
   (누가 누구를 맡았나)는 있지만 scheduled_at·round 가 없어서 "언제 몇 차"를
   물어볼 곳이 없다. 스키마는 팀장 소관이라 여기서는 목데이터를 유지한다. */
interface Interview {
  time: string
  name: string
  posting: string
  stage: string
}

const SCHEDULE: Interview[] = [
  { time: '09:30', name: '이서연', posting: 'QA 엔지니어', stage: '1차 면접' },
  { time: '10:00', name: '김도현', posting: '백엔드 개발자 (신입)', stage: '1차 기술면접' },
  { time: '10:20', name: '크리스토퍼 알렉산더 반 데 베르그', posting: '백엔드 개발자 (신입)', stage: '1차 기술면접' },
  { time: '10:40', name: '오세훈', posting: '백엔드 개발자 (신입)', stage: '1차 기술면접' },
  { time: '11:30', name: '임재현', posting: '데이터 엔지니어', stage: '2차 면접' },
  { time: '13:00', name: '최민서', posting: 'QA 엔지니어', stage: '1차 면접' },
  { time: '13:30', name: '배수진', posting: '프로덕트 디자이너 (신입·경력)', stage: '포트폴리오 발표' },
  { time: '14:00', name: '정우진', posting: 'UX 디자이너', stage: '포트폴리오 발표' },
  { time: '15:00', name: '신동혁', posting: '글로벌 커머스 플랫폼 백엔드 시스템 아키텍처 설계 및 대규모 트래픽 처리 인프라 운영 시니어 엔지니어 (10년 이상)', stage: '1차 기술면접' },
  { time: '16:30', name: '박지훈', posting: '프론트엔드 개발자 (경력)', stage: '1차 면접' },
  { time: '16:50', name: '문가영', posting: '프론트엔드 개발자 (경력)', stage: '1차 면접' },
]

const SLOT_LIMIT = 3

/* 같은 시간대끼리 묶되, 라벨과 대표 이름은 그 안에서 가장 이른 면접을 쓴다
   (16:30 한 건을 16:00 으로 반올림하면 없는 일정을 보여주는 셈이다).
   SCHEDULE 이 시각순이라 각 슬롯의 첫 항목이 곧 첫 타자다. */
function groupByHour(list: Interview[]) {
  const slots: { label: string; items: Interview[] }[] = []
  for (const iv of list) {
    const last = slots[slots.length - 1]
    const sameHour = last && last.items[0].time.slice(0, 2) === iv.time.slice(0, 2)
    if (sameHour) last.items.push(iv)
    else slots.push({ label: iv.time, items: [iv] })
  }
  return slots
}

/* ── 전형 현황 ────────────────────────────────────────────────────
   단계는 서버가 가진 것만 쓴다. 대시보드 목업은 "1차 면접 / 2차 면접" 으로
   나눠 그렸지만 applications.current_stage 에 회차 개념이 없어 물어볼 수 없다.
   라벨은 공고 상세 화면의 퍼널(mockup.html)이 쓰는 것과 같게 맞췄다. */
const FUNNEL_STAGES: { stage: Stage; label: string; pass?: boolean }[] = [
  { stage: 'applied', label: '지원 접수' },
  { stage: 'screening', label: '서류 검토' },
  { stage: 'interview', label: '면접' },
  { stage: 'accepted', label: '최종 합격', pass: true },
]

/* 공고 카드의 3단 레일. 왼쪽부터 검토 → 진행 → 완료 */
const RAIL_STAGES: Stage[] = ['screening', 'interview', 'accepted']

interface DashboardData {
  reviewWaiting: number
  openPostings: Posting[]
  funnel: { label: string; count: number; pass?: boolean }[]
  rails: Record<number, number[]>
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const slots = groupByHour(SCHEDULE)

  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!user) return
    const ac = new AbortController()
    setError(null)

    async function load(userId: number) {
      const [assigned, allPostings, funnelCounts] = await Promise.all([
        assignments.mine(userId, ac.signal),
        postingsApi.list(ac.signal),
        Promise.all(FUNNEL_STAGES.map((f) => applications.countByStage(f.stage, undefined, ac.signal))),
      ])

      const open = allPostings.filter((p) => p.status === 'open')
      // 공고마다 레일 세 칸을 채운다. 공고 수 × 3 번이라 열린 공고만 부른다.
      const railPairs = await Promise.all(
        open.map(async (p) => {
          const counts = await Promise.all(
            RAIL_STAGES.map((s) => applications.countByStage(s, p.id, ac.signal)),
          )
          return [p.id, counts] as const
        }),
      )

      return {
        reviewWaiting: assigned.count,
        openPostings: open,
        funnel: FUNNEL_STAGES.map((f, i) => ({ label: f.label, count: funnelCounts[i], pass: f.pass })),
        rails: Object.fromEntries(railPairs),
      }
    }

    load(user.id)
      .then(setData)
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '대시보드를 불러오지 못했습니다')
      })

    return () => ac.abort()
  }, [user])

  const stats = [
    { label: '내 리뷰 대기', value: data?.reviewWaiting, unit: '명' },
    // 면접 일정 테이블이 없어 셀 수 없다. 위 SCHEDULE 주석 참고.
    { label: '오늘 면접', value: SCHEDULE.length, unit: '건' },
    { label: '진행중 공고', value: data?.openPostings.length, unit: '개' },
  ]

  /* 퍼널 막대는 가장 큰 단계를 100% 로 잡는다. 고정값을 두면 실제 수가
     그보다 커졌을 때 막대가 넘친다. */
  const funnelMax = Math.max(1, ...(data?.funnel.map((f) => f.count) ?? [1]))

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

        <div className={styles.twoCol}>
          <div className={styles.card}>
            <h2 className={styles.cardTitle}>
              <Link to="/interviews">면접 일정 <span className={styles.go}>전체 →</span></Link>
            </h2>
            <div className={styles.scheduleList}>
              {slots.slice(0, SLOT_LIMIT).map((slot) => {
                const [first, ...rest] = slot.items
                const postings = new Set(slot.items.map((iv) => iv.posting))
                return (
                  <div key={slot.label} className={styles.slot}>
                    <button
                      className={styles.scheduleItem}
                      onClick={() => navigate(`/interviews?slot=${slot.label}`)}
                    >
                      <span className={styles.scheduleTime}>{slot.label}</span>
                      <span className={styles.scheduleInfo}>
                        <span className={styles.scheduleName}>
                          {first.name}
                          {rest.length > 0 && <em className={styles.scheduleRest}> 외 {rest.length}명</em>}
                        </span>
                        <span className={styles.scheduleSub}>
                          {postings.size > 1 ? `공고 ${postings.size}개` : first.posting} · {first.stage}
                        </span>
                      </span>
                    </button>

                    {/* 명단 미리보기 — 버튼 바깥 형제로 둔다. 안에 넣으면 목록을
                        스크롤하다 눌려서 화면이 넘어간다. */}
                    {rest.length > 0 && (
                      <div className={styles.slotPop} role="tooltip">
                        <div className={styles.slotPopHead}>
                          {slot.label.slice(0, 2)}시 면접 {slot.items.length}건
                        </div>
                        {slot.items.map((iv) => (
                          <div key={iv.time + iv.name} className={styles.slotPopItem}>
                            <span className={styles.slotPopTime}>{iv.time}</span>
                            <span className={styles.slotPopName}>{iv.name}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
              {slots.length > SLOT_LIMIT && (
                <button className={styles.scheduleMore} onClick={() => navigate('/interviews')}>
                  외 {slots.length - SLOT_LIMIT}건 더 →
                </button>
              )}
            </div>
          </div>

          <div className={styles.card}>
            <div className={styles.cardTitle}>전형 현황</div>
            {data === null && error === null && <p className={styles.state}>불러오는 중…</p>}
            {data !== null && (
              <div className={styles.funnelList}>
                {data.funnel.map((row) => (
                  <div key={row.label} className={styles.funnelRow}>
                    <span className={styles.funnelLabel}>{row.label}</span>
                    <div className={styles.funnelTrack}>
                      <div
                        className={styles.funnelFill}
                        style={{
                          width: `${Math.round((row.count / funnelMax) * 100)}%`,
                          background: row.pass ? 'var(--sprout)' : 'var(--neutral)',
                        }}
                      />
                    </div>
                    <span className={styles.funnelCount}>{row.count}명</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className={styles.sectionTitle}>진행중 공고</div>
        {data === null && error === null && <p className={styles.state}>불러오는 중…</p>}
        {data !== null && data.openPostings.length === 0 && (
          <p className={styles.state}>진행중인 공고가 없습니다.</p>
        )}
        <div className={styles.postingList}>
          {data?.openPostings.map((p) => {
            const counts = data.rails[p.id] ?? [0, 0, 0]
            const total = counts.reduce((a, b) => a + b, 0)
            const pct = (n: number) => (total === 0 ? 0 : Math.round((n / total) * 100))
            return (
              <button key={p.id} className={styles.postingCard} onClick={() => navigate('/postings')}>
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
