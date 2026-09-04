import { createContext, useCallback, useContext, useEffect, useMemo, useRef } from 'react'
import type { ReactNode } from 'react'
import styles from './DiveTransition.module.css'

/* 접속 시퀀스 — 로그인에서 대시보드로 "파고들어" 도착하는 전환.

   규칙 하나: 연출이 응답보다 오래 끌지 않는다.

   응답을 기다리는 동안은 0 → 0.60 구간을 천천히 기어간다(--dur-dive 속도).
   응답이 도착하는 순간, 그 지점이 어디였든 거기서 1 까지 --dur-land 에 마무리한다.
   그래서 총 길이 = 실제 대기 시간 + 착지 280ms 이고, 서버가 빠르면 전환도 짧다.
   착지 280ms 는 유일한 고정 비용이다 — 이보다 짧으면 전환이 안 읽힌다.
   로딩 스피너를 이 연출이 대신하는 셈이라 대기 표시가 따로 필요 없다.

   왜 라우트 밖(App)에 있나: 흰빛이 /login → /dashboard 이동을 건너 살아남아야
   한다. 로그인 화면 안에 두면 언마운트되면서 흰빛도 같이 사라져 딱 끊긴다.
   MorphNav 가 대시보드→캘린더 전환을 라우트 밖에서 하는 것과 같은 이유다.

   값은 상태로 들고 있지 않는다 — 매 프레임 setState 하면 초당 60번 리렌더가
   걸린다. ref 에 두고 wash 의 opacity 와 구독자(캔버스)에게 직접 밀어 넣는다. */

interface DiveCtx {
  /** 0→1 값을 구독한다. 캔버스가 카메라를 이 값으로 몬다 */
  subscribe: (cb: (d: number) => void) => () => void
  /** 로그인 요청을 감싸 실행한다. 착지까지 끝난 뒤 resolve 된다 */
  run: <T>(task: () => Promise<T>) => Promise<T>
  /** 착지 후 화면이 바뀌면 흰빛을 걷는다 */
  clear: () => void
}

const Ctx = createContext<DiveCtx>({
  subscribe: () => () => {},
  run: (task) => task(),
  clear: () => {},
})

export function useDive() {
  return useContext(Ctx)
}

/* 시간은 토큰에서 읽는다 — 여기서 숫자를 새로 만들지 않는다 (05-design §5).
   MorphNav 가 쓰는 것과 같은 방식이다. */
function cssMs(name: string, fallback: number): number {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  const n = Number.parseFloat(raw)
  if (Number.isNaN(n)) return fallback
  return raw.endsWith('ms') ? n : n * 1000
}

function reduceMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export default function DiveTransition({ children }: { children: ReactNode }) {
  const washRef = useRef<HTMLDivElement>(null)
  const subs = useRef(new Set<(d: number) => void>())
  const raf = useRef<number | null>(null)
  const running = useRef(false)

  const paint = useCallback((d: number) => {
    for (const cb of subs.current) cb(d)
    const w = washRef.current
    if (w === null) return
    /* 흰빛은 0.60 부터 올라온다 — 그 전까지는 파고들기만 보인다 */
    w.style.opacity = d < 0.60 ? '0' : String(Math.min(1, (d - 0.60) / 0.24))
  }, [])

  const subscribe = useCallback((cb: (d: number) => void) => {
    subs.current.add(cb)
    return () => { subs.current.delete(cb) }
  }, [])

  const clear = useCallback(() => {
    running.current = false
    if (raf.current !== null) { cancelAnimationFrame(raf.current); raf.current = null }
    const w = washRef.current
    if (w === null) { paint(0); return }
    /* 도착한 화면이 흰빛 아래에서 드러난다. 레이아웃을 안 건드리는 값(opacity)만
       움직이므로 새 화면이 그려지는 중에도 프레임이 튀지 않는다. */
    w.style.transition = `opacity ${cssMs('--dur-slow', 320)}ms var(--ease)`
    w.style.opacity = '0'
    window.setTimeout(() => {
      if (w.isConnected) w.style.transition = ''
      paint(0)
    }, cssMs('--dur-slow', 320))
  }, [paint])

  const run = useCallback(<T,>(task: () => Promise<T>): Promise<T> => {
    if (running.current) return task()
    running.current = true

    if (reduceMotion()) {
      paint(1)
      return task().catch((err) => { running.current = false; paint(0); throw err })
    }

    const dive = cssMs('--dur-dive', 1600)
    const land = cssMs('--dur-land', 280)
    const t0 = performance.now()
    let resolved = false
    let landT = 0
    let dAtResolve = 0
    let cur = 0

    const step = () => {
      let d: number
      if (!resolved) {
        /* 대기 중에는 0.60 에서 멈춰 선다 — 응답이 늦어도 흰빛까지 가 버리면
           아직 도착하지도 않았는데 도착한 것처럼 보인다 */
        d = Math.min(0.60, (performance.now() - t0) / dive)
      } else {
        if (landT === 0) { landT = performance.now(); dAtResolve = cur }
        const k = Math.min(1, (performance.now() - landT) / land)
        d = dAtResolve + (1 - dAtResolve) * (k * k * (3 - 2 * k)) // smoothstep
      }
      cur = d
      paint(d)
      if (d < 1) raf.current = requestAnimationFrame(step)
      else raf.current = null
    }
    raf.current = requestAnimationFrame(step)

    return task().then(
      (v) => new Promise<T>((res) => {
        resolved = true
        /* 착지가 끝난 뒤에야 부른 쪽으로 돌려준다 — 그래야 화면 이동이
           흰빛이 가장 짙을 때 일어나 교체 순간이 안 보인다 */
        window.setTimeout(() => res(v), land + 16)
      }),
      (err) => {
        /* 실패하면 되돌린다 — 에러 문구는 로그인 카드 위에 떠야 하므로
           흰빛이 남아 있으면 안 된다 */
        running.current = false
        if (raf.current !== null) { cancelAnimationFrame(raf.current); raf.current = null }
        paint(0)
        throw err
      },
    )
  }, [paint])

  /* 전환 중 언마운트되면 루프를 반드시 걷는다 */
  useEffect(() => () => {
    if (raf.current !== null) cancelAnimationFrame(raf.current)
  }, [])

  const value = useMemo<DiveCtx>(() => ({ subscribe, run, clear }), [subscribe, run, clear])

  return (
    <Ctx.Provider value={value}>
      {children}
      <div ref={washRef} className={styles.wash} aria-hidden="true" />
    </Ctx.Provider>
  )
}
