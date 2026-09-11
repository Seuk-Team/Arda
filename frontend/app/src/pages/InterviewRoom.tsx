import { type RefObject, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { applications, interviews, postings } from '../api/endpoints'
import type { InterviewFinding, InterviewSessionDetail } from '../api/types'
import styles from './InterviewRoom.module.css'
import { useLiveAnalysis, type VoiceSignals } from './useLiveAnalysis'
import { phaseLabel, useInterviewRoom } from './useInterviewRoom'

/** 숫자 한 칸. 값이 없으면 자리만 지킨다 — `InterviewWatch` 와 같은 표기. */
function fmt(v: number | undefined): string {
  return typeof v === 'number' ? `${v.toFixed(1)}%` : '—'
}

/** 한 쪽의 확률 막대.
 *
 *  **초록·빨강을 쓰지 않는다.** 어느 쪽이 큰지는 길이로 이미 보이고, 색까지
 *  칠하면 글이 말하지 않은 판단("이 사람은 거짓이다")을 색이 말한다.
 *  앞선 쪽만 진하게 둔다. */
function _Bar({ label, pct, lead }: { label: string; pct?: number; lead: boolean }) {
  const v = typeof pct === 'number' ? Math.max(0, Math.min(100, pct)) : 0
  return (
    <div className={styles.barRow}>
      <span className={styles.barLabel}>{label}</span>
      <span className={styles.barTrack}>
        <span
          className={lead ? styles.barFillLead : styles.barFill}
          style={{ width: `${v}%` }}
        />
      </span>
      <span className={styles.barPct}>{fmt(pct)}</span>
    </div>
  )
}

/* ── 목소리 (2026-09-11) ─────────────────────────────────────────
   판정 입력 100개 중 86개가 목소리인데 판넬에는 얼굴만 있었다. 음색(MFCC 80개)은
   사람이 읽을 숫자가 아니라 빼고, 음 높이·크기·말소리 비율만 보여 준다.

   **「평소」 는 이 면접에서 잰 값의 가운데값이다.** 사람마다 목소리가 달라 절대
   기준(몇 Hz 면 높다)을 두면 목소리가 낮은 사람에게는 늘 "낮음" 이 뜬다. 같은
   사람의 앞선 값과만 비교한다. 방향 말(높음·낮음)도 색 없이 굵기로만 — 막대와
   같은 규칙이다. */

/** 평소를 말하려면 이만큼은 모여야 한다. 몇 개로 잡은 가운데값은 우연이다 */
const BASELINE_MIN = 5

const VOICE_ROWS: {
  key: keyof VoiceSignals
  label: string
  unit: string
  digits: number
  /** 평소와의 차이. 음 높이는 반음으로 잰다 — 같은 Hz 차이도 목소리 높낮이에 따라 무게가 다르다 */
  diff: (now: number, base: number) => number
  /** 이만큼 벌어지면 방향 말을 붙인다 */
  gap: number
  up: string
  down: string
}[] = [
  {
    key: 'pitch_hz',
    label: '음 높이',
    unit: 'Hz',
    digits: 0,
    diff: (n, b) => (n > 0 && b > 0 ? 12 * Math.log2(n / b) : 0),
    gap: 1.5,
    up: '높음',
    down: '낮음',
  },
  { key: 'pitch_var_st', label: '억양 폭', unit: '반음', digits: 1, diff: (n, b) => n - b, gap: 1, up: '큼', down: '작음' },
  { key: 'loud_db', label: '목소리 크기', unit: 'dB', digits: 0, diff: (n, b) => n - b, gap: 3, up: '큼', down: '작음' },
  { key: 'loud_var_db', label: '크기 흔들림', unit: 'dB', digits: 1, diff: (n, b) => n - b, gap: 2, up: '큼', down: '작음' },
  { key: 'voiced_pct', label: '말소리 비율', unit: '%', digits: 0, diff: (n, b) => n - b, gap: 15, up: '많음', down: '적음' },
]

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b)
  const m = Math.floor(s.length / 2)
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2
}

function num(v: number | undefined, digits: number, unit: string): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${v.toFixed(digits)} ${unit}` : '—'
}

/** 목소리 표 — 지금 / 평소 / 차이. `past` 는 지금 값을 뺀 앞선 값들 */
function _VoiceTable({ now, past }: { now: VoiceSignals; past: VoiceSignals[] }) {
  return (
    <div className={styles.voice}>
      <p className={styles.groupLabel}>목소리 (판정 입력 100개 중 86개)</p>
      <table className={styles.voiceTable}>
        <thead>
          <tr>
            <th scope="col">항목</th>
            <th scope="col">지금</th>
            <th scope="col">평소</th>
            <th scope="col">차이</th>
          </tr>
        </thead>
        <tbody>
          {VOICE_ROWS.map((r) => {
            const v = now[r.key]
            const seen = past
              .map((p) => p[r.key])
              .filter((x): x is number => typeof x === 'number' && Number.isFinite(x))
            const base = seen.length >= BASELINE_MIN ? median(seen) : undefined
            let note = '—'
            if (typeof v === 'number' && base !== undefined) {
              const d = r.diff(v, base)
              note = d >= r.gap ? r.up : d <= -r.gap ? r.down : '비슷'
            } else if (typeof v === 'number') {
              note = `모으는 중 ${seen.length}/${BASELINE_MIN}`
            }
            const marked = note === r.up || note === r.down
            return (
              <tr key={r.key}>
                <th scope="row">{r.label}</th>
                <td>{num(v, r.digits, r.unit)}</td>
                <td>{num(base, r.digits, r.unit)}</td>
                <td className={marked ? styles.signalMarked : undefined}>{note}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className={styles.voiceNote}>
        음색(MFCC 80개)은 사람이 읽을 숫자가 아니라 뺐습니다. 「평소」는 이 면접에서 잰
        값의 가운데값이고, 크기(dB)는 마이크마다 기준이 달라 변화만 봅니다.
      </p>
    </div>
  )
}

/* ── 서류 대조 (2026-09-11) ──────────────────────────────────────
   답변이 저장될 때마다 서버가 그 답변 하나를 이력서·자기소개서와 맞춰 본다.
   **서류 원문을 그대로** 두고 판단은 면접관이 한다 (ADR-0003). 판정 말은
   `agent/interview_findings.py` 의 `KOREAN` 과 같다. 여기서도 색을 쓰지 않는다. */
const VERDICT_KO: Record<string, string> = {
  consistent: '서류와 일치',
  inconsistent: '서류와 불일치',
  unverified: '확인필요',
}
const SOURCE_KO: Record<string, string> = { resume: '이력서', self_intro: '자기소개서' }

function _Finding({ f }: { f: InterviewFinding }) {
  return (
    <div className={styles.finding}>
      <span className={f.verdict === 'inconsistent' ? styles.findingMarked : styles.findingVerdict}>
        {VERDICT_KO[f.verdict] ?? f.verdict}
      </span>
      <span className={styles.findingSource}>{SOURCE_KO[f.claim_source] ?? f.claim_source}</span>
      <q className={styles.findingClaim}>{f.claim_text}</q>
    </div>
  )
}

/* ── 판 뒤의 밝기 (2026-09-11) ─────────────────────────────────────
   실시간 분석은 지원자 영상 위에 거의 투명한 판으로 뜬다. 뒤에 깔린 영상이
   밝으면 밝은 글자가, 어두우면 어두운 글자가 사라진다. 판이 덮은 자리의 영상을
   0.5초마다 작게 떠서 밝기를 재고 글자 색을 고른다.

   **경계에서 깜빡이지 않게** 밝아질 때와 어두워질 때의 기준을 다르게 둔다. */
type Backdrop = 'dark' | 'light'

const TONE_EVERY_MS = 500
const TO_LIGHT = 0.6
const TO_DARK = 0.45
/** 영상이 안 그려진 여백(`object-fit: contain` 의 띠)은 `--bg-sunken` — 어둡다 */
const LETTERBOX_LUM = 0.08

function useBackdropTone(
  videoRef: RefObject<HTMLVideoElement | null>,
  boxRef: RefObject<HTMLElement | null>,
  active: boolean,
): Backdrop {
  const [tone, setTone] = useState<Backdrop>('dark')

  useEffect(() => {
    if (!active) return
    const canvas = document.createElement('canvas')
    canvas.width = 24
    canvas.height = 24
    const g = canvas.getContext('2d', { willReadFrequently: true })

    const timer = window.setInterval(() => {
      const v = videoRef.current
      const box = boxRef.current
      if (!v || !box || !g || !v.videoWidth || !v.videoHeight) return
      const vr = v.getBoundingClientRect()
      const br = box.getBoundingClientRect()
      if (!br.width || !br.height) return

      /* `contain` 이라 요소 안에서 실제로 그림이 그려진 사각형을 먼저 구한다 */
      const scale = Math.min(vr.width / v.videoWidth, vr.height / v.videoHeight)
      const dw = v.videoWidth * scale
      const dh = v.videoHeight * scale
      const dx = vr.left + (vr.width - dw) / 2
      const dy = vr.top + (vr.height - dh) / 2
      const x0 = Math.max(br.left, dx)
      const y0 = Math.max(br.top, dy)
      const x1 = Math.min(br.right, dx + dw)
      const y1 = Math.min(br.bottom, dy + dh)

      let lum = LETTERBOX_LUM
      if (x1 > x0 && y1 > y0) {
        try {
          g.drawImage(
            v,
            (x0 - dx) / scale,
            (y0 - dy) / scale,
            (x1 - x0) / scale,
            (y1 - y0) / scale,
            0,
            0,
            canvas.width,
            canvas.height,
          )
          const px = g.getImageData(0, 0, canvas.width, canvas.height).data
          let sum = 0
          for (let i = 0; i < px.length; i += 4) {
            sum += 0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]
          }
          const onVideo = sum / (px.length / 4) / 255
          /* 판이 여백에 걸쳐 있으면 그만큼 어두운 쪽으로 섞는다 */
          const cover = ((x1 - x0) * (y1 - y0)) / (br.width * br.height)
          lum = onVideo * cover + LETTERBOX_LUM * (1 - cover)
        } catch {
          return /* 프레임을 못 읽으면 지난 색을 그대로 둔다 */
        }
      }
      setTone((prev) =>
        prev === 'dark' ? (lum > TO_LIGHT ? 'light' : 'dark') : lum < TO_DARK ? 'dark' : 'light',
      )
    }, TONE_EVERY_MS)

    return () => window.clearInterval(timer)
  }, [active, videoRef, boxRef])

  return tone
}

/* 채용자용 실시간 면접 화면 (docs/02_tasks/실시간-면접-시그널링.md).

   **레이아웃 밖에 둔다.** 사이드바·헤더가 있으면 지원자 얼굴이 그만큼 작아지고,
   면접 중에 다른 데로 새는 길이 화면에 남는다. 면접은 한 번에 하나만 한다. */

export default function InterviewRoom() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const id = Number(sessionId)
  const valid = Number.isFinite(id) && id > 0

  /* 훅이 돌려주는 것을 통째로 들고 다니지 않고 바로 푼다 — 상태와 ref 가
     한 덩어리로 있으면 React 컴파일러가 상태를 읽는 것까지 ref 접근으로 본다. */
  const { phase, error, muted, toggleMute, leave, localRef, remoteRef, remoteStream } =
    useInterviewRoom({ role: 'recruiter', sessionId: valid ? id : null })
  /* **지원자에게서 받은 영상을 분석에 넘긴다.** 지원자 기기가 아니라 여기서
     보내는 이유는 `useLiveAnalysis` 머리말에 적어 뒀다 (ADR-0029). */
  const analysis = useLiveAnalysis(remoteStream)
  /* 영상 위 홀로그램 판과, 그 뒤 영상의 밝기 (2026-09-11) */
  const holoRef = useRef<HTMLDivElement>(null)
  const backdrop = useBackdropTone(remoteRef, holoRef, phase === 'live')
  const [detail, setDetail] = useState<InterviewSessionDetail | null>(null)
  /* 누구를 면접하는지. 세션 상세에는 이름이 없어 지원자를 한 번 더 읽는다. */
  const [who, setWho] = useState<{ name: string; posting: string } | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!valid) return
    const ac = new AbortController()
    interviews
      .detail(id, ac.signal)
      .then(async (d) => {
        setDetail(d)
        try {
          const app = await applications.detail(d.application_id, ac.signal)
          /* 공고 제목은 지원서에 안 실려 온다 — 공고를 한 번 더 읽는다.
             이름부터 먼저 띄우지 않고 둘을 모아 한 번에 넣는다. */
          const posting = await postings.get(app.job_posting_id, ac.signal)
          setWho({ name: app.name, posting: posting.title })
        } catch {
          /* 이름을 못 읽어도 면접은 된다 */
        }
      })
      .catch(() => {
        /* 상세를 못 읽어도 면접 자체는 된다 — 질문 목록만 안 보인다.
           여기서 화면을 막으면 붙을 수 있는 면접을 못 하게 만든다. */
      })
    return () => ac.abort()
  }, [id, valid])

  /* 답변 전사 갱신 (2026-09-09) — 지원자가 답을 마칠 때마다 서버가 저장하지만
     담당자 브라우저에는 밀어 넣지 않는다. 3초 간격으로 다시 읽어 새 답변을
     붙인다. **폴링이 심하지 않은 이유**: 면접이 도는 동안만 돌고, 응답은 세션
     한 개(질문 목록·답변)라 서버 부담이 작다. */
  useEffect(() => {
    if (!valid) return
    const ac = new AbortController()
    const timer = window.setInterval(() => {
      interviews
        .detail(id, ac.signal)
        .then(setDetail)
        .catch(() => {
          /* 한 번 실패해도 다음 주기를 기다린다 */
        })
    }, 3000)
    return () => {
      window.clearInterval(timer)
      ac.abort()
    }
  }, [id, valid])

  const copyLink = useCallback(async () => {
    if (!detail?.url) return
    try {
      await navigator.clipboard.writeText(detail.url)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      /* 클립보드 권한이 없으면 아래 주소를 직접 긁으면 된다 */
    }
  }, [detail])

  if (!valid) {
    return (
      <div className={styles.page}>
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>잘못된 주소입니다</h2>
        </div>
      </div>
    )
  }

  /* 서류 대조를 답변 번호로 묶는다. 번호가 없는 것은 끝난 뒤 전체로 본 것이다. */
  const findings = detail?.findings ?? []
  const findingsBySeq = new Map<number, InterviewFinding[]>()
  for (const f of findings) {
    if (typeof f.turn_seq !== 'number') continue
    findingsBySeq.set(f.turn_seq, [...(findingsBySeq.get(f.turn_seq) ?? []), f])
  }
  const unmatched = findings.filter((f) => typeof f.turn_seq !== 'number')
  const counts = {
    consistent: findings.filter((f) => f.verdict === 'consistent').length,
    inconsistent: findings.filter((f) => f.verdict === 'inconsistent').length,
    unverified: findings.filter((f) => f.verdict === 'unverified').length,
  }

  const waiting = phase !== 'live'

  return (
    <div className={styles.page}>
      <header className={styles.bar}>
        <div className={styles.who}>
          <h1 className={styles.name}>{who?.name ?? '실시간 면접'}</h1>
          {who?.posting && <p className={styles.posting}>{who.posting}</p>}
        </div>
        <div className={styles.state} aria-live="polite">
          <span className={`${styles.dot} ${phase === 'live' ? styles.dotLive : ''}`} />
          {phaseLabel('recruiter', phase)}
        </div>
      </header>

      <div className={styles.stage}>
        {/* 지원자. 화면의 주인공이라 남는 자리를 전부 준다. */}
        <div className={styles.remoteWrap}>
          <video ref={remoteRef} className={styles.remote} autoPlay playsInline />

          {waiting && (
            <div className={styles.overlay}>
              <p className={styles.overlayTitle}>{phaseLabel('recruiter', phase)}</p>
              {error ? (
                <p className={styles.overlayBody}>{error}</p>
              ) : (
                <>
                  <p className={styles.overlayBody}>
                    지원자가 링크를 열면 자동으로 연결됩니다.
                  </p>
                  {detail?.url && (
                    <div className={styles.linkRow}>
                      <code className={styles.link}>{detail.url}</code>
                      <button type="button" className="btn btn-secondary" onClick={copyLink}>
                        {copied ? '복사됨' : '링크 복사'}
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* **좌우를 뒤집는 것은 내 얼굴뿐이다.** 상대는 뒤집지 않는다 —
              거울로 보이는 게 자연스러운 건 자기 모습일 때뿐이다. */}
          <video ref={localRef} className={styles.local} autoPlay playsInline muted />

          {/* 실시간 분석 (2026-09-09). **지원자에게서 받은 영상을 여기서**
              워커로 넘긴다 — 지원자 기기는 아무것도 더 하지 않고, 판정이
              그쪽으로 갈 길도 없다 (ADR-0029 · `useLiveAnalysis`).

              **영상 위에 띄운다** (2026-09-11). 옆 칸에 두면 담당자 눈이 얼굴과
              숫자 사이를 오가고, 질문 목록에 밀려 화면 밖으로 나갔다. 글자 색은
              판 뒤 영상의 밝기를 따라 바뀐다(`useBackdropTone`). 붙기 전에는
              위 안내가 영상 자리를 덮으므로 띄우지 않는다. */}
          {!waiting && (
          <div ref={holoRef} className={styles.holo} data-backdrop={backdrop} aria-live="polite">
            <h2 className={styles.holoTitle}>실시간 분석</h2>

            {/* **값이 있으면 값을 먼저 보여 준다.** 소켓이 끊겼다고 숫자를 감추면
                그 아래 붙는 100·0 경고까지 같이 사라진다 — 경고 없이 숫자만 본
                뒤라 더 나쁘다(2026-09-09 실측: 흐름에는 100.0 이 쌓였는데 위는
                "연결하는 중" 이었다). 대신 **멈춘 값이라고 적는다.** */}
            {!remoteStream ? (
              <p className={styles.empty}>지원자가 연결되면 시작됩니다.</p>
            ) : analysis.latest?.truth_pct === undefined ? (
              <p className={styles.empty}>
                {analysis.error ??
                  (analysis.connected
                    ? (analysis.latest?.reason ?? '지원자가 말하기 시작하면 여기에 나타납니다.')
                    : '분석 서버에 연결하는 중…')}
              </p>
            ) : (
              <>
                {/* **어느 쪽에 가까운지를 먼저 적는다.** 숫자 둘만 두면 보는 사람이
                    머릿속에서 비교해야 하는데, 그 사이에 큰 숫자만 눈에 남는다.

                    모델이 배운 라벨이 실제로 "진실 / 거짓" 이라 그 말을 쓴다.
                    **다만 그 말이 곧 사실이라는 뜻은 아니다** — 아래 문단이
                    그것을 적고, 100·0 이면 경고가 하나 더 붙는다. */}
                <p className={styles.lean}>
                  모델이 본 쪽:{' '}
                  <strong>
                    {analysis.latest.truth_pct >= 50 ? '진실 쪽' : '거짓 쪽'}
                  </strong>
                </p>

                <_Bar
                  label="진실"
                  pct={analysis.latest.truth_pct}
                  lead={analysis.latest.truth_pct >= 50}
                />
                <_Bar
                  label="거짓"
                  pct={analysis.latest.lie_pct}
                  lead={(analysis.latest.truth_pct ?? 0) < 50}
                />

                {/* 표정 top-3 — 우리가 학습한 ViT (`cloverky/arda-expression-vit`,
                    2026-09-10) 가 본 결과. **판정에는 안 들어간다** — model.pkl 은
                    아직 100차원이라 표정 7개가 벡터에 붙지 않는다(ADR-0032 §정하지 못한 것 ③).
                    담당자에게 "우리 ViT 가 뭘 보고 있나" 를 근거로 보여 주는 자리다. */}
                {analysis.latest.expressions?.length ? (
                  <div className={styles.expressions}>
                    <p className={styles.expressionsLabel}>
                      표정 (우리 ViT · 판정엔 안 들어감)
                    </p>
                    <ul className={styles.expressionsList}>
                      {analysis.latest.expressions.slice(0, 3).map((ex) => (
                        <li key={ex.label} className={styles.expressionRow}>
                          <span className={styles.expressionName}>
                            {ex.label_ko || ex.label}
                          </span>
                          <span className={styles.expressionPct}>
                            {Math.round(ex.prob * 100)}%
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {/* 얼굴에서 실제로 잰 것들 — mediapipe 로 재는 landmarks 기반 값.
                    표정 라벨과 별개로 눈 깜빡임·눈썹 높이·고개 움직임 같은 것. */}
                {analysis.latest.signals?.length ? (
                  <p className={styles.groupLabel}>얼굴 (판정 입력 100개 중 14개)</p>
                ) : null}
                {analysis.latest.signals?.length ? (
                  <ul className={styles.signals}>
                    {analysis.latest.signals.map((sig) => (
                      <li key={sig.key} className={styles.signalRow}>
                        <span className={styles.signalKey}>{sig.key}</span>
                        <span
                          className={
                            sig.flag === 'high' || sig.flag === 'low'
                              ? styles.signalMarked
                              : styles.signalValue
                          }
                        >
                          {sig.value}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}

                {analysis.latest.voice && (
                  <_VoiceTable now={analysis.latest.voice} past={analysis.voices.slice(1)} />
                )}

                {/* **이 문단을 지우지 말 것.** 숫자만 두면 합불 근거처럼 읽힌다.
                    `InterviewWatch` 와 같은 말을 쓴다 — 같은 값을 두 화면이
                    다르게 설명하면 그 자체가 오해를 만든다. */}
                <p className={styles.caveat}>
                  표정·음성 신호가 모델이 학습한 패턴과 얼마나 맞는지입니다.
                  <strong> 거짓말 여부가 아니고, 합격·불합격의 근거도 아닙니다.</strong>
                  모델은 121개 표본에 교차검증 76%이며, 긴장·말더듬·비원어민 지원자에게
                  불리하게 작동하지 않는다는 검증은 아직 없습니다 (ADR-0029).
                </p>

                {/* 100·0 은 자신 있다는 뜻이 아니라 **제대로 안 배웠다는 신호**다
                    (cloverky, 2026-09-08 실측). 그 값이 뜨는 자리마다 같이 적는다. */}
                {(analysis.latest.truth_pct === 100 || analysis.latest.truth_pct === 0) && (
                  <p className={styles.saturated}>
                    <strong>100 / 0 은 확신이 아니라 경고입니다.</strong> 표본이 적어
                    모델이 규칙 대신 외운 자리이고, 사실을 말한 대본과 지어낸 대본이
                    똑같이 100으로 나온 적이 있습니다. 이 값은 근거로 쓰지 마세요.
                  </p>
                )}

                {/* 끊긴 채로 옛 숫자를 그대로 두면 지금 값처럼 읽힌다 */}
                {!analysis.connected && (
                  <p className={styles.stale}>
                    {analysis.error ?? '연결이 끊겨 갱신이 멈췄습니다. 다시 붙는 중…'}
                    {' '}위 숫자는 마지막으로 받은 값입니다.
                  </p>
                )}
              </>
            )}
          </div>
          )}
        </div>

        <aside className={styles.side}>
          <section className={styles.panel}>
            <h2 className={styles.panelTitle}>질문·답변</h2>
            {/* 대조가 비어 있을 때 **꺼진 것인지 아직 없는 것인지** 를 가른다 —
                둘 다 빈 목록이라 적지 않으면 기능이 고장 난 것처럼 보인다. */}
            {detail && (
              <p className={styles.findingSummary}>
                {detail.findings_enabled === false
                  ? '서류 대조가 꺼져 있습니다 — 서버 설정(AGENT_FINDINGS_BACKEND)이 비어 있습니다.'
                  : `서류 대조 · 불일치 ${counts.inconsistent} · 일치 ${counts.consistent}` +
                    (counts.unverified ? ` · 확인필요 ${counts.unverified}` : '')}
              </p>
            )}
            {detail?.turns?.length ? (
              <ol className={styles.questions}>
                {detail.turns.map((t) => (
                  <li key={t.seq} className={styles.question}>
                    {t.question}
                    {/* 서버가 저장한 답변 전사(2026-09-09).
                        아직 안 온 것은 자리만 남긴다 — "아직 답 없음" 을 안 적으면
                        지원자가 지금 답하는 중인지 다 넘긴 것인지 화면으로 알 수 없다. */}
                    <div className={styles.answer}>
                      {t.transcript ?? <em className={styles.pending}>아직 답이 저장되지 않았습니다.</em>}
                    </div>
                    {/* 이 답변을 서류와 맞춰 본 것 (2026-09-11). 답변이 저장되고 몇 초 뒤 붙는다 */}
                    {findingsBySeq.get(t.seq)?.map((f) => (
                      <_Finding key={`${f.claim_source}:${f.claim_text}`} f={f} />
                    ))}
                  </li>
                ))}
              </ol>
            ) : (
              <p className={styles.empty}>준비된 질문이 없습니다.</p>
            )}
            {unmatched.length > 0 && (
              <div className={styles.unmatched}>
                <p className={styles.groupLabel}>면접 전체로 본 대조 (끝난 뒤)</p>
                {unmatched.map((f) => (
                  <_Finding key={`${f.claim_source}:${f.claim_text}`} f={f} />
                ))}
              </div>
            )}
          </section>

          {analysis.history.length > 0 && (
            <section className={styles.panel}>
              <h2 className={styles.panelTitle}>흐름</h2>
              <ul className={styles.log}>
                {analysis.history.map((v) => (
                  <li key={v.at} className={styles.logRow}>
                    <span className={styles.logTime}>
                      {new Date(v.at).toLocaleTimeString('ko-KR')}
                    </span>
                    <span>진실 쪽 {fmt(v.truth_pct)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>

      <footer className={styles.actions}>
        <button type="button" className="btn btn-secondary" onClick={toggleMute}>
          {muted ? '마이크 켜기' : '마이크 끄기'}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => {
            leave()
            navigate(-1)
          }}
        >
          나가기
        </button>
      </footer>
    </div>
  )
}
