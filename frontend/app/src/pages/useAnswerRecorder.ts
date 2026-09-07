import { useCallback, useEffect, useRef, useState } from 'react'

/* 면접 답변 녹음 (설계 §5-4).

   페이지에서 떼어 낸 이유는 **정리(cleanup)가 까다로워서**다. 마이크 트랙을
   안 끊으면 브라우저 탭에 녹음 표시가 계속 남는다 — 지원자 입장에서는 면접이
   끝났는데도 마이크가 켜져 있는 것으로 보인다.

   브라우저마다 낼 수 있는 형식이 다르다. 크롬은 webm/opus, 사파리는 mp4 다.
   **서버가 받는 목록(webm·m4a·mp3·wav)과 맞는 것만 고른다.** */

type Candidate = { mime: string; ext: string; type: string }

/* `mime` 은 MediaRecorder 에 주는 값(코덱 포함), `type` 은 S3 에 보낼 값이다.
   서명에 들어간 Content-Type 과 실제 PUT 헤더가 **글자까지 같아야** 하므로,
   코덱이 붙지 않은 쪽을 따로 들고 다닌다. */
const CANDIDATES: Candidate[] = [
  { mime: 'audio/webm;codecs=opus', ext: 'webm', type: 'audio/webm' },
  { mime: 'audio/webm', ext: 'webm', type: 'audio/webm' },
  { mime: 'audio/mp4', ext: 'm4a', type: 'audio/mp4' },
]

function pickCandidate(): Candidate | null {
  if (typeof MediaRecorder === 'undefined') return null
  for (const c of CANDIDATES) {
    if (MediaRecorder.isTypeSupported(c.mime)) return c
  }
  return null
}

export type Recorded = { blob: Blob; ext: string; type: string; seconds: number }

export type RecorderState = 'idle' | 'recording' | 'recorded'

export function useAnswerRecorder() {
  const [state, setState] = useState<RecorderState>('idle')
  const [seconds, setSeconds] = useState(0)
  const [recorded, setRecorded] = useState<Recorded | null>(null)
  const [error, setError] = useState<string | null>(null)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const startedAtRef = useRef(0)
  const timerRef = useRef<number | null>(null)

  /* 이 브라우저에서 녹음이 가능한가. `getUserMedia` 는 https(또는 localhost)
     에서만 있으므로 여기서 같이 본다 — 없으면 텍스트로 답하면 된다. */
  const supported = pickCandidate() !== null && !!navigator.mediaDevices?.getUserMedia

  const stopTracks = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  /* 화면을 떠날 때 마이크를 반드시 끈다. */
  useEffect(() => stopTracks, [stopTracks])

  const start = useCallback(async () => {
    const candidate = pickCandidate()
    if (!candidate) {
      setError('이 브라우저는 녹음을 지원하지 않습니다. 텍스트로 답변해 주세요')
      return
    }
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      chunksRef.current = []

      const recorder = new MediaRecorder(stream, { mimeType: candidate.mime })
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: candidate.type })
        const elapsed = Math.max(1, Math.round((Date.now() - startedAtRef.current) / 1000))
        setRecorded({ blob, ext: candidate.ext, type: candidate.type, seconds: elapsed })
        setState('recorded')
        stopTracks()
      }

      recorderRef.current = recorder
      startedAtRef.current = Date.now()
      setSeconds(0)
      timerRef.current = window.setInterval(
        () => setSeconds(Math.round((Date.now() - startedAtRef.current) / 1000)),
        1000,
      )
      recorder.start()
      setState('recording')
    } catch {
      /* 거부·마이크 없음·정책 차단이 전부 여기로 온다. 사유를 나누지 않는 이유는
         지원자가 할 일이 같기 때문이다 — 권한을 켜거나 텍스트로 답하거나. */
      setError('마이크를 사용할 수 없습니다. 권한을 허용하거나 텍스트로 답변해 주세요')
      stopTracks()
      setState('idle')
    }
  }, [stopTracks])

  const stop = useCallback(() => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
  }, [])

  /* 다시 녹음. 이전 것은 버린다 — 서버로 보낸 적이 없으므로 남길 이유가 없다. */
  const reset = useCallback(() => {
    setRecorded(null)
    setSeconds(0)
    setError(null)
    setState('idle')
  }, [])

  return { supported, state, seconds, recorded, error, start, stop, reset }
}

export function formatSeconds(total: number): string {
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
