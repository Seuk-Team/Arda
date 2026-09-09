import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api/client'
import { FRAME_MS, KIND_AUDIO, KIND_VIDEO, SR, WORKLET, aiWsUrl, sendMedia } from './aiSocket'

/* AI 면접 — 아르가 묻고, 얼굴을 실시간으로 본다.

   **소켓은 하나뿐이다.** 카메라·마이크를 `/ai/ws/interview/{token}` 한 곳에만
   보내고 질문을 받는다.

   ## 판정은 이 기기를 지나가지 않는다

   처음에는 지원자 폰이 `/ai/ws/live` 로 판정을 받아 담당자에게 중계했다.
   화면에 안 그리면 된다고 봤는데, **개발자 도구를 열면 보인다** —
   ADR-0029 의 "지원자에게 판정을 보여 주지 않는다"가 거기서 깨진다
   (2026-09-08 cloverky 지적).

   지금은 **워커 → 백엔드 → 담당자** 다.

       거짓말 탐지 워커
         └─ POST /api/v1/internal/interview/{token}/verdict   (서비스 토큰)
              └─ 백엔드가 시그널링 방의 **채용자에게만** 민다

   그래서 이 훅에는 판정을 받는 코드가 아예 없다. 화면이 그리려 해도 그럴
   값이 오지 않는다 — 안 그리기로 한 약속을 코드가 지킬 수 없게가 아니라
   **지킬 수밖에 없게** 만든 것이다. */

export type AiPhase = 'preparing' | 'waiting' | 'listening' | 'thinking' | 'done' | 'error'

export const AI_PHASE_LABEL: Record<AiPhase, string> = {
  preparing: '준비 중',
  waiting: '말씀해 주세요',
  listening: '듣고 있습니다',
  thinking: '정리하는 중',
  done: '면접이 끝났습니다',
  error: '연결 실패',
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
      /* **소켓에 붙기 전에 동의·시작을 REST 로 끝낸다** (PROTOCOL.md).
         안 하면 세션이 `pending` 이라 소켓이 "진행 중인 면접이 아닙니다" 로
         끊는다 — 화면에서는 카메라만 켜지고 질문이 영영 안 온다.

         둘 다 **이미 했으면 그냥 지나간다**: 동의는 두 번 해도 200 이고,
         시작은 이미 `in_progress` 면 409 다. 그래서 응답을 보고 막지 않는다
         — 새로고침으로 다시 들어온 경우가 정상 경로다. */
      try {
        await api.post(`/public/interview/${token}/consent`, { agreed: true }, { auth: false })
      } catch {
        /* 이미 동의했으면 여기로 온다. 진행에 지장 없다. */
      }
      try {
        await api.post(`/public/interview/${token}/start`, {}, { auth: false })
      } catch (err) {
        /* 409 는 "이미 시작됨" 이라 정상이다. 그 밖(질문 없음 422·만료 410)은
           소켓을 열어 봐야 같은 이유로 막히므로 여기서 멈춘다. */
        if (err instanceof ApiError && err.status !== 409) {
          if (!aliveRef.current) return
          setError(err.message)
          setPhase('error')
          return
        }
      }
      if (!aliveRef.current) return

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

      socketsRef.current = [askWs]

      /* 아르에게만 보낸다. **판정은 지원자 기기를 지나가지 않는다** —
         워커가 백엔드로 직접 밀고, 백엔드가 담당자에게 준다 (ADR-0029). */
      const fanout = (kind: number, payload: ArrayBuffer) => sendMedia(askWs, kind, payload)

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

  /* 중도 종료. **서버에 알린다** — 안 알리면 세션이 `in_progress` 로 남아
     담당자 쪽에서 "아직 보는 중"과 "그만둔 것"이 구별되지 않는다.

     정상 종료(질문 소진)는 워커가 `finish` 를 부른다(cloverky, 2026-09-08).
     여기서 또 부르면 두 번이 되는데, 서버가 이미 `done` 이면 그대로 200 을
     주므로 해가 없다 — 그래도 화면이 부르는 것은 **중도 종료뿐**이다. */
  const leave = useCallback(() => {
    cleanup()
    setPhase('done')
    if (token) {
      void api
        .post(`/public/interview/${token}/finish`, {}, { auth: false })
        .catch(() => {
          /* 못 알려도 지원자 쪽 화면은 끝난다. 담당자 화면이 늦게 알 뿐이다. */
        })
    }
  }, [cleanup, token])

  return { phase, question, seq, error, videoRef, leave }
}
