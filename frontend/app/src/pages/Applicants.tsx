import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import PageHead from '../components/PageHead'
import { useRightPanel } from '../components/RightPanel'
import ApplicantPanel from './ApplicantPanel'
import { ApiError } from '../api/client'
import { applications, postings as postingsApi } from '../api/endpoints'
import type { ApplicationListItem, Posting, Stage } from '../api/types'
import { STAGE_LABEL, careerText, fmtDate } from '../lib/stage'
import styles from './Applicants.module.css'

/* 1280×720 에서 스크롤 없이 들어가는 수. 20 이면 절반이 화면 밖이라,
   목록을 보려면 스크롤부터 해야 했다 (2026-09-10) */
const PAGE_SIZE = 10

/* 단계마다 다른 배지. lib/stage.ts 의 stageTone 은 셋(진행/합격/불합격)으로만
   나눠서 면접을 따로 강조할 수 없다 — 그 함수는 공고별 지원자 화면도 쓰므로
   건드리지 않고 여기서 다섯으로 편다. */
const STAGE_CLASS: Record<Stage, string> = {
  applied: styles.stageProgress,
  screening: styles.stageProgress,
  interview: styles.stageNow,
  accepted: styles.stageAccepted,
  rejected: styles.stageRejected,
}

/* 끝난 건 — 시선만 낮춘다. 클릭은 그대로 된다 */
const isClosed = (s: Stage) => s === 'accepted' || s === 'rejected'

/* 칩 다섯 칸. 합격·불합격은 '종료' 하나로 합친다 — 매일 볼 항목이 아니라
   두 칸을 따로 내주면 진행 중인 것들이 그만큼 밀린다. */
type ChipKey = '' | 'applied' | 'screening' | 'interview' | 'closed'

const CHIPS: { key: ChipKey; label: string }[] = [
  { key: '', label: '전체' },
  { key: 'applied', label: '접수' },
  { key: 'screening', label: '서류' },
  { key: 'interview', label: '면접' },
  { key: 'closed', label: '종료' },
]

/* 서버에 보낼 값. '종료' 는 둘을 한 번에 보낸다(?stage=accepted&stage=rejected) */
const CHIP_STAGES: Record<ChipKey, Stage[] | undefined> = {
  '': undefined,
  applied: ['applied'],
  screening: ['screening'],
  interview: ['interview'],
  closed: ['accepted', 'rejected'],
}

/* 서버가 받는 정렬은 둘뿐이다 (backend/app/api/search.py SORTS).
   경력 순은 없다 — 클라이언트에서 섞으면 현재 쪽 10건만 뒤집혀 거짓말이 된다. */
const SORTS = [
  { key: 'created_at:desc', label: '지원일 최신순' },
  { key: 'created_at:asc', label: '지원일 오래된순' },
  { key: 'score:desc', label: '평점 높은순' },
] as const
type SortKey = (typeof SORTS)[number]['key']

const NARROW_MQ = '(max-width: 768px)'

function stageBadgeClass(stage: Stage): string {
  if (stage === 'accepted') return 'badge badge-open'
  return 'badge badge-closed'
}

export default function Applicants() {
  /* 필터는 URL 에 둔다. 로컬 상태로만 두면 새로고침·뒤로가기·링크 공유에서
     전부 초기화된다 — 상세를 열었다 닫아도 필터가 남아야 한다.
     프로젝트 전례: Settings.tsx 의 ?tab= */
  const [params, setParams] = useSearchParams()

  const job = params.get('job')
  const jobId = job === null ? undefined : Number(job)
  const chip = (params.get('stage') ?? '') as ChipKey
  const sortKey = (params.get('sort') ?? 'created_at:desc') as SortKey
  const page = Math.max(0, Number(params.get('page') ?? '1') - 1)
  const urlQ = params.get('q') ?? ''

  /* 한 번에 여러 값을 바꿀 때가 많아 patch 로 받는다. 필터가 바뀌면 1쪽으로
     되돌린다 — 3쪽을 보다 필터를 걸면 빈 화면이 된다 */
  function setFilter(patch: Record<string, string | null>, keepPage = false) {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === '') next.delete(k)
      else next.set(k, v)
    }
    if (!keepPage) next.delete('page')
    setParams(next, { replace: true })
  }

  const [jobOpen, setJobOpen] = useState(false)
  const [sortOpen, setSortOpen] = useState(false)
  const [q, setQ] = useState(urlQ)
  const term = urlQ

  /* 타자마다 URL 을 바꾸면 히스토리가 더러워진다 — 멈춘 뒤에 한 번 쓴다 */
  useEffect(() => {
    if (q === urlQ) return
    const t = setTimeout(() => setFilter({ q: q || null }), 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

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

  /* 목록의 [평가] 로 들어왔는지. 상세가 평가 입력을 펼친 채로 열린다 */
  const [startRating, setStartRating] = useState(false)

  function openDetail(id: number, rating = false) {
    setOpenId(id)
    setStartRating(rating)
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
  const [error, setError] = useState<string | null>(null)
  const [postingMap, setPostingMap] = useState<Map<number, Posting>>(new Map())


  useEffect(() => {
    const ac = new AbortController()
    postingsApi
      .list(ac.signal)
      .then((list) => setPostingMap(new Map(list.map((p) => [p.id, p]))))
      .catch(() => {})
    return () => ac.abort()
  }, [])

  /* 진행 중인 공고를 위에, 마감된 것을 아래에 */
  const postingList = useMemo(() => {
    const all = [...postingMap.values()]
    const openOnes = all.filter((p) => p.status !== 'closed')
    const closedOnes = all.filter((p) => p.status === 'closed')
    return { openOnes, closedOnes }
  }, [postingMap])

  /* 칩 숫자는 **서버 집계**를 쓴다. 현재 쪽의 행을 세면 페이지를 넘기는
     순간 숫자가 바뀐다. Posting.stage_counts (B3) 가 이미 서버 계산값이라
     새 엔드포인트가 필요 없다 — 공고를 고르면 그것, 전체면 합계다. */
  const counts = useMemo(() => {
    const src = jobId === undefined
      ? [...postingMap.values()]
      : [postingMap.get(jobId)].filter((x): x is Posting => x !== undefined)
    const sum = (k: string) => src.reduce((t, p) => t + (p.stage_counts?.[k] ?? 0), 0)
    return {
      '': src.reduce((t, p) => t + p.application_count, 0),
      applied: sum('applied'),
      screening: sum('screening'),
      interview: sum('interview'),
      closed: sum('accepted') + sum('rejected'),
    } as Record<ChipKey, number>
  }, [postingMap, jobId])

  const [sortField, sortOrder] = sortKey.split(':') as ['created_at' | 'score', 'desc' | 'asc']
  const jobTitle = jobId === undefined ? null : postingMap.get(jobId)?.title ?? null

  useEffect(() => {
    const ac = new AbortController()
    setError(null)
    applications
      .search(
        {
          q: term || undefined,
          stage: CHIP_STAGES[chip],
          posting_id: jobId,
          sort: sortField,
          order: sortOrder,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
          with_total: true,
        },
        ac.signal,
      )
      .then((res) => {
        setRows(res.items)
        setTotal(res.total)
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '지원자를 불러오지 못했습니다')
      })
    return () => ac.abort()
  }, [term, jobId, chip, sortField, sortOrder, page, tick])

  const pages = total === null ? 1 : Math.max(1, Math.ceil(total / PAGE_SIZE))
  const from = page * PAGE_SIZE + 1
  const to = page * PAGE_SIZE + (rows?.length ?? 0)

  return (
    <div className={styles.split}>
      <div className={styles.col}>
        {/* 공고는 나머지 필터를 지배하는 상위 조건이라 제목 옆에 둔다 —
            검색·정렬과 같은 줄에 두면 위계가 안 맞는다 */}
        {/* 공고 드롭다운은 PageHead 의 meta 자리에 넣는다 — 제목 옆에 붙는
            요약 칸이고, 그 뒤 spacer 가 계정 메뉴를 오른쪽 끝으로 민다.
            바깥에서 flex 로 감싸면 계정 메뉴까지 제목 옆으로 끌려온다. */}
        <PageHead
          title="지원자"
          meta={(
            <>
              <div className={`${styles.dd} ${jobOpen ? styles.ddOpen : ''}`}>
                <button
                  type="button"
                  className={`${styles.jobBtn} ${jobId !== undefined ? styles.jobOn : ''}`}
                  aria-haspopup="listbox"
                  aria-expanded={jobOpen}
                  onClick={() => setJobOpen((v) => !v)}
                >
                  <span>{jobTitle ?? '전체 공고'}</span>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
                </button>
                <ul className={styles.ddMenu} role="listbox">
                  {/* 고르기 전에 그 공고에 몇 명인지 보인다 — 안 보이면 하나씩
                      골라 보며 확인해야 한다. application_count 는 서버 값이다 */}
                  <li role="option" aria-selected={jobId === undefined}
                    className={`${styles.ddRow} ${jobId === undefined ? styles.ddSel : ''}`}
                    onClick={() => { setFilter({ job: null }); setJobOpen(false) }}>
                    <span className={styles.ddTitle}>전체 공고</span>
                    <span className={styles.ddCount}>{counts['']}</span>
                  </li>
                  {/* 진행 중이 위, 마감이 아래. 구분 머리 대신 **배지**를 붙인다 —
                      머리를 두면 목록이 두 토막으로 갈려 훑기가 끊긴다 */}
                  {[...postingList.openOnes, ...postingList.closedOnes].map((o) => (
                    <li key={o.id} role="option" aria-selected={o.id === jobId}
                      className={`${styles.ddRow} ${o.id === jobId ? styles.ddSel : ''}`}
                      onClick={() => { setFilter({ job: String(o.id) }); setJobOpen(false) }}>
                      <span className={styles.ddTitle}>{o.title}</span>
                      {o.status === 'closed' && <span className={styles.ddClosed}>마감</span>}
                      <span className={styles.ddCount}>{o.application_count}</span>
                    </li>
                  ))}
                </ul>
              </div>
              {jobId !== undefined && (
                <button type="button" className={styles.clearJob} onClick={() => setFilter({ job: null })}>
                  × 전체 보기
                </button>
              )}
            </>
          )}
        />

        {/* 칩 줄과 검색·정렬 줄은 **한 덩어리다**. 각자 반투명 배경을 깔면
            뒤의 오로라가 자리마다 달라 같은 값인데도 색이 갈리고 경계선이 생긴다.
            바깥에서 한 겹만 깔고 안쪽은 투명하게 둔다. */}
        <div className={styles.filterBar}>
        {/* 칩은 좁은 화면·넓은 화면이 같이 쓴다 — 전에는 모바일 툴바 안에만
            있어서 데스크탑에는 단계로 좁힐 수단이 아예 없었다 */}
        <div className={styles.pills} role="tablist" aria-label="단계 필터">
          {CHIPS.map((c) => (
            <button
              key={c.key}
              type="button"
              role="tab"
              aria-selected={chip === c.key}
              className={`${styles.pill} ${chip === c.key ? styles.pillOn : ''} ${c.key === 'closed' ? styles.pillQuiet : ''}`}
              onClick={() => setFilter({ stage: c.key })}
            >
              {c.label} <b>{counts[c.key]}</b>
            </button>
          ))}
        </div>
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
          </div>
        ) : (
          /* ── 데스크탑 툴바 ───────────── */
          <div className={styles.toolbar}>
            {/* 공고는 드롭다운이 맡는다 — 검색은 이름만 본다 */}
            <div className={styles.search}>
              <svg viewBox="0 0 24 24" aria-hidden="true" className={styles.searchIcon}>
                <circle cx="11" cy="11" r="7" /><path d="m16.5 16.5 4 4" />
              </svg>
              <input
                type="text"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="이름 검색"
              />
              {q && (
                <button type="button" className={styles.sx} aria-label="검색어 지우기" onClick={() => setQ('')}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
                </button>
              )}
            </div>
            <div className={`${styles.dd} ${sortOpen ? styles.ddOpen : ''}`}>
              <button
                type="button"
                className={styles.ddBtn}
                aria-haspopup="listbox"
                aria-expanded={sortOpen}
                onClick={() => setSortOpen((v) => !v)}
              >
                <span>{SORTS.find((o) => o.key === sortKey)?.label ?? SORTS[0].label}</span>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
              </button>
              <ul className={styles.ddMenu} role="listbox">
                {SORTS.map((o) => (
                  <li
                    key={o.key}
                    role="option"
                    aria-selected={o.key === sortKey}
                    className={o.key === sortKey ? styles.ddSel : undefined}
                    onClick={() => { setFilter({ sort: o.key === 'created_at:desc' ? null : o.key }); setSortOpen(false) }}
                  >
                    {o.label}
                  </li>
                ))}
              </ul>
            </div>
            <span className={styles.meta}>
              {total === null ? '—' : `${total.toLocaleString()}건`}
            </span>
          </div>
        )}

        </div>

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
                  className={`${styles.row} ${styles.item} ${isClosed(a.current_stage) ? styles.closed : ''} ${a.id === openId ? styles.cur : ''}`}
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
                  <span>
                    <span className={`${styles.stageBadge} ${STAGE_CLASS[a.current_stage]}`}>
                      {STAGE_LABEL[a.current_stage]}
                    </span>
                  </span>
                  <span className={styles.num}>{careerText(a.career_years)}</span>
                  {/* 값이 없다고 줄표를 두면 컬럼이 통째로 죽는다 — 리스트에
                      평가를 넣을 자리가 없어서 아무도 안 채우고 있었다.
                      빈 상태를 행동으로 바꾼다 (행 클릭과 겹치지 않게 stopPropagation) */}
                  <span className={styles.num}>
                    {a.avg_score === null ? (
                      <button
                        type="button"
                        className={styles.rate}
                        onClick={(e) => { e.stopPropagation(); openDetail(a.id, true) }}
                      >
                        평가
                      </button>
                    ) : a.avg_score.toFixed(1)}
                  </span>
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
                      onClick={() => setFilter({ page: String(page) }, true)}>이전</button>
                    <button type="button" className={`${styles.page} ${styles.pageCur}`}>{page + 1}</button>
                    <button type="button" className={styles.page} disabled={page + 1 >= pages}
                      onClick={() => setFilter({ page: String(page + 2) }, true)}>다음</button>
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
          startRating={startRating}
          onClose={closeDetail}
          onChanged={() => setTick((n) => n + 1)}
        />
      )}
    </div>
  )
}
