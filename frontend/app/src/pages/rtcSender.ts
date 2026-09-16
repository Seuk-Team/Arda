import { wsUrl } from '../api/client'

/* 지원자 쪽 WebRTC 송신기 — AI 면접 화면(`useAiInterview`)이 이미 켠 카메라·마이크
   스트림을 **담당자 화상 면접방(`InterviewRoom`)에도 흘린다** (2026-09-16).

   앱의 `interview_live_screen.dart` 가 하는 것을 웹에 옮긴 것이다: 한 화면에서
   ① 아르가 질문하고(AI 면접 소켓) ② 담당자가 얼굴을 보고(WebRTC) ③ 소리·표정이
   분석 서버로 간다. 이게 없으면 담당자는 `/interview-room/<id>` 에서 영영
   "지원자를 기다리는 중" 이다 — 지원자 링크(`/interview/<token>`)는 AI 면접만 열고
   시그널링 방에는 들어가지 않았기 때문(2026-09-16 실측).

   `useInterviewRoom` 의 지원자 경로를 훅 없이 떼어 낸 것이다. 역할은 고정이다:
   - 절대 offer 를 만들지 않는다. 담당자가 걸어오면 answer 만 낸다 (glare 방지 —
     서버 `hello.should_offer` 규칙과 같다).
   - 담당자가 아직 없으면 그냥 붙어서 기다린다. 담당자가 들어오면 서버가 담당자에게
     `peer-join` 을 주고 담당자가 offer 를 만든다.
   - 스트림의 트랙을 **멈추지 않는다** — 카메라는 `useAiInterview` 의 것이라 거기서 끈다.

   판정은 이 경로로 오지 않는다(ADR-0029). 서버는 지원자 소켓에 `verdict` 를 중계하지
   않고, 여기서도 모르는 타입은 버린다. */

export type RtcSenderState =
  | 'off'
  /* 시그널링 방에 붙었고 담당자를 기다린다 */
  | 'waiting'
  /* 담당자가 들어와 offer/answer 를 주고받는 중 */
  | 'connecting'
  /* 담당자에게 영상이 간다 */
  | 'live'
  | 'peer-left'
  | 'error'

type Signal = {
  type: string
  sdp?: string
  candidate?: RTCIceCandidateInit
  peer_present?: boolean
  ice_servers?: RTCIceServer[]
  code?: string
  message?: string
}

const PING_MS = 25_000
const FATAL_CODES = new Set(['session_closed', 'replaced'])

export type RtcSender = { stop: () => void }

export function startRtcSender(
  token: string,
  stream: MediaStream,
  onState: (s: RtcSenderState, message?: string) => void,
): RtcSender {
  let ws: WebSocket | null = null
  let pc: RTCPeerConnection | null = null
  let iceServers: RTCIceServer[] = []
  let ping: number | null = null
  let stopped = false

  const send = (msg: Signal) => {
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg))
  }

  const teardownPeer = () => {
    pc?.close()
    pc = null
  }

  /* PeerConnection 은 offer 마다 새로 만든다 — 담당자가 나갔다 들어오면 헌 것을
     재활용해도 ICE 상태가 남아 안 붙는다(`useInterviewRoom` 과 같은 이유). */
  const newPeer = () => {
    teardownPeer()
    const conn = new RTCPeerConnection({ iceServers })
    pc = conn
    stream.getTracks().forEach((t) => conn.addTrack(t, stream))
    conn.onicecandidate = (e) => {
      if (e.candidate) send({ type: 'ice', candidate: e.candidate.toJSON() })
    }
    conn.onconnectionstatechange = () => {
      if (stopped) return
      if (conn.connectionState === 'connected') onState('live')
      else if (conn.connectionState === 'failed') {
        onState('error', '면접관과 연결하지 못했습니다. 서로 다른 망이면 붙지 않을 수 있습니다')
      }
    }
    return conn
  }

  const handle = async (msg: Signal) => {
    switch (msg.type) {
      case 'hello':
        if (msg.ice_servers?.length) iceServers = msg.ice_servers
        onState(msg.peer_present ? 'connecting' : 'waiting')
        break
      case 'peer-join':
        onState('connecting')
        break
      case 'peer-leave':
        teardownPeer()
        onState('peer-left')
        break
      case 'offer': {
        if (!msg.sdp) break
        const conn = newPeer()
        await conn.setRemoteDescription({ type: 'offer', sdp: msg.sdp })
        const answer = await conn.createAnswer()
        await conn.setLocalDescription(answer)
        send({ type: 'answer', sdp: answer.sdp })
        break
      }
      case 'ice':
        if (pc && msg.candidate) await pc.addIceCandidate(msg.candidate).catch(() => {})
        break
      case 'error':
        /* `no_peer` 는 오류가 아니다. 방이 닫혔거나 다른 곳에서 접속해 밀려난 것만 알린다. */
        if (msg.code && FATAL_CODES.has(msg.code)) onState('error', msg.message)
        break
    }
  }

  ws = new WebSocket(wsUrl(`/ws/interview/${token}/rtc`))
  ws.onmessage = (ev) => {
    let msg: Signal
    try {
      msg = JSON.parse(ev.data)
    } catch {
      return
    }
    void handle(msg).catch(() => {
      /* SDP 협상 중 예외 — 다음 offer 에서 다시 시도된다 */
    })
  }
  ws.onerror = () => {
    if (!stopped) onState('error', '면접관 연결 서버에 붙지 못했습니다')
  }
  ws.onclose = () => {
    if (!stopped) onState('off')
  }
  ping = window.setInterval(() => send({ type: 'ping' }), PING_MS)

  return {
    stop: () => {
      stopped = true
      if (ping !== null) window.clearInterval(ping)
      ping = null
      teardownPeer()
      /* `bye` 를 먼저 보내고 닫는다 — 담당자 화면이 "끊겼나?" 하고 기다리지 않게. */
      send({ type: 'bye' })
      ws?.close()
      ws = null
    },
  }
}
