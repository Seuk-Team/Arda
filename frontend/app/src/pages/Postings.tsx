import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageHead from '../components/PageHead'
import { ApiError } from '../api/client'
import { postings as postingsApi } from '../api/endpoints'
import type { Posting } from '../api/types'
import styles from './Postings.module.css'

const STATUS_LABEL: Record<Posting['status'], string> = {
  draft: '작성중',
  open: '진행중',
  closed: '마감',
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return iso.slice(0, 10).replaceAll('-', '.')
}

function deadlineText(p: Posting): string {
  if (p.deadline === null) return '상시'
  if (p.d_day === null) return fmtDate(p.deadline)
  const dday = p.d_day >= 0 ? `D-${p.d_day}` : `D+${-p.d_day}`
  return `${fmtDate(p.deadline)} · ${dday}`
}

const STAGES = [
  { key: 'applied',   label: '접수', color: 'var(--stage-1)' },
  { key: 'screening', label: '서류', color: 'var(--stage-2)' },
  { key: 'interview', label: '면접', color: 'var(--stage-3)' },
  { key: 'accepted',  label: '합격', color: 'var(--stage-4)' },
]

const NARROW_MQ = '(max-width: 768px)'

export default function Postings() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<Posting[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(NARROW_MQ).matches,
  )

  useEffect(() => {
    const mq = window.matchMedia(NARROW_MQ)
    const on = () => setNarrow(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  useEffect(() => {
    const ac = new AbortController()
    setError(null)
    postingsApi
      .list(ac.signal)
      .then(setRows)
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '공고를 불러오지 못했습니다')
      })
    return () => ac.abort()
  }, [])

  return (
    <>
      <PageHead
        title="채용 공고"
        actions={<button className={styles.addBtn} aria-label="공고 등록">+</button>}
      />
      <main className="page-content">
        {narrow ? (
          <div className={styles.cardList}>
            {rows?.map((p) => {
              const sc = p.stage_counts ?? {}
              const total = Object.values(sc).reduce((a, b) => a + b, 0)
              return (
                <div
                  key={p.id}
                  className={styles.card}
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(`/postings/${p.id}`)}
                  onKeyDown={(e) => e.key === 'Enter' && navigate(`/postings/${p.id}`)}
                >
                  <div className={styles.cardTop}>
                    <span className={styles.cardTitle}>{p.title}</span>
                    <span className={`badge ${p.status === 'open' ? 'badge-open' : 'badge-closed'}`}>
                      {STATUS_LABEL[p.status]}
                    </span>
                  </div>
                  <p className={styles.cardSub}>
                    지원자 {p.application_count}명 · 마감 {deadlineText(p)}
                  </p>
                  {total > 0 && (
                    <>
                      <div
                        className={styles.bar}
                        style={{
                          gridTemplateColumns: STAGES.map((s) => `minmax(6px, ${sc[s.key] ?? 0}fr)`).join(' '),
                        }}
                      >
                        {STAGES.map((s) => (
                          <div key={s.key} className={styles.barSeg} style={{ background: s.color }} />
                        ))}
                      </div>
                      <div className={styles.stageCounts}>
                        {STAGES.map((s, i) => (
                          <span key={s.key} className={styles.stageItem}>
                            <span className={styles.stageDot} style={{ background: s.color }} />
                            {s.label} {sc[s.key] ?? 0}
                            {i < STAGES.length - 1 && <span className={styles.sep}> · </span>}
                          </span>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )
            })}
            {error !== null && <p className={styles.state} role="alert">{error}</p>}
            {error === null && rows === null && <p className={styles.state}>불러오는 중…</p>}
            {error === null && rows?.length === 0 && (
              <p className={styles.state}>등록된 공고가 없습니다.</p>
            )}
          </div>
        ) : (
          <div className={styles.panel}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>공고명</th>
                  <th>상태</th>
                  <th className={styles.num}>지원자</th>
                  <th className={styles.num}>마감</th>
                  <th className={styles.num}>등록일</th>
                </tr>
              </thead>
              <tbody>
                {rows?.map((p) => (
                  <tr key={p.id} className={styles.clickable} onClick={() => navigate(`/postings/${p.id}`)}>
                    <td className={styles.name}>{p.title}</td>
                    <td>
                      <span className={`badge ${p.status === 'open' ? 'badge-open' : 'badge-closed'}`}>
                        {STATUS_LABEL[p.status]}
                      </span>
                    </td>
                    <td className={styles.num}>{p.application_count}명</td>
                    <td className={styles.num}>{deadlineText(p)}</td>
                    <td className={styles.num}>{fmtDate(p.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {error !== null && <p className={styles.state} role="alert">{error}</p>}
            {error === null && rows === null && <p className={styles.state}>불러오는 중…</p>}
            {error === null && rows?.length === 0 && (
              <p className={styles.state}>등록된 공고가 없습니다.</p>
            )}
          </div>
        )}
      </main>
    </>
  )
}
