import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { applications, postings as postingsApi, stages as stagesApi } from '../api/endpoints'
import type { ApplicationListItem, Posting, Stage } from '../api/types'
import { STAGE_LABEL, careerText, fmtDate, stageTone, withRo } from '../lib/stage'
import ApplicantPanel from './ApplicantPanel'
import { useRightPanel } from '../components/RightPanel'
import Kanban from './Kanban'
import styles from './PostingApplicants.module.css'

/* 공고의 지원자 화면 (05-design §0.5 "본 작업 화면") — D1·D4.
   목록은 GET /applications?posting_id= 로 받는다. 공고별 전용 경로
   (GET /postings/{id}/applications)는 검색·단계·페이지 쿼리가 아직 구현돼
   있지 않아 전건을 그대로 준다. */

const FIELDS = ['전체', '이름', '이메일'] as const
type Field = (typeof FIELDS)[number]

const PAGE_SIZE = 20

const TONE_CLASS = {
  progress: styles.stageProgress,
  accepted: styles.stageAccepted,
  rejected: styles.stageRejected,
}

/* 퍼널 순서·색. 색은 판단에만 (§1) — 진행 중은 무채 3단, 합격만 연두, 불합격만 적갈 */
const FUNNEL: { stage: Stage; color: string }[] = [
  { stage: 'applied', color: '#C9CFC3' },
  { stage: 'screening', color: '#AEB6A8' },
  { stage: 'interview', color: '#8A9284' },
  { stage: 'accepted', color: '#8CC63F' },
  { stage: 'rejected', color: '#A9503C' },
]

export default function PostingApplicants() {
  const { id } = useParams<{ id: string }>()
  const [params] = useSearchParams()
  const postingId = Number(id)

  /* ?applicant=12 — 캘린더의 그날 일정에서 그 사람을 눌러 넘어온 경우.
     상세 패널을 그 지원자로 열고 시작한다. */
  const fromUrl = Number(params.get('applicant'))
  const applicantFromUrl = Number.isInteger(fromUrl) && fromUrl > 0 ? fromUrl : null
  const navigate = useNavigate()

  const [posting, setPosting] = useState<Posting | null>(null)
  const [rows, setRows] = useState<ApplicationListItem[] | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [counts, setCounts] = useState<number[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [field, setField] = useState<Field>('전체')
  const [ddOpen, setDdOpen] = useState(false)
  const [q, setQ] = useState('')
  const [term, setTerm] = useState('')
  const [stage, setStage] = useState<Stage | null>(null)
  const [page, setPage] = useState(0)
  const [view, setView] = useState<'list' | 'kanban'>('list')

  /* 상세 패널에 열려 있는 지원자. 아르 패널과 오른쪽 한 자리를 나눠 쓴다 —
     아르를 열면 이쪽이 닫힌다 (RightPanel) */
  const rightPanel = useRightPanel()
  const [openId, setOpenId] = useState<number | null>(applicantFromUrl)
  const detailOpen = openId !== null && rightPanel.active === 'applicant'

  useEffect(() => {
    /* ?applicant= 로 들어왔을 때만 열고, 그냥 들어오면 닫은 채로 시작한다.
       열림 상태가 화면 밖(RightPanel)에 있어서 안 닫으면 지난번에 열어 둔 지원자가
       다른 공고 화면에까지 따라온다. */
    if (applicantFromUrl !== null) {
      setOpenId(applicantFromUrl)
      rightPanel.open('applicant')
    } else {
      setOpenId(null)
      rightPanel.close('applicant')
    }
    // 들어올 때 한 번만 — 이후 여닫기는 사용자가 한다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicantFromUrl, postingId])

  function openDetail(id: number) {
    setOpenId(id)
    rightPanel.open('applicant')
  }

  function closeDetail() {
    setOpenId(null)
    rightPanel.close('applicant')
  }

  /* 일괄 단계 변경 (D9) — 고른 사람들 */
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [bulkReject, setBulkReject] = useState(false)
  const [bulkReason, setBulkReason] = useState('')
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkError, setBulkError] = useState<string | null>(null)
  /* 목록·퍼널을 다시 세게 하는 방아쇠 */
  const [tick, setTick] = useState(0)

  const debounce = useRef<number | undefined>(undefined)
  useEffect(() => {
    window.clearTimeout(debounce.current)
    debounce.current = window.setTimeout(() => {
      setTerm(q.trim())
      setPage(0)
    }, 300)
    return () => window.clearTimeout(debounce.current)
  }, [q])

  /* 공고 정보 + 단계별 인원. 목록 조건이 바뀌어도 이건 그대로라 따로 받는다 */
  useEffect(() => {
    if (!Number.isFinite(postingId)) return
    const ac = new AbortController()
    setError(null)
    Promise.all([
      postingsApi.get(postingId, ac.signal),
      Promise.all(FUNNEL.map((f) => applications.countByStage(f.stage, postingId, ac.signal))),
    ])
      .then(([p, c]) => {
        setPosting(p)
        setCounts(c)
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '공고를 불러오지 못했습니다')
      })
    return () => ac.abort()
  }, [postingId, tick])

  useEffect(() => {
    if (!Number.isFinite(postingId)) return
    const ac = new AbortController()
    applications
      .search(
        {
          posting_id: postingId,
          q: term || undefined,
          stage: stage ?? undefined,
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
  }, [postingId, term, stage, page, tick])

  /* 조건이 바뀌면 고른 사람들을 비운다. 안 보이는 행이 선택된 채로 남으면
     "3명 선택됨" 이라고 떠 있는데 화면에는 한 명도 체크돼 있지 않게 된다. */
  useEffect(() => {
    setPicked(new Set())
    setBulkReject(false)
    setBulkReason('')
    setBulkError(null)
  }, [term, stage, page, postingId])

  function toggle(id: number) {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const allPicked = rows !== null && rows.length > 0 && rows.every((r) => picked.has(r.id))

  function toggleAll() {
    setPicked(allPicked ? new Set() : new Set(rows?.map((r) => r.id) ?? []))
  }

  /* D9 — 전부 성공하거나 전부 롤백된다. 한 건이라도 규칙에 걸리면 서버가 409 로
     돌려보내고 아무도 안 바뀐다. 그래서 낙관적 업데이트를 하지 않고 응답을 기다린다. */
  async function bulkChange(to: Stage) {
    if (picked.size === 0) return
    if (to === 'rejected' && bulkReason.trim() === '') {
      setBulkReject(true)
      return
    }
    setBulkBusy(true)
    setBulkError(null)
    try {
      const res = await stagesApi.bulk(
        [...picked],
        to,
        to === 'rejected' ? bulkReason.trim() : undefined,
      )
      setPicked(new Set())
      setBulkReject(false)
      setBulkReason('')
      setTick((n) => n + 1)
      if (res.skipped.length > 0) {
        setBulkError(`${res.changed}명 변경, ${res.skipped.length}명은 이미 그 단계라 건너뛰었습니다.`)
      }
    } catch (err) {
      setBulkError(err instanceof ApiError ? err.message : '단계를 바꾸지 못했습니다')
    } finally {
      setBulkBusy(false)
    }
  }

  const grandTotal = counts?.reduce((a, b) => a + b, 0) ?? 0
  const pages = total === null ? 1 : Math.max(1, Math.ceil(total / PAGE_SIZE))
  const from = page * PAGE_SIZE + 1
  const to = page * PAGE_SIZE + (rows?.length ?? 0)

  const dday =
    posting?.d_day === null || posting === null
      ? null
      : posting.d_day >= 0
        ? `D-${posting.d_day}`
        : `D+${-posting.d_day}`

  return (
    <>
      <header className={styles.head}>
        <div className={styles.headTop}>
          <button
            type="button"
            className={styles.back}
            aria-label="채용 공고 목록으로"
            onClick={() => navigate('/postings')}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 12H5M11 6l-6 6 6 6" /></svg>
          </button>
          <h1 className={styles.title}>{posting?.title ?? '…'}</h1>
          {posting && (
            <span className={`badge ${posting.status === 'open' ? 'badge-open' : 'badge-closed'}`}>
              {posting.status === 'open' ? '진행중' : posting.status === 'closed' ? '마감' : '작성중'}
            </span>
          )}
          <span className={styles.meta}>
            {dday && `마감 ${dday} · `}총 {grandTotal.toLocaleString()}명
          </span>
        </div>

        {/* 단계 필터. 폭은 인원 비율이고, 누르면 그 단계만 남는다 */}
        {counts && grandTotal > 0 && (
          <>
            <div
              className={styles.funnel}
              style={{ gridTemplateColumns: counts.map((n) => `${Math.max(n, 0.02)}fr`).join(' ') }}
              aria-label="단계별 인원 비율 (누르면 그 단계만 본다)"
            >
              {FUNNEL.map((f, i) => (
                <button
                  key={f.stage}
                  type="button"
                  className={`${styles.seg} ${stage === f.stage ? styles.segOn : ''}`}
                  style={{ background: f.color }}
                  aria-pressed={stage === f.stage}
                  title={`${STAGE_LABEL[f.stage]} ${counts[i]}명`}
                  onClick={() => {
                    setStage(stage === f.stage ? null : f.stage)
                    setPage(0)
                  }}
                />
              ))}
            </div>
            <div className={styles.flabels}>
              {FUNNEL.map((f, i) => (
                <span key={f.stage} className={styles.flabel}>
                  {STAGE_LABEL[f.stage]} <b>{counts[i]}</b>
                </span>
              ))}
            </div>
          </>
        )}
      </header>

      <div className={styles.toolbar}>
        <div className={styles.search}>
          <div className={`${styles.dd} ${ddOpen ? styles.ddOpen : ''}`}>
            <button
              type="button"
              className={styles.ddBtn}
              aria-haspopup="listbox"
              aria-expanded={ddOpen}
              onClick={() => setDdOpen((v) => !v)}
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
                  onClick={() => { setField(f); setDdOpen(false) }}
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
            placeholder="검색어 입력"
          />
          {q && (
            <button type="button" className={styles.sx} aria-label="검색어 지우기" onClick={() => setQ('')}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          )}
        </div>

        {stage && (
          <button type="button" className={styles.chip} onClick={() => { setStage(null); setPage(0) }}>
            {STAGE_LABEL[stage]}만 <span aria-hidden="true">✕</span>
          </button>
        )}

        {/* 칸반은 큐 8번(D2·D3)이라 아직 없다. 자리만 두고 잠가 둔다 */}
        <div className={styles.vtoggle} role="group" aria-label="보기 방식">
          <button
            type="button"
            className={view === 'list' ? styles.vOn : undefined}
            aria-pressed={view === 'list'}
            onClick={() => setView('list')}
          >
            목록
          </button>
          <button
            type="button"
            className={view === 'kanban' ? styles.vOn : undefined}
            aria-pressed={view === 'kanban'}
            onClick={() => setView('kanban')}
          >
            칸반
          </button>
        </div>
      </div>

      {/* 고른 사람이 있을 때만 뜬다. D9 — 한 번에 200명까지 */}
      {picked.size > 0 && (
        <div className={styles.bulkbar}>
          <span className={styles.bulkCount}>{picked.size}명 선택됨</span>
          <button type="button" className={styles.chip} onClick={() => setPicked(new Set())}>
            선택 해제
          </button>
          <div className={styles.bulkActions}>
            {(['screening', 'interview', 'accepted', 'rejected'] as Stage[]).map((s) => (
              <button
                key={s}
                type="button"
                className={s === 'rejected' ? styles.btnReject : styles.btnStage}
                disabled={bulkBusy}
                onClick={() => bulkChange(s)}
              >
                {withRo(STAGE_LABEL[s])}
              </button>
            ))}
          </div>

          {/* 불합격은 사유가 필수다 (D8) */}
          {bulkReject && (
            <div className={styles.bulkReason}>
              <input
                type="text"
                value={bulkReason}
                disabled={bulkBusy}
                placeholder="불합격 사유 — 적어야 옮길 수 있습니다"
                aria-label="불합격 사유"
                onChange={(e) => setBulkReason(e.target.value)}
              />
              <button
                type="button"
                className={styles.btnReject}
                disabled={bulkBusy || bulkReason.trim() === ''}
                onClick={() => bulkChange('rejected')}
              >
                {bulkBusy ? '변경 중…' : `${picked.size}명 불합격`}
              </button>
            </div>
          )}

          {bulkError && <p className={styles.bulkErr} role="alert">{bulkError}</p>}
        </div>
      )}

      <div className={styles.body}>
      <main className="page-content">
        {view === 'kanban' ? (
          <Kanban postingId={postingId} tick={tick} onChanged={() => setTick((n) => n + 1)} />
        ) : (
        <div className={styles.panel}>
          <div className={`${styles.row} ${styles.rowSel} ${styles.thead}`}>
            <input
              type="checkbox"
              aria-label="이 페이지 전체 선택"
              checked={allPicked}
              onChange={toggleAll}
            />
            <span>이름</span>
            <span>단계</span>
            <span className={styles.num}>경력</span>
            <span>이메일</span>
            <span className={styles.num}>평점</span>
            <span className={styles.num}>지원일</span>
          </div>

          {rows?.map((a) => (
            <div
              key={a.id}
              className={`${styles.row} ${styles.rowSel} ${styles.item} ${a.id === openId ? styles.cur : ''}`}
              tabIndex={0}
              aria-current={a.id === openId ? 'true' : undefined}
              onClick={() => openDetail(a.id)}
            >
              {/* 체크는 행 열기와 다른 동작이다 — 여기서 멈춘다 */}
              <input
                type="checkbox"
                aria-label={`${a.name} 선택`}
                checked={picked.has(a.id)}
                onClick={(e) => e.stopPropagation()}
                onChange={() => toggle(a.id)}
              />
              <span className={styles.name}>{a.name}</span>
              <span className={TONE_CLASS[stageTone(a.current_stage)]}>{STAGE_LABEL[a.current_stage]}</span>
              <span className={styles.num}>{careerText(a.career_years)}</span>
              <span className={styles.email}>{a.email}</span>
              {/* 서버는 sort=score 로 부를 때만 평균을 채운다 */}
              <span className={styles.num}>{a.avg_score === null ? '—' : a.avg_score.toFixed(1)}</span>
              <span className={styles.num}>{fmtDate(a.created_at)}</span>
            </div>
          ))}

          {error !== null && <p className={styles.state} role="alert">{error}</p>}
          {error === null && rows === null && <p className={styles.state}>불러오는 중…</p>}
          {error === null && rows?.length === 0 && (
            <p className={styles.state}>
              {term || stage ? '조건에 맞는 지원자가 없습니다.' : '아직 지원자가 없습니다.'}
            </p>
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
        )}
      </main>

      {detailOpen && openId !== null && (
        <ApplicantPanel
          applicationId={openId}
          onClose={closeDetail}
          onChanged={() => setTick((n) => n + 1)}
        />
      )}
      </div>
    </>
  )
}
