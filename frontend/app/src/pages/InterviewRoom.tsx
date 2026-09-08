import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { applications, interviews } from '../api/endpoints'
import type { InterviewSessionDetail } from '../api/types'
import styles from './InterviewRoom.module.css'
import { PHASE_LABEL, useInterviewRoom } from './useInterviewRoom'

/* 채용자용 실시간 면접 화면 (docs/02_tasks/실시간-면접-시그널링.md).

   **레이아웃 밖에 둔다.** 사이드바·헤더가 있으면 지원자 얼굴이 그만큼 작아지고,
   면접 중에 다른 데로 새는 길이 화면에 남는다. 면접은 한 번에 하나만 한다. */

export default function InterviewRoom() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const id = Number(sessionId)
  const valid = Number.isFinite(id) && id > 0

  /* 훅이 돌려주는 것을 통째로 들고 다니지 않고 바로 푼다 — 상태와 ref 가
     한 덩어리로 있으면 React 컴파일러가 상태를 읽는 것까지 ref 접근으로 본다. */
  const { phase, error, muted, toggleMute, leave, localRef, remoteRef } =
    useInterviewRoom(valid ? id : null)
  const [detail, setDetail] = useState<InterviewSessionDetail | null>(null)
  /* 누구를 면접하는지. 세션 상세에는 이름이 없어 지원자를 한 번 더 읽는다. */
  const [who, setWho] = useState<{ name: string; posting: string } | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!valid) return
    const ac = new AbortController()
    interviews
      .detail(id, ac.signal)
      .then(async (d) => {
        setDetail(d)
        try {
          const app = await applications.detail(d.application_id, ac.signal)
          setWho({ name: app.name, posting: app.posting_title })
        } catch {
          /* 이름을 못 읽어도 면접은 된다 */
        }
      })
      .catch(() => {
        /* 상세를 못 읽어도 면접 자체는 된다 — 질문 목록만 안 보인다.
           여기서 화면을 막으면 붙을 수 있는 면접을 못 하게 만든다. */
      })
    return () => ac.abort()
  }, [id, valid])

  const copyLink = useCallback(async () => {
    if (!detail?.url) return
    try {
      await navigator.clipboard.writeText(detail.url)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      /* 클립보드 권한이 없으면 아래 주소를 직접 긁으면 된다 */
    }
  }, [detail])

  if (!valid) {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>잘못된 주소입니다</h2>
        </div>
      </div>
    )
  }

  const waiting = phase !== 'live'

  return (
    <div className={styles.page}>
      <header className={styles.bar}>
        <div className={styles.who}>
          <h1 className={styles.name}>{who?.name ?? '실시간 면접'}</h1>
          {who?.posting && <p className={styles.posting}>{who.posting}</p>}
        </div>
        <div className={styles.state} aria-live="polite">
          <span className={`${styles.dot} ${phase === 'live' ? styles.dotLive : ''}`} />
          {PHASE_LABEL[phase]}
        </div>
      </header>

      <div className={styles.stage}>
        {/* 지원자. 화면의 주인공이라 남는 자리를 전부 준다. */}
        <div className={styles.remoteWrap}>
          <video ref={remoteRef} className={styles.remote} autoPlay playsInline />

          {waiting && (
            <div className={styles.overlay}>
              <p className={styles.overlayTitle}>{PHASE_LABEL[phase]}</p>
              {error ? (
                <p className={styles.overlayBody}>{error}</p>
              ) : (
                <>
                  <p className={styles.overlayBody}>
                    지원자가 링크를 열면 자동으로 연결됩니다.
                  </p>
                  {detail?.url && (
                    <div className={styles.linkRow}>
                      <code className={styles.link}>{detail.url}</code>
                      <button type="button" className="btn btn-secondary" onClick={copyLink}>
                        {copied ? '복사됨' : '링크 복사'}
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* **좌우를 뒤집는 것은 내 얼굴뿐이다.** 상대는 뒤집지 않는다 —
              거울로 보이는 게 자연스러운 건 자기 모습일 때뿐이다. */}
          <video ref={localRef} className={styles.local} autoPlay playsInline muted />
        </div>

        <aside className={styles.side}>
          <section className={styles.panel}>
            <h2 className={styles.panelTitle}>질문</h2>
            {detail?.turns?.length ? (
              <ol className={styles.questions}>
                {detail.turns.map((t) => (
                  <li key={t.seq} className={styles.question}>
                    {t.question}
                  </li>
                ))}
              </ol>
            ) : (
              <p className={styles.empty}>준비된 질문이 없습니다.</p>
            )}
          </section>

          {/* 소연님의 실시간 분석이 들어올 자리. **자리만 잡아 둔다** —
              여기에 임시 숫자를 채우면 나중에 진짜 값과 구별이 안 된다. */}
          <section className={styles.panel}>
            <h2 className={styles.panelTitle}>실시간 분석</h2>
            <p className={styles.empty}>
              아직 붙지 않았습니다. 표정·음성 분석(ADR-0029)이 이 자리에 들어옵니다.
            </p>
          </section>
        </aside>
      </div>

      <footer className={styles.actions}>
        <button type="button" className="btn btn-secondary" onClick={toggleMute}>
          {muted ? '마이크 켜기' : '마이크 끄기'}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => {
            leave()
            navigate(-1)
          }}
        >
          나가기
        </button>
      </footer>
    </div>
  )
}
