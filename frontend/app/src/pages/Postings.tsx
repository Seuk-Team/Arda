import styles from './Postings.module.css'

interface Posting {
  id: number
  title: string
  team: string
  status: 'open' | 'closed'
  applicants: number
  deadline: string
}

const MOCK: Posting[] = [
  { id: 1, title: '백엔드 개발자', team: '개발팀', status: 'open', applicants: 24, deadline: '2026-09-15' },
  { id: 2, title: '프론트엔드 개발자', team: '개발팀', status: 'open', applicants: 18, deadline: '2026-09-20' },
  { id: 3, title: 'UX 디자이너', team: '디자인팀', status: 'open', applicants: 12, deadline: '2026-09-10' },
  { id: 4, title: '데이터 분석가', team: '데이터팀', status: 'closed', applicants: 31, deadline: '2026-08-20' },
  { id: 5, title: 'DevOps 엔지니어', team: '인프라팀', status: 'open', applicants: 9, deadline: '2026-09-25' },
]

export default function Postings() {
  return (
    <div>
      <header className={styles.header}>
        <h1 className={styles.title}>공고 관리</h1>
        <button className="btn btn-primary">+ 새 공고</button>
      </header>

      <table className={styles.table}>
        <thead>
          <tr>
            <th>공고명</th>
            <th>팀</th>
            <th>상태</th>
            <th>지원자</th>
            <th>마감일</th>
          </tr>
        </thead>
        <tbody>
          {MOCK.map((p) => (
            <tr key={p.id}>
              <td className={styles.name}>{p.title}</td>
              <td>{p.team}</td>
              <td>
                <span className={`badge ${p.status === 'open' ? 'badge-open' : 'badge-closed'}`}>
                  {p.status === 'open' ? '진행중' : '마감'}
                </span>
              </td>
              <td className={styles.num}>{p.applicants}명</td>
              <td className={styles.num}>{p.deadline}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
