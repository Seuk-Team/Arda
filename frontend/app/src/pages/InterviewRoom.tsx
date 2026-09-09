import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { applications, interviews, postings } from '../api/endpoints'
import type { InterviewSessionDetail } from '../api/types'
import styles from './InterviewRoom.module.css'
import { useLiveAnalysis } from './useLiveAnalysis'
import { phaseLabel, useInterviewRoom } from './useInterviewRoom'

/** 숫자 한 칸. 값이 없으면 자리만 지킨다 — `InterviewWatch` 와 같은 표기. */
function fmt(v: number | undefined): string {
  return typeof v === 'number' ? `${v.toFixed(1)}%` : '—'
}

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
  const { phase, error, muted, toggleMute, leave, localRef, remoteRef, remoteStream } =
    useInterviewRoom({ role: 'recruiter', sessionId: valid ? id : null })
  /* **지원자에게서 받은 영상을 분석에 넘긴다.** 지원자 기기가 아니라 여기서
     보내는 이유는 `useLiveAnalysis` 머리말에 적어 뒀다 (ADR-0029). */
  const analysis = useLiveAnalysis(remoteStream)
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
          /* 공고 제목은 지원서에 안 실려 온다 — 공고를 한 번 더 읽는다.
             이름부터 먼저 띄우지 않고 둘을 모아 한 번에 넣는다. */
          const posting = await postings.get(app.job_posting_id, ac.signal)
          setWho({ name: app.name, posting: posting.title })
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
          {phaseLabel('recruiter', phase)}
        </div>
      </header>

      <div className={styles.stage}>
        {/* 지원자. 화면의 주인공이라 남는 자리를 전부 준다. */}
        <div className={styles.remoteWrap}>
          <video ref={remoteRef} className={styles.remote} autoPlay playsInline />

          {waiting && (
            <div className={styles.overlay}>
              <p className={styles.overlayTitle}>{phaseLabel('recruiter', phase)}</p>
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

          {/* 실시간 분석 (2026-09-09). **지원자에게서 받은 영상을 여기서**
              워커로 넘긴다 — 지원자 기기는 아무것도 더 하지 않고, 판정이
              그쪽으로 갈 길도 없다 (ADR-0029 · `useLiveAnalysis`). */}
          <section className={styles.panel}>
            <h2 className={styles.panelTitle}>실시간 분석</h2>

            {analysis.error ? (
              /* **면접을 막지 않는다.** 분석이 안 되는 것과 면접이 안 되는 것은 다르다 */
              <p className={styles.empty}>{analysis.error}</p>
            ) : !remoteStream ? (
              <p className={styles.empty}>지원자가 연결되면 시작됩니다.</p>
            ) : !analysis.connected ? (
              <p className={styles.empty}>분석 서버에 연결하는 중…</p>
            ) : analysis.latest?.truth_pct === undefined ? (
              <p className={styles.empty}>
                {analysis.latest?.reason ?? '지원자가 말하기 시작하면 여기에 나타납니다.'}
              </p>
            ) : (
              <>
                <div className={styles.pair}>
                  <div className={styles.metric}>
                    <span className={styles.metricLabel}>일치</span>
                    <span className={styles.metricValue}>{fmt(analysis.latest.truth_pct)}</span>
                  </div>
                  <div className={styles.metric}>
                    <span className={styles.metricLabel}>불일치</span>
                    <span className={styles.metricValue}>{fmt(analysis.latest.lie_pct)}</span>
                  </div>
                </div>

                {/* **이 문단을 지우지 말 것.** 숫자만 두면 합불 근거처럼 읽힌다.
                    `InterviewWatch` 와 같은 말을 쓴다 — 같은 값을 두 화면이
                    다르게 설명하면 그 자체가 오해를 만든다. */}
                <p className={styles.caveat}>
                  표정·음성 신호가 모델이 학습한 패턴과 얼마나 맞는지입니다.
                  <strong> 거짓말 여부가 아니고, 합격·불합격의 근거도 아닙니다.</strong>
                  모델은 121개 표본에 교차검증 76%이며, 긴장·말더듬·비원어민 지원자에게
                  불리하게 작동하지 않는다는 검증은 아직 없습니다 (ADR-0029).
                </p>

                {/* 100·0 은 자신 있다는 뜻이 아니라 **제대로 안 배웠다는 신호**다
                    (cloverky, 2026-09-08 실측). 그 값이 뜨는 자리마다 같이 적는다. */}
                {(analysis.latest.truth_pct === 100 || analysis.latest.truth_pct === 0) && (
                  <p className={styles.saturated}>
                    <strong>100 / 0 은 확신이 아니라 경고입니다.</strong> 표본이 적어
                    모델이 규칙 대신 외운 자리이고, 사실을 말한 대본과 지어낸 대본이
                    똑같이 100으로 나온 적이 있습니다. 이 값은 근거로 쓰지 마세요.
                  </p>
                )}
              </>
            )}
          </section>

          {analysis.history.length > 0 && (
            <section className={styles.panel}>
              <h2 className={styles.panelTitle}>흐름</h2>
              <ul className={styles.log}>
                {analysis.history.map((v) => (
                  <li key={v.at} className={styles.logRow}>
                    <span className={styles.logTime}>
                      {new Date(v.at).toLocaleTimeString('ko-KR')}
                    </span>
                    <span>일치 {fmt(v.truth_pct)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
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
