import { useCallback, useEffect, useRef, useState } from 'react'
import { api, wsUrl } from '../api/client'

/* 실시간 면접 — 채용자 쪽 (docs/02_tasks/실시간-면접-시그널링.md).

   **서버는 신호만 나른다.** 영상·음성은 두 브라우저가 직접 주고받는다(WebRTC).
   여기서 하는 일은 셋뿐이다 — 카메라를 켜고, 서버를 통해 상대와 쪽지를 주고받아
   연결을 맺고, 붙은 뒤에는 상태만 지켜본다.

   페이지에서 떼어 낸 이유는 **정리가 까다로워서**다. 카메라 트랙과
   PeerConnection 과 WebSocket 이 각자 따로 살아서, 하나라도 안 끊으면
   면접이 끝난 뒤에도 카메라 표시가 남거나 서버 방이 안 비워진다. */

export type RoomPhase =
  /* 입장권을 받고 카메라를 켜는 중 */
  | 'preparing'
  /* 붙었지만 지원자가 아직 안 들어옴 */
  | 'waiting'
  /* 서로 쪽지를 주고받는 중 */
  | 'connecting'
  /* 영상·음성이 오간다 */
  | 'live'
  /* 지원자가 나갔다 — 다시 들어오면 저절로 이어진다 */
  | 'peer-left'
  | 'error'

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

export function useInterviewRoom(sessionId: number | null) {
  const [phase, setPhase] = useState<RoomPhase>('preparing')
  const [error, setError] = useState<string | null>(null)
  /* 마이크를 껐는지. 영상은 끄지 않는다 — 얼굴이 안 보이면 면접이 아니다. */
  const [muted, setMuted] = useState(false)

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

  /* PeerConnection 은 **매번 새로 만든다.** 지원자가 나갔다 들어올 때 헌 것을
     재활용하면 ICE 상태가 남아 안 붙는다. */
  const newPeer = useCallback(() => {
    teardownPeer()
    const pc = new RTCPeerConnection({ iceServers: iceServersRef.current })
    pcRef.current = pc

    streamRef.current?.getTracks().forEach((t) => {
      if (streamRef.current) pc.addTrack(t, streamRef.current)
    })

    pc.onicecandidate = (e) => {
      if (e.candidate) send({ type: 'ice', candidate: e.candidate.toJSON() })
    }
    pc.ontrack = (e) => {
      if (remoteRef.current) remoteRef.current.srcObject = e.streams[0]
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
  }, [send, teardownPeer])

  const makeOffer = useCallback(async () => {
    setPhase('connecting')
    const pc = newPeer()
    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    send({ type: 'offer', sdp: offer.sdp })
  }, [newPeer, send])

  useEffect(() => {
    if (sessionId === null) return
    aliveRef.current = true

    ;(async () => {
      let ticket: { ticket: string; token: string; ice_servers: RTCIceServer[] }
      try {
        /* **입장권은 접속 직전에 받는다.** 60초·1회용이라 미리 받아 두면 만료된다. */
        ticket = await api.post(`/interview-sessions/${sessionId}/rtc-ticket`)
      } catch {
        if (!aliveRef.current) return
        setError('면접방에 들어갈 수 없습니다. 세션을 확인해 주세요')
        setPhase('error')
        return
      }
      if (!aliveRef.current) return
      iceServersRef.current = ticket.ice_servers ?? []

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
          video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
        })
        if (!aliveRef.current) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        if (localRef.current) {
          localRef.current.srcObject = stream
          localRef.current.muted = true
          void localRef.current.play().catch(() => {})
        }
      } catch {
        if (!aliveRef.current) return
        setError('카메라·마이크를 사용할 수 없습니다. 권한을 허용해 주세요')
        setPhase('error')
        return
      }

      const ws = new WebSocket(
        `${wsUrl(`/ws/interview/${ticket.token}/rtc`)}?ticket=${encodeURIComponent(ticket.ticket)}`,
      )
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
            /* 거는 쪽을 **서버가 정해 준다** — 양쪽이 동시에 걸면 협상이 꼬인다. */
            if (msg.should_offer) await makeOffer()
            else setPhase('waiting')
            break
          case 'peer-join':
            await makeOffer()
            break
          case 'peer-leave':
            teardownPeer()
            setPhase('peer-left')
            break
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
            /* `no_peer` 는 오류가 아니다 — 지원자가 아직 안 들어온 것뿐이다. */
            break
        }
      }
    })()

    return () => {
      aliveRef.current = false
      cleanup()
    }
  }, [sessionId, cleanup, makeOffer, send, teardownPeer])

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

  return { phase, error, muted, toggleMute, leave, localRef, remoteRef }
}

export const PHASE_LABEL: Record<RoomPhase, string> = {
  preparing: '준비 중',
  waiting: '지원자를 기다리는 중',
  connecting: '연결하는 중',
  live: '연결됨',
  'peer-left': '지원자가 나갔습니다',
  error: '연결 실패',
}
