import { Link, useNavigate } from 'react-router-dom'
import styles from './Dashboard.module.css'

const STATS = [
  { label: '내 리뷰 대기', value: 12, unit: '명' },
  { label: '오늘 면접', value: 4, unit: '건' },
  { label: '진행중 공고', value: 4, unit: '개' },
]

/* 면접 한 건 = 지원자 한 명. 같은 시각에 여러 건이면 화면에서 슬롯으로 묶는다. */
interface Interview {
  time: string
  name: string
  posting: string
  stage: string
}

const SCHEDULE: Interview[] = [
  { time: '10:00', name: '김도현', posting: '백엔드 개발자 (신입)', stage: '1차 기술면접' },
  { time: '10:20', name: '크리스토퍼 알렉산더 반 데 베르그', posting: '백엔드 개발자 (신입)', stage: '1차 기술면접' },
  { time: '14:00', name: '정우진', posting: 'UX 디자이너', stage: '포트폴리오 발표' },
  { time: '16:30', name: '박지훈', posting: '프론트엔드 개발자 (경력)', stage: '1차 면접' },
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

const FUNNEL_MAX = 24

const FUNNEL = [
  { label: '서류 검토', count: 24, pass: false },
  { label: '1차 면접', count: 12, pass: false },
  { label: '2차 면접', count: 6, pass: false },
  { label: '최종 합격', count: 2, pass: true },
]

const POSTINGS = [
  { id: 1, title: '백엔드 개발자 (신입)', team: '개발팀', dday: 12, reviewed: 14, inprogress: 6, done: 4 },
  { id: 2, title: '프론트엔드 개발자 (경력)', team: '개발팀', dday: 5, reviewed: 10, inprogress: 5, done: 3 },
  { id: 3, title: '글로벌 커머스 플랫폼 백엔드 시스템 아키텍처 설계 및 대규모 트래픽 최적화', team: '인프라팀', dday: 21, reviewed: 8, inprogress: 3, done: 1 },
]

export default function Dashboard() {
  const navigate = useNavigate()
  const slots = groupByHour(SCHEDULE)

  return (
    <div>
      <h1 className={styles.title}>대시보드</h1>

      <div className={styles.stats}>
        {STATS.map((s) => (
          <div key={s.label} className={styles.stat}>
            <div className={styles.statLabel}>{s.label}</div>
            <div className={styles.statVal}>
              {s.value}<span className={styles.statUnit}>{s.unit}</span>
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
          <div className={styles.funnelList}>
            {FUNNEL.map((row) => (
              <div key={row.label} className={styles.funnelRow}>
                <span className={styles.funnelLabel}>{row.label}</span>
                <div className={styles.funnelTrack}>
                  <div
                    className={styles.funnelFill}
                    style={{
                      width: `${Math.round(row.count / FUNNEL_MAX * 100)}%`,
                      background: row.pass ? 'var(--sprout)' : 'var(--neutral)',
                    }}
                  />
                </div>
                <span className={styles.funnelCount}>{row.count}명</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className={styles.sectionTitle}>진행중 공고</div>
      <div className={styles.postingList}>
        {POSTINGS.map((p) => {
          const total = p.reviewed + p.inprogress + p.done
          return (
            <button
              key={p.id}
              className={styles.postingCard}
              onClick={() => navigate('/postings')}
            >
              <div className={styles.postingLeft}>
                <div className={styles.postingName}>{p.title}</div>
                <div className={styles.postingTeam}>{p.team}</div>
                <div className={styles.postingRail}>
                  <div className={styles.railSeg} style={{ width: `${Math.round(p.reviewed / total * 100)}%`, background: 'var(--border)' }} />
                  <div className={styles.railSeg} style={{ width: `${Math.round(p.inprogress / total * 100)}%`, background: 'var(--neutral)' }} />
                  <div className={styles.railSeg} style={{ width: `${Math.round(p.done / total * 100)}%`, background: 'var(--sprout)' }} />
                </div>
              </div>
              <div className={styles.postingDday}>D-{p.dday}</div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
