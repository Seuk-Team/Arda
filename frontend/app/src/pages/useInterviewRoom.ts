import { useCallback, useEffect, useRef, useState } from 'react'
import { api, wsUrl } from '../api/client'

/* 실시간 면접 (docs/02_tasks/실시간-면접-시그널링.md) — 양쪽이 이 훅 하나를 쓴다.

   **서버는 신호만 나른다.** 영상·음성은 두 브라우저가 직접 주고받고(WebRTC),
   서버는 연결을 맺는 쪽지(SDP·ICE)만 상대에게 넘긴다.

   두 자리가 하는 일이 다르다.

   | | 채용자 | 지원자 |
   |---|---|---|
   | 붙는 법 | 입장권(60초·1회용)을 REST 로 먼저 받는다 | 메일 링크의 토큰만 |
   | offer | **만든다** | 절대 만들지 않는다 — 받아서 answer 만 낸다 |

   거는 쪽을 하나로 고정한 이유는 glare 다 — 양쪽이 동시에 걸면 협상이 꼬인다.
   그리고 **누가 걸지는 서버가 정해 준다**(`hello.should_offer`).

   페이지에서 떼어 낸 이유는 정리가 까다로워서다. 카메라 트랙과 PeerConnection 과
   WebSocket 이 각자 따로 살아서, 하나라도 안 끊으면 면접이 끝난 뒤에도 카메라
   표시가 남거나 서버 방이 안 비워진다. */

export type RoomPhase =
  /* 입장권을 받고 카메라를 켜는 중 */
  | 'preparing'
  /* 붙었지만 상대가 아직 안 들어옴 */
  | 'waiting'
  /* 서로 쪽지를 주고받는 중 */
  | 'connecting'
  /* 영상·음성이 오간다 */
  | 'live'
  /* 상대가 나갔다 — 다시 들어오면 저절로 이어진다 */
  | 'peer-left'
  | 'error'

export type RoomRole = 'recruiter' | 'applicant'

type Signal = {
  type: string
  sdp?: string
  candidate?: RTCIceCandidateInit
  role?: string
  peer_present?: boolean
  should_offer?: boolean
  ice_servers?: RTCIceServer[]
  code?: string
  message?: string
}

/* 서버가 주는 error.code 중 화면이 말을 바꿔야 하는 것들. 모르는 코드는
   서버 message 를 그대로 보여준다 — 서버가 늘려도 화면이 안 깨지게. */
const FATAL_CODES = new Set(['session_closed', 'replaced'])

const PING_MS = 25_000

export type RoomOptions =
  | { role: 'recruiter'; sessionId: number | null }
  | { role: 'applicant'; token: string | null }

export function useInterviewRoom(opts: RoomOptions) {
  const role = opts.role
  const sessionId = opts.role === 'recruiter' ? opts.sessionId : null
  const token = opts.role === 'applicant' ? opts.token : null

  const [phase, setPhase] = useState<RoomPhase>('preparing')
  const [error, setError] = useState<string | null>(null)
  /* 마이크를 껐는지. 영상은 끄지 않는다 — 얼굴이 안 보이면 면접이 아니다. */
  const [muted, setMuted] = useState(false)
  /* 상대에게서 받은 것. **채용자 쪽에서 실시간 분석에 넘긴다**(`useLiveAnalysis`) —
     그래서 ref 만이 아니라 상태로도 들고 있다. 상대가 나가면 `null` 이 되어
     분석도 같이 멈춘다. */
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null)

  const localRef = useRef<HTMLVideoElement | null>(null)
  const remoteRef = useRef<HTMLVideoElement | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const pcRef = useRef<RTCPeerConnection | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const iceServersRef = useRef<RTCIceServer[]>([])
  const pingRef = useRef<number | null>(null)
  /* 언마운트 뒤에 도착한 응답이 다시 카메라를 켜지 않게 한다. */
  const aliveRef = useRef(true)

  const send = useCallback((msg: Signal) => {
    const ws = wsRef.current
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg))
  }, [])

  const teardownPeer = useCallback(() => {
    pcRef.current?.close()
    pcRef.current = null
    if (remoteRef.current) remoteRef.current.srcObject = null
    setRemoteStream(null)
  }, [])

  const cleanup = useCallback(() => {
    if (pingRef.current !== null) {
      window.clearInterval(pingRef.current)
      pingRef.current = null
    }
    teardownPeer()
    /* `bye` 를 먼저 보내고 닫는다 — 상대가 "끊겼나?" 하고 기다리지 않게. */
    send({ type: 'bye' })
    wsRef.current?.close()
    wsRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (localRef.current) localRef.current.srcObject = null
  }, [send, teardownPeer])

  /* PeerConnection 은 **매번 새로 만든다.** 상대가 나갔다 들어올 때 헌 것을
     재활용하면 ICE 상태가 남아 안 붙는다. */
  const newPeer = useCallback(() => {
    teardownPeer()
    const pc = new RTCPeerConnection({ iceServers: iceServersRef.current })
    pcRef.current = pc

    streamRef.current?.getTracks().forEach((t) => {
      if (streamRef.current) pc.addTrack(t, streamRef.current)
    })
    /* **담당자 PC 에 카메라·마이크가 없어도 받기는 한다** (2026-09-11). 제안(offer)은
       담당자가 만드는데, 보낼 트랙이 없으면 제안에 영상·소리 자리가 아예 안 생겨
       지원자 영상도 못 받는다. 받기 전용 자리를 따로 연다. 판정은 **받은** 영상으로
       하므로(`useLiveAnalysis`) 담당자 카메라는 필요 없다. */
    if (role === 'recruiter') {
      if (!streamRef.current?.getVideoTracks().length) {
        pc.addTransceiver('video', { direction: 'recvonly' })
      }
      if (!streamRef.current?.getAudioTracks().length) {
        pc.addTransceiver('audio', { direction: 'recvonly' })
      }
    }

    pc.onicecandidate = (e) => {
      if (e.candidate) send({ type: 'ice', candidate: e.candidate.toJSON() })
    }
    pc.ontrack = (e) => {
      if (remoteRef.current) remoteRef.current.srcObject = e.streams[0]
      setRemoteStream(e.streams[0] ?? null)
      setPhase('live')
    }
    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'failed') {
        /* 여기까지 왔는데 실패면 대개 **망 문제**다 — 서로 다른 망이면
           TURN 없이는 못 붙는다. 사유를 지어내지 않고 사실만 적는다. */
        setError('연결하지 못했습니다. 서로 다른 망이면 붙지 않을 수 있습니다')
        setPhase('error')
      }
    }
    return pc
  }, [role, send, teardownPeer])

  const makeOffer = useCallback(async () => {
    setPhase('connecting')
    const pc = newPeer()
    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    send({ type: 'offer', sdp: offer.sdp })
  }, [newPeer, send])

  useEffect(() => {
    if (role === 'recruiter' && sessionId === null) return
    if (role === 'applicant' && !token) return
    aliveRef.current = true

    ;(async () => {
      let wsToken = token ?? ''
      let query = ''

      if (role === 'recruiter') {
        try {
          /* **입장권은 접속 직전에 받는다.** 60초·1회용이라 미리 받아 두면 만료된다. */
          const t = await api.post<{ ticket: string; token: string; ice_servers: RTCIceServer[] }>(
            `/interview-sessions/${sessionId}/rtc-ticket`,
          )
          if (!aliveRef.current) return
          wsToken = t.token
          query = `?ticket=${encodeURIComponent(t.ticket)}`
          iceServersRef.current = t.ice_servers ?? []
        } catch {
          if (!aliveRef.current) return
          setError('면접방에 들어갈 수 없습니다. 세션을 확인해 주세요')
          setPhase('error')
          return
        }
      }

      /* 지원자는 카메라·마이크가 있어야 한다(영상을 보내는 쪽). **담당자는 없어도
         된다** — 판정은 지원자에게서 받은 영상으로 하므로 담당자 카메라는 보여 주기일
         뿐이다(2026-09-11). 카메라가 안 되면 소리만, 그것도 안 되면 받기만 한다. */
      let stream: MediaStream | null = null
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
        })
      } catch {
        if (role === 'recruiter') {
          try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true })
          } catch {
            stream = null
          }
        }
      }
      if (!aliveRef.current) {
        stream?.getTracks().forEach((t) => t.stop())
        return
      }
      if (stream === null && role !== 'recruiter') {
        setError('카메라·마이크를 사용할 수 없습니다. 권한을 허용해 주세요')
        setPhase('error')
        return
      }
      streamRef.current = stream
      if (stream && localRef.current) {
        localRef.current.srcObject = stream
        localRef.current.muted = true
        void localRef.current.play().catch(() => {})
      }

      const ws = new WebSocket(`${wsUrl(`/ws/interview/${wsToken}/rtc`)}${query}`)
      wsRef.current = ws

      ws.onmessage = (ev) => {
        let msg: Signal
        try {
          msg = JSON.parse(ev.data)
        } catch {
          return
        }
        void handle(msg)
      }
      ws.onerror = () => {
        if (!aliveRef.current) return
        setError('서버에 연결하지 못했습니다')
        setPhase('error')
      }

      pingRef.current = window.setInterval(() => send({ type: 'ping' }), PING_MS)

      async function handle(msg: Signal) {
        const pc = pcRef.current
        switch (msg.type) {
          case 'hello':
            if (msg.ice_servers?.length) iceServersRef.current = msg.ice_servers
            /* 거는 쪽을 **서버가 정해 준다** — 양쪽이 동시에 걸면 협상이 꼬인다.
               지원자에게는 이 값이 오지 않으므로 그냥 기다린다. */
            if (msg.should_offer) await makeOffer()
            else setPhase(msg.peer_present ? 'connecting' : 'waiting')
            break
          case 'peer-join':
            /* **채용자만 건다.** 지원자는 상대가 들어와도 offer 를 만들지 않는다. */
            if (role === 'recruiter') await makeOffer()
            else setPhase('connecting')
            break
          case 'peer-leave':
            teardownPeer()
            setPhase('peer-left')
            break
          case 'offer': {
            /* 지원자 쪽 경로다. 받은 offer 로 새 연결을 만들고 answer 를 낸다. */
            if (!msg.sdp) break
            const conn = newPeer()
            await conn.setRemoteDescription({ type: 'offer', sdp: msg.sdp })
            const answer = await conn.createAnswer()
            await conn.setLocalDescription(answer)
            send({ type: 'answer', sdp: answer.sdp })
            break
          }
          case 'answer':
            if (pc && msg.sdp) {
              await pc.setRemoteDescription({ type: 'answer', sdp: msg.sdp })
            }
            break
          case 'ice':
            /* 아직 offer/answer 가 안 끝났는데 후보가 먼저 오면 던진다.
               치명적이지 않다 — 다음 후보로 붙는다. */
            if (pc && msg.candidate) await pc.addIceCandidate(msg.candidate).catch(() => {})
            break
          case 'error':
            if (msg.code && FATAL_CODES.has(msg.code)) {
              setError(msg.message ?? '면접방에 들어갈 수 없습니다')
              setPhase('error')
            }
            /* `no_peer` 는 오류가 아니다 — 상대가 아직 안 들어온 것뿐이다. */
            break
        }
      }
    })()

    return () => {
      aliveRef.current = false
      cleanup()
    }
  }, [role, sessionId, token, cleanup, makeOffer, newPeer, send, teardownPeer])

  const toggleMute = useCallback(() => {
    const tracks = streamRef.current?.getAudioTracks() ?? []
    const next = !muted
    tracks.forEach((t) => { t.enabled = !next })
    setMuted(next)
  }, [muted])

  const leave = useCallback(() => {
    cleanup()
    setPhase('peer-left')
  }, [cleanup])

  return { phase, error, muted, toggleMute, leave, localRef, remoteRef, remoteStream }
}

export const PHASE_LABEL: Record<RoomPhase, string> = {
  preparing: '준비 중',
  waiting: '상대를 기다리는 중',
  connecting: '연결하는 중',
  live: '연결됨',
  'peer-left': '상대가 나갔습니다',
  error: '연결 실패',
}

/* 자리마다 말이 다르다. "상대"라고만 쓰면 누가 안 왔는지 알 수 없다. */
export function phaseLabel(role: RoomRole, phase: RoomPhase): string {
  if (phase === 'waiting') {
    return role === 'recruiter' ? '지원자를 기다리는 중' : '면접관을 기다리는 중'
  }
  if (phase === 'peer-left') {
    return role === 'recruiter' ? '지원자가 나갔습니다' : '면접관이 나갔습니다'
  }
  return PHASE_LABEL[phase]
}
