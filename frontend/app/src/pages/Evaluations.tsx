import { useEffect, useState } from 'react'
import PageHead from '../components/PageHead'
import styles from './Evaluations.module.css'

/* 면접관 관점 — 내게 배정된 평가 대기 큐 + 우측 평가 패널 (05-design §0.5).
   등록하면 자동으로 다음 지원자로 넘어간다. */
interface Assignment {
  id: number
  name: string
  posting: string
  stage: string
  assigned: string
  edu: string
  career: string
  skills: string
}

const QUEUE: Assignment[] = [
  { id: 1, name: '김도현', posting: '백엔드 개발자 (신입)', stage: '면접', assigned: '2026.08.20', edu: 'OO대학교 컴퓨터공학과', career: '2년 (백엔드)', skills: 'Python · FastAPI · PostgreSQL' },
  { id: 2, name: '박서연', posting: '프론트엔드 개발자', stage: '서류 검토', assigned: '2026.08.21', edu: 'OO대학교 시각디자인학과', career: '1년 (프론트엔드)', skills: 'React · TypeScript · Figma' },
  { id: 3, name: '이준호', posting: '백엔드 개발자 (신입)', stage: '면접', assigned: '2026.08.19', edu: 'OO대학교 소프트웨어학과', career: '신입', skills: 'Java · Spring Boot' },
  { id: 4, name: '최유진', posting: '데이터 엔지니어', stage: '서류 검토', assigned: '2026.08.22', edu: 'OO대학교 통계학과', career: '3년 (데이터)', skills: 'Python · SQL · Spark' },
  { id: 5, name: '정민재', posting: '백엔드 개발자 (신입)', stage: '면접', assigned: '2026.08.18', edu: '부트캠프 수료', career: '1년 (백엔드)', skills: 'Python · Django · PostgreSQL' },
  { id: 6, name: '한소희', posting: '프론트엔드 개발자', stage: '서류 검토', assigned: '2026.08.23', edu: 'OO대학교 컴퓨터공학과', career: '2년 (프론트엔드)', skills: 'Vue · JavaScript · CSS' },
]

export default function Evaluations() {
  const [queue, setQueue] = useState(QUEUE)
  const [openId, setOpenId] = useState<number | null>(null)
  const [score, setScore] = useState<number | null>(null)
  const [comment, setComment] = useState('')

  const current = queue.find((a) => a.id === openId) ?? null

  function open(a: Assignment) {
    setOpenId(a.id)
    setScore(null)
    setComment('')
  }

  function close() {
    setOpenId(null)
  }

  /* 등록하면 그 사람을 큐에서 빼고 다음 지원자를 바로 연다 (§0.5 연속 심사) */
  function submit() {
    if (score === null || current === null) return
    const i = queue.findIndex((a) => a.id === current.id)
    const rest = queue.filter((a) => a.id !== current.id)
    setQueue(rest)
    const next = rest[i] ?? rest[i - 1] ?? null
    setOpenId(next ? next.id : null)
    setScore(null)
    setComment('')
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') close()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <PageHead
        title="평가 현황"
        actions={<span className={styles.meta}>평가 대기 {queue.length}명</span>}
      />

      <div className={styles.body}>
        <main className="page-content">
          <div className={styles.panel}>
            <div className={`${styles.row} ${styles.thead}`}>
              <span>이름</span>
              <span>공고</span>
              <span>단계</span>
              <span className={styles.num}>배정일</span>
            </div>

            {queue.map((a) => (
              <div
                key={a.id}
                className={`${styles.row} ${styles.item} ${a.id === openId ? styles.cur : ''}`}
                tabIndex={0}
                aria-current={a.id === openId ? 'true' : undefined}
                onClick={() => open(a)}
              >
                <span className={styles.name}>{a.name}</span>
                <span className={styles.posting}>{a.posting}</span>
                {/* 판단 전이라 색 없이 라벨로만 (§1) */}
                <span className={styles.stage}>{a.stage}</span>
                <span className={styles.num}>{a.assigned}</span>
              </div>
            ))}

            {queue.length === 0 && (
              <p className={styles.empty}>평가 대기 중인 지원자가 없습니다.</p>
            )}
          </div>
        </main>

        <aside className={`${styles.side} ${current ? styles.sideOpen : ''}`} aria-label="평가 패널">
          {current && (
            <div className={styles.sideInner}>
              <div className={styles.sideHead}>
                <span className={styles.sideName}>{current.name}</span>
                <span className={styles.stage}>{current.stage}</span>
              </div>
              <button type="button" className={styles.close} aria-label="패널 닫기" onClick={close}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>

              <div className={styles.sec}>
                <h2>지원 정보</h2>
                <dl className={styles.list}>
                  <dt>학력</dt><dd>{current.edu}</dd>
                  <dt>경력</dt><dd>{current.career}</dd>
                  <dt>기술</dt><dd>{current.skills}</dd>
                </dl>
              </div>

              <div className={styles.sec}>
                <h2>평가</h2>
                <div className={styles.rate} role="group" aria-label="평가 점수">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      type="button"
                      aria-pressed={score === n}
                      onClick={() => setScore(n)}
                    >
                      {n}
                    </button>
                  ))}
                </div>
                <textarea
                  className={styles.input}
                  rows={3}
                  aria-label="평가 코멘트 입력"
                  placeholder="평가 코멘트를 입력합니다"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                />
                <div className={styles.actions}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={score === null}
                    onClick={submit}
                  >
                    등록
                  </button>
                </div>
                <p className={styles.hint}>등록하면 다음 지원자로 넘어갑니다</p>
              </div>
            </div>
          )}
        </aside>
      </div>
    </>
  )
}
