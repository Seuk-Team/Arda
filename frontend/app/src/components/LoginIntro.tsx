import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import type { SceneHandle } from '../lib/networkScene'
import styles from './LoginIntro.module.css'

/* 시네마틱 인트로 — 세션당 1회.

   위에서부터 후두둑: 워드마크와 카피가 190ms 간격으로 왼쪽에서 들어와 함께 서고,
   같은 순서·같은 간격으로 오른쪽으로 빠진다. 각자 문법은 하나다 —
   슥(672ms 진입) → 머묾 → 가속 퇴장. 마지막에 로그인 카드가 같은 문법으로 뜬다.

   왜 CSS 애니메이션이 아니라 rAF 인가: 배경 캔버스 감광(scene.setIntro)과
   프레임을 맞춰야 한다. 둘을 따로 돌리면 글자가 빠지는 타이밍과 망이 되살아나는
   타이밍이 어긋나 두 개의 연출로 보인다.

   매번 나오면 통행세다 — sessionStorage 로 1회만, Skip 은 어느 지점에서든 즉시
   끝낸다. prefers-reduced-motion 이면 아예 돌지 않는다 (05-design §5). */

const SEEN_KEY = 'arda-intro-seen'
const T_END = 3600      /* 카드 등장이 3592ms 에 끝난다 — 그 뒤에 닫아야 안 튄다 */
const SEUK_IN = 672     /* 진입 이징 길이 */
const SEUK_BEAT = 190   /* 줄 사이 간격 */
const CARD_AT = 2920    /* 로그인 카드가 떠오르기 시작하는 시각 */

function clamp01(v: number) { return v < 0 ? 0 : v > 1 ? 1 : v }

/* cubic-bezier(.2,.7,.2,1) 을 뉴턴법으로 푼다. team.seuk.cloud 의 hero-enter 가
   쓰는 곡선이라 같은 값을 그대로 쓴다 */
function ease(x: number): number {
  if (x <= 0) return 0
  if (x >= 1) return 1
  let t = x
  for (let i = 0; i < 6; i++) {
    const f = 3 * (1 - t) * (1 - t) * t * 0.2 + 3 * (1 - t) * t * t * 0.2 + t * t * t - x
    const d = 3 * (1 - t) * (1 - t) * 0.2 + 3 * t * t * 0.8
    if (Math.abs(d) < 1e-6) break
    t -= f / d
  }
  t = clamp01(t)
  return 3 * (1 - t) * (1 - t) * t * 0.7 + 3 * (1 - t) * t * t + t * t * t
}

export function introAlreadySeen(): boolean {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return true
  try { return sessionStorage.getItem(SEEN_KEY) === '1' } catch { return true }
}

interface Props {
  /* 인트로가 끝에서 띄우는 로그인 카드. 자리를 안 건드리는 값만 만진다 */
  stageRef: RefObject<HTMLDivElement | null>
  sceneRef: RefObject<SceneHandle | null>
  onDone: () => void
}

export default function LoginIntro({ stageRef, sceneRef, onDone }: Props) {
  const wordRef = useRef<HTMLDivElement>(null)
  const copyRef = useRef<HTMLDivElement>(null)
  const doneRef = useRef(false)
  const rafRef = useRef<number | null>(null)
  /* 렌더가 아니라 효과에서 갱신한다 — 렌더 중 ref 쓰기는 동시성 렌더에서
     버려질 렌더의 값을 남긴다. 선언 순서상 아래 인트로 효과보다 먼저 돈다. */
  const onDoneRef = useRef(onDone)
  useEffect(() => { onDoneRef.current = onDone })

  const finish = useRef(() => {
    if (doneRef.current) return
    doneRef.current = true
    if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null }
    sceneRef.current?.setIntro({ w: 0, out: 0 })
    const stage = stageRef.current
    if (stage !== null) { stage.style.opacity = ''; stage.style.transform = '' }
    try { sessionStorage.setItem(SEEN_KEY, '1') } catch { /* 사파리 프라이빗 등 — 인트로가 한 번 더 나올 뿐이라 무시 */ }
    onDoneRef.current()
  })

  useEffect(() => {
    const stage = stageRef.current
    if (stage !== null) {
      stage.style.opacity = '0'
      stage.style.transform = 'translateX(-72px) scale(.96)'
    }
    const t0 = performance.now()

    const step = () => {
      const t = performance.now() - t0

      /* 두 덩어리가 연달아 들어왔다 연달아 빠진다 */
      const PASS: [HTMLElement | null, number, number, number][] = [
        [wordRef.current, 0, 2350, 460],
        [copyRef.current, SEUK_BEAT, 2350 + SEUK_BEAT, 380],
      ]
      for (const [el, enter, leave, dist] of PASS) {
        if (el === null) continue
        let o = 0, dx = 0
        if (t >= enter && t < leave) {
          const e = ease(clamp01((t - enter) / SEUK_IN))
          o = e
          dx = -dist * (1 - e)
        } else if (t >= leave) {
          let q = clamp01((t - leave) / 640)
          q = q * q
          o = 1 - q
          dx = (dist + 60) * q
        }
        el.style.opacity = String(o)
        el.style.transform = `translateX(${Math.round(dx)}px)`
      }

      /* 배경 망 감광 — 인트로가 시작할 때 눌리고 마지막 덩어리가 빠질 때 되살아난다 */
      sceneRef.current?.setIntro({ w: ease(clamp01(t / 600)), out: clamp01((t - 2540) / 640) })

      /* 로그인 카드도 같은 문법 — 왼쪽에서 슥. 가운데 카드라 이동 거리는 짧게 */
      if (t >= CARD_AT && stage !== null) {
        const e = ease(clamp01((t - CARD_AT) / SEUK_IN))
        stage.style.opacity = String(e)
        stage.style.transform = `translateX(${(-72 * (1 - e)).toFixed(2)}px) scale(${(0.96 + 0.04 * e).toFixed(4)})`
      }

      if (t < T_END) rafRef.current = requestAnimationFrame(step)
      else finish.current()
    }
    rafRef.current = requestAnimationFrame(step)

    const end = finish.current
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
      /* 인트로 도중에 화면을 떠나도 카드와 배경을 원래대로 돌려놓는다 */
      end()
    }
  }, [stageRef, sceneRef])

  return (
    <div className={styles.intro}>
      <div className={styles.stack}>
        <div className={styles.wordmark} ref={wordRef}>SEUK</div>
        <div className={styles.copy} ref={copyRef}>
          <div className={styles.slogan}>AI 기반 채용 프로세스 자동화 및 지원자 통합 관리 플랫폼</div>
          <div className={styles.subcopy}>
            이력서 AI 파싱, 칸반 보드, Tool-Calling Agent, RAG 질의응답까지 —<br />
            채용 프로세스를 하나의 플랫폼에서 자동화합니다.
          </div>
        </div>
      </div>
      <button type="button" className={styles.skip} onClick={() => finish.current()}>Skip →</button>
    </div>
  )
}
