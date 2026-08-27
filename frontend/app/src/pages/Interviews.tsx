import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import PageHead from '../components/PageHead'
import styles from './Interviews.module.css'

interface Interview {
  id: number
  time: string
  applicant: string
  posting: string
  round: string
  interviewer: string
}

const DATE = '2026.08.26'

const MOCK: Interview[] = [
  { id: 1, time: '10:00', applicant: '김도현', posting: '백엔드 개발자 (신입)', round: '1차 기술면접', interviewer: '이지훈' },
  { id: 2, time: '10:20', applicant: '크리스토퍼 알렉산더 반 데 베르그', posting: '백엔드 개발자 (신입)', round: '1차 기술면접', interviewer: '이지훈' },
  { id: 3, time: '14:00', applicant: '정우진', posting: 'UX 디자이너', round: '포트폴리오 발표', interviewer: '한소미' },
  { id: 4, time: '16:30', applicant: '박지훈', posting: '프론트엔드 개발자 (경력)', round: '1차 면접', interviewer: '김채용 외 2명' },
]

export default function Interviews() {
  const navigate = useNavigate()
  const [params] = useSearchParams()

  /* 대시보드에서 한 시간대를 눌러 넘어오면 그 슬롯만 남긴다.
     시각이 10:00·10:20 처럼 쪼개져 있어 정각이 아니라 '시' 단위로 묶는다. */
  const slot = params.get('slot')
  const list = slot ? MOCK.filter((iv) => iv.time.slice(0, 2) === slot.slice(0, 2)) : MOCK

  return (
    <>
      <PageHead title="면접 일정" />
      <main className="page-content">
      <div className={styles.daybar}>
        <button className={styles.dayNav} aria-label="이전 날">‹</button>
        <button className={styles.dayNav} aria-label="다음 날">›</button>
        <span className={styles.dayLabel}>{DATE}</span>
        <span className={styles.dayCount}>{list.length}건</span>
        {slot && (
          <Link className={styles.slotChip} to="/interviews" aria-label="슬롯 필터 해제 — 그 날 전체 보기">
            {slot} 면접만 <span aria-hidden="true">✕</span>
          </Link>
        )}
        <button className={styles.dayToday}>오늘</button>
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
