import { useParams } from 'react-router-dom'
import styles from './InterviewAi.module.css'
import { AI_PHASE_LABEL, useAiInterview } from './useAiInterview'

/* AI 면접 — 지원자 화면 (ADR-0029).

   아르가 묻고, 지원자가 말하면 **버튼 없이** 다음 질문으로 넘어간다.
   서버가 소리를 듣고 말이 끝난 것을 판정한다 (`ai/lie-detection/PROTOCOL.md`).

   **판정을 여기에 띄우지 않는다.** ADR-0029 이고 소연님이 서비스 코드에도
   적어 뒀다 — 판정을 실시간으로 보여 주면 그 자체가 답변을 바꾼다.
   훅도 그 값을 상태로 들고 있지 않아서, 화면이 그리려 해도 그릴 것이 없다.

   폰 세로가 기본이다. */

export default function InterviewAi() {
  const { token } = useParams<{ token: string }>()
  const { phase, question, seq, error, videoRef, leave } = useAiInterview(token ?? null)

  return (
    <div className={styles.page}>
      <header className={styles.bar}>
        <h1 className={styles.logo}><span className={styles.seed}>A</span>rda</h1>
        <div className={styles.state} aria-live="polite">
          {/* 말하는 중일 때만 점이 뛴다. 지원자가 "듣고 있나?" 를 알아야 한다 —
              1~2초 공백에 멈췄다고 생각하면 그 자체가 면접을 망친다. */}
          <span className={`${styles.dot} ${phase === 'listening' ? styles.dotLive : ''}`} />
          {AI_PHASE_LABEL[phase]}
        </div>
      </header>

      {/* 질문. 화면에서 제일 큰 글씨다 — 지원자가 볼 것은 이것 하나다. */}
      <section className={styles.askWrap}>
        {phase === 'error' ? (
          <p className={styles.error} role="alert">{error}</p>
        ) : phase === 'done' ? (
          <>
            <h2 className={styles.ask}>면접이 끝났습니다</h2>
            <p className={styles.help}>참여해 주셔서 감사합니다.</p>
          </>
        ) : question ? (
          <>
            {seq !== null && <p className={styles.seq}>질문 {seq}</p>}
            <h2 className={styles.ask}>{question}</h2>
            <p className={styles.help}>
              준비되시면 그냥 말씀하시면 됩니다. 버튼을 누르지 않으셔도 됩니다.
            </p>
          </>
        ) : (
          <p className={styles.help}>아르가 첫 질문을 준비하고 있습니다…</p>
        )}
      </section>

      {/* 자기 모습. 카메라가 켜졌는지 스스로 확인하는 자리다.
          거울처럼 보여야 자연스러우므로 좌우를 뒤집는다(화면에만). */}
      <video ref={videoRef} className={styles.cam} autoPlay playsInline muted />

      <footer className={styles.actions}>
        <button type="button" className="btn btn-secondary" onClick={leave}>
          면접 끝내기
        </button>
      </footer>
    </div>
  )
}
