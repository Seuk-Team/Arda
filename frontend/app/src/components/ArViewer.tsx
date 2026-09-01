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
  /* 커서를 눈으로 따라간다. 켜져 있는 동안만 듣고, 꺼지면 정면으로 되돌아온다.
     모바일은 hover 가 없어(§5) 아무 일도 일어나지 않는다 — 정보는 여기 담지 않는다. */
  track?: boolean
  /* 원샷 모션이 끝나 idle 로 복귀할 때 */
  onMotionEnd?: (motion: Motion) => void
  className?: string
}

export default function ArViewer({ motion = 'idle', speed, expression, interactive = false, track = false, onMotionEnd, className }: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  /* 커서 추적. 목표 각도(rad)와 현재 각도를 따로 두고 매 프레임 좁힌다 —
     포인터 이벤트가 띄엄띄엄 와도 움직임이 끊기지 않는다. */
  const trackRef = useRef(false)
  trackRef.current = track
  const aimRef = useRef({ yaw: 0, pitch: 0 })
  const nowRef = useRef({ yaw: 0, pitch: 0 })
  const rootRef = useRef<THREE.Object3D | null>(null)
  const restRef = useRef({ yaw: 0, pitch: 0 })
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
    /* preserveDrawingBuffer: 캔버스 스냅숏(toDataURL)용 — 아바타 정지 이미지 추출 */
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true })
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
      /* 커서 추적은 모델 전체를 조금 돌려서 낸다 — 목 본 이름에 기대지 않으므로
         glb 가 바뀌어도 안 깨진다. 원래 각도를 기억해 두고 그 위에 더한다. */
      rootRef.current = g.scene
      restRef.current = { yaw: g.scene.rotation.y, pitch: g.scene.rotation.x }
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

    /* 커서 위치 → 목표 각도. 칸 중심을 원점으로 -1..1 로 정규화한 뒤 최대 각도를 곱한다.
       화면 어디서 움직이든 듣되(칸을 살짝 벗어나도 눈이 따라간다) 값은 칸 기준이다. */
    const MAX_YAW = 0.42   // rad, 약 24°
    const MAX_PITCH = 0.22 // rad, 약 13° — 위아래는 덜 돌린다(턱이 들려 보인다)
    const onPointer = (e: PointerEvent) => {
      if (!trackRef.current) return
      const r = host.getBoundingClientRect()
      if (!r.width || !r.height) return
      const nx = ((e.clientX - (r.left + r.width / 2)) / (r.width / 2))
      const ny = ((e.clientY - (r.top + r.height / 2)) / (r.height / 2))
      const clamp = (v: number) => Math.max(-1.5, Math.min(1.5, v))
      aimRef.current.yaw = clamp(nx) * MAX_YAW
      aimRef.current.pitch = clamp(ny) * MAX_PITCH
    }
    window.addEventListener('pointermove', onPointer)

    const clock = new THREE.Clock()
    let raf = 0
    const tick = () => {
      raf = requestAnimationFrame(tick)
      const dt = clock.getDelta()
      mixerRef.current?.update(dt * speedRef.current)
      /* 강제 표정: 애니메이션이 매 프레임 Ex 본을 키하므로 update 뒤에 덮어쓴다 */
      const forced = exprRef.current
      if (forced) {
        EXPRESSIONS.forEach((e) => exBonesRef.current[e]?.scale.setScalar(e === forced ? 1 : 0.001))
      }
      /* 커서 추적 — 목표로 매 프레임 조금씩 좁힌다. 벗어나면 목표가 0 이라 정면으로
         돌아온다. 모션 애니메이션은 본을 돌리고 이건 루트를 돌려서 서로 안 부딪힌다.
         reduced-motion 이면 speed 가 0 이라 모션은 멈추지만 추적은 남긴다 — 회전 자체가
         커서를 따라오는 반응이지 등장 애니메이션이 아니다(§5). */
      const root = rootRef.current
      if (root && !interactive) {
        if (!trackRef.current) { aimRef.current.yaw = 0; aimRef.current.pitch = 0 }
        /* 프레임 독립 보간 — 초당 약 92% 를 좁힌다 */
        const k = 1 - Math.pow(0.08, dt)
        nowRef.current.yaw += (aimRef.current.yaw - nowRef.current.yaw) * k
        nowRef.current.pitch += (aimRef.current.pitch - nowRef.current.pitch) * k
        root.rotation.y = restRef.current.yaw + nowRef.current.yaw
        root.rotation.x = restRef.current.pitch + nowRef.current.pitch
      }
      controls?.update()
      renderer.render(scene, cam)
    }
    tick()

    return () => {
      disposed = true
      cancelAnimationFrame(raf)
      window.removeEventListener('pointermove', onPointer)
      ro.disconnect()
      controls?.dispose()
      rootRef.current = null
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
