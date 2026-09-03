import { useCallback, useEffect, useState } from 'react'
import PageHead from '../components/PageHead'
import { useRightPanel } from '../components/RightPanel'
import { ApiError } from '../api/client'
import { applications, assignments, evaluations, postings as postingsApi } from '../api/endpoints'
import type { ApplicationDetail, Posting } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { STAGE_LABEL, careerText, fmtDate } from '../lib/stage'
import styles from './Evaluations.module.css'

/* 내게 배정된 평가 대기 큐 + 우측 평가 패널 (05-design §0.5).
   등록하면 자동으로 다음 지원자로 넘어간다.

   화면 자체는 로그인한 전원이 본다 — 역할로 가리지 않는다. 남는 제한은 하나,
   "평가는 자기에게 배정된 건만 쓴다" 뿐이고 그건 큐가 이미 배정된 건만
   담아서 지켜진다. 그래도 서버가 403 을 주면 그대로 보여 준다(§6).

   큐는 GET /interviewers/{me}/applications 가 준다. 그 응답은 배정 관계만 담아서
   (application_id·배정일) 이름·공고를 알 수 없다 — 지원자마다 상세를 한 번 더 부른다. */
interface QueueItem {
  applicationId: number
  assignedAt: string
  detail: ApplicationDetail
}

/* 403 은 "배정이 풀렸다"는 뜻이다 — 서버 문구만으로는 무엇을 해야 할지 모른다.
   조용히 삼키지 않고 사유를 붙여 보여 준다. */
function evalErrorText(err: unknown): string {
  if (err instanceof ApiError && err.code === 'FORBIDDEN') {
    return '내게 배정된 지원자가 아니라 평가를 등록할 수 없습니다. 배정이 해제됐는지 확인해 주세요.'
  }
  return err instanceof ApiError ? err.message : '평가를 등록하지 못했습니다'
}

export default function Evaluations() {
  const { user } = useAuth()

  const [queue, setQueue] = useState<QueueItem[] | null>(null)
  const [postingMap, setPostingMap] = useState<Map<number, Posting>>(new Map())
  const [error, setError] = useState<string | null>(null)

  const [openId, setOpenId] = useState<number | null>(null)
  const [score, setScore] = useState<number | null>(null)
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  /* 평가 패널도 오른쪽 한 자리를 나눠 쓴다 — 아르를 열면 이쪽이 닫힌다 (RightPanel) */
  const rightPanel = useRightPanel()
  const current = rightPanel.active === 'evaluation'
    ? queue?.find((a) => a.applicationId === openId) ?? null
    : null

  useEffect(() => {
    const ac = new AbortController()
    postingsApi
      .list(ac.signal)
      .then((list) => setPostingMap(new Map(list.map((p) => [p.id, p]))))
      .catch(() => {
        /* 공고 이름을 못 받아도 큐는 보여 준다 */
      })
    return () => ac.abort()
  }, [])

  const load = useCallback(
    async (userId: number, signal: AbortSignal) => {
      const res = await assignments.mine(userId, signal)
      const details = await Promise.all(
        res.assignments.map(async (a) => ({
          applicationId: a.application_id,
          assignedAt: a.created_at,
          detail: await applications.detail(a.application_id, signal),
        })),
      )
      return details
    },
    [],
  )

  const [loadKey, setLoadKey] = useState(0)
  const retry = () => { setQueue(null); setError(null); setLoadKey((k) => k + 1) }

  useEffect(() => {
    if (!user) return
    const ac = new AbortController()
    setError(null)
    load(user.id, ac.signal)
      .then(setQueue)
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '평가 대기 목록을 불러오지 못했습니다')
      })
    return () => ac.abort()
  }, [user, load, loadKey])

  function open(item: QueueItem) {
    setOpenId(item.applicationId)
    rightPanel.open('evaluation')
    setScore(null)
    setComment('')
    setSubmitError(null)
  }

  const close = useCallback(() => {
    setOpenId(null)
    rightPanel.close('evaluation')
  }, [rightPanel])

  /* 오른쪽 자리를 다른 패널에 뺏기면 고른 것도 버린다 — 행 강조가 남아 밑에
     깔아 둔 것처럼 되지 않게 */
  useEffect(() => {
    if (rightPanel.active !== 'evaluation') setOpenId(null)
  }, [rightPanel.active])

  /* 등록하면 그 사람을 큐에서 빼고 다음 지원자를 바로 연다 (§0.5 연속 심사).
     서버가 받아 준 뒤에 뺀다 — 먼저 빼면 실패했을 때 되돌릴 자리가 없다. */
  async function submit() {
    if (score === null || current === null || queue === null) return
    setSaving(true)
    setSubmitError(null)
    try {
      await evaluations.create(current.applicationId, score, comment)
      const i = queue.findIndex((a) => a.applicationId === current.applicationId)
      const rest = queue.filter((a) => a.applicationId !== current.applicationId)
      setQueue(rest)
      /* 다음 지원자로 이어서 연다 (§0.5 연속 심사). 없으면 자리를 비운다 */
      const next = rest[i] ?? rest[i - 1] ?? null
      setOpenId(next ? next.applicationId : null)
      if (next === null) rightPanel.close('evaluation')
      setScore(null)
      setComment('')
    } catch (err) {
      setSubmitError(evalErrorText(err))
    } finally {
      setSaving(false)
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') close()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [close])

  return (
    /* 패널이 열리면 제목까지 같이 밀린다 — 화면 전체를 한 열로 묶고 패널을
       그 열의 형제로 둔다 (2026-09-01, 공고의 지원자 화면과 같은 구성) */
    <div className={styles.split}>
      <div className={styles.col}>
      <PageHead
        title="평가 현황"
        actions={<span className={styles.meta}>평가 대기 {queue?.length ?? 0}명</span>}
      />

        <main className="page-content">
          <div className={styles.panel}>
            <div className={`${styles.row} ${styles.thead}`}>
              <span>이름</span>
              <span>공고</span>
              <span>단계</span>
              <span className={styles.num}>배정일</span>
            </div>

            {queue?.map((a) => (
              <div
                key={a.applicationId}
                className={`${styles.row} ${styles.item} ${a.applicationId === openId ? styles.cur : ''}`}
                tabIndex={0}
                aria-current={a.applicationId === openId ? 'true' : undefined}
                onClick={() => open(a)}
              >
                <span className={styles.name}>{a.detail.name}</span>
                <span className={styles.posting}>
                  {postingMap.get(a.detail.job_posting_id)?.title ?? '—'}
                </span>
                {/* 판단 전이라 색 없이 라벨로만 (§1) */}
                <span className={styles.stage}>{STAGE_LABEL[a.detail.current_stage]}</span>
                <span className={styles.num}>{fmtDate(a.assignedAt)}</span>
              </div>
            ))}

            {error === null && queue === null && (
              [0, 1, 2].map((i) => <div key={i} className={`${styles.row} ${styles.skelRow}`} />)
            )}
            {error === null && queue?.length === 0 && (
              <div className={styles.emptyState} role="status">
                <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                </svg>
                <p>평가 대기 중인 지원자가 없습니다.</p>
              </div>
            )}
            {error !== null && (
              <div className={styles.errorCard} role="alert">
                <p>{error}</p>
                <button type="button" className={styles.retryBtn} onClick={retry}>다시 시도</button>
              </div>
            )}
          </div>
        </main>
      </div>

        <aside className={`${styles.side} ${current ? styles.sideOpen : ''}`} aria-label="평가 패널">
          {current && (
            <div className={styles.sideInner}>
              {/* 모바일 전용 뒤로가기 헤더 */}
              <div className={styles.mobileBack}>
                <button type="button" aria-label="닫기" onClick={close}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>
                </button>
                <h1>평가</h1>
              </div>

              {/* 모바일 전용 점수 요약 */}
              <div className={styles.scoreSummary}>
                <div className={styles.scoreMain}>
                  <p className={styles.scoreNum}>
                    {current.detail.avg_score?.toFixed(1) ?? '—'}
                    <span> / 5</span>
                  </p>
                  <p className={styles.scoreCount}>
                    {current.detail.eval_count ?? 0}명이 평가했습니다
                  </p>
                </div>
                <div className={styles.scoreBars}>
                  {[5, 4, 3, 2, 1].map((n) => (
                    <div key={n} className={styles.scoreBarRow}>
                      <span>{n}</span>
                      <div className={styles.scoreBarTrack}>
                        <div className={styles.scoreBarFill} style={{ width: 0 }} />
                      </div>
                      <span>0</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className={styles.sideHead}>
                <span className={styles.sideName}>{current.detail.name}</span>
                <span className={styles.stage}>{STAGE_LABEL[current.detail.current_stage]}</span>
              </div>
              <button type="button" className={styles.close} aria-label="패널 닫기" onClick={close}>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>

              <div className={styles.sec}>
                <h2>지원 정보</h2>
                <dl className={styles.list}>
                  <dt>학력</dt><dd>{current.detail.education ?? '—'}</dd>
                  <dt>경력</dt><dd>{careerText(current.detail.career_years)}</dd>
                  <dt>기술</dt><dd>{current.detail.skills?.join(' · ') || '—'}</dd>
                </dl>
              </div>

              <div className={styles.sec}>
                <h2>평가</h2>
                <p className={styles.secLabel}>내 평가</p>
                <div className={styles.rate} role="group" aria-label="평가 점수">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      type="button"
                      aria-pressed={score === n}
                      disabled={saving}
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
                  placeholder="코멘트 (선택)"
                  value={comment}
                  disabled={saving}
                  onChange={(e) => setComment(e.target.value)}
                />
                {submitError && <p className={styles.err} role="alert">{submitError}</p>}
                <div className={styles.actions}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={score === null || saving}
                    onClick={submit}
                  >
                    {saving ? '등록 중…' : '등록'}
                  </button>
                </div>
                <p className={styles.hint}>등록하면 다음 지원자로 넘어갑니다</p>
              </div>
            </div>
          )}
        </aside>
    </div>
  )
}
