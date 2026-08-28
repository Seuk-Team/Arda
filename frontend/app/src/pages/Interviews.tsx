import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import PageHead from '../components/PageHead'
import styles from './Interviews.module.css'

interface Interview {
  id: number
  /* 오늘 기준 오프셋. 면접 일정 테이블이 생기면 실제 날짜로 바뀐다 */
  day: number
  time: string
  applicant: string
  posting: string
  round: string
  interviewer: string
}

/* 면접 일정을 담는 테이블이 아직 없다 (01-erd 에 scheduled_at·round 가 없다).
   그래서 목데이터에 오늘 기준 오프셋(day)을 두고 날짜별로 갈라 보여 준다. */
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

const MOCK: Interview[] = [
  { id: 1, day: -2, time: '09:00', applicant: '윤하늘', posting: '프론트엔드 개발자 (경력)', round: '최종 면접', interviewer: '김채용 외 2명' },
  { id: 2, day: -2, time: '10:00', applicant: '한지우', posting: '데이터 엔지니어', round: '최종 면접', interviewer: '김채용 외 2명' },
  { id: 3, day: -2, time: '14:00', applicant: '강민수', posting: '프론트엔드 개발자 (경력)', round: '1차 면접', interviewer: '한소미' },
  { id: 4, day: -1, time: '10:00', applicant: '노아름', posting: '프로덕트 디자이너 (신입·경력)', round: '포트폴리오 발표', interviewer: '한소미' },
  { id: 5, day: -1, time: '11:00', applicant: '남기훈', posting: '글로벌 커머스 플랫폼 백엔드 시스템 아키텍처 설계 및 대규모 트래픽 처리 인프라 운영 시니어 엔지니어 (10년 이상)', round: '1차 기술면접', interviewer: '이지훈' },
  { id: 6, day: -1, time: '14:00', applicant: '홍준서', posting: '프론트엔드 개발자 (경력)', round: '1차 면접', interviewer: '한소미' },
  { id: 7, day: -1, time: '15:30', applicant: '서지호', posting: '데이터 엔지니어', round: '1차 기술면접', interviewer: '이지훈' },
  { id: 8, day: 0, time: '09:30', applicant: '이서연', posting: 'QA 엔지니어', round: '1차 면접', interviewer: '한소미' },
  { id: 9, day: 0, time: '10:00', applicant: '김도현', posting: '백엔드 개발자 (신입)', round: '1차 기술면접', interviewer: '이지훈' },
  { id: 10, day: 0, time: '10:20', applicant: '크리스토퍼 알렉산더 반 데 베르그', posting: '백엔드 개발자 (신입)', round: '1차 기술면접', interviewer: '이지훈' },
  { id: 11, day: 0, time: '10:40', applicant: '오세훈', posting: '백엔드 개발자 (신입)', round: '1차 기술면접', interviewer: '이지훈' },
  { id: 12, day: 0, time: '11:30', applicant: '임재현', posting: '데이터 엔지니어', round: '2차 면접', interviewer: '김채용 외 2명' },
  { id: 13, day: 0, time: '13:00', applicant: '최민서', posting: 'QA 엔지니어', round: '1차 면접', interviewer: '한소미' },
  { id: 14, day: 0, time: '13:30', applicant: '배수진', posting: '프로덕트 디자이너 (신입·경력)', round: '포트폴리오 발표', interviewer: '한소미' },
  { id: 15, day: 0, time: '14:00', applicant: '정우진', posting: 'UX 디자이너', round: '포트폴리오 발표', interviewer: '한소미' },
  { id: 16, day: 0, time: '15:00', applicant: '신동혁', posting: '글로벌 커머스 플랫폼 백엔드 시스템 아키텍처 설계 및 대규모 트래픽 처리 인프라 운영 시니어 엔지니어 (10년 이상)', round: '1차 기술면접', interviewer: '이지훈' },
  { id: 17, day: 0, time: '16:30', applicant: '박지훈', posting: '프론트엔드 개발자 (경력)', round: '1차 면접', interviewer: '김채용 외 2명' },
  { id: 18, day: 0, time: '16:50', applicant: '문가영', posting: '프론트엔드 개발자 (경력)', round: '1차 면접', interviewer: '김채용 외 2명' },
  { id: 19, day: 1, time: '09:30', applicant: '백승우', posting: '백엔드 개발자 (신입)', round: '1차 기술면접', interviewer: '이지훈' },
  { id: 20, day: 1, time: '10:00', applicant: '권나영', posting: '백엔드 개발자 (신입)', round: '1차 기술면접', interviewer: '이지훈' },
  { id: 21, day: 1, time: '11:00', applicant: '유채원', posting: 'QA 엔지니어', round: '1차 면접', interviewer: '한소미' },
  { id: 22, day: 1, time: '14:00', applicant: '심예린', posting: '데이터 엔지니어', round: '1차 기술면접', interviewer: '이지훈' },
  { id: 23, day: 1, time: '16:00', applicant: '조은지', posting: 'QA 엔지니어', round: '1차 면접', interviewer: '한소미' },
  { id: 24, day: 2, time: '10:00', applicant: '곽민준', posting: '백엔드 개발자 (신입)', round: '1차 기술면접', interviewer: '이지훈' },
  { id: 25, day: 2, time: '13:00', applicant: '황태섭', posting: '프론트엔드 개발자 (경력)', round: '1차 면접', interviewer: '한소미' },
]

export default function Interviews() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [day, setDay] = useState(startOfToday)

  const today = startOfToday()
  const offset = Math.round((day.getTime() - today.getTime()) / 86400000)

  function move(days: number) {
    setDay((d) => {
      const next = new Date(d)
      next.setDate(next.getDate() + days)
      return next
    })
  }

  /* 대시보드에서 한 시간대를 눌러 넘어오면 그 슬롯만 남긴다.
     시각이 10:00·10:20 처럼 쪼개져 있어 정각이 아니라 '시' 단위로 묶는다. */
  /* URL 의 ?slot= 은 대시보드에서 넘어올 때의 초기값이고, 이후에는 화면 안에서 고른다 */
  const [slot, setSlot] = useState<string | null>(() => params.get('slot'))
  const [ddOpen, setDdOpen] = useState(false)

  useEffect(() => {
    if (!ddOpen) return
    const close = () => setDdOpen(false)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [ddOpen])
  const ofDay = MOCK.filter((iv) => iv.day === offset)
  const list = slot ? ofDay.filter((iv) => iv.time.slice(0, 2) === slot.slice(0, 2)) : ofDay

  /* 고를 수 있는 시간대는 그 날 실제로 면접이 있는 시(hour)뿐이다.
     없는 시간을 목록에 두면 눌러 놓고 빈 화면만 본다. */
  const hours = [...new Set(ofDay.map((iv) => iv.time.slice(0, 2)))].sort()

  return (
    <>
      <PageHead title="면접 일정" />
      <main className="page-content">
      <div className={styles.daybar}>
        <button className={styles.dayNav} aria-label="이전 날" onClick={() => move(-1)}>‹</button>
        <button className={styles.dayNav} aria-label="다음 날" onClick={() => move(1)}>›</button>
        <span className={styles.dayLabel}>{fmt(day)}</span>
        <span className={styles.dayCount}>{list.length}건</span>
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
        <button className={styles.dayToday} onClick={() => setDay(startOfToday())}>오늘</button>
      </div>

      <div className={styles.panel}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>시각</th>
              <th>지원자</th>
              <th>공고</th>
              <th>회차</th>
              <th>면접관</th>
            </tr>
          </thead>
          <tbody>
            {list.map((iv) => (
              <tr key={iv.id} onClick={() => navigate('/postings')}>
                <td className={styles.num}>{iv.time}</td>
                <td className={styles.name}>{iv.applicant}</td>
                <td className={styles.posting}>{iv.posting}</td>
                <td className={styles.sub}>{iv.round}</td>
                <td className={styles.sub}>{iv.interviewer}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {list.length === 0 ? (
          <p className={styles.empty}>
            {slot ? '이 시간대에 잡힌 면접이 없습니다.' : '이 날짜에 잡힌 면접이 없습니다.'}
          </p>
        ) : (
          <div className={styles.foot}>
            <span>{list.length}건 중 1–{list.length}</span>
          </div>
        )}
      </div>
      </main>
    </>
  )
}
