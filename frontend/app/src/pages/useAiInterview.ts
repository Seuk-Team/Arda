import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api/client'
import { FRAME_MS, KIND_AUDIO, KIND_VIDEO, SR, WORKLET, aiWsUrl, sendMedia } from './aiSocket'
import { startRtcSender, type RtcSender, type RtcSenderState } from './rtcSender'

/* AI 면접 — 아르가 묻고, 얼굴을 실시간으로 본다.

   **분석 소켓은 하나뿐이다.** 카메라·마이크를 `/ai/ws/interview/{token}` 한 곳에만
   보내고 질문을 받는다.

   ## 담당자에게도 얼굴을 보낸다 (2026-09-16 · 앱 `interview_live_screen.dart` 와 동일)

   같은 카메라 스트림을 시그널링 방(`/ws/interview/{token}/rtc`)에 **지원자 자리**로
   붙여 WebRTC 로 담당자 `InterviewRoom` 에 흘린다(`rtcSender.ts`). 담당자가 방에
   없으면 그냥 기다리고, 들어오면 담당자가 offer 를 만들어 붙는다. 이게 없으면
   담당자 화상 면접방은 영영 "지원자를 기다리는 중" 이다. 담당자 쪽은 받은 영상을
   자기 분석(`useLiveAnalysis`)에 넘기고, 이 워커 소켓은 그대로 본인 확인·표정·전사를
   맡는다 — 두 경로가 겹치지만 심사 시연은 동시 면접 1건이라 감당된다.

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
  /* 서버가 같은 질문에 다시 답하라고 한 이유(`retry` 의 message). 질문이 바뀌면 지운다. */
  const [note, setNote] = useState<string | null>(null)
  /* 담당자 화상 연결 상태. 화면은 안 그려도 된다 — 판정이 아니라 연결 여부일 뿐이고,
     문제 진단(담당자가 방에 들어왔는데 영상이 안 갈 때) 에 쓴다. */
  const [rtcState, setRtcState] = useState<RtcSenderState>('off')

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const timerRef = useRef<number | null>(null)
  const socketsRef = useRef<WebSocket[]>([])
  const rtcRef = useRef<RtcSender | null>(null)
  const aliveRef = useRef(true)

  const cleanup = useCallback(() => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current)
    timerRef.current = null
    /* 트랙을 멈추기 **전에** 담당자 쪽에 bye 를 보낸다 */
    rtcRef.current?.stop()
    rtcRef.current = null
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

      /* ⓞ 담당자 화상 면접방 — 같은 스트림을 WebRTC 로. 실패해도 면접은 계속된다
         (담당자가 얼굴을 못 보는 것뿐이고, 판정·질문은 아래 워커 소켓이 맡는다). */
      try {
        rtcRef.current = startRtcSender(token, stream, (s) => {
          if (aliveRef.current) setRtcState(s)
        })
      } catch {
        setRtcState('error')
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
            setNote(null)
            setPhase('waiting')
            break
          case 'listening':
            setPhase('listening')
            break
          case 'processing':
            setPhase('thinking')
            break
          case 'retry':
            /* 받아쓴 글이 비었다 — 같은 질문을 그대로 두고 다시 답하게 한다 (PROTOCOL.md) */
            setNote(m.message ?? '말이 들리지 않았어요. 다시 답변해 주세요')
            setPhase('waiting')
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

  /* [답변 완료] (2026-09-15). **답변은 이 버튼으로만 끝난다** — 침묵으로도,
     "이상입니다" 로도 넘어가지 않는다(PROTOCOL.md). 서버는 여기까지의 소리를 받아써서
     글이 있으면 저장하고 다음 `question` 을, 비었으면 `retry` 를 보낸다. 그 사이는
     `processing` 이라 화면이 "정리하는 중" 을 보인다. 앱(interview_live_screen.dart)
     의 `sendEnd` 와 같은 메시지다. */
  const endAnswer = useCallback(() => {
    const ws = socketsRef.current[0]
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    setNote(null)
    setPhase('thinking')
    ws.send(JSON.stringify({ type: 'end' }))
  }, [])

  return { phase, question, seq, error, note, rtcState, videoRef, leave, endAnswer }
}
