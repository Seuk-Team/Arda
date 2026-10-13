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

/** 표정 판정 하나. 우리가 학습한 ViT (`cloverky/arda-expression-vit`) 결과다.
    라벨은 영어 · `label_ko` 는 담당자용 한국어. `prob` 는 0~1 (2026-09-10). */
export type Expression = {
  label: string
  label_ko: string
  prob: number
}

/** 목소리에서 잰 것들 (2026-09-11, `feature_extractor.voice_signals`). 판정 입력
    100개 중 86개가 목소리인데 화면에 하나도 없었다. **높다·낮다는 서버가 붙이지
    않는다** — 사람마다 목소리가 달라 같은 사람의 앞선 값과 비교한다. */
export type VoiceSignals = {
  /** 말하는 동안 음 높이 가운데값 (Hz). 말소리가 적으면 없다 */
  pitch_hz?: number
  /** 음 높이가 오르내린 폭 (반음) — 억양 */
  pitch_var_st?: number
  /** 목소리 크기 (dBFS). 마이크마다 기준이 달라 변화만 본다 */
  loud_db?: number
  /** 크기가 오르내린 폭 (dB) */
  loud_var_db?: number
  /** 창 안에서 목소리가 난 비율 (%) */
  voiced_pct?: number
}

export type LiveVerdict = {
  truth_pct?: number
  lie_pct?: number
  /** 얼굴에서 관찰된 것들. 프레임이 적으면 비어 있다 */
  signals?: FaceSignal[]
  /** 목소리에서 잰 것들 */
  voice?: VoiceSignals
  /** ViT 로 읽은 표정 top-3. VIT_MODEL 꺼져 있으면 undefined */
  expressions?: Expression[]
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
  /** 목소리 값만 더 길게 들고 있는다 — 「평소」 를 말하는 데 쓴다. 최근 것이 앞이다 */
  voices: VoiceSignals[]
  /** 분석만 실패한 것. **면접 자체는 계속된다** */
  error: string | null
  /** 브라우저가 소리 장치를 멈춰 둔 채다 — 화면을 한 번 누르면 풀린다 */
  audioBlocked: boolean
}

const EMPTY: LiveAnalysis = {
  connected: false,
  speaking: false,
  latest: null,
  history: [],
  voices: [],
  error: null,
  audioBlocked: false,
}

/** 흐름에 남기는 개수. 면접 내내 쌓으면 화면이 길어지기만 한다 */
const HISTORY_MAX = 30

/** 목소리 「평소」 에 쓰는 개수. 판정이 말하는 동안 초당 한 번이라 약 5분치다.
    흐름(30개)으로 평소를 잡으면 30초 전과만 비교하게 된다 */
const VOICE_MAX = 300

/** 끊겼을 때 다시 붙어 보는 횟수. 이 뒤로는 오류로 적는다 */
const RETRY_MAX = 5

/* 판정 한 통을 화면이 쓰는 모양으로. **두 길에서 같은 것을 쓴다** —
   `/ai/ws/live` 소켓(`type: 'live'`)과 시그널링 방(`type: 'verdict'`) 둘 다
   워커가 만든 같은 값이라, 모양을 두 벌 두면 한쪽만 고치는 날이 온다. */
function toVerdict(m: Record<string, unknown>): LiveVerdict {
  return {
    truth_pct: typeof m.truth_pct === 'number' ? m.truth_pct : undefined,
    lie_pct: typeof m.lie_pct === 'number' ? m.lie_pct : undefined,
    signals: Array.isArray(m.signals) ? (m.signals as FaceSignal[]) : undefined,
    expressions: Array.isArray(m.expressions) ? (m.expressions as Expression[]) : undefined,
    voice:
      m.voice && typeof m.voice === 'object' ? (m.voice as VoiceSignals) : undefined,
    /* 방으로 오는 판정에는 이 값이 없다 — 워커가 판정을 못 내면 **아예 안
       민다**(`app.py` 가 로그만 남기고 돌아선다). `/ws/live` 갈래에서만 온다 */
    reason: m.ok === false ? (m.reason as string | undefined) : undefined,
    at: Date.now(),
  }
}

function fold(s: LiveAnalysis, v: LiveVerdict): LiveAnalysis {
  return {
    ...s,
    latest: v,
    /* 못 낸 것(`reason`)은 흐름에 안 쌓는다 — "얼굴이 잘 안 보여요" 가
       줄줄이 쌓이면 진짜 값이 묻힌다 */
    history: v.reason ? s.history : [v, ...s.history].slice(0, HISTORY_MAX),
    voices: v.voice && !v.reason ? [v.voice, ...s.voices].slice(0, VOICE_MAX) : s.voices,
  }
}

/**
 * 상대 영상을 워커에 넘겨 실시간 분석을 받는다.
 *
 * `stream` 이 `null` 이면 아무것도 하지 않는다 — 상대가 아직 안 붙었거나
 * 나간 상태다. 다시 붙으면 새 스트림으로 저절로 다시 시작한다.
 */
export function useLiveAnalysis(
  stream: MediaStream | null,
  /* 면접 토큰. 있으면 **그 세션 소켓**에 붙는다 (2026-09-16, 백엔드 PR #273).
     없으면 예전처럼 `/ai/ws/live` — 토큰 없는 자리다.

     **왜 갈아탔나**: `/ai/ws/live` 로 보내면 얼굴이 그 면접 세션 장부에 안
     남는다. 앱이 소리를, 담당자가 얼굴을 같은 토큰으로 보내야 서버가 둘을
     한 판정으로 묶는다 — 전에는 소켓마다 세션을 새로 만들어 앱은 `no_face`,
     담당자는 `short_audio` 로 양쪽 다 판정이 안 났다. */
  token?: string | null,
  /* 방으로 들어온 판정. **토큰 갈래에서는 소켓이 판정을 안 준다** —
     `{"type":"ready"}` 와 `ping/pong` 뿐이고, 판정은 워커 → 백엔드 →
     시그널링 방으로 간다. 그래서 밖에서 받아 넣는다. */
  pushed?: Record<string, unknown> | null,
): LiveAnalysis {
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
    let stopWaking: (() => void) | null = null

    const cleanup = () => {
      closing = true
      stopWaking?.()
      stopWaking = null
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
      /* **`?role=recruiter` 를 꼭 붙인다** — 안 붙이면 서버가 지원자 자리로
         본다(백엔드 PR #273). 이 역할로 붙으면 서버가 얼굴(`0x02`)만 받고
         소리(`0x01`)는 버리며, 질문·답변 흐름에 끼우지 않는다. */
      const socket = new WebSocket(
        token
          ? aiWsUrl(`/ai/ws/interview/${encodeURIComponent(token)}`, {
              role: 'recruiter',
            })
          : aiWsUrl('/ai/ws/live'),
      )
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
          expressions?: Expression[]
          voice?: VoiceSignals
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
        setState((s) => fold(s, toVerdict(m)))
      }
    }

    ;(async () => {
      connect()

      /* 오디오 — 상대 소리를 그대로 PCM 으로 옮긴다. **스피커로 내보내지 않는다**:
         소리는 `<video>` 가 이미 내고 있어서, 여기서 또 내면 두 번 들린다.

         **소리 트랙이 없는 상대가 있다** (2026-10-13). 앱(`interview_live_screen.dart`)
         은 WebRTC 를 `audio: false` 로 연다 — 안드로이드가 마이크를 하나만 줘서,
         지원자 소리는 앱이 워커로 직접 보내고 담당자에게는 **영상만** 온다.

         그 스트림으로 `createMediaStreamSource` 를 부르면
         `InvalidStateError: MediaStream has no audio track` 이 나는데, 그 예외가
         **아래 얼굴 전송 루프까지 통째로 날렸다.** 담당자 화면이 "지원자가 말하기
         시작하면…" 에서 영영 멈춘 원인이 이것이다 — 웹 지원자는 소리 트랙이 있어서
         멀쩡하고 **앱 지원자일 때만** 그랬다(10-13 실측).

         소리가 없으면 소리만 건너뛴다. 얼굴은 보내야 한다 — 그 토큰의 판정은
         앱이 보내는 소리와 여기서 보내는 얼굴을 서버가 묶어서 낸다. */
      const hasAudio = stream.getAudioTracks().length > 0
      if (hasAudio) await setUpAudio()
      if (!aliveRef.current) return

      async function setUpAudio() {
        const audio = new AudioContext({ sampleRate: SR })
        ctx = audio
        const blobUrl = URL.createObjectURL(new Blob([WORKLET], { type: 'text/javascript' }))
        try {
          await audio.audioWorklet.addModule(blobUrl)
        } catch {
          if (!aliveRef.current) return
          /* **영상까지 멈추지는 않는다** — 얼굴만으로도 담당자가 볼 것이 있다 */
          setState((s) => ({ ...s, error: '소리를 분석에 넘기지 못했습니다' }))
          return
        } finally {
          URL.revokeObjectURL(blobUrl)
        }
        if (!aliveRef.current) return

        /* **크롬은 페이지를 한 번도 누르지 않았으면 소리 장치를 멈춘 채로 만든다**
           (자동재생 정책). 면접방 주소를 새 탭에 붙여 열면 그렇다 — 그러면 지원자
           소리가 분석으로 한 조각도 안 가서 판정이 영영 안 뜬다(2026-09-11 실측:
           "말하기 시작하면…" 에서 멈춤). 바로 깨워 보고, 안 깨면 첫 클릭·키에 깨운다.
           멈춰 있는 동안은 화면이 "한 번 누르세요" 를 띄운다(`audioBlocked`). */
        const wake = () => {
          if (audio.state === 'suspended') void audio.resume().catch(() => {})
        }
        audio.onstatechange = () => {
          if (!aliveRef.current) return
          setState((s) => ({ ...s, audioBlocked: audio.state === 'suspended' }))
        }
        window.addEventListener('pointerdown', wake)
        window.addEventListener('keydown', wake)
        stopWaking = () => {
          window.removeEventListener('pointerdown', wake)
          window.removeEventListener('keydown', wake)
          audio.onstatechange = null
        }
        wake()
        setState((s) => ({ ...s, audioBlocked: audio.state === 'suspended' }))

        const node = new AudioWorkletNode(audio, 'pcm')
        node.port.onmessage = (e) => {
          if (ws) sendMedia(ws, KIND_AUDIO, e.data as ArrayBuffer)
        }
        audio.createMediaStreamSource(stream).connect(node)
        /* 워크릿에 목적지가 없으면 브라우저가 그래프를 안 돌린다. 소리는 죽여 둔다. */
        const mute = audio.createGain()
        mute.gain.value = 0
        node.connect(mute).connect(audio.destination)
      }

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
  }, [stream, token])

  /* 방으로 들어온 판정을 접어 넣는다 (2026-09-16).

     **토큰 갈래에서는 이것이 유일한 판정 경로다.** 담당자 소켓은 얼굴을
     보내기만 하고 판정은 안 준다 — 워커 → 백엔드 → 시그널링 방으로 간다.
     [useInterviewRoom] 이 그 방에서 받아 넘겨 준다. */
  const foldedRef = useRef<Record<string, unknown> | null>(null)
  useEffect(() => {
    if (!pushed || pushed === foldedRef.current) return
    foldedRef.current = pushed
    setState((s) => fold(s, toVerdict(pushed)))
  }, [pushed])

  return state
}
