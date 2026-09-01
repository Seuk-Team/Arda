import { useEffect, useMemo, useRef, useState } from 'react'
import PageHead from '../components/PageHead'
import { useRightPanel } from '../components/RightPanel'
import ApplicantPanel from './ApplicantPanel'
import { ApiError } from '../api/client'
import { applications, postings as postingsApi } from '../api/endpoints'
import type { ApplicationListItem, Posting } from '../api/types'
import { STAGE_LABEL, careerText, fmtDate, stageTone } from '../lib/stage'
import styles from './Applicants.module.css'

/* 전 공고 통합 검색 테이블 (05-design §0.5). 칸반 없음. */
const FIELDS = ['전체', '이름', '공고'] as const
type Field = (typeof FIELDS)[number]

const PAGE_SIZE = 20

const TONE_CLASS = {
  progress: styles.stageProgress,
  accepted: styles.stageAccepted,
  rejected: styles.stageRejected,
}

export default function Applicants() {
  const [field, setField] = useState<Field>('전체')
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  /* 타이핑마다 서버를 때리지 않는다. 10만 건 검색은 한 번이 비싸다. */
  const [term, setTerm] = useState('')
  const [page, setPage] = useState(0)

  /* 상세 패널에 열려 있는 지원자. 오른쪽 한 자리를 나눠 쓴다 —
     아르를 열면 이쪽이 닫힌다 (RightPanel) */
  const rightPanel = useRightPanel()
  const [openId, setOpenId] = useState<number | null>(null)
  const detailOpen = openId !== null && rightPanel.active === 'applicant'
  /* 단계가 바뀌면 목록을 다시 센다 */
  const [tick, setTick] = useState(0)

  function openDetail(id: number) {
    setOpenId(id)
    rightPanel.open('applicant')
  }

  function closeDetail() {
    setOpenId(null)
    rightPanel.close('applicant')
  }

  /* 오른쪽 자리를 다른 패널(아르 등)에 뺏기면 고른 것도 버린다 —
     안 버리면 행 강조가 남아 밑에 깔아 둔 것처럼 되고, 그 패널이 닫힐 때
     되살아난 것처럼 보인다 */
  useEffect(() => {
    if (rightPanel.active !== 'applicant') setOpenId(null)
  }, [rightPanel.active])

  const [rows, setRows] = useState<ApplicationListItem[] | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [tookMs, setTookMs] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [postingMap, setPostingMap] = useState<Map<number, Posting>>(new Map())

  const debounce = useRef<number | undefined>(undefined)
  useEffect(() => {
    window.clearTimeout(debounce.current)
    debounce.current = window.setTimeout(() => {
      setTerm(q.trim())
      setPage(0)
    }, 300)
    return () => window.clearTimeout(debounce.current)
  }, [q])

  /* 공고명은 목록에 없다 — 지원자 행은 job_posting_id 만 준다. 한 번 받아 두고 이름을 붙인다 */
  useEffect(() => {
    const ac = new AbortController()
    postingsApi
      .list(ac.signal)
      .then((list) => setPostingMap(new Map(list.map((p) => [p.id, p]))))
      .catch(() => {
        /* 공고 이름을 못 받아도 목록 자체는 보여 준다 */
      })
    return () => ac.abort()
  }, [])

  /* "공고" 검색은 서버 q 가 이름·이메일만 보므로 posting_id 로 바꿔 보낸다.
     API 가 공고를 하나만 받아서, 여러 개가 걸리면 첫 번째만 쓴다. */
  const postingIdFilter = useMemo(() => {
    if (field !== '공고' || term === '') return undefined
    const hit = [...postingMap.values()].find((p) =>
      p.title.toLowerCase().includes(term.toLowerCase()),
    )
    return hit?.id ?? -1 // 걸리는 공고가 없으면 빈 결과가 되도록 없는 id 를 보낸다
  }, [field, term, postingMap])

  useEffect(() => {
    const ac = new AbortController()
    setError(null)
    applications
      .search(
        {
          q: field === '공고' ? undefined : term || undefined,
          posting_id: postingIdFilter,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
          with_total: true,
        },
        ac.signal,
      )
      .then((res) => {
        setRows(res.items)
        setTotal(res.total)
        setTookMs(res.took_ms)
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '지원자를 불러오지 못했습니다')
      })
    return () => ac.abort()
    /* tick — 상세 패널에서 단계를 바꾸면 목록도 다시 받는다 */
  }, [term, field, postingIdFilter, page, tick])

  const pages = total === null ? 1 : Math.max(1, Math.ceil(total / PAGE_SIZE))
  const from = page * PAGE_SIZE + 1
  const to = page * PAGE_SIZE + (rows?.length ?? 0)

  return (
    /* 패널이 열리면 제목·툴바까지 같이 밀린다 — 화면 전체를 한 열로 묶고 패널을
       그 열의 형제로 둔다 (2026-09-01, 공고의 지원자 화면과 같은 구성) */
    <div className={styles.split}>
      <div className={styles.col}>
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
                  onClick={() => { setField(f); setOpen(false); setPage(0) }}
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
        {/* 10만 건 검색 무대라 응답 시간을 표기한다 (05-design §0.5).
            숫자는 서버가 잰 took_ms 다 — 화면이 지어내지 않는다 */}
        <span className={styles.meta}>
          {total === null ? '—' : `${total.toLocaleString()}건`}
          {tookMs !== null && ` · ${(tookMs / 1000).toFixed(2)}초`}
        </span>
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

          {rows?.map((a) => (
            <div
              key={a.id}
              className={`${styles.row} ${styles.item} ${a.id === openId ? styles.cur : ''}`}
              tabIndex={0}
              role="button"
              aria-current={a.id === openId ? 'true' : undefined}
              onClick={() => openDetail(a.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  openDetail(a.id)
                }
              }}
            >
              <span className={styles.name}>{a.name}</span>
              <span className={styles.posting}>{postingMap.get(a.job_posting_id)?.title ?? '—'}</span>
              <span className={TONE_CLASS[stageTone(a.current_stage)]}>{STAGE_LABEL[a.current_stage]}</span>
              <span className={styles.num}>{careerText(a.career_years)}</span>
              {/* 서버는 sort=score 로 부를 때만 평균을 채운다. 지원일순인 이 화면에서는
                  아직 못 받는다 — 목업이 미평가에 쓰는 표기를 그대로 둔다 */}
              <span className={styles.num}>{a.avg_score === null ? '—' : a.avg_score.toFixed(1)}</span>
              <span className={styles.num}>{fmtDate(a.created_at)}</span>
            </div>
          ))}

          {error !== null && <p className={styles.empty} role="alert">{error}</p>}
          {error === null && rows === null && <p className={styles.empty}>불러오는 중…</p>}
          {error === null && rows?.length === 0 && (
            <p className={styles.empty}>{term ? '검색 결과가 없습니다.' : '등록된 지원자가 없습니다.'}</p>
          )}

          {rows !== null && rows.length > 0 && (
            <div className={styles.foot}>
              <span>{total === null ? `${rows.length}명` : `${total.toLocaleString()}명 중 ${from}–${to}`}</span>
              <span className={styles.pager}>
                <button
                  type="button"
                  className={styles.page}
                  disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                >
                  이전
                </button>
                <button type="button" className={`${styles.page} ${styles.pageCur}`}>{page + 1}</button>
                <button
                  type="button"
                  className={styles.page}
                  disabled={page + 1 >= pages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  다음
                </button>
              </span>
            </div>
          )}
        </div>
      </main>
      </div>

      {/* 상세는 페이지 이동 없이 옆에서 연다 (05-design §0.5) — 공고의 지원자 화면과
          같은 패널이다. 오른쪽 한 자리를 나눠 쓴다 (RightPanel) */}
      {detailOpen && openId !== null && (
        <ApplicantPanel
          applicationId={openId}
          onClose={closeDetail}
          onChanged={() => setTick((n) => n + 1)}
        />
      )}
    </div>
  )
}
