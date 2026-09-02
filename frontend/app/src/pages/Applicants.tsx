import { useEffect, useMemo, useRef, useState } from 'react'
import PageHead from '../components/PageHead'
import { useRightPanel } from '../components/RightPanel'
import ApplicantPanel from './ApplicantPanel'
import { ApiError } from '../api/client'
import { applications, postings as postingsApi } from '../api/endpoints'
import type { ApplicationListItem, Posting, Stage } from '../api/types'
import { STAGE_LABEL, careerText, fmtDate, stageTone } from '../lib/stage'
import styles from './Applicants.module.css'

const FIELDS = ['전체', '이름', '공고'] as const
type Field = (typeof FIELDS)[number]

const PAGE_SIZE = 20

const TONE_CLASS = {
  progress: styles.stageProgress,
  accepted: styles.stageAccepted,
  rejected: styles.stageRejected,
}

const STAGE_PILLS: { value: Stage | null; label: string }[] = [
  { value: null, label: '전체' },
  { value: 'applied', label: '접수' },
  { value: 'screening', label: '서류' },
  { value: 'interview', label: '면접' },
  { value: 'accepted', label: '합격' },
  { value: 'rejected', label: '불합격' },
]

const NARROW_MQ = '(max-width: 768px)'

function stageBadgeClass(stage: Stage): string {
  if (stage === 'accepted') return 'badge badge-open'
  return 'badge badge-closed'
}

export default function Applicants() {
  const [field, setField] = useState<Field>('전체')
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [term, setTerm] = useState('')
  const [page, setPage] = useState(0)
  const [stageFilter, setStageFilter] = useState<Stage | null>(null)

  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(NARROW_MQ).matches,
  )

  useEffect(() => {
    const mq = window.matchMedia(NARROW_MQ)
    const on = () => setNarrow(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  const rightPanel = useRightPanel()
  const [openId, setOpenId] = useState<number | null>(null)
  const detailOpen = openId !== null && rightPanel.active === 'applicant'
  const [tick, setTick] = useState(0)

  function openDetail(id: number) {
    setOpenId(id)
    rightPanel.open('applicant')
  }

  function closeDetail() {
    setOpenId(null)
    rightPanel.close('applicant')
  }

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

  useEffect(() => {
    const ac = new AbortController()
    postingsApi
      .list(ac.signal)
      .then((list) => setPostingMap(new Map(list.map((p) => [p.id, p]))))
      .catch(() => {})
    return () => ac.abort()
  }, [])

  const postingIdFilter = useMemo(() => {
    if (field !== '공고' || term === '') return undefined
    const hit = [...postingMap.values()].find((p) =>
      p.title.toLowerCase().includes(term.toLowerCase()),
    )
    return hit?.id ?? -1
  }, [field, term, postingMap])

  useEffect(() => {
    const ac = new AbortController()
    setError(null)
    applications
      .search(
        {
          q: field === '공고' ? undefined : term || undefined,
          stage: stageFilter ?? undefined,
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
  }, [term, field, postingIdFilter, page, tick, stageFilter])

  const pages = total === null ? 1 : Math.max(1, Math.ceil(total / PAGE_SIZE))
  const from = page * PAGE_SIZE + 1
  const to = page * PAGE_SIZE + (rows?.length ?? 0)

  return (
    <div className={styles.split}>
      <div className={styles.col}>
        <PageHead title="지원자" />

        {narrow ? (
          /* ── 모바일 툴바 ─────────────── */
          <div className={styles.mobileToolbar}>
            <div className={styles.mobileSearch}>
              <svg viewBox="0 0 24 24" aria-hidden="true" className={styles.searchIcon}>
                <circle cx="11" cy="11" r="7" /><path d="m16.5 16.5 4 4" />
              </svg>
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
            <div className={styles.pills} role="tablist">
              {STAGE_PILLS.map((p) => (
                <button
                  key={String(p.value)}
                  type="button"
                  role="tab"
                  aria-selected={stageFilter === p.value}
                  className={`${styles.pill} ${stageFilter === p.value ? styles.pillOn : ''}`}
                  onClick={() => { setStageFilter(p.value); setPage(0) }}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* ── 데스크탑 툴바 ───────────── */
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
            <span className={styles.meta}>
              {total === null ? '—' : `${total.toLocaleString()}건`}
            </span>
          </div>
        )}

        <main className="page-content">
          {narrow ? (
            /* ── 모바일 카드 목록 ───────── */
            <div className={styles.cardList}>
              {total !== null && (
                <p className={styles.countLine}>{total.toLocaleString()}건</p>
              )}
              {rows?.map((a) => (
                <div
                  key={a.id}
                  className={`${styles.appCard} ${a.id === openId ? styles.appCardCur : ''}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => openDetail(a.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openDetail(a.id) }
                  }}
                >
                  <div className={styles.appCardTop}>
                    <span className={styles.appName}>{a.name}</span>
                    <span className={stageBadgeClass(a.current_stage)}>
                      {STAGE_LABEL[a.current_stage]}
                    </span>
                  </div>
                  <p className={styles.appPosting}>
                    {postingMap.get(a.job_posting_id)?.title ?? '—'}
                  </p>
                  <p className={styles.appMeta}>
                    {careerText(a.career_years)} · 평가 {a.avg_score === null ? '—' : a.avg_score.toFixed(1)} · {fmtDate(a.created_at)} 지원
                  </p>
                </div>
              ))}
              {error !== null && <p className={styles.empty} role="alert">{error}</p>}
              {error === null && rows === null && <p className={styles.empty}>불러오는 중…</p>}
              {error === null && rows?.length === 0 && (
                <p className={styles.empty}>{term ? '검색 결과가 없습니다.' : '등록된 지원자가 없습니다.'}</p>
              )}
            </div>
          ) : (
            /* ── 데스크탑 테이블 ─────────── */
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
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openDetail(a.id) }
                  }}
                >
                  <span className={styles.name}>{a.name}</span>
                  <span className={styles.posting}>{postingMap.get(a.job_posting_id)?.title ?? '—'}</span>
                  <span className={TONE_CLASS[stageTone(a.current_stage)]}>{STAGE_LABEL[a.current_stage]}</span>
                  <span className={styles.num}>{careerText(a.career_years)}</span>
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
                    <button type="button" className={styles.page} disabled={page === 0}
                      onClick={() => setPage((p) => Math.max(0, p - 1))}>이전</button>
                    <button type="button" className={`${styles.page} ${styles.pageCur}`}>{page + 1}</button>
                    <button type="button" className={styles.page} disabled={page + 1 >= pages}
                      onClick={() => setPage((p) => p + 1)}>다음</button>
                  </span>
                </div>
              )}
            </div>
          )}
        </main>
      </div>

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
