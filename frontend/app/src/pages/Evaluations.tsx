import { useCallback, useEffect, useState } from 'react'
import PageHead from '../components/PageHead'
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

  const current = queue?.find((a) => a.applicationId === openId) ?? null

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
  }, [user, load])

  function open(item: QueueItem) {
    setOpenId(item.applicationId)
    setScore(null)
    setComment('')
    setSubmitError(null)
  }

  const close = useCallback(() => setOpenId(null), [])

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
      const next = rest[i] ?? rest[i - 1] ?? null
      setOpenId(next ? next.applicationId : null)
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
    <>
      <PageHead
        title="평가 현황"
        actions={<span className={styles.meta}>평가 대기 {queue?.length ?? 0}명</span>}
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

            {error !== null && <p className={styles.empty} role="alert">{error}</p>}
            {error === null && queue === null && <p className={styles.empty}>불러오는 중…</p>}
            {error === null && queue?.length === 0 && (
              <p className={styles.empty}>평가 대기 중인 지원자가 없습니다.</p>
            )}
          </div>
        </main>

        <aside className={`${styles.side} ${current ? styles.sideOpen : ''}`} aria-label="평가 패널">
          {current && (
            <div className={styles.sideInner}>
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
                  placeholder="평가 코멘트를 입력합니다"
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
    </>
  )
}
