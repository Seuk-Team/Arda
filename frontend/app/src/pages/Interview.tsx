import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { InterviewAudioUpload, InterviewPublic, PacingHint } from '../api/types'
import styles from './Interview.module.css'
import { formatSeconds, useAnswerRecorder } from './useAnswerRecorder'

/* 진행 보조 문구는 서버가 준 것을 그대로 쓴다 (ADR-0026 결정 4).
   **여기서 문구를 만들지 않는다** — 규칙과 말이 백엔드 한 곳에 있어야
   나중에 신호가 늘어도 같이 간다. `action` 은 화면 톤을 고를 때만 쓴다.
   **모르는 action 은 무시한다** — 서버가 늘려도 화면이 안 깨지게. */
const KNOWN_PACING = new Set(['follow_up', 'offer_break', 'rephrase'])

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
  const [pacing, setPacing] = useState<PacingHint | null>(null)
  const [byText, setByText] = useState(false)
  /* 영상으로 답할지. 화면이 뜨면 카메라를 켜 두는 것이 기본이다 — 면접이니까.
     ADR-0026 대로 **영상 자체를 우리가 보관하지는 않는다**: 답변 파일은 전사가
     끝나면 그 목적이 다하고, 진위 분석(ADR-0029)은 설정이 있을 때만 부른다. */
  const [withVideo, setWithVideo] = useState(true)
  const rec = useAnswerRecorder(withVideo)

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

  /* 답변 응답에는 다음 질문과 진행 보조가 같이 온다. `load()` 로 다시 불러오면
     **진행 보조가 사라진다** — 서버가 저장하지 않아서 조회에는 안 실린다.
     그래서 응답을 그대로 화면 상태로 쓴다. */
  function applyAnswerResult(next: InterviewPublic) {
    setState({ kind: 'ready', data: next })
    const hint = next.pacing
    setPacing(hint && KNOWN_PACING.has(hint.action) ? hint : null)
  }

  function describeError(err: unknown): string {
    return err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요'
  }

  async function submitText() {
    if (!answer.trim()) return
    setPending(true)
    setNotice(null)
    try {
      const next = await api.post<InterviewPublic>(
        `/public/interview/${token}/answer`,
        { transcript: answer.trim() },
        { auth: false },
      )
      setAnswer('')
      applyAnswerResult(next)
    } catch (err) {
      setNotice(describeError(err))
    } finally {
      setPending(false)
    }
  }

  /* 음성 답변: 서명 URL 을 받아 **브라우저가 S3 로 직접** 올리고, 키만 서버에 준다.
     음성 본문이 API 를 지나가지 않는다 — 이력서 업로드와 같은 방식이다. */
  async function submitAudio() {
    const taken = rec.recorded
    if (!taken) return
    setPending(true)
    setNotice(null)
    try {
      const up = await api.post<InterviewAudioUpload>(
        `/public/interview/${token}/audio-upload-url`,
        { filename: `answer.${taken.ext}`, content_type: taken.type, size_bytes: taken.blob.size },
        { auth: false },
      )

      /* S3 는 우리 API 가 아니라서 api 클라이언트를 안 쓴다.
         **Content-Type 이 서명에 들어가 있으므로 글자까지 같아야 한다.** */
      const put = await fetch(up.upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': taken.type },
        body: taken.blob,
      })
      if (!put.ok) throw new Error('upload failed')

      const next = await api.post<InterviewPublic>(
        `/public/interview/${token}/answer`,
        { audio_s3_key: up.s3_key },
        { auth: false },
      )
      rec.reset()
      applyAnswerResult(next)
    } catch (err) {
      /* 전사 실패(502)면 서버가 아무것도 저장하지 않았다 — 같은 질문이 그대로
         남아 있으므로 다시 녹음하면 된다. 녹음본은 지우지 않는다. */
      setNotice(describeError(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className={styles.page}>
      <main
        className={
          withVideo && !byText
            ? `${styles.column} ${styles.columnWide}`
            : styles.column
        }
      >
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
                    {rec.supported
                      ? ' 음성으로 답변하거나 텍스트로 입력할 수 있습니다.'
                      : ' 답변은 텍스트로 입력합니다.'}
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
                  {/* 진행 보조 — 아르가 앞 답변을 듣고 건네는 말.
                      **경고처럼 보이게 하지 않는다.** 지적이 아니라 배려다. */}
                  {pacing && (
                    <p className={styles.pacing}>{pacing.message}</p>
                  )}

                  {d.question_seq !== null && (
                    <div className={styles.seq}>질문 {d.question_seq}</div>
                  )}
                  <p className={styles.question}>{d.current_question}</p>

                  {rec.supported && !byText ? (
                    <div className={styles.recorder}>
                      {withVideo && (
                        <video
                          ref={rec.previewRef}
                          className={styles.preview}
                          playsInline
                          muted
                          hidden={rec.state !== 'recording'}
                        />
                      )}
                      {rec.state === 'idle' && (
                        <p className={styles.recorderHint}>
                          {withVideo
                            ? '버튼을 누르면 카메라와 마이크가 켜집니다.'
                            : '버튼을 누르고 답변해 주세요.'}
                        </p>
                      )}
                      {rec.state === 'recording' && (
                        <p className={styles.recording} aria-live="polite">
                          <span className={styles.dot} aria-hidden="true" />
                          녹음 중 {formatSeconds(rec.seconds)}
                        </p>
                      )}
                      {rec.state === 'recorded' && (
                        <p className={styles.recorderHint} aria-live="polite">
                          {formatSeconds(rec.recorded?.seconds ?? 0)} 녹음됐습니다. 제출하거나 다시 녹음할 수 있습니다.
                        </p>
                      )}
                      {rec.error && <p className={styles.error} role="alert">{rec.error}</p>}

                      <div className={styles.recorderActions}>
                        {rec.state === 'idle' && (
                          <button type="button" className="btn btn-primary" disabled={pending}
                            onClick={() => void rec.start()}>
                            녹음 시작
                          </button>
                        )}
                        {rec.state === 'recording' && (
                          <button type="button" className="btn btn-primary" onClick={rec.stop}>
                            녹음 정지
                          </button>
                        )}
                        {rec.state === 'recorded' && (
                          <>
                            <button type="button" className="btn btn-secondary" disabled={pending}
                              onClick={rec.reset}>
                              다시 녹음
                            </button>
                            <button type="button" className="btn btn-primary" disabled={pending}
                              onClick={submitAudio}>
                              {pending ? '보내는 중…' : '답변 제출'}
                            </button>
                          </>
                        )}
                      </div>

                      {rec.state !== 'recording' && (
                        <div className={styles.switchRow}>
                          <button type="button" className={styles.switchMode}
                            onClick={() => { rec.reset(); setWithVideo(!withVideo) }}>
                            {withVideo ? '카메라 없이 음성만' : '카메라도 켜기'}
                          </button>
                          <button type="button" className={styles.switchMode}
                            onClick={() => { rec.reset(); setByText(true) }}>
                            텍스트로 답변하기
                          </button>
                        </div>
                      )}
                    </div>
                  ) : (
                    <>
                      <textarea
                        className={styles.answerInput}
                        rows={6}
                        placeholder="답변을 입력해 주세요"
                        value={answer}
                        disabled={pending}
                        onChange={(e) => setAnswer(e.target.value)}
                      />
                      <div className={styles.actions}>
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={pending || answer.trim() === ''}
                          onClick={submitText}
                        >
                          {pending ? '제출 중…' : '답변 제출'}
                        </button>
                      </div>
                      {rec.supported && (
                        <button type="button" className={styles.switchMode}
                          onClick={() => { setAnswer(''); setByText(false) }}>
                          음성으로 답변하기
                        </button>
                      )}
                    </>
                  )}

                  {notice && <p className={styles.error} role="alert">{notice}</p>}
                </div>
              )}
            </>
          )
        })()}
      </main>
    </div>
  )
}
