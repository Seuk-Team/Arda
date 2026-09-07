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
const AUDIO_CANDIDATES: Candidate[] = [
  { mime: 'audio/webm;codecs=opus', ext: 'webm', type: 'audio/webm' },
  { mime: 'audio/webm', ext: 'webm', type: 'audio/webm' },
  { mime: 'audio/mp4', ext: 'm4a', type: 'audio/mp4' },
]

/* 영상은 **음성이 같은 파일에 들어간다.** 그래서 올리는 경로가 하나로 끝나고,
   서버는 그 파일에서 음성만 뽑아 전사한다 — 영상이 섞여 있어도 된다. */
const VIDEO_CANDIDATES: Candidate[] = [
  { mime: 'video/webm;codecs=vp8,opus', ext: 'webm', type: 'video/webm' },
  { mime: 'video/webm', ext: 'webm', type: 'video/webm' },
  { mime: 'video/mp4', ext: 'mp4', type: 'video/mp4' },
]

function pickCandidate(withVideo: boolean): Candidate | null {
  if (typeof MediaRecorder === 'undefined') return null
  for (const c of withVideo ? VIDEO_CANDIDATES : AUDIO_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(c.mime)) return c
  }
  return null
}

export type Recorded = { blob: Blob; ext: string; type: string; seconds: number }

export type RecorderState = 'idle' | 'recording' | 'recorded'

export function useAnswerRecorder(withVideo = false) {
  const [state, setState] = useState<RecorderState>('idle')
  const [seconds, setSeconds] = useState(0)
  const [recorded, setRecorded] = useState<Recorded | null>(null)
  const [error, setError] = useState<string | null>(null)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const startedAtRef = useRef(0)
  const timerRef = useRef<number | null>(null)
  /* 촬영 중 자기 모습을 보여줄 <video> 엘리먼트. 카메라가 켜졌는지 스스로
     확인할 수 있어야 한다 — 안 보이면 찍히고 있는지 모른 채로 말하게 된다. */
  const previewRef = useRef<HTMLVideoElement | null>(null)

  /* 이 브라우저에서 녹음이 가능한가. `getUserMedia` 는 https(또는 localhost)
     에서만 있으므로 여기서 같이 본다 — 없으면 텍스트로 답하면 된다. */
  const supported =
    pickCandidate(withVideo) !== null && !!navigator.mediaDevices?.getUserMedia

  const stopTracks = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (previewRef.current) previewRef.current.srcObject = null
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  /* 화면을 떠날 때 마이크를 반드시 끈다. */
  useEffect(() => stopTracks, [stopTracks])

  const start = useCallback(async () => {
    const candidate = pickCandidate(withVideo)
    if (!candidate) {
      setError('이 브라우저는 녹음을 지원하지 않습니다. 텍스트로 답변해 주세요')
      return
    }
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia(
        withVideo
          ? {
              audio: true,
              /* `ideal` 로 준다 — `exact` 면 못 맞추는 카메라에서 아예 실패한다.
                 4:3(640x480)으로 묶으면 웹캠이 16:9 화각을 잘라 내보내서
                 **사람이 화면에 다 안 들어온다.** 16:9 로 요청해 원래 화각을 쓴다. */
              video: {
                width: { ideal: 1280 },
                height: { ideal: 720 },
                facingMode: 'user',
              },
            }
          : { audio: true },
      )
      streamRef.current = stream
      chunksRef.current = []

      if (withVideo && previewRef.current) {
        previewRef.current.srcObject = stream
        /* 자기 목소리가 스피커로 되돌아오면 하울링이 난다. 미리보기는 소리를 끈다. */
        previewRef.current.muted = true
        void previewRef.current.play().catch(() => {})
      }

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
      setError(
        withVideo
          ? '카메라·마이크를 사용할 수 없습니다. 권한을 허용하거나 텍스트로 답변해 주세요'
          : '마이크를 사용할 수 없습니다. 권한을 허용하거나 텍스트로 답변해 주세요',
      )
      stopTracks()
      setState('idle')
    }
  }, [stopTracks, withVideo])

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

  return { supported, state, seconds, recorded, error, start, stop, reset, previewRef }
}

export function formatSeconds(total: number): string {
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}
