import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { InterviewPublic } from '../api/types'
import styles from './InterviewAi.module.css'
import { AI_PHASE_LABEL, useAiInterview } from './useAiInterview'

/* AI 면접 — 지원자 화면 (ADR-0029).

   ## 앱과 같은 단계 UI (2026-09-14)

   모바일 앱 `mobile/lib/screens/interview_screen.dart` 를 따라 상태별 화면을 나눈다:

   | 세션 상태 | 화면 |
   |---|---|
   | 로딩 · 에러 | 스피너 · 재시도 |
   | `pending` + 동의 필요 | 동의 화면 ("동의하고 계속하기") |
   | `pending` + 동의 완료 | 준비 화면 ("시작하기") |
   | `in_progress` | 실시간 면접 (카메라·질문) |
   | `done` | 완료 |
   | `expired` | 만료 |

   옛 웹은 링크 클릭만으로 자동 동의·시작이 이뤄져 지원자가 무엇이 시작되는지
   모른 채 카메라 권한 팝업을 마주쳤다. 앱은 명시적 확인을 받는 흐름 —
   지원자에게 무엇이 시작되는지 안내하고 준비할 시간을 준다.

   ## 판정을 여기에 띄우지 않는다 (ADR-0029)

   판정을 실시간으로 보여 주면 그 자체가 답변을 바꾼다. 훅도 그 값을 상태로
   들고 있지 않아, 화면이 그리려 해도 그릴 것이 없다.

   폰 세로가 기본이다.

   ## 두 자리에서 열린다 (2026-09-15)

   `/interview/:token`·`/interview-ai/:token`(메일 링크)과 `/my/interview`
   (지원자 셸의 탭). **화면은 한 벌이다** — Aptitude.tsx 의 같은 주석을 보라.
   앱도 탭 안에서 면접을 본다(하단 탭이 그대로 남는다). */

interface Props {
  /* 셸이 열 때 넘겨주는 토큰. 없으면 주소에서 읽는다 (메일 링크) */
  token?: string
  /* 셸 안이면 자기 제목 띠와 100dvh 를 접는다 */
  nested?: boolean
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; data: InterviewPublic }
  | { kind: 'invalid' }
  | { kind: 'error'; message: string }

export default function InterviewAi({ token: given, nested = false }: Props = {}) {
  const { token: fromUrl } = useParams<{ token: string }>()
  const token = given ?? fromUrl
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [started, setStarted] = useState(false)
  const [pending, setPending] = useState(false)

  // 세션 상태를 REST 로 가져온다. 소켓은 '시작' 이후에만 연다.
  const load = useCallback(async () => {
    if (!token) return
    try {
      const data = await api.get<InterviewPublic>(`/public/interview/${token}`, { auth: false })
      setState({ kind: 'ready', data })
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setState({ kind: 'invalid' })
      else setState({ kind: 'error', message: err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요' })
    }
  }, [token])

  useEffect(() => { void load() }, [load])

  // 소켓은 started=true 로 바뀌었을 때만 열린다 (useAiInterview 는 token=null 이면 아무것도 안 함).
  const { phase, question, seq, error, note, videoRef, leave, endAnswer } = useAiInterview(started ? token ?? null : null)

  async function handleConsent() {
    if (!token) return
    setPending(true)
    try {
      await api.post(`/public/interview/${token}/consent`, { agreed: true }, { auth: false })
      await load()
    } catch (err) {
      setState({ kind: 'error', message: err instanceof ApiError ? err.message : '동의를 저장하지 못했습니다' })
    } finally {
      setPending(false)
    }
  }

  function handleStart() {
    // useAiInterview 훅이 REST start + 소켓 연결 + 카메라 요청을 순서대로 처리한다.
    setStarted(true)
  }

  return (
    <div className={`${styles.page} ${nested ? styles.nested : ''}`}>
      {/* 셸 안에서는 제목 띠를 그리지 않는다 — 상단 바가 이미 「AI 면접」이다 */}
      {!nested && (
        <header className={styles.topBar}>
          <h1 className={styles.title}>AI 면접</h1>
        </header>
      )}

      <div className={styles.body}>
        {state.kind === 'loading' && <Loading />}
        {state.kind === 'invalid' && <Invalid />}
        {state.kind === 'error' && <ErrorPanel message={state.message} onRetry={load} />}

        {state.kind === 'ready' && (
          <ReadyBody
            data={state.data}
            started={started}
            pending={pending}
            phase={phase}
            question={question}
            seq={seq}
            note={note}
            liveError={error}
            videoRef={videoRef}
            onConsent={handleConsent}
            onStart={handleStart}
            onEndAnswer={endAnswer}
            onLeave={leave}
          />
        )}
      </div>
    </div>
  )
}

function Loading() {
  return <p className={styles.help}>불러오는 중입니다…</p>
}

function Invalid() {
  return (
    <>
      <h2 className={styles.name}>링크를 확인해 주세요</h2>
      <p className={styles.help}>
        이 면접 링크는 찾을 수 없습니다. 담당자에게 문의해 주세요.
      </p>
    </>
  )
}

function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <>
      <p className={styles.error} role="alert">{message}</p>
      <div className={styles.actions}>
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          다시 시도
        </button>
      </div>
    </>
  )
}

function ReadyBody(props: {
  data: InterviewPublic
  started: boolean
  pending: boolean
  phase: ReturnType<typeof useAiInterview>['phase']
  question: string | null
  seq: number | null
  note: string | null
  liveError: string | null
  videoRef: ReturnType<typeof useAiInterview>['videoRef']
  onConsent: () => void
  onStart: () => void
  onEndAnswer: () => void
  onLeave: () => void
}) {
  const { data, started, pending, phase, question, seq, note, liveError, videoRef, onConsent, onStart, onEndAnswer, onLeave } = props

  const posting = data.posting_title
  const name = data.applicant_name

  // 앱과 같은 상태 분기. `started` 는 웹만의 UI 상태 — 지원자가 시작 버튼을 눌러
  // 훅을 켰는지.
  const showConsent = data.status === 'pending' && data.consent_required

  /* **서버가 이미 `in_progress` 여도, 이 화면에서 시작을 누르기 전까지는 준비
     화면이다** (2026-09-15).

     전에는 곧장 실시간 화면으로 넘겼다. 그런데 훅은 `started` 로만 켜지므로
     (`useAiInterview(started ? token : null)`) **카메라도 소켓도 없는 죽은
     화면**이 떴다 — 까만 칸에 「준비 중」만 남고 질문이 영영 안 온다.
     프로덕션 실측에서 나왔고, 로컬에서 그대로 재현했다(video 는 있는데
     srcObject 가 null).

     세션이 열린 채 남는 경로가 흔하다: **새로고침·창 닫기는 `/finish` 를
     안 부른다**(useAiInterview 는 「면접 끝내기」에서만 부른다). 그래서 이
     상태로 다시 들어오는 것이 드문 일이 아니다.

     자동으로 켜지 않는 이유는 2026-09-14 에 정한 것 그대로다 — 옛 웹은 링크
     클릭만으로 카메라가 켜져, 지원자가 무엇이 시작되는지 모른 채 권한 팝업을
     마주쳤다. 한 번 더 누르게 한다. */
  const showReady =
    !started && !showConsent && (data.status === 'pending' || data.status === 'in_progress')

  const showLive = started && data.status !== 'done' && data.status !== 'expired'
  const showDone = data.status === 'done'
  const showExpired = data.status === 'expired'

  return (
    <>
      <p className={styles.posting}>{posting}</p>
      <h2 className={styles.name}>{name}님</h2>

      {showConsent && (
        <ConsentPanel busy={pending} onAgree={onConsent} />
      )}

      {showReady && (
        <ReadyPanel busy={pending} onStart={onStart} resume={data.status === 'in_progress'} />
      )}

      {showLive && (
        <LivePanel
          phase={phase}
          question={question}
          seq={seq}
          note={note}
          liveError={liveError}
          videoRef={videoRef}
          onEndAnswer={onEndAnswer}
          onLeave={onLeave}
        />
      )}

      {showDone && <DonePanel />}
      {showExpired && <ExpiredPanel />}
    </>
  )
}

function ConsentPanel({ busy, onAgree }: { busy: boolean; onAgree: () => void }) {
  return (
    <>
      {/* AI 를 쓴다는 것을 지원자에게 알린다 — 질문·답변 정리에 AI, 카메라·마이크는
          본인 확인과 기록, 표정·음성 분석은 참고 신호, 합격 여부는 사람. AI 이용정책
          (고위험 용도: 고지 + 사람 검토)과 개인정보 동의가 요구하는 것이다. 앱
          (interview_live_screen.dart) 과 같은 내용.

          「기기 밖으로 나간다」와 무엇이 남는지까지 적는다 (2026-10-13, 앱과 맞춤).
          이 화면은 얼굴 프레임과 음성을 소켓으로 서버에 보낸다(useAiInterview).
          영상은 쌓지 않고 버리며(lie-detection interview_ws.add_frame), 음성은
          받아쓰기에 실패한 회차만 남는다(preserve_audio). 그 음성을 다시 받아쓰게
          하면 외부 전사 서비스로 나갈 수 있다(backend agent/stt.py 기본값 openai). */}
      <p className={styles.help}>
        면접이 시작되면 <strong>카메라와 마이크가 켜집니다</strong>. 질문 생성과 답변 정리에
        AI(아르)가 쓰이고, 담당자가 실시간으로 참여합니다. 면접 중 카메라 영상과 마이크 음성은{' '}
        <strong>회사 서버로 전송</strong>되어 본인 확인과 답변 기록에 쓰이며, 표정·음성 분석은
        참고 신호일 뿐입니다. 영상은 저장하지 않고, 받아쓰기에 실패한 답변만 음성이 보관되며
        이때 외부 전사 서비스로 전송될 수 있습니다. <strong>합격 여부는 담당자가 직접
        판단</strong>하고, 면접 내용은 채용 검토 목적으로만 활용됩니다.
      </p>
      <div className={styles.actions}>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={onAgree}>
          {busy ? '진행 중…' : '동의하고 계속하기'}
        </button>
      </div>
    </>
  )
}

/* `resume` — 서버에 세션이 이미 열려 있는 경우. **그런 적 없는 것처럼 쓰지
   않는다**: 지원자는 자기가 아까 시작했던 것을 기억하므로, 「시작하기」만
   덩그러니 두면 처음부터 다시 하는 것인지 헷갈린다 */
function ReadyPanel({
  busy,
  onStart,
  resume,
}: {
  busy: boolean
  onStart: () => void
  resume: boolean
}) {
  return (
    <>
      <p className={styles.help}>
        {resume
          ? '면접이 아직 열려 있습니다. 아래 버튼을 누르면 이어서 진행합니다. 카메라와 마이크 권한을 허용해 주세요.'
          : '준비되시면 아래 버튼을 눌러 시작하세요. 시작 후 카메라와 마이크 권한을 허용해 주세요.'}
      </p>
      <div className={styles.actions}>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={onStart}>
          {resume ? '이어서 하기' : '시작하기'}
        </button>
      </div>
    </>
  )
}

function LivePanel(props: {
  phase: ReturnType<typeof useAiInterview>['phase']
  question: string | null
  seq: number | null
  note: string | null
  liveError: string | null
  videoRef: ReturnType<typeof useAiInterview>['videoRef']
  onEndAnswer: () => void
  onLeave: () => void
}) {
  const { phase, question, seq, note, liveError, videoRef, onEndAnswer, onLeave } = props
  const showLiveDot = phase === 'listening'
  // 질문이 있고 서버가 전사 중이 아닐 때만 누를 수 있다 — 전사 중에 또 누르면 서버가 무시하지만
  // 화면에서는 "정리하는 중" 을 지키는 편이 덜 헷갈린다
  const canEnd = question !== null && (phase === 'waiting' || phase === 'listening')

  return (
    <>
      <div className={styles.cameraBox}>
        <video ref={videoRef} className={styles.cam} autoPlay playsInline muted />
        {showLiveDot && (
          <span className={styles.liveDot} aria-hidden>
            <span className={styles.liveDotPulse} />
            LIVE
          </span>
        )}
      </div>

      <div className={styles.state} aria-live="polite">
        <span className={`${styles.stateDot} ${phase === 'listening' ? styles.stateDotLive : ''}`} />
        {AI_PHASE_LABEL[phase]}
      </div>

      <section className={styles.askWrap}>
        {phase === 'error' ? (
          <p className={styles.error} role="alert">{liveError}</p>
        ) : phase === 'done' ? (
          <>
            <h3 className={styles.ask}>면접이 끝났습니다</h3>
            <p className={styles.help}>참여해 주셔서 감사합니다.</p>
          </>
        ) : question ? (
          <>
            {seq !== null && <p className={styles.seq}>질문 {seq}</p>}
            <h3 className={styles.ask}>{question}</h3>
            {note ? (
              <p className={styles.error} role="alert">{note}</p>
            ) : (
              <p className={styles.help}>
                답변을 마치면 아래 <strong>[답변 완료]</strong> 를 눌러 주세요. 그래야 다음 질문으로 넘어갑니다.
              </p>
            )}
          </>
        ) : (
          <p className={styles.help}>아르가 첫 질문을 준비하고 있습니다…</p>
        )}
      </section>

      <footer className={styles.actions}>
        {/* 주 동작 = 답변 완료 (2026-09-15 · 앱과 같은 버튼). 끝내기는 되돌릴 수 없는 쪽이라 2차 */}
        <button type="button" className="btn btn-primary" disabled={!canEnd} onClick={onEndAnswer}>
          {phase === 'thinking' ? '저장 중…' : '답변 완료'}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onLeave}>
          면접 끝내기
        </button>
      </footer>
    </>
  )
}

function DonePanel() {
  return (
    <section className={styles.askWrap}>
      <h3 className={styles.ask}>면접이 끝났습니다</h3>
      <p className={styles.help}>참여해 주셔서 감사합니다.</p>
    </section>
  )
}

function ExpiredPanel() {
  return (
    <section className={styles.askWrap}>
      <h3 className={styles.ask}>면접 링크가 만료되었습니다</h3>
      <p className={styles.help}>담당자에게 문의해 주세요.</p>
    </section>
  )
}
