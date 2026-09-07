import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { integrity as integrityApi } from '../api/endpoints'
import type { ApplicationIntegrity, IntegrityVerdict, Publication } from '../api/types'
import styles from './IntegrityBadge.module.css'

/* 제출물 무결성 배지 (ADR-0028).

   **"위조 방지"가 아니라 "위조 검출"이다.** DB 를 고치는 건 누구도 막을 수
   없다. 달라지는 건 고친 사실이 드러난다는 점이고, 문구도 그렇게 쓴다 —
   "우리도 못 바꾼다"가 아니라 "우리가 바꿔도 숨길 수 없다".

   상세 화면에서 한 번만 부른다. 이 API 는 볼 때마다 S3 에서 원본을 다시 읽어
   지문을 새로 뜨므로, 목록에서 부르면 사람 수만큼 S3 를 읽는다. */

/* 네 상태. `none` 을 `ok` 와 같은 초록으로 칠하면 안 된다 —
   `none` 은 "깨끗하다"가 아니라 **"증명할 근거가 아예 없다"** 이고,
   초록으로 칠하면 우리가 보증하지 않는 것을 보증하는 것처럼 보인다.
   `unreadable` 도 `mismatch` 와 갈라야 한다: 하나는 "바뀌었다",
   하나는 "확인을 못 했다"이다. */
const VERDICT: Record<IntegrityVerdict, { label: string; tone: string; note: string }> = {
  ok: {
    label: '제출 당시와 같음',
    tone: 'ok',
    note: '접수 시 뜬 지문과 지금 원본이 일치합니다.',
  },
  mismatch: {
    label: '내용이 바뀜',
    tone: 'bad',
    note: '접수 시 뜬 지문과 지금 원본이 다릅니다. 어느 문서인지 아래에서 확인하세요.',
  },
  unreadable: {
    label: '확인 못 함',
    tone: 'warn',
    note: '원본을 읽지 못했습니다(파일이 없거나 저장소 오류). 바뀌었다는 뜻은 아닙니다.',
  },
  none: {
    label: '대조할 지문 없음',
    tone: 'none',
    note: '접수 시 지문을 뜨기 전에 들어온 지원서입니다. 검사할 근거가 없습니다.',
  },
}

const DOC_TYPE: Record<string, string> = {
  resume: '이력서',
  cover_letter: '자기소개서',
  self_intro: '자기소개(폼 입력)',
}

const ITEM_STATUS: Record<string, { label: string; tone: string }> = {
  ok: { label: '일치', tone: 'ok' },
  mismatch: { label: '다름', tone: 'bad' },
  unreadable: { label: '못 읽음', tone: 'warn' },
}

export default function IntegrityBadge({ applicationId }: { applicationId: number }) {
  const [data, setData] = useState<ApplicationIntegrity | null>(null)
  const [pubs, setPubs] = useState<Publication[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const ac = new AbortController()
    setData(null)
    setOpen(false)

    integrityApi
      .get(applicationId, ac.signal)
      .then((res) => {
        setError(null)
        setData(res)
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '무결성을 확인하지 못했습니다')
      })

    /* 체인 게시 기록은 지원자별이 아니라 전체 사슬에 대한 것이라 실패해도
       배지 자체는 보여준다 — "체인에 못 박힘" 한 줄만 빠진다 */
    integrityApi
      .publications(ac.signal)
      .then(setPubs)
      .catch(() => {})

    return () => ac.abort()
  }, [applicationId])

  if (error !== null) {
    return (
      <div className={styles.sec}>
        <h2>제출물 무결성</h2>
        <p className={styles.state} role="alert">{error}</p>
      </div>
    )
  }

  if (data === null) {
    return (
      <div className={styles.sec}>
        <h2>제출물 무결성</h2>
        <p className={styles.state}>확인하는 중…</p>
      </div>
    )
  }

  const v = VERDICT[data.verdict]

  /* 공개 체인에 올라간 구간인지. covered_through_seq 보다 seq 가 작거나 같은
     고리가 이미 밖에서 확인 가능한 것이다. 확정(confirmed)된 기록만 센다 —
     대기 중인 거래를 근거로 "못 박혔다"고 하면 안 된다. */
  const confirmed = (pubs ?? []).filter((p) => p.status === 'confirmed')
  const coveredThrough = confirmed.reduce((m, p) => Math.max(m, p.covered_through_seq), 0)
  const maxSeq = data.items.reduce((m, i) => Math.max(m, i.seq), 0)
  const allCovered = data.items.length > 0 && maxSeq <= coveredThrough
  /* 링크는 서버가 준 것만 쓴다 — 네트워크마다 탐색기가 달라 주소를 조립하면 안 된다 */
  const pub = confirmed.find((p) => p.explorer_url) ?? null

  return (
    <div className={styles.sec}>
      <div className={styles.head}>
        <h2>제출물 무결성</h2>
        <span className={`${styles.badge} ${styles[v.tone]}`}>{v.label}</span>
      </div>

      <p className={styles.note}>{v.note}</p>

      {allCovered && pub !== null && (
        <p className={styles.chain}>
          지문이 공개 체인에 올라가 있습니다 — 우리가 고쳐도 숨길 수 없습니다.{' '}
          <a href={pub.explorer_url!} target="_blank" rel="noreferrer noopener">
            거래 보기 ↗
          </a>
        </p>
      )}

      {data.items.length > 0 && (
        <>
          <button
            type="button"
            className={styles.toggle}
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
          >
            문서 {data.items.length}건 {open ? '접기' : '펼치기'}
          </button>

          {open && (
            <ul className={styles.list}>
              {data.items.map((it) => {
                const st = ITEM_STATUS[it.status] ?? { label: it.status, tone: 'none' }
                return (
                  <li key={it.seq} className={styles.item}>
                    <span className={styles.itemName}>
                      {it.filename ?? DOC_TYPE[it.doc_type] ?? it.doc_type}
                    </span>
                    <span className={`${styles.chip} ${styles[st.tone]}`}>{st.label}</span>
                    {it.reason !== null && <span className={styles.reason}>{it.reason}</span>}
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
