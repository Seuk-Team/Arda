import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import PageHead from '../components/PageHead'
import { ApiError } from '../api/client'
import { schedules } from '../api/endpoints'
import type { Interview } from '../api/types'
import styles from './Interviews.module.css'

/* 담당자 관점 시간축 뷰 (05-design §0.5). 데이터는 확정된 일정 제안이다
   (ADR-0016) — 목데이터를 걷어내고 GET /schedules 로 바꿨다 (2026-08-31).
   회차 컬럼은 뺐다: 단계가 5개뿐이고 면접 라운드 개념이 스키마에 없어
   "1차/2차"를 물어볼 곳이 없다. 지어내느니 안 보여 준다. */

function startOfToday() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

function fmt(d: Date) {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}.${m}.${day}`
}

/* 면접은 한국에서 열린다 — 지원자 페이지와 같은 이유로 KST 고정 (Schedule.tsx) */
const timeFmt = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false,
})

function hhmm(iso: string): string {
  return timeFmt.format(new Date(iso))
}

export default function Interviews() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [day, setDay] = useState(startOfToday)

  const [list, setList] = useState<Interview[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  /* "내 면접만" — 면접관 계정은 서버가 어차피 본인 것만 주므로 이 체크는
     담당자가 자기 면접을 추려 볼 때 쓰인다 */
  const [mine, setMine] = useState(false)

  function move(days: number) {
    setDay((d) => {
      const next = new Date(d)
      next.setDate(next.getDate() + days)
      return next
    })
  }

  useEffect(() => {
    const ac = new AbortController()
    const to = new Date(day)
    to.setDate(to.getDate() + 1)

    schedules
      .interviews({ from: day.toISOString(), to: to.toISOString(), mine }, ac.signal)
      .then((res) => { setList(res.items); setError(null) })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setList([])
        setError(err instanceof ApiError ? err.message : '면접 일정을 불러오지 못했습니다')
      })

    return () => ac.abort()
  }, [day, mine])

  /* 대시보드에서 한 시간대를 눌러 넘어오면 그 슬롯만 남긴다.
     URL 의 ?slot= 은 초기값이고, 이후에는 화면 안에서 고른다 */
  const [slot, setSlot] = useState<string | null>(() => params.get('slot'))
  const [ddOpen, setDdOpen] = useState(false)

  useEffect(() => {
    if (!ddOpen) return
    const close = () => setDdOpen(false)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [ddOpen])

  const ofDay = list ?? []
  const shown = slot ? ofDay.filter((iv) => hhmm(iv.start_at).slice(0, 2) === slot.slice(0, 2)) : ofDay

  /* 고를 수 있는 시간대는 그 날 실제로 면접이 있는 시(hour)뿐이다.
     없는 시간을 목록에 두면 눌러 놓고 빈 화면만 본다. */
  const hours = [...new Set(ofDay.map((iv) => hhmm(iv.start_at).slice(0, 2)))].sort()

  return (
    <>
      <PageHead title="면접 일정" />
      <main className="page-content">
      <div className={styles.daybar}>
        <button className={styles.dayNav} aria-label="이전 날" onClick={() => move(-1)}>‹</button>
        <button className={styles.dayNav} aria-label="다음 날" onClick={() => move(1)}>›</button>
        <span className={styles.dayLabel}>{fmt(day)}</span>
        <span className={styles.dayCount}>{shown.length}건</span>
        <div className={`${styles.dd} ${ddOpen ? styles.ddOpen : ''}`}>
          <button
            type="button"
            className={styles.ddBtn}
            aria-haspopup="listbox"
            aria-expanded={ddOpen}
            onClick={(e) => { e.stopPropagation(); setDdOpen((v) => !v) }}
          >
            {slot ? `${slot.slice(0, 2)}시` : '시간대'}
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
          </button>
          <ul className={styles.ddMenu} role="listbox">
            <li
              role="option"
              aria-selected={slot === null}
              className={slot === null ? styles.ddSel : undefined}
              onClick={() => { setSlot(null); setDdOpen(false) }}
            >
              전체
            </li>
            {hours.map((h) => (
              <li
                key={h}
                role="option"
                aria-selected={slot?.slice(0, 2) === h}
                className={slot?.slice(0, 2) === h ? styles.ddSel : undefined}
                onClick={() => { setSlot(`${h}:00`); setDdOpen(false) }}
              >
                {h}시
              </li>
            ))}
          </ul>
        </div>

        {slot && (
          <button
            type="button"
            className={styles.slotChip}
            aria-label="시간대 필터 해제 — 그 날 전체 보기"
            onClick={() => setSlot(null)}
          >
            {slot} 면접만 <span aria-hidden="true">✕</span>
          </button>
        )}

        <label className={styles.mine}>
          <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
          내 면접만
        </label>
        <button className={styles.dayToday} onClick={() => setDay(startOfToday())}>오늘</button>
      </div>

      {error !== null && <p className={styles.empty} role="alert">{error}</p>}

      <div className={styles.panel}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>시각</th>
              <th>지원자</th>
              <th>공고</th>
              <th>면접관</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((iv) => (
              /* 행 클릭 = 그 지원자가 있는 공고 화면 (05-design §0.5 진입점) */
              <tr key={iv.proposal_id} onClick={() => navigate(`/applicants?q=${encodeURIComponent(iv.applicant_name)}`)}>
                <td className={styles.num}>{hhmm(iv.start_at)}</td>
                <td className={styles.name}>{iv.applicant_name}</td>
                <td className={styles.posting}>{iv.posting_title}</td>
                <td className={styles.sub}>{iv.interviewer_name}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {list === null && error === null && <p className={styles.empty}>불러오는 중…</p>}

        {list !== null && shown.length === 0 ? (
          <p className={styles.empty}>
            {slot
              ? '이 시간대에 잡힌 면접이 없습니다.'
              : mine
                ? '이 날짜에 내 면접이 없습니다.'
                : '이 날짜에 잡힌 면접이 없습니다. 확정된 일정만 표시됩니다.'}
          </p>
        ) : (
          shown.length > 0 && (
            <div className={styles.foot}>
              <span>{shown.length}건 중 1–{shown.length}</span>
            </div>
          )
        )}
      </div>
      </main>
    </>
  )
}
