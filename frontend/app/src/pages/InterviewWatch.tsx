import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, wsUrl } from '../api/client'
import { interviews } from '../api/endpoints'
import type { InterviewSessionDetail } from '../api/types'
import styles from './InterviewWatch.module.css'

/* 담당자용 — AI 면접이 도는 동안 실시간 판정을 본다 (ADR-0029).

   **카메라를 켜지 않는다.** 담당자는 보기만 한다 — 지원자와 얼굴을 맞대는
   화면(`InterviewRoom`)과 다른 자리다.

   판정은 **워커가 백엔드로 직접 민 것**이다 (#97) — 지원자 기기를 지나가지
   않는다. `워커 → POST /internal/interview/{token}/verdict → 시그널링 방`.
   서버는 나르기만 하고 저장하지 않는다.

   (사람 대 사람 화상 면접은 다른 화면이다 — `InterviewRoom` 이 자기가 받은
   영상을 직접 분석에 넘긴다. `useLiveAnalysis` 머리말 참고.)

   ## "일치" 라고 쓰지 않는다 (2026-09-09 · cloverky)

   09-08 까지 이 화면은 `일치 / 불일치` 라고 적었다. 그런데 **서버가 보내는 값은
   목소리와 얼굴로 낸 진실/거짓 확률이고, 서류를 아예 안 본다.** "일치" 라고
   적으면 담당자가 "이력서에 쓴 것과 말한 것이 맞다" 로 읽는다 — 그건 앞으로
   만들 `interview_findings`(서류 대조) 가 할 말이지 이 값이 할 말이 아니다.

   그래서 `진실 쪽 / 거짓 쪽` 으로 적는다. **모델이 배운 라벨이 실제로 그것이다.**
   그 말이 사실이라는 뜻은 아니라는 것은 아래 문단과 100·0 경고가 맡는다.

   ## 이 화면이 조심하는 것

   **숫자를 판정처럼 보이게 만들지 않는다.** 모델은 121 표본에 76% 고
   (ADR-0029 「정하지 못한 것」①), 그 위에 합불을 얹을 근거가 아직 없다.
   그래서 합격/불합격 같은 말도, 초록·빨강도 쓰지 않는다 — 색으로 칠하는 순간
   글이 말하지 않은 것을 색이 말한다. */

type Verdict = {
  truth_pct?: number
  lie_pct?: number
  window_sec?: number
  at: number
}

export default function InterviewWatch() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const id = Number(sessionId)
  const valid = Number.isFinite(id) && id > 0

  const [connected, setConnected] = useState(false)
  const [peerHere, setPeerHere] = useState(false)
  const [latest, setLatest] = useState<Verdict | null>(null)
  const [history, setHistory] = useState<Verdict[]>([])
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<InterviewSessionDetail | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const aliveRef = useRef(true)

  useEffect(() => {
    if (!valid) return
    const ac = new AbortController()
    interviews.detail(id, ac.signal).then(setDetail).catch(() => {
      /* 질문 목록을 못 읽어도 판정은 본다 */
    })
    return () => ac.abort()
  }, [id, valid])

  useEffect(() => {
    if (!valid) return
    aliveRef.current = true

    ;(async () => {
      let ticket: { ticket: string; token: string }
      try {
        /* 입장권은 접속 직전에 받는다 — 60초·1회용이다 */
        ticket = await api.post(`/interview-sessions/${id}/rtc-ticket`)
      } catch {
        if (!aliveRef.current) return
        setError('면접방에 들어갈 수 없습니다. 세션을 확인해 주세요')
        return
      }
      if (!aliveRef.current) return

      const ws = new WebSocket(
        `${wsUrl(`/ws/interview/${ticket.token}/rtc`)}?ticket=${encodeURIComponent(ticket.ticket)}`,
      )
      wsRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onclose = () => setConnected(false)
      ws.onerror = () => setError('서버에 연결하지 못했습니다')
      ws.onmessage = (e) => {
        let m: Record<string, unknown>
        try {
          m = JSON.parse(e.data)
        } catch {
          return
        }
        if (m.type === 'hello') setPeerHere(Boolean(m.peer_present))
        if (m.type === 'peer-join') setPeerHere(true)
        if (m.type === 'peer-leave') setPeerHere(false)
        if (m.type === 'verdict') {
          const v: Verdict = {
            truth_pct: typeof m.truth_pct === 'number' ? m.truth_pct : undefined,
            lie_pct: typeof m.lie_pct === 'number' ? m.lie_pct : undefined,
            window_sec: typeof m.window_sec === 'number' ? m.window_sec : undefined,
            at: Date.now(),
          }
          setLatest(v)
          /* 최근 것만 남긴다. 다 쌓으면 면접 끝에 화면이 스크롤 지옥이 된다. */
          setHistory((h) => [v, ...h].slice(0, 12))
        }
      }
    })()

    return () => {
      aliveRef.current = false
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [id, valid])

  const fmt = useCallback(
    (n?: number) => (typeof n === 'number' ? `${n.toFixed(1)}%` : '—'),
    [],
  )

  if (!valid) {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>잘못된 주소입니다</h2>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <header className={styles.bar}>
        <h1 className={styles.title}>실시간 분석</h1>
        <div className={styles.state} aria-live="polite">
          <span className={`${styles.dot} ${peerHere ? styles.dotLive : ''}`} />
          {error
            ? '연결 실패'
            : !connected
              ? '연결하는 중'
              : peerHere
                ? '지원자 면접 중'
                : '지원자를 기다리는 중'}
        </div>
      </header>

      {error && <p className={styles.error} role="alert">{error}</p>}

      <div className={styles.stage}>
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>지금</h2>
          {latest ? (
            <>
              <div className={styles.pair}>
                <div className={styles.metric}>
                  <span className={styles.metricLabel}>진실 쪽</span>
                  <span className={styles.metricValue}>{fmt(latest.truth_pct)}</span>
                </div>
                <div className={styles.metric}>
                  <span className={styles.metricLabel}>거짓 쪽</span>
                  <span className={styles.metricValue}>{fmt(latest.lie_pct)}</span>
                </div>
              </div>
              {/* **이 문단을 지우지 말 것.** 숫자만 두면 합불 근거처럼 읽힌다. */}
              <p className={styles.caveat}>
                표정·음성 신호가 모델이 학습한 패턴과 얼마나 맞는지입니다.
                <strong> 거짓말 여부가 아니고, 합격·불합격의 근거도 아닙니다.</strong>
                모델은 121개 표본에 교차검증 76%이며, 긴장·말더듬·비원어민 지원자에게
                불리하게 작동하지 않는다는 검증은 아직 없습니다 (ADR-0029).
              </p>

              {/* 100·0 은 **자신 있다는 뜻이 아니다.** 121개 표본으로 배운 모델이
                  규칙 대신 외운 결과라, 사실 대본과 지어낸 대본 둘 다 100 이 나온
                  적이 있다 (2026-09-07·09-08 실측, cloverky). 그 값이 뜨는
                  자리에서 그렇게 말해 두지 않으면 제일 확실한 판정처럼 읽힌다. */}
              {(latest.truth_pct === 100 || latest.truth_pct === 0) && (
                <p className={styles.saturated}>
                  <strong>100 / 0 은 확신이 아니라 경고입니다.</strong> 표본이 적어
                  모델이 규칙 대신 외운 자리이고, 사실을 말한 대본과 지어낸 대본이
                  똑같이 100으로 나온 적이 있습니다. 이 값은 근거로 쓰지 마세요.
                </p>
              )}
            </>
          ) : (
            <p className={styles.empty}>
              {peerHere
                ? '지원자가 말하기 시작하면 여기에 나타납니다.'
                : '지원자가 면접에 들어오면 시작됩니다.'}
            </p>
          )}
        </section>

        <aside className={styles.side}>
          <section className={styles.card}>
            <h2 className={styles.cardTitle}>질문</h2>
            {detail?.turns?.length ? (
              <ol className={styles.questions}>
                {detail.turns.map((t) => (
                  <li key={t.seq} className={styles.question}>{t.question}</li>
                ))}
              </ol>
            ) : (
              <p className={styles.empty}>준비된 질문이 없습니다.</p>
            )}
          </section>

          <section className={styles.card}>
            <h2 className={styles.cardTitle}>흐름</h2>
            {history.length === 0 ? (
              <p className={styles.empty}>아직 없습니다.</p>
            ) : (
              <ul className={styles.log}>
                {history.map((v) => (
                  <li key={v.at} className={styles.logRow}>
                    <span className={styles.logTime}>
                      {new Date(v.at).toLocaleTimeString('ko-KR')}
                    </span>
                    <span>진실 쪽 {fmt(v.truth_pct)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>
    </div>
  )
}
