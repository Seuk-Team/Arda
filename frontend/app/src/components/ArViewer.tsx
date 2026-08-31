/* 아르 3D 뷰어. 바탕화면 아르-미리보기.html 의 three.js 로직을 React 로 이식했다.
   glb: public/ar.glb — 모션 7종. 표정은 입체 세트(ExAsk·ExHappy·ExSad 본 스케일 교체)가
   모션에 내장돼 있다: ask→질문 얼굴, confirm→행복, fail→실패, 나머지는 기본 얼굴. */
import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

export const MOTIONS = ['idle', 'enter', 'listen', 'think', 'ask', 'confirm', 'fail'] as const
export type Motion = (typeof MOTIONS)[number]

/* 루프 모션 외(enter·confirm·fail)는 1회 재생 후 idle 복귀 */
const LOOPS: ReadonlySet<Motion> = new Set(['idle', 'listen', 'think', 'ask'])
const FADE = 0.12

/* 표정 세트 본 이름. 스케일 1=표시, 0.001=숨김 (모션 애니메이션이 매 프레임 키를 갖고 있어
   강제 표정은 mixer.update 이후에 덮어쓴다) */
export const EXPRESSIONS = ['ask', 'happy', 'sad'] as const
export type Expression = (typeof EXPRESSIONS)[number]
const EX_BONES: Record<Expression, string> = { ask: 'ExAsk', happy: 'ExHappy', sad: 'ExSad' }

interface Props {
  motion?: Motion
  /* 재생 배속. 미지정 시 1, 단 prefers-reduced-motion 이면 0(정지 프레임) */
  speed?: number
  /* 표정 강제. 미지정 시 모션 내장 표정 그대로 */
  expression?: Expression
  /* 드래그 회전·휠 줌 (OrbitControls) */
  interactive?: boolean
  /* 원샷 모션이 끝나 idle 로 복귀할 때 */
  onMotionEnd?: (motion: Motion) => void
  className?: string
}

export default function ArViewer({ motion = 'idle', speed, expression, interactive = false, onMotionEnd, className }: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const mixerRef = useRef<THREE.AnimationMixer | null>(null)
  const actionsRef = useRef<Partial<Record<Motion, THREE.AnimationAction>>>({})
  const exBonesRef = useRef<Partial<Record<Expression, THREE.Object3D>>>({})
  const currentRef = useRef<Motion>('idle')
  const speedRef = useRef(1)
  /* prop 최신값을 렌더 루프·finished 리스너에서 쓰기 위한 ref */
  const onEndRef = useRef(onMotionEnd)
  onEndRef.current = onMotionEnd
  const exprRef = useRef(expression)
  exprRef.current = expression

  const reduced =
    typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  speedRef.current = speed ?? (reduced ? 0 : 1)

  /* 장면 구성 — 마운트 1회 */
  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    host.appendChild(renderer.domElement)
    const scene = new THREE.Scene()
    const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 2000)
    scene.add(new THREE.AmbientLight(0xffffff, 2.6))
    const dl = new THREE.DirectionalLight(0xffffff, 1.1)
    dl.position.set(60, 120, 140)
    scene.add(dl)

    const resize = () => {
      const w = host.clientWidth, h = host.clientHeight
      if (!w || !h) return
      renderer.setSize(w, h)
      const s = 95, a = w / h
      cam.left = -s * a; cam.right = s * a; cam.top = s; cam.bottom = -s
      cam.updateProjectionMatrix()
    }
    const ro = new ResizeObserver(resize)
    ro.observe(host)

    let controls: OrbitControls | null = null
    let disposed = false
    new GLTFLoader().load(`${import.meta.env.BASE_URL}ar.glb`, (g) => {
      if (disposed) return
      scene.add(g.scene)
      EXPRESSIONS.forEach((e) => {
        const bone = g.scene.getObjectByName(EX_BONES[e])
        if (bone) exBonesRef.current[e] = bone
      })
      const box = new THREE.Box3().setFromObject(g.scene)
      const c = box.getCenter(new THREE.Vector3())
      cam.position.set(c.x, c.y + 8, c.z + 600)
      cam.lookAt(c)
      if (interactive) {
        controls = new OrbitControls(cam, renderer.domElement)
        controls.target.copy(c)
      }
      const mixer = new THREE.AnimationMixer(g.scene)
      mixerRef.current = mixer
      const clips = Object.fromEntries(g.animations.map((a) => [a.name, a]))
      MOTIONS.filter((n) => clips[n]).forEach((name) => {
        const a = mixer.clipAction(clips[name])
        if (!LOOPS.has(name)) {
          a.setLoop(THREE.LoopOnce, 1)
          a.clampWhenFinished = true
        }
        actionsRef.current[name] = a
      })
      mixer.addEventListener('finished', () => {
        const ended = currentRef.current
        if (!LOOPS.has(ended)) {
          play('idle')
          onEndRef.current?.(ended)
        }
      })
      resize()
      play(currentRef.current, true)
    })

    const clock = new THREE.Clock()
    let raf = 0
    const tick = () => {
      raf = requestAnimationFrame(tick)
      mixerRef.current?.update(clock.getDelta() * speedRef.current)
      /* 강제 표정: 애니메이션이 매 프레임 Ex 본을 키하므로 update 뒤에 덮어쓴다 */
      const forced = exprRef.current
      if (forced) {
        EXPRESSIONS.forEach((e) => exBonesRef.current[e]?.scale.setScalar(e === forced ? 1 : 0.001))
      }
      controls?.update()
      renderer.render(scene, cam)
    }
    tick()

    return () => {
      disposed = true
      cancelAnimationFrame(raf)
      ro.disconnect()
      controls?.dispose()
      mixerRef.current = null
      actionsRef.current = {}
      exBonesRef.current = {}
      scene.traverse((o) => {
        if ((o as THREE.Mesh).isMesh) {
          const mesh = o as THREE.Mesh
          mesh.geometry.dispose()
          const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
          mats.forEach((m) => m.dispose())
        }
      })
      renderer.dispose()
      renderer.domElement.remove()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* 모션 전환 (glb 로드 전이면 currentRef 만 갱신, 로드 콜백이 이어받는다) */
  function play(name: Motion, force = false) {
    const prevName = currentRef.current
    currentRef.current = name
    const actions = actionsRef.current
    const next = actions[name]
    if (!next) return
    const prev = prevName !== name ? actions[prevName] : undefined
    if (!force && prev) prev.fadeOut(FADE)
    next.reset().fadeIn(force ? 0 : FADE).play()
  }

  useEffect(() => {
    if (motion !== currentRef.current) play(motion)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [motion])

  return <div ref={hostRef} className={className} />
}
