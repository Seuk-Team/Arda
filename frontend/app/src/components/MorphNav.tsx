import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import styles from './MorphNav.module.css'

/* 대시보드 축소판 → 전체 화면으로 이어지는 전환 (컨테이너 트랜스폼).
   "갑자기 사라지거나 생겨나는 것 없이 도형이 확장되며 이어진다"가 요구사항이라
   화면 교체를 세 겹으로 나눈다.

     ① out  — 떠나는 화면에서 축소판만 남기고 나머지가 페이드아웃 (--dur-base)
     ② 교체 — 라우팅과 동시에 축소판 자리에 같은 크기의 도형(복제본 포함)을 띄운다.
              한 커밋 안에서 일어나므로 둘 사이에 빈 화면이 그려지는 프레임이 없다
     ③ in   — 도형이 목적지 카드의 위치·크기로 확장(--dur-slow)되는 동안
              복제본은 앞부분에서 지고, 새 화면은 뒷부분에서 뜬다

   레이아웃을 매 프레임 건드리지 않도록 움직이는 값은 transform·opacity 뿐이다.
   목적지는 `data-morph-target` 이 붙은 요소이고, 없으면 그냥 즉시 전환된다.
   돌아오는 길(캘린더 → 대시보드)은 모션 없음 — 역재생은 범위 밖. */

const OUT_ANCHOR = 'data-morph-shell'

/* 축소판 복제본이 지는 구간 / 새 화면이 뜨는 구간 — 도형 확장 시간에 대한 비율.
   새 화면은 도형이 거의 다 자란 뒤에야 뜬다 — 먼저 뜨면 도형이 아직 안 덮은 자리에
   목적지 내용이 미리 나타나 "생겨나는" 것처럼 보인다 */
const CLONE_OUT = 0.5
const SHELL_IN: [number, number] = [0.35, 0.9]
/* 도형은 뒷구간에서 지며 밑에 깔린 진짜 카드를 드러낸다. 끝이 투명이라
   목적지 카드가 전환 중 몇 px 자라도 착지에서 튀지 않는다 */
const SHAPE_OUT = 0.5

interface Pending {
  rect: DOMRect
  clone: Node
  to: string
  target: string
  from: string
}

interface MorphCtx {
  /* 떠나는 화면이 "나만 남기고 페이드아웃" 을 그릴 때 쓴다 */
  leaving: boolean
  start: (origin: HTMLElement, to: string, target: string) => void
}

const Ctx = createContext<MorphCtx>({ leaving: false, start: () => {} })

export function useMorphNav() {
  return useContext(Ctx)
}

/* 시간·이징은 05-design §5 토큰만 쓴다 — 여기서 숫자를 새로 만들지 않는다 */
function cssMs(name: string, fallback: number): number {
  if (typeof window === 'undefined') return fallback
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  const n = Number.parseFloat(raw)
  if (Number.isNaN(n)) return fallback
  return raw.endsWith('ms') ? n : n * 1000
}

function cssEase(fallback: string): string {
  if (typeof window === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue('--ease').trim() || fallback
}

function reduceMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export default function MorphNav({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const location = useLocation()

  const [phase, setPhase] = useState<'idle' | 'out' | 'in'>('idle')
  const pending = useRef<Pending | null>(null)
  /* 라우팅은 트랜지션이라 목적지 주소가 한 박자 늦게 온다 — 도착 전과 후를 나눠 봐야
     "아직 안 왔다"와 "떠났다"를 구분할 수 있다 */
  const arrived = useRef(false)
  const anims = useRef<Animation[]>([])
  const shapeRef = useRef<HTMLDivElement>(null)
  const holderRef = useRef<HTMLDivElement>(null)

  const finish = useCallback(() => {
    for (const a of anims.current) a.cancel()
    anims.current = []
    document.querySelector<HTMLElement>(`[${OUT_ANCHOR}]`)?.style.removeProperty('opacity')
    delete document.body.dataset.morph
    pending.current = null
    arrived.current = false
    setPhase('idle')
  }, [])

  /* 연타·중간 이탈 대비: 전환이 도는 동안 새 요청을 받지 않는다 */
  const start = useCallback((origin: HTMLElement, to: string, target: string) => {
    if (pending.current !== null) return
    if (reduceMotion() || typeof origin.animate !== 'function') {
      navigate(to)
      return
    }

    pending.current = {
      rect: origin.getBoundingClientRect(),
      clone: origin.cloneNode(true),
      to,
      target,
      from: window.location.pathname,
    }
    document.body.dataset.morph = 'out'
    setPhase('out')

    /* 제목 띠는 떠나는 화면 바깥(Layout)에 있어 페이지 CSS 가 닿지 않는다 */
    const head = document.querySelector<HTMLElement>('[data-pagehead]')
    const a = head?.animate([{ opacity: 1 }, { opacity: 0 }], {
      duration: cssMs('--dur-base', 200),
      easing: cssEase('cubic-bezier(.2,0,0,1)'),
      fill: 'forwards',
    })
    if (a) anims.current.push(a)
  }, [navigate])

  /* ① out 이 끝나면 라우팅과 도형 띄우기를 같은 커밋에서 한다 */
  useEffect(() => {
    if (phase !== 'out') return
    const t = window.setTimeout(() => {
      const p = pending.current
      if (p === null) return
      if (window.location.pathname !== p.from) {
        finish()
        return
      }
      setPhase('in')
      navigate(p.to)
    }, cssMs('--dur-base', 200))
    return () => window.clearTimeout(t)
  }, [phase, navigate, finish])

  /* ③ 페인트 전에 도형을 축소판 자리에 앉히고, 목적지가 붙는 즉시 확장을 건다.
     react-router 는 라우팅을 트랜지션으로 넘기므로 새 화면이 같은 커밋에 오지 않는다 —
     그래서 도형을 먼저 축소판 자리에 그대로 앉혀 두고(그 사이엔 화면이 안 바뀐 것처럼 보인다)
     목적지가 그려진 프레임에 다시 재어 확장한다. */
  useLayoutEffect(() => {
    if (phase !== 'in') return
    const p = pending.current
    const shape = shapeRef.current
    const holder = holderRef.current
    const shell = document.querySelector<HTMLElement>(`[${OUT_ANCHOR}]`)
    if (p === null || shape === null || holder === null || shell === null) {
      finish()
      return
    }

    /* 출발 자리 = 축소판이 있던 그 자리 (transform 은 아직 걸지 않는다) */
    shape.style.left = `${p.rect.left}px`
    shape.style.top = `${p.rect.top}px`
    shape.style.width = `${p.rect.width}px`
    shape.style.height = `${p.rect.height}px`
    holder.style.width = `${p.rect.width}px`
    holder.style.height = `${p.rect.height}px`
    holder.replaceChildren(p.clone)
    shell.style.opacity = '0'

    const duration = cssMs('--dur-slow', 320)
    const easing = cssEase('cubic-bezier(.2,0,0,1)')

    /* 목적지를 기다리는 재시도는 타이머로 돈다 — 탭이 안 보여 rAF 가 초당 1회로
       묶이는 환경에서도 라우팅이 끝나는 즉시 잡기 위해서다 */
    let retry = 0
    const deadline = performance.now() + cssMs('--dur-slow', 320)
    let done = false
    let guard = 0
    let grow: Animation | null = null

    const end = () => {
      if (done) return
      done = true
      finish()
    }

    const run = () => {
      const dest = document.querySelector<HTMLElement>(`[data-morph-target="${p.target}"]`)
      /* 목적지가 끝내 안 나오면 애니메이션 없이 새 화면을 보여준다 (깨진 화면 금지) */
      if (dest === null) {
        if (performance.now() > deadline) {
          end()
          return
        }
        retry = window.setTimeout(run, 0)
        return
      }

      const d = dest.getBoundingClientRect()
      const sx = d.width === 0 ? 1 : p.rect.width / d.width
      const sy = d.height === 0 ? 1 : p.rect.height / d.height

      /* 도착 자리로 옮겨 놓고 같은 프레임에 출발 자리로 되돌리는 transform 을 건다 —
         화면상 위치는 그대로고, 여기서부터 도형이 자란다 (FLIP) */
      shape.style.left = `${d.left}px`
      shape.style.top = `${d.top}px`
      shape.style.width = `${d.width}px`
      shape.style.height = `${d.height}px`
      const from = `translate(${p.rect.left - d.left}px, ${p.rect.top - d.top}px) scale(${sx}, ${sy})`

      /* 복제본은 축소판의 자연 크기(p.rect)로 재 놓았는데, 그 위에 도형의 축소가
         한 번 더 곱해진다 — 그대로 두면 전환 첫 프레임에 내용만 sx·sy 배로
         쪼그라들어 "툭" 튄다. 도형의 축소를 되돌려 출발 프레임에서 축소판과
         1:1 로 겹치게 하고, 이후엔 도형과 같은 비율로 함께 자란다. */
      holder.style.transform = `scale(${1 / sx}, ${1 / sy})`

      grow = shape.animate([{ transform: from }, { transform: 'none' }], { duration, easing, fill: 'both' })

      anims.current.push(
        grow,
        shape.animate(
          [{ opacity: 1, offset: 0 }, { opacity: 1, offset: SHAPE_OUT }, { opacity: 0, offset: 1 }],
          { duration, easing: 'linear', fill: 'both' },
        ),
        holder.animate([{ opacity: 1 }, { opacity: 0 }], {
          duration: duration * CLONE_OUT,
          easing: 'linear',
          fill: 'both',
        }),
        shell.animate(
          [
            { opacity: 0, offset: 0 },
            { opacity: 0, offset: SHELL_IN[0] },
            { opacity: 1, offset: SHELL_IN[1] },
            { opacity: 1, offset: 1 },
          ],
          { duration, easing: 'linear', fill: 'both' },
        ),
      )

      grow.addEventListener('finish', end)
      /* 탭이 백그라운드로 가 finish 가 늦어져도 임시 레이어는 반드시 걷는다 */
      guard = window.setTimeout(end, duration * 3)
    }

    run()

    return () => {
      window.clearTimeout(retry)
      grow?.removeEventListener('finish', end)
      window.clearTimeout(guard)
    }
  }, [phase, finish])

  /* 전환 중 뒤로가기·다른 메뉴로 새면 그 자리에서 접는다.
     목적지에 닿기 전이라도 출발 화면을 벗어났으면 마찬가지다 */
  useEffect(() => {
    const p = pending.current
    if (p === null) return
    if (location.pathname === p.to) {
      arrived.current = true
      return
    }
    if (arrived.current || location.pathname !== p.from) finish()
  }, [location, finish])

  useEffect(() => () => {
    for (const a of anims.current) a.cancel()
    delete document.body.dataset.morph
  }, [])

  const value = useMemo<MorphCtx>(() => ({ leaving: phase === 'out', start }), [phase, start])

  return (
    <Ctx.Provider value={value}>
      {children}
      {/* inert — 복제본 안의 버튼이 탭 순서에 끼어들지 않게 */}
      {phase === 'in' && (
        <div className={styles.layer} inert aria-hidden="true">
          <div ref={shapeRef} className={styles.shape}>
            <div ref={holderRef} className={styles.holder} />
          </div>
        </div>
      )}
    </Ctx.Provider>
  )
}
