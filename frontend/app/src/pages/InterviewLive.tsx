import { useParams } from 'react-router-dom'
import styles from './InterviewLive.module.css'
import { phaseLabel, useInterviewRoom } from './useInterviewRoom'

/* 지원자 쪽 실시간 면접 (docs/02_tasks/실시간-면접-시그널링.md).

   채용자 쪽(`InterviewRoom.tsx`)과 **같은 훅**을 쓰고 자리만 다르다 —
   지원자는 입장권이 없고(메일 링크의 토큰이 곧 자격), offer 를 만들지 않는다.

   **폰 세로가 기본이다** (ADR-0031 전제: 지원자는 자기 스마트폰으로 들어온다).
   그래서 면접관 영상을 위에 크게, 내 얼굴을 아래 작게 둔다 — 가로 배치는
   폰에서 둘 다 작아진다. */

export default function InterviewLive() {
  const { token } = useParams<{ token: string }>()
  const { phase, error, muted, toggleMute, leave, localRef, remoteRef } =
    useInterviewRoom({ role: 'applicant', token: token ?? null })

  const waiting = phase !== 'live'

  return (
    <div className={styles.page}>
      <header className={styles.bar}>
        <h1 className={styles.logo}><span className={styles.seed}>A</span>rda</h1>
        <div className={styles.state} aria-live="polite">
          <span className={`${styles.dot} ${phase === 'live' ? styles.dotLive : ''}`} />
          {phaseLabel('applicant', phase)}
        </div>
      </header>

      <div className={styles.stage}>
        {/* 면접관. 지원자가 봐야 하는 얼굴이라 여기가 크다. */}
        <div className={styles.remoteWrap}>
          <video ref={remoteRef} className={styles.remote} autoPlay playsInline />

          {waiting && (
            <div className={styles.overlay}>
              <p className={styles.overlayTitle}>{phaseLabel('applicant', phase)}</p>
              <p className={styles.overlayBody}>
                {error ?? '면접관이 들어오면 자동으로 연결됩니다. 잠시만 기다려 주세요.'}
              </p>
            </div>
          )}
        </div>

        {/* 내 모습. **여기만 좌우를 뒤집는다** — 거울처럼 보여야 자연스러운 건
            자기 얼굴일 때뿐이다. 카메라가 켜졌는지 스스로 확인하는 자리이기도 하다. */}
        <video ref={localRef} className={styles.local} autoPlay playsInline muted />
      </div>

      <footer className={styles.actions}>
        <button type="button" className="btn btn-secondary" onClick={toggleMute}>
          {muted ? '마이크 켜기' : '마이크 끄기'}
        </button>
        {/* 나가는 길이 화면에 있어야 한다. 없으면 창을 닫는 수밖에 없고,
            그러면 면접관 쪽에서 "끊긴 것"과 "그만둔 것"이 구별되지 않는다. */}
        <button type="button" className="btn btn-secondary" onClick={leave}>
          면접 나가기
        </button>
      </footer>
    </div>
  )
}
