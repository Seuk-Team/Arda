import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { InterviewPublic } from '../api/types'
import styles from './Interview.module.css'

/* 지원자용 AI 면접 공개 페이지 — 로그인 없음, 메일 링크의 토큰이 곧 인증.
   Schedule.tsx 와 같은 패턴. */

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; data: InterviewPublic }
  | { kind: 'invalid' }
  | { kind: 'error'; message: string }

export default function Interview() {
  const { token } = useParams<{ token: string }>()
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [pending, setPending] = useState(false)
  const [answer, setAnswer] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await api.get<InterviewPublic>(`/public/interview/${token}`, { auth: false })
      setState({ kind: 'ready', data })
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setState({ kind: 'invalid' })
      else setState({ kind: 'error', message: err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요' })
    }
  }, [token])

  useEffect(() => { void load() }, [load])

  async function consent() {
    setPending(true)
    setNotice(null)
    try {
      await api.post(`/public/interview/${token}/consent`, { agreed: true }, { auth: false })
      await load()
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요')
    } finally {
      setPending(false)
    }
  }

  async function start() {
    setPending(true)
    setNotice(null)
    try {
      await api.post(`/public/interview/${token}/start`, {}, { auth: false })
      await load()
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요')
    } finally {
      setPending(false)
    }
  }

  async function submitAnswer() {
    if (!answer.trim()) return
    setPending(true)
    setNotice(null)
    try {
      await api.post(`/public/interview/${token}/answer`, { transcript: answer.trim() }, { auth: false })
      setAnswer('')
      await load()
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요')
    } finally {
      setPending(false)
    }
  }

  async function finish() {
    setPending(true)
    setNotice(null)
    try {
      await api.post(`/public/interview/${token}/finish`, {}, { auth: false })
      await load()
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className={styles.page}>
      <main className={styles.column}>
        <h1 className={styles.logo}><span className={styles.seed}>A</span>rda</h1>

        {state.kind === 'loading' && (
          <div className={styles.card} aria-busy="true">
            <div className={styles.skeleton} style={{ width: '60%' }} />
            <div className={styles.skeleton} style={{ width: '40%' }} />
            <div className={styles.skeleton} />
          </div>
        )}

        {state.kind === 'invalid' && (
          <div className={styles.card}>
            <h2 className={styles.noticeTitle}>유효하지 않은 링크입니다</h2>
            <p className={styles.noticeBody}>안내 메일의 링크를 다시 확인해 주세요.</p>
          </div>
        )}

        {state.kind === 'error' && (
          <div className={`${styles.card} ${styles.cardDanger}`} role="alert">
            <h2 className={styles.noticeTitle}>불러오지 못했습니다</h2>
            <p className={styles.noticeBody}>{state.message}</p>
            <button type="button" className="btn btn-secondary"
              onClick={() => { setState({ kind: 'loading' }); void load() }}>
              다시 시도
            </button>
          </div>
        )}

        {state.kind === 'ready' && (() => {
          const d = state.data
          return (
            <>
              <p className={styles.posting}>{d.posting_title}</p>

              {d.status === 'expired' && (
                <div className={styles.card}>
                  <h2 className={styles.noticeTitle}>만료된 면접입니다</h2>
                  <p className={styles.noticeBody}>면접 링크의 유효 기간이 지났습니다. 담당자에게 문의해 주세요.</p>
                </div>
              )}

              {d.status === 'done' && (
                <div className={styles.card}>
                  <h2 className={styles.noticeTitle}>면접이 완료되었습니다</h2>
                  <p className={styles.noticeBody}>{d.applicant_name}님, 참여해 주셔서 감사합니다.</p>
                </div>
              )}

              {d.status === 'pending' && d.consent_required && (
                <div className={styles.card}>
                  <h2 className={styles.cardTitle}>{d.applicant_name}님, 안녕하세요</h2>
                  <p className={styles.noticeBody}>
                    {d.posting_title} 채용과 관련한 AI 면접입니다.
                    면접 내용은 채용 검토 목적으로만 활용됩니다.
                  </p>
                  {notice && <p className={styles.error} role="alert">{notice}</p>}
                  <div className={styles.actions}>
                    <button type="button" className="btn btn-primary" disabled={pending} onClick={consent}>
                      {pending ? '처리 중…' : '동의하고 계속하기'}
                    </button>
                  </div>
                </div>
              )}

              {d.status === 'pending' && !d.consent_required && (
                <div className={styles.card}>
                  <h2 className={styles.cardTitle}>{d.applicant_name}님, 준비되셨나요?</h2>
                  <p className={styles.noticeBody}>
                    시작 버튼을 누르면 첫 번째 질문이 표시됩니다.
                    답변은 텍스트로 입력합니다.
                  </p>
                  {notice && <p className={styles.error} role="alert">{notice}</p>}
                  <div className={styles.actions}>
                    <button type="button" className="btn btn-primary" disabled={pending} onClick={start}>
                      {pending ? '시작 중…' : '면접 시작'}
                    </button>
                  </div>
                </div>
              )}

              {d.status === 'in_progress' && (
                <div className={styles.card}>
                  {d.question_seq !== null && (
                    <div className={styles.seq}>질문 {d.question_seq}</div>
                  )}
                  <p className={styles.question}>{d.current_question}</p>
                  <textarea
                    className={styles.answerInput}
                    rows={6}
                    placeholder="답변을 입력해 주세요"
                    value={answer}
                    disabled={pending}
                    onChange={(e) => setAnswer(e.target.value)}
                  />
                  {notice && <p className={styles.error} role="alert">{notice}</p>}
                  <div className={styles.actions}>
                    <button type="button" className="btn" disabled={pending} onClick={finish}>
                      그만하기
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={pending || answer.trim() === ''}
                      onClick={submitAnswer}
                    >
                      {pending ? '제출 중…' : '답변 제출'}
                    </button>
                  </div>
                </div>
              )}
            </>
          )
        })()}
      </main>
    </div>
  )
}
