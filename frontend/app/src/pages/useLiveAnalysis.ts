import { useEffect, useRef, useState } from 'react'
import { FRAME_MS, KIND_AUDIO, KIND_VIDEO, SR, WORKLET, aiWsUrl, sendMedia } from './aiSocket'

/* 사람 대 사람 화상 면접에서 **채용자가 지원자 얼굴 분석을 실시간으로 본다**
   (2026-09-09).

   ## 왜 채용자 기기가 보내는가

   AI 면접(`useAiInterview`)은 지원자 기기가 워커에게 미디어를 보낸다. 사람
   면접은 영상이 두 브라우저 사이를 직접 오가서(WebRTC) **워커가 볼 길이 없다.**
   누군가는 워커에게 보내 줘야 하는데, 보낼 수 있는 자리가 둘이다.

   | | 지원자 기기가 보낸다 | **채용자 기기가 보낸다** |
   |---|---|---|
   | 판정이 도착하는 곳 | 지원자 기기 → ADR-0029 위반 | 채용자 기기 — 봐야 할 사람 |
   | 지원자 쪽 부담 | 업로드가 두 배 (상대에게 + 워커에게) | 그대로 |
   | 우회 경로 | 워커 → 백엔드 → 담당자 (아직 없다) | 필요 없다 |

   **채용자가 이미 받아 보고 있는 그 영상**을 그대로 워커에 넘긴다. 그래서
   판정이 지원자 기기를 지나갈 길이 아예 없고, 지원자 쪽은 아무것도 더 하지
   않는다. AI 면접에서 겪었던 문제(#97)가 여기서는 생기지 않는다.

   ## 무엇을 보내는가

   `/ai/ws/live` 는 토큰이 없는 자리다 — 원래 만든 사람이 숫자를 눈으로 보려고
   둔 데모용 소켓이고, 세션·저장과 엮이지 않는다. 사람 면접에는 그 점이 맞는다:
   여기서 나오는 값은 **흘러가는 참고치**이고 남기지 않는다(남길 것을 정한 적이
   없다 — ADR-0029 는 AI 면접의 결과만 다룬다).

   ## 이 값을 판정으로 읽으면 안 된다

   모델은 법정 영상 121개로 배웠다. 100·0 은 확신이 아니라 **제대로 안 배웠다는
   신호**다(cloverky, 2026-09-08). 화면이 그 말을 같이 띄운다. */

/** 얼굴에서 관찰된 것 하나. **표정 이름이 아니다** — 눈 깜빡임·고개 움직임처럼
    잰 값이다(`feature_extractor.face_signals`). `flag` 는 눈에 띄는 값인지. */
export type FaceSignal = {
  key: string
  value: string
  flag?: string
}

export type LiveVerdict = {
  truth_pct?: number
  lie_pct?: number
  /** 얼굴에서 관찰된 것들. 프레임이 적으면 비어 있다 */
  signals?: FaceSignal[]
  /** 못 낸 이유. 얼굴이 안 보이거나 소리가 짧을 때 서버가 준다 */
  reason?: string
  at: number
}

export type LiveAnalysis = {
  /** 소켓이 붙었는가 */
  connected: boolean
  /** 지원자가 지금 말하고 있는가 (서버 판정) */
  speaking: boolean
  /** 가장 최근 판정 */
  latest: LiveVerdict | null
  /** 지나간 것들. 최근 것이 앞이다 */
  history: LiveVerdict[]
  /** 분석만 실패한 것. **면접 자체는 계속된다** */
  error: string | null
}

const EMPTY: LiveAnalysis = {
  connected: false,
  speaking: false,
  latest: null,
  history: [],
  error: null,
}

/** 흐름에 남기는 개수. 면접 내내 쌓으면 화면이 길어지기만 한다 */
const HISTORY_MAX = 30

/** 끊겼을 때 다시 붙어 보는 횟수. 이 뒤로는 오류로 적는다 */
const RETRY_MAX = 5

/**
 * 상대 영상을 워커에 넘겨 실시간 분석을 받는다.
 *
 * `stream` 이 `null` 이면 아무것도 하지 않는다 — 상대가 아직 안 붙었거나
 * 나간 상태다. 다시 붙으면 새 스트림으로 저절로 다시 시작한다.
 */
export function useLiveAnalysis(stream: MediaStream | null): LiveAnalysis {
  const [state, setState] = useState<LiveAnalysis>(EMPTY)

  /* 상대가 바뀌면(들어오거나 나가면) 앞사람 값을 지운다.
     **렌더 중에 맞춘다** — effect 안에서 지우면 헌 값이 한 번 그려진 뒤에
     지워져서, 나간 사람의 숫자가 잠깐 남는다. */
  const [seen, setSeen] = useState<MediaStream | null>(stream)
  if (stream !== seen) {
    setSeen(stream)
    setState(EMPTY)
  }

  const aliveRef = useRef(true)

  useEffect(() => {
    if (!stream) return
    aliveRef.current = true

    let ws: WebSocket | null = null
    let ctx: AudioContext | null = null
    let timer: number | null = null
    let video: HTMLVideoElement | null = null
    let retryTimer: number | null = null
    let retries = 0
    let closing = false

    const cleanup = () => {
      closing = true
      if (timer !== null) window.clearInterval(timer)
      timer = null
      if (retryTimer !== null) window.clearTimeout(retryTimer)
      retryTimer = null
      try {
        ws?.close()
      } catch {
        /* 이미 닫힌 소켓 */
      }
      ws = null
      void ctx?.close().catch(() => {})
      ctx = null
      if (video) {
        video.srcObject = null
        video = null
      }
    }

    /* 소켓 하나를 연다. **끊기면 다시 붙는다** — 워커가 재시작하거나 잠깐
       끊겼을 때 그대로 두면 면접이 끝날 때까지 분석이 영영 멈춘다(2026-09-09
       실측: 흐름에는 값이 쌓였는데 화면은 "연결하는 중" 에 멈춰 있었다).
       카메라·마이크 쪽은 살아 있으므로 소켓만 갈아 끼우면 이어진다. */
    const connect = () => {
      if (closing || !aliveRef.current) return
      const socket = new WebSocket(aiWsUrl('/ai/ws/live'))
      socket.binaryType = 'arraybuffer'
      ws = socket

      socket.onopen = () => {
        if (!aliveRef.current) return
        retries = 0
        setState((s) => ({ ...s, connected: true, error: null }))
      }
      socket.onclose = () => {
        if (closing || !aliveRef.current) return
        setState((s) => ({ ...s, connected: false, speaking: false }))
        if (retries >= RETRY_MAX) {
          setState((s) => ({ ...s, error: '분석 서버와 연결이 끊겼습니다' }))
          return
        }
        retries += 1
        // 1초·2초·3초… 로 늘려 가며. 워커가 다시 뜨는 데 몇 초가 걸린다
        retryTimer = window.setTimeout(connect, 1000 * retries)
      }
      socket.onerror = () => {
        /* 여기서는 상태를 건드리지 않는다 — 곧바로 `onclose` 가 따라오고,
           다시 붙는 판단은 거기 한 곳에서만 한다 */
      }
      socket.onmessage = (e) => {
        if (!aliveRef.current) return
        let m: {
          type?: string
          ok?: boolean
          truth_pct?: number
          lie_pct?: number
          reason?: string
          signals?: FaceSignal[]
        }
        try {
          m = JSON.parse(e.data)
        } catch {
          return
        }
        if (m.type === 'speaking' || m.type === 'quiet') {
          setState((s) => ({ ...s, speaking: m.type === 'speaking' }))
          return
        }
        if (m.type !== 'live') return

        const v: LiveVerdict = {
          truth_pct: typeof m.truth_pct === 'number' ? m.truth_pct : undefined,
          lie_pct: typeof m.lie_pct === 'number' ? m.lie_pct : undefined,
          signals: Array.isArray(m.signals) ? m.signals : undefined,
          reason: m.ok === false ? m.reason : undefined,
          at: Date.now(),
        }
        setState((s) => ({
          ...s,
          latest: v,
          /* 못 낸 것(`reason`)은 흐름에 안 쌓는다 — "얼굴이 잘 안 보여요" 가
             줄줄이 쌓이면 진짜 값이 묻힌다 */
          history: v.reason ? s.history : [v, ...s.history].slice(0, HISTORY_MAX),
        }))
      }
    }

    ;(async () => {
      connect()

      /* 오디오 — 상대 소리를 그대로 PCM 으로 옮긴다. **스피커로 내보내지 않는다**:
         소리는 `<video>` 가 이미 내고 있어서, 여기서 또 내면 두 번 들린다. */
      const audio = new AudioContext({ sampleRate: SR })
      ctx = audio
      const blobUrl = URL.createObjectURL(new Blob([WORKLET], { type: 'text/javascript' }))
      try {
        await audio.audioWorklet.addModule(blobUrl)
      } catch {
        if (!aliveRef.current) return
        setState((s) => ({ ...s, error: '소리를 분석에 넘기지 못했습니다' }))
        return
      } finally {
        URL.revokeObjectURL(blobUrl)
      }
      if (!aliveRef.current) return

      const node = new AudioWorkletNode(audio, 'pcm')
      node.port.onmessage = (e) => {
        if (ws) sendMedia(ws, KIND_AUDIO, e.data as ArrayBuffer)
      }
      audio.createMediaStreamSource(stream).connect(node)
      /* 워크릿에 목적지가 없으면 브라우저가 그래프를 안 돌린다. 소리는 죽여 둔다. */
      const mute = audio.createGain()
      mute.gain.value = 0
      node.connect(mute).connect(audio.destination)

      /* 영상 — 화면에 그려진 것이 아니라 **스트림에서 직접** 뽑는다.
         화면의 `<video>` 를 읽으면 그 요소가 언제 붙는지에 매이고, 채용자가
         창을 줄이면 해상도까지 따라 줄어든다. */
      const el = document.createElement('video')
      el.srcObject = stream
      el.muted = true
      el.playsInline = true
      video = el
      await el.play().catch(() => {})

      const canvas = document.createElement('canvas')
      canvas.width = 480
      canvas.height = 360
      const g = canvas.getContext('2d')
      timer = window.setInterval(() => {
        if (!el.videoWidth || !g || !ws) return
        g.drawImage(el, 0, 0, canvas.width, canvas.height)
        canvas.toBlob(
          (b) => void b?.arrayBuffer().then((a) => {
            if (ws) sendMedia(ws, KIND_VIDEO, a)
          }),
          'image/jpeg',
          0.6,
        )
      }, FRAME_MS)
    })()

    return () => {
      aliveRef.current = false
      cleanup()
    }
  }, [stream])

  return state
}
