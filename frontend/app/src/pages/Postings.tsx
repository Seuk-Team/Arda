import { useEffect, useState } from 'react'
import PageHead from '../components/PageHead'
import { ApiError } from '../api/client'
import { postings as postingsApi } from '../api/endpoints'
import type { Posting } from '../api/types'
import styles from './Postings.module.css'

/* 서버는 draft/open/closed 로 준다. 목업이 그린 뱃지는 진행중·마감 둘뿐이라
   draft 는 중립 뱃지에 "작성중" 으로 둔다 — 확정 문구는 팀장 확인 필요. */
const STATUS_LABEL: Record<Posting['status'], string> = {
  draft: '작성중',
  open: '진행중',
  closed: '마감',
}

/* 서버가 주는 ISO 날짜(2026-09-15)를 목업 표기(2026.09.15)로. */
function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return iso.slice(0, 10).replaceAll('-', '.')
}

/* 마감일 칸은 날짜가 본체고 D-day 는 그 옆에 붙는 보조 정보다.
   d_day 는 서버가 응답 시점에 계산해 준다(음수면 이미 지났다). */
function deadlineText(p: Posting): string {
  if (p.deadline === null) return '상시'
  if (p.d_day === null) return fmtDate(p.deadline)
  const dday = p.d_day >= 0 ? `D-${p.d_day}` : `D+${-p.d_day}`
  return `${fmtDate(p.deadline)} · ${dday}`
}

export default function Postings() {
  const [rows, setRows] = useState<Posting[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const ac = new AbortController()
    setError(null)
    postingsApi
      .list(ac.signal)
      .then(setRows)
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        // 401 은 RequireAuth 가 다음 렌더에서 로그인으로 보낸다. 여기서 또 안내하지 않는다.
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '공고를 불러오지 못했습니다')
      })
    return () => ac.abort()
  }, [])

  return (
    <>
      <PageHead
        title="채용 공고"
        actions={<button className="btn btn-primary">공고 등록</button>}
      />
      <main className="page-content">
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
                <tr key={p.id}>
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

          {/* §6 데이터 화면 3종. 표 헤더는 남겨 두고 본문 자리에만 상태를 그린다 */}
          {error !== null && <p className={styles.state} role="alert">{error}</p>}
          {error === null && rows === null && <p className={styles.state}>불러오는 중…</p>}
          {error === null && rows?.length === 0 && (
            <p className={styles.state}>등록된 공고가 없습니다.</p>
          )}
        </div>
      </main>
    </>
  )
}
