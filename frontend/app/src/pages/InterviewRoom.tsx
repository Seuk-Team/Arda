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

/** 한 쪽의 확률 막대.
 *
 *  **초록·빨강을 쓰지 않는다.** 어느 쪽이 큰지는 길이로 이미 보이고, 색까지
 *  칠하면 글이 말하지 않은 판단("이 사람은 거짓이다")을 색이 말한다.
 *  앞선 쪽만 진하게 둔다. */
function _Bar({ label, pct, lead }: { label: string; pct?: number; lead: boolean }) {
  const v = typeof pct === 'number' ? Math.max(0, Math.min(100, pct)) : 0
  return (
    <div className={styles.barRow}>
      <span className={styles.barLabel}>{label}</span>
      <span className={styles.barTrack}>
        <span
          className={lead ? styles.barFillLead : styles.barFill}
          style={{ width: `${v}%` }}
        />
      </span>
      <span className={styles.barPct}>{fmt(pct)}</span>
    </div>
  )
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

  /* 답변 전사 갱신 (2026-09-09) — 지원자가 답을 마칠 때마다 서버가 저장하지만
     담당자 브라우저에는 밀어 넣지 않는다. 3초 간격으로 다시 읽어 새 답변을
     붙인다. **폴링이 심하지 않은 이유**: 면접이 도는 동안만 돌고, 응답은 세션
     한 개(질문 목록·답변)라 서버 부담이 작다. */
  useEffect(() => {
    if (!valid) return
    const ac = new AbortController()
    const timer = window.setInterval(() => {
      interviews
        .detail(id, ac.signal)
        .then(setDetail)
        .catch(() => {
          /* 한 번 실패해도 다음 주기를 기다린다 */
        })
    }, 3000)
    return () => {
      window.clearInterval(timer)
      ac.abort()
    }
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
            <h2 className={styles.panelTitle}>질문·답변</h2>
            {detail?.turns?.length ? (
              <ol className={styles.questions}>
                {detail.turns.map((t) => (
                  <li key={t.seq} className={styles.question}>
                    {t.question}
                    {/* 서버가 저장한 답변 전사(2026-09-09).
                        아직 안 온 것은 자리만 남긴다 — "아직 답 없음" 을 안 적으면
                        지원자가 지금 답하는 중인지 다 넘긴 것인지 화면으로 알 수 없다. */}
                    <div className={styles.answer}>
                      {t.transcript ?? <em className={styles.pending}>아직 답이 저장되지 않았습니다.</em>}
                    </div>
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

            {/* **값이 있으면 값을 먼저 보여 준다.** 소켓이 끊겼다고 숫자를 감추면
                그 아래 붙는 100·0 경고까지 같이 사라진다 — 경고 없이 숫자만 본
                뒤라 더 나쁘다(2026-09-09 실측: 흐름에는 100.0 이 쌓였는데 위는
                "연결하는 중" 이었다). 대신 **멈춘 값이라고 적는다.** */}
            {!remoteStream ? (
              <p className={styles.empty}>지원자가 연결되면 시작됩니다.</p>
            ) : analysis.latest?.truth_pct === undefined ? (
              <p className={styles.empty}>
                {analysis.error ??
                  (analysis.connected
                    ? (analysis.latest?.reason ?? '지원자가 말하기 시작하면 여기에 나타납니다.')
                    : '분석 서버에 연결하는 중…')}
              </p>
            ) : (
              <>
                {/* **어느 쪽에 가까운지를 먼저 적는다.** 숫자 둘만 두면 보는 사람이
                    머릿속에서 비교해야 하는데, 그 사이에 큰 숫자만 눈에 남는다.

                    모델이 배운 라벨이 실제로 "진실 / 거짓" 이라 그 말을 쓴다.
                    **다만 그 말이 곧 사실이라는 뜻은 아니다** — 아래 문단이
                    그것을 적고, 100·0 이면 경고가 하나 더 붙는다. */}
                <p className={styles.lean}>
                  모델이 본 쪽:{' '}
                  <strong>
                    {analysis.latest.truth_pct >= 50 ? '진실 쪽' : '거짓 쪽'}
                  </strong>
                </p>

                <_Bar
                  label="진실"
                  pct={analysis.latest.truth_pct}
                  lead={analysis.latest.truth_pct >= 50}
                />
                <_Bar
                  label="거짓"
                  pct={analysis.latest.lie_pct}
                  lead={(analysis.latest.truth_pct ?? 0) < 50}
                />

                {/* 표정 top-3 — 우리가 학습한 ViT (`cloverky/arda-expression-vit`,
                    2026-09-10) 가 본 결과. **판정에는 안 들어간다** — model.pkl 은
                    아직 100차원이라 표정 7개가 벡터에 붙지 않는다(ADR-0032 §정하지 못한 것 ③).
                    담당자에게 "우리 ViT 가 뭘 보고 있나" 를 근거로 보여 주는 자리다. */}
                {analysis.latest.expressions?.length ? (
                  <div className={styles.expressions}>
                    <p className={styles.expressionsLabel}>
                      표정 (우리 ViT · 판정엔 안 들어감)
                    </p>
                    <ul className={styles.expressionsList}>
                      {analysis.latest.expressions.slice(0, 3).map((ex) => (
                        <li key={ex.label} className={styles.expressionRow}>
                          <span className={styles.expressionName}>
                            {ex.label_ko || ex.label}
                          </span>
                          <span className={styles.expressionPct}>
                            {Math.round(ex.prob * 100)}%
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {/* 얼굴에서 실제로 잰 것들 — mediapipe 로 재는 landmarks 기반 값.
                    표정 라벨과 별개로 눈 깜빡임·눈썹 높이·고개 움직임 같은 것. */}
                {analysis.latest.signals?.length ? (
                  <ul className={styles.signals}>
                    {analysis.latest.signals.map((sig) => (
                      <li key={sig.key} className={styles.signalRow}>
                        <span className={styles.signalKey}>{sig.key}</span>
                        <span
                          className={
                            sig.flag === 'high' || sig.flag === 'low'
                              ? styles.signalMarked
                              : styles.signalValue
                          }
                        >
                          {sig.value}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}

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

                {/* 끊긴 채로 옛 숫자를 그대로 두면 지금 값처럼 읽힌다 */}
                {!analysis.connected && (
                  <p className={styles.stale}>
                    {analysis.error ?? '연결이 끊겨 갱신이 멈췄습니다. 다시 붙는 중…'}
                    {' '}위 숫자는 마지막으로 받은 값입니다.
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
                    <span>진실 쪽 {fmt(v.truth_pct)}</span>
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
