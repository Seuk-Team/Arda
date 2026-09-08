import { useCallback, useEffect, useRef, useState } from 'react'
import { wsUrl } from '../api/client'

/* AI 면접 — 아르가 묻고, 얼굴을 실시간으로 본다.

   **소켓 셋을 동시에 연다.** 소연님 서비스가 아직 둘로 나뉘어 있어서다
   (`ai/lie-detection/app.py`).

   | 소켓 | 무엇 | 왜 따로 |
   |---|---|---|
   | `/ai/ws/interview/{token}` | 아르의 질문·답변 저장 | **판정을 안 보낸다** |
   | `/ai/ws/live` | 실시간 판정 | 토큰이 없고 면접과 연결 안 됨 |
   | `/api/v1/ws/interview/{token}/rtc` | 판정을 담당자에게 나르기 | 서버에 그 통로가 없어서 |

   카메라 한 대에서 나온 것을 앞의 두 소켓에 **같이** 보낸다. 소연님이 나중에
   둘을 합치면 여기서 `/ws/live` 쪽만 지우면 된다.

   ## 지원자에게 판정을 보여 주지 않는다

   ADR-0029 이고 소연님이 코드에도 적어 뒀다 — **판정을 실시간으로 보여 주면
   그 자체가 답변을 바꾼다.** 그래서 이 훅은 판정을 상태로 들고 있지 않고
   받는 즉시 담당자 쪽으로 넘긴다. 화면이 그릴 수 있는 값 자체를 안 만든다. */

/* 소연님 규격 (PROTOCOL.md · demo.html). 바꾸면 서버가 못 알아듣는다. */
const SR = 16000 //   서버가 기대하는 표본율
const AUDIO_MS = 50 // 오디오 한 조각. 서버가 이 단위로 말/침묵을 가른다
const FRAME_MS = 200 // 영상 5장/초. 더 자주 보내도 서버가 안 쓴다
const KIND_AUDIO = 0x01
const KIND_VIDEO = 0x02

/* 오디오를 Int16 로 바꿔 50ms 씩 모아 보내는 워크릿. 파일로 두면 배포에 하나가
   더 붙으므로 문자열로 만들어 쓴다 (demo.html 과 같은 방식). */
const WORKLET = `
class PCM extends AudioWorkletProcessor {
  constructor() { super(); this.buf = []; this.n = 0;
                  this.need = Math.round(sampleRate * ${AUDIO_MS} / 1000); }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    const out = new Int16Array(ch.length);
    for (let i = 0; i < ch.length; i++) {
      const s = Math.max(-1, Math.min(1, ch[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    this.buf.push(out); this.n += out.length;
    if (this.n >= this.need) {
      const all = new Int16Array(this.n); let o = 0;
      for (const b of this.buf) { all.set(b, o); o += b.length; }
      this.port.postMessage(all.buffer, [all.buffer]);
      this.buf = []; this.n = 0;
    }
    return true;
  }
}
registerProcessor('pcm', PCM);`

export type AiPhase = 'preparing' | 'waiting' | 'listening' | 'thinking' | 'done' | 'error'

export const AI_PHASE_LABEL: Record<AiPhase, string> = {
  preparing: '준비 중',
  waiting: '말씀해 주세요',
  listening: '듣고 있습니다',
  thinking: '정리하는 중',
  done: '면접이 끝났습니다',
  error: '연결 실패',
}

function aiWsUrl(path: string): string {
  /* `/ai/*` 는 Caddy 가 거짓말 탐지 서비스로 넘긴다. `wsUrl` 이 붙이는
     `/api/v1` 접두어를 쓰면 안 되므로 여기서 직접 만든다. */
  const u = new URL(wsUrl('/'))
  u.pathname = path
  u.search = ''
  return u.toString()
}

export function useAiInterview(token: string | null) {
  const [phase, setPhase] = useState<AiPhase>('preparing')
  const [question, setQuestion] = useState<string | null>(null)
  const [seq, setSeq] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const timerRef = useRef<number | null>(null)
  const socketsRef = useRef<WebSocket[]>([])
  const aliveRef = useRef(true)

  const cleanup = useCallback(() => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current)
    timerRef.current = null
    socketsRef.current.forEach((ws) => {
      try {
        ws.close()
      } catch {
        /* 이미 닫힌 소켓 */
      }
    })
    socketsRef.current = []
    void ctxRef.current?.close().catch(() => {})
    ctxRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
  }, [])

  useEffect(() => {
    if (!token) return
    aliveRef.current = true

    ;(async () => {
      let stream: MediaStream
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
          audio: true,
        })
      } catch {
        if (!aliveRef.current) return
        setError('카메라·마이크를 사용할 수 없습니다. 권한을 허용해 주세요')
        setPhase('error')
        return
      }
      if (!aliveRef.current) {
        stream.getTracks().forEach((t) => t.stop())
        return
      }
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        videoRef.current.muted = true
        void videoRef.current.play().catch(() => {})
      }

      /* ① 아르 — 질문을 준다 */
      const askWs = new WebSocket(aiWsUrl(`/ai/ws/interview/${token}`))
      askWs.binaryType = 'arraybuffer'
      askWs.onmessage = (e) => {
        const m = JSON.parse(e.data)
        switch (m.type) {
          case 'question':
            setQuestion(m.text)
            setSeq(m.seq)
            setPhase('waiting')
            break
          case 'listening':
            setPhase('listening')
            break
          case 'processing':
            setPhase('thinking')
            break
          case 'done':
            setPhase('done')
            setQuestion(null)
            break
          case 'error':
            setError(m.message ?? '면접을 진행하지 못했습니다')
            setPhase('error')
            break
        }
      }
      askWs.onerror = () => {
        if (!aliveRef.current) return
        setError('서버에 연결하지 못했습니다')
        setPhase('error')
      }

      /* ② 판정 — 받는 즉시 ③ 으로 넘긴다. **화면에는 두지 않는다.** */
      const liveWs = new WebSocket(aiWsUrl('/ai/ws/live'))
      liveWs.binaryType = 'arraybuffer'

      /* ③ 담당자에게 나르는 통로 (지원자 자리라 입장권이 없다) */
      const relayWs = new WebSocket(wsUrl(`/ws/interview/${token}/rtc`))
      liveWs.onmessage = (e) => {
        const m = JSON.parse(e.data)
        if (m.type !== 'live') return
        if (relayWs.readyState === WebSocket.OPEN) {
          relayWs.send(JSON.stringify({ ...m, type: 'verdict' }))
        }
      }

      socketsRef.current = [askWs, liveWs, relayWs]

      const send = (ws: WebSocket, kind: number, payload: ArrayBuffer) => {
        if (ws.readyState !== WebSocket.OPEN) return
        const packet = new Uint8Array(1 + payload.byteLength)
        packet[0] = kind
        packet.set(new Uint8Array(payload), 1)
        ws.send(packet)
      }
      /* 같은 조각을 **둘 다**에게 보낸다 — 아르는 말이 끝난 것을 알아야 하고,
         판정기는 얼굴과 목소리를 봐야 한다. */
      const fanout = (kind: number, payload: ArrayBuffer) => {
        send(askWs, kind, payload)
        send(liveWs, kind, payload)
      }

      // 오디오
      const ctx = new AudioContext({ sampleRate: SR })
      ctxRef.current = ctx
      const blobUrl = URL.createObjectURL(new Blob([WORKLET], { type: 'text/javascript' }))
      await ctx.audioWorklet.addModule(blobUrl)
      URL.revokeObjectURL(blobUrl)
      if (!aliveRef.current) return
      const node = new AudioWorkletNode(ctx, 'pcm')
      node.port.onmessage = (e) => fanout(KIND_AUDIO, e.data as ArrayBuffer)
      ctx.createMediaStreamSource(stream).connect(node)
      /* 워크릿에 목적지가 없으면 브라우저가 그래프를 안 돌린다. 소리는 내지 않는다. */
      const mute = ctx.createGain()
      mute.gain.value = 0
      node.connect(mute).connect(ctx.destination)

      // 영상
      const canvas = document.createElement('canvas')
      canvas.width = 480
      canvas.height = 360
      const g = canvas.getContext('2d')
      timerRef.current = window.setInterval(() => {
        const v = videoRef.current
        if (!v?.videoWidth || !g) return
        g.drawImage(v, 0, 0, canvas.width, canvas.height)
        canvas.toBlob(
          (b) => void b?.arrayBuffer().then((a) => fanout(KIND_VIDEO, a)),
          'image/jpeg',
          0.6,
        )
      }, FRAME_MS)
    })()

    return () => {
      aliveRef.current = false
      cleanup()
    }
  }, [token, cleanup])

  const leave = useCallback(() => {
    cleanup()
    setPhase('done')
  }, [cleanup])

  return { phase, question, seq, error, videoRef, leave }
}
