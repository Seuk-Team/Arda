import { wsUrl } from '../api/client'

/* 거짓말 탐지 워커로 미디어를 보내는 두 화면이 함께 쓰는 규격.

   원본은 `ai/lie-detection/PROTOCOL.md` 다 — 여기 값을 바꾸면 서버가 못
   알아듣는다. 앱은 `mobile/lib/data/mic_service.dart` 가 같은 값을 들고 있다.

   쓰는 곳이 둘이라 떼어 냈다.

   | | 보내는 것 | 판정을 받는 곳 |
   |---|---|---|
   | `useAiInterview` (AI 면접) | 지원자 기기 → `/ai/ws/interview/{token}` | **안 받는다** (워커 → 백엔드 → 담당자) |
   | `useLiveAnalysis` (사람 면접) | 채용자 기기 → `/ai/ws/live` | 채용자 화면 |

   두 번째가 지원자 기기를 안 지나가는 것이 중요하다 — 채용자가 **자기가 받은
   영상**을 분석에 넘기므로 판정이 지원자 쪽으로 갈 길 자체가 없다(ADR-0029). */

/** 서버가 기대하는 표본율 */
export const SR = 16000

/** 오디오 한 조각. 서버가 이 단위로 말/침묵을 가른다 */
export const AUDIO_MS = 50

/** 영상 5장/초. 더 자주 보내도 서버가 3장에 1장만 본다 */
export const FRAME_MS = 200

export const KIND_AUDIO = 0x01
export const KIND_VIDEO = 0x02

/* 오디오를 Int16 로 바꿔 50ms 씩 모아 보내는 워크릿. 파일로 두면 배포에 하나가
   더 붙으므로 문자열로 만들어 쓴다 (demo.html 과 같은 방식). */
export const WORKLET = `
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

/** `/ai/*` 는 Caddy 가 거짓말 탐지 서비스로 넘긴다. `wsUrl` 이 붙이는
    `/api/v1` 접두어를 쓰면 안 되므로 여기서 직접 만든다. */
export function aiWsUrl(path: string): string {
  const u = new URL(wsUrl('/'))
  u.pathname = path
  u.search = ''
  return u.toString()
}

/** 첫 바이트가 종류, 나머지가 알맹이 */
export function sendMedia(ws: WebSocket, kind: number, payload: ArrayBuffer): void {
  if (ws.readyState !== WebSocket.OPEN) return
  const packet = new Uint8Array(1 + payload.byteLength)
  packet[0] = kind
  packet.set(new Uint8Array(payload), 1)
  ws.send(packet)
}
