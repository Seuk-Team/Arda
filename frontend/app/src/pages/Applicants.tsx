import { useMemo, useState } from 'react'
import PageHead from '../components/PageHead'
import styles from './Applicants.module.css'

/* 전 공고 통합 검색 테이블 (05-design §0.5). 칸반 없음. */
type Stage = '지원 접수' | '서류 검토' | '면접' | '최종 합격' | '불합격'

interface Applicant {
  id: number
  name: string
  posting: string
  stage: Stage
  career: string
  score: string
  applied: string
}

const MOCK: Applicant[] = [
  { id: 1, name: '김도현', posting: '백엔드 개발자 (신입)', stage: '면접', career: '2년', score: '4.5', applied: '2026.03.12' },
  { id: 2, name: '크리스토퍼 알렉산더 반 데 베르그', posting: '백엔드 개발자 (신입)', stage: '면접', career: '12년', score: '4.8', applied: '2026.03.12' },
  { id: 3, name: '윤하늘', posting: '프론트엔드 개발자 (경력)', stage: '최종 합격', career: '1년', score: '5.0', applied: '2026.03.11' },
  { id: 4, name: '박지훈', posting: '글로벌 커머스 플랫폼 백엔드 시스템 아키텍처 설계 및 대규모 트래픽 처리 인프라 운영 시니어 엔지니어 (10년 이상)', stage: '지원 접수', career: '신입', score: '—', applied: '2026.03.11' },
  { id: 5, name: '정우진', posting: '데이터 엔지니어', stage: '서류 검토', career: '1년', score: '4.0', applied: '2026.03.11' },
  { id: 6, name: '강민수', posting: '프론트엔드 개발자 (경력)', stage: '불합격', career: '신입', score: '2.0', applied: '2026.03.10' },
  { id: 7, name: '이서연', posting: 'QA 엔지니어', stage: '서류 검토', career: '4년', score: '4.2', applied: '2026.03.10' },
  { id: 8, name: '한지우', posting: '데이터 엔지니어', stage: '최종 합격', career: '3년', score: '4.9', applied: '2026.03.09' },
  { id: 9, name: '최민서', posting: 'QA 엔지니어', stage: '서류 검토', career: '2년', score: '3.8', applied: '2026.03.09' },
  { id: 10, name: '오세훈', posting: '백엔드 개발자 (신입)', stage: '면접', career: '3년', score: '4.4', applied: '2026.03.08' },
  { id: 11, name: '심예린', posting: '데이터 엔지니어', stage: '서류 검토', career: '2년', score: '3.9', applied: '2026.03.02' },
  { id: 12, name: '곽민준', posting: '백엔드 개발자 (신입)', stage: '지원 접수', career: '신입', score: '—', applied: '2026.03.01' },
]

const FIELDS = ['전체', '이름', '공고'] as const
const TOTAL = '1,248'

/* 색은 판단에만 (05-design §1) — 진행 중은 무채, 합격만 연두, 불합격만 적갈 */
function stageClass(stage: Stage) {
  if (stage === '최종 합격') return styles.stageAccepted
  if (stage === '불합격') return styles.stageRejected
  return styles.stageProgress
}

export default function Applicants() {
  const [field, setField] = useState<(typeof FIELDS)[number]>('전체')
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')

  const list = useMemo(() => {
    const term = q.trim().toLowerCase()
    if (!term) return MOCK
    return MOCK.filter((a) => {
      const hay = field === '이름' ? a.name : field === '공고' ? a.posting : `${a.name} ${a.posting}`
      return hay.toLowerCase().includes(term)
    })
  }, [q, field])

  return (
    <>
      <PageHead title="지원자" />

      <div className={styles.toolbar}>
        <div className={styles.search}>
          <div className={`${styles.dd} ${open ? styles.ddOpen : ''}`}>
            <button
              type="button"
              className={styles.ddBtn}
              aria-haspopup="listbox"
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
            >
              <span>{field}</span>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
            </button>
            <ul className={styles.ddMenu} role="listbox">
              {FIELDS.map((f) => (
                <li
                  key={f}
                  role="option"
                  aria-selected={f === field}
                  className={f === field ? styles.ddSel : undefined}
                  onClick={() => { setField(f); setOpen(false) }}
                >
                  {f}
                </li>
              ))}
            </ul>
          </div>
          <span className={styles.sep} />
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="이름 또는 공고 검색"
          />
          {q && (
            <button type="button" className={styles.sx} aria-label="검색어 지우기" onClick={() => setQ('')}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          )}
        </div>
        {/* 10만 건 검색 무대라 응답 시간을 표기한다 (05-design §0.5) */}
        <span className={styles.meta}>{q ? `${list.length}건` : `${TOTAL}건`} · 0.14초</span>
      </div>

      <main className="page-content">
        <div className={styles.panel}>
          <div className={`${styles.row} ${styles.thead}`}>
            <span>이름</span>
            <span>공고</span>
            <span>단계</span>
            <span className={styles.num}>경력</span>
            <span className={styles.num}>평가</span>
            <span className={styles.num}>지원일</span>
          </div>

          {list.map((a) => (
            <div key={a.id} className={`${styles.row} ${styles.item}`} tabIndex={0}>
              <span className={styles.name}>{a.name}</span>
              <span className={styles.posting}>{a.posting}</span>
              <span className={stageClass(a.stage)}>{a.stage}</span>
              <span className={styles.num}>{a.career}</span>
              <span className={styles.num}>{a.score}</span>
              <span className={styles.num}>{a.applied}</span>
            </div>
          ))}

          {list.length === 0 && (
            <p className={styles.empty}>검색 결과가 없습니다.</p>
          )}

          <div className={styles.foot}>
            <span>{q ? `${list.length}명` : `${TOTAL}명 중 1–${list.length}`}</span>
            {!q && (
              <span className={styles.pager}>
                <button type="button" className={styles.page} disabled>이전</button>
                <button type="button" className={`${styles.page} ${styles.pageCur}`}>1</button>
                <button type="button" className={styles.page}>2</button>
                <button type="button" className={styles.page}>다음</button>
              </span>
            )}
          </div>
        </div>
      </main>
    </>
  )
}
