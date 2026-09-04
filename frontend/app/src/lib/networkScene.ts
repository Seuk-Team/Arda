/* 딥 노드 네트워크 — 로그인 화면 배경.

   깊이는 "레이어를 나눠 따로 흐리고 다시 합치는" 방식으로 만든다:
     1) 노드를 3D 상자에 흩고 원근 투영한다. 화면 크기 s 가 곧 깊이다.
     2) s 로 세 구간(먼/중간/가까운)을 나눠 각각 별도 캔버스에 그린다.
     3) 먼 구간일수록 크게 흐려 겹치고, 사이사이 어두운 안개를 덮는다 → 공기 원근.
     4) 밝은 심만 따로 모아 크게 흐린 뒤 lighter 로 얹는다 → 블룸.

   연결선은 매 프레임 거리로 잇지 않는다. 처음에 최근접 이웃으로 고정 그래프를
   만들어 두어야 선이 깜빡이지 않고, 그 위로 펄스가 일정한 경로를 따라 흐른다.

   React 와 분리해 둔다 — 매 프레임 값이 바뀌는 것을 상태로 들고 있으면 초당 60번
   리렌더가 걸린다. 컴포넌트는 canvas 하나만 넘기고 나머지는 여기서 돈다. */

export interface SceneOptions {
  /** 노드 수. 시안 확정값 170 */
  density?: number
  /** 피사계 심도 배율 */
  dof?: number
  /** 블룸 세기 */
  bloom?: number
  /** 커서 자기장 세기 */
  magnet?: number
  /** 선을 지나는 펄스에 사람·매칭 글리프를 태운다 */
  glyphs?: boolean
  /** 바탕색 (rgb 성분 문자열) */
  base?: string
}

export interface SceneHandle {
  /** 접속 시퀀스 0→1. 캔버스 카메라가 망 속으로 파고든다 */
  setDive: (d: number) => void
  /** 인트로 감광 — w 만큼 배경을 누르고, out 으로 되살린다 */
  setIntro: (v: { w: number; out: number }) => void
  stop: () => void
}

interface Node {
  bx: number; by: number; bz: number; hub: boolean
  r: number; cs: string
  p1: number; p2: number; p3: number
  s1: number; amp: number; pph: number; psp: number
  dx: number; dy: number
  X: number; Y: number; S: number
  band: number; near: number; str: number; vis: boolean
}

interface Edge { a: number; b: number; ph: number; sp: number; gate: number; gi: number }

/* 성운 — 망 뒤에 깔리는 거대한 색 안개. 빈 공간이 그냥 검게 남으면 "우주"가
   아니라 그냥 어두운 화면이 된다. 아주 느리게 흐른다. */
const NEB = [
  { c: '56,130,246', x: 0.24, y: 0.30, r: 0.95, a: 0.20, sp: 0.000021, ph: 0.0 },
  { c: '139,92,246', x: 0.74, y: 0.26, r: 0.82, a: 0.17, sp: 0.000017, ph: 1.9 },
  { c: '16,185,129', x: 0.66, y: 0.78, r: 0.78, a: 0.13, sp: 0.000013, ph: 3.6 },
  { c: '34,211,238', x: 0.18, y: 0.76, r: 0.70, a: 0.12, sp: 0.000025, ph: 5.2 },
]

const LAYER = [
  { max: 0.70, res: 0.5, blur: 7.6, fog: 0.20 },
  { max: 0.90, res: 0.85, blur: 2.7, fog: 0.09 },
  { max: 9.99, res: 1.0, blur: 0, fog: 0 },
]

/* 배경 팔레트의 정점들. 노드 색은 이 넷 사이를 오간다 */
const ANCHOR = [[56, 130, 246], [34, 211, 238], [139, 92, 246], [16, 185, 129]]

function mix(u: number): string {
  const f = Math.max(0, Math.min(0.9999, u)) * (ANCHOR.length - 1)
  const i = Math.floor(f), k = f - i, a = ANCHOR[i], b = ANCHOR[i + 1]
  return `${Math.round(a[0] + (b[0] - a[0]) * k)},${Math.round(a[1] + (b[1] - a[1]) * k)},${Math.round(a[2] + (b[2] - a[2]) * k)}`
}

export function buildScene(el: HTMLCanvasElement, options: SceneOptions = {}): SceneHandle {
  const opt = {
    density: 170, dof: 1, bloom: 1, magnet: 1,
    glyphs: true, base: '6,9,18',
    ...options,
  }

  const ctx = el.getContext('2d')
  if (ctx === null) return { setDive: () => {}, setIntro: () => {}, stop: () => {} }

  const canFilter = typeof ctx.filter === 'string'
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  /* DPR 은 1.5 에서 끊는다 — 3배 화면에서 픽셀 수가 9배가 되면 이 정도 합성은
     프레임을 못 지킨다. 발광체라 선명도 손해가 눈에 띄지 않는 종류의 그림이다. */
  const dpr = Math.min(window.devicePixelRatio || 1, 1.5)

  let W = 1, H = 1, raf: number | null = null, dead = false
  const t0 = Date.now()
  let diveV = 0
  let intro = { w: 0, out: 0 }

  const N = Math.max(24, Math.round(opt.density))
  const nodes: Node[] = []
  for (let i = 0; i < N; i++) {
    const bx = (Math.random() * 2 - 1) * 1.62
    const by = (Math.random() * 2 - 1) * 1.18
    const bz = Math.random() * 2 - 1
    const hub = Math.random() < 0.17
    nodes.push({
      bx, by, bz, hub,
      r: hub ? 2.4 + Math.random() * 1.7 : 0.62 + Math.random() * 0.95,
      /* 색은 무작위가 아니라 공간의 부드러운 함수로 뽑는다 — 이웃끼리 색이 이어져
         망 전체가 한 장의 그라데이션으로 읽힌다. 좌표를 그냥 더하면 값이 가운데로
         쏠려 한 색으로 뭉치므로 사인으로 편다. */
      cs: mix(0.5 + 0.5 * Math.sin(bx * 1.9 + bz * 1.1 + by * 0.6)),
      p1: Math.random() * 6.283, p2: Math.random() * 6.283, p3: Math.random() * 6.283,
      s1: 0.00012 + Math.random() * 0.00016,
      amp: 0.05 + Math.random() * 0.10,
      pph: Math.random() * 6.283, psp: 0.0009 + Math.random() * 0.0012,
      dx: 0, dy: 0, X: 0, Y: 0, S: 1, band: 0, near: 0, str: 0, vis: true,
    })
  }

  const edges: Edge[] = []
  const seen = new Set<string>()
  for (let a0 = 0; a0 < N; a0++) {
    const order: { j: number; d: number }[] = []
    for (let b0 = 0; b0 < N; b0++) {
      if (b0 === a0) continue
      const ex = nodes[a0].bx - nodes[b0].bx
      const ey = nodes[a0].by - nodes[b0].by
      const ez = nodes[a0].bz - nodes[b0].bz
      order.push({ j: b0, d: ex * ex + ey * ey + ez * ez })
    }
    order.sort((p, q) => p.d - q.d)
    const k = nodes[a0].hub ? 4 : 2
    for (let m = 0; m < k && m < order.length; m++) {
      const lo = Math.min(a0, order[m].j), hi = Math.max(a0, order[m].j)
      const key = `${lo}_${hi}`
      if (seen.has(key)) continue
      seen.add(key)
      edges.push({ a: lo, b: hi, ph: Math.random(), sp: 0.00015 + Math.random() * 0.00024, gate: Math.random(), gi: Math.random() < 0.5 ? 0 : 1 })
    }
  }

  const lay = LAYER.map(() => ({ cv: document.createElement('canvas'), g: null as CanvasRenderingContext2D | null }))
  const bloomCv = document.createElement('canvas')
  let bloomG: CanvasRenderingContext2D | null = null

  let tx = 0, ty = 0, mx = 0, my = 0, px = -9999, py = -9999, hasPointer = false

  function sizeAll() {
    for (let L = 0; L < LAYER.length; L++) {
      const c = lay[L].cv
      c.width = Math.max(1, Math.round(W * dpr * LAYER[L].res))
      c.height = Math.max(1, Math.round(H * dpr * LAYER[L].res))
      lay[L].g = c.getContext('2d')
    }
    bloomCv.width = Math.max(1, Math.round(W * dpr * 0.5))
    bloomCv.height = Math.max(1, Math.round(H * dpr * 0.5))
    bloomG = bloomCv.getContext('2d')
  }

  function drawNode(g: CanvasRenderingContext2D, n: Node, t: number) {
    if (!n.vis) return
    const pulse = reduced ? 1 : 1 + Math.sin(t * n.psp + n.pph) * 0.26
    const boost = 1 + n.near * 1.9
    const rr = n.r * n.S * 3.7 * pulse * boost
    const al = Math.min(1, Math.pow(n.S, 1.35) * (n.hub ? 1 : 0.9) * (1 + n.near * 0.7))

    /* 파고드는 동안 노드는 점이 아니라 스쳐 가는 빛줄기가 된다 — 중심에서 바깥으로
       늘어난다. 이게 없으면 그냥 커지기만 해서 속도가 안 읽힌다. 몸통 뒤에 깐다. */
    if (n.str > 1) {
      const vx = n.X - W / 2, vy = n.Y - H / 2
      const vl = Math.sqrt(vx * vx + vy * vy) || 1
      const L = Math.min(n.str * n.S * 0.6, vl)
      const tx2 = n.X - (vx / vl) * L, ty2 = n.Y - (vy / vl) * L
      const sg2 = g.createLinearGradient(tx2, ty2, n.X, n.Y)
      sg2.addColorStop(0, `rgba(${n.cs},0)`)
      sg2.addColorStop(1, `rgba(${n.cs},${Math.min(1, al * 0.8).toFixed(3)})`)
      g.strokeStyle = sg2
      g.lineWidth = Math.max(0.8, rr * 0.55)
      g.lineCap = 'round'
      g.beginPath(); g.moveTo(tx2, ty2); g.lineTo(n.X, n.Y); g.stroke()
    }

    const glowR = rr * (n.hub ? 6.5 : 5.0)
    const gg = g.createRadialGradient(n.X, n.Y, 0, n.X, n.Y, glowR)
    gg.addColorStop(0, `rgba(${n.cs},${(al * 0.5).toFixed(3)})`)
    gg.addColorStop(0.38, `rgba(${n.cs},${(al * 0.14).toFixed(3)})`)
    gg.addColorStop(1, `rgba(${n.cs},0)`)
    g.fillStyle = gg; g.beginPath(); g.arc(n.X, n.Y, glowR, 0, 6.283); g.fill()

    if (n.hub) {
      const sg = g.createRadialGradient(n.X - rr * 0.34, n.Y - rr * 0.38, rr * 0.12, n.X, n.Y, rr)
      sg.addColorStop(0, `rgba(255,255,255,${Math.min(1, al * 0.96).toFixed(3)})`)
      sg.addColorStop(0.42, `rgba(${n.cs},${Math.min(1, al * 0.92).toFixed(3)})`)
      sg.addColorStop(1, `rgba(${n.cs},${(al * 0.18).toFixed(3)})`)
      g.fillStyle = sg; g.beginPath(); g.arc(n.X, n.Y, rr, 0, 6.283); g.fill()
      g.strokeStyle = `rgba(255,255,255,${(al * 0.22).toFixed(3)})`; g.lineWidth = 0.6
      g.beginPath(); g.arc(n.X, n.Y, rr, 0, 6.283); g.stroke()
    } else {
      /* 심은 흰빛으로 올리고 색은 그 둘레에 남긴다 — 발광체는 가운데가 흰색으로
         날아가야 빛나 보인다. 색만 칠하면 아무리 진해도 형광펜처럼 보인다. */
      const cr = Math.max(0.5, rr * 0.66)
      const cg2 = g.createRadialGradient(n.X, n.Y, 0, n.X, n.Y, cr)
      cg2.addColorStop(0, `rgba(255,255,255,${Math.min(1, al * 0.94).toFixed(3)})`)
      cg2.addColorStop(0.5, `rgba(${n.cs},${al.toFixed(3)})`)
      cg2.addColorStop(1, `rgba(${n.cs},0)`)
      g.fillStyle = cg2
      g.beginPath(); g.arc(n.X, n.Y, cr, 0, 6.283); g.fill()
    }
  }

  /* 선을 지나는 펄스에 태우는 글리프 — 사람(지원자)과 매칭. 이 화면이 무엇에
     관한 것인지 말하는 유일한 그림이라 남긴다. */
  function glyphPerson(g: CanvasRenderingContext2D, x: number, y: number, sc: number, cs: string, al: number) {
    g.save(); g.translate(x, y); g.scale(sc, sc)
    g.strokeStyle = `rgba(${cs},${al.toFixed(3)})`; g.lineWidth = 1.4; g.lineCap = 'round'
    g.beginPath(); g.arc(0, -3.6, 2.5, 0, 6.283); g.stroke()
    g.beginPath(); g.arc(0, 5.6, 5.0, Math.PI, 0); g.stroke()
    g.restore()
  }

  function glyphMatch(g: CanvasRenderingContext2D, x: number, y: number, sc: number, cs: string, al: number) {
    g.save(); g.translate(x, y); g.scale(sc, sc)
    g.strokeStyle = `rgba(${cs},${al.toFixed(3)})`; g.lineWidth = 1.4; g.lineCap = 'round'; g.lineJoin = 'round'
    g.beginPath(); g.moveTo(-6.4, -4.2); g.lineTo(-2.0, 0); g.lineTo(-6.4, 4.2); g.stroke()
    g.beginPath(); g.moveTo(6.4, -4.2); g.lineTo(2.0, 0); g.lineTo(6.4, 4.2); g.stroke()
    g.fillStyle = `rgba(${cs},${al.toFixed(3)})`
    g.beginPath(); g.arc(0, 0, 1.5, 0, 6.283); g.fill()
    g.restore()
  }

  function drawEdge(g: CanvasRenderingContext2D, e: Edge, t: number) {
    const A = nodes[e.a], B = nodes[e.b]
    if (!A.vis || !B.vis) return
    const s = (A.S + B.S) * 0.5
    const near = Math.max(A.near, B.near)
    const al = Math.min(0.92, Math.pow(s, 1.9) * 0.86) * (1 + near * 2.2)
    if (al < 0.008) return

    const lg = g.createLinearGradient(A.X, A.Y, B.X, B.Y)
    lg.addColorStop(0, `rgba(${A.cs},${al.toFixed(3)})`)
    lg.addColorStop(0.5, `rgba(${B.cs},${(al * 0.55).toFixed(3)})`)
    lg.addColorStop(1, `rgba(${B.cs},${al.toFixed(3)})`)
    g.strokeStyle = lg
    g.lineWidth = Math.max(0.35, s * 0.95 * (1 + near))
    g.beginPath(); g.moveTo(A.X, A.Y); g.lineTo(B.X, B.Y); g.stroke()

    /* 색 halo 안에 흰 심을 한 겹 더 — 광섬유는 둘레가 물들고 가운데가 하얗다.
       한 획만 그으면 아무리 진해도 그냥 색연필 선으로 보인다. */
    g.strokeStyle = `rgba(255,255,255,${Math.min(0.5, al * 0.34).toFixed(3)})`
    g.lineWidth = Math.max(0.22, s * 0.34)
    g.beginPath(); g.moveTo(A.X, A.Y); g.lineTo(B.X, B.Y); g.stroke()

    if (reduced) return

    const p = (t * e.sp + e.ph) % 1
    const q = Math.max(0, p - 0.14)
    const hx = A.X + (B.X - A.X) * p, hy = A.Y + (B.Y - A.Y) * p
    const qx = A.X + (B.X - A.X) * q, qy = A.Y + (B.Y - A.Y) * q
    const pal = Math.min(1, Math.pow(s, 2.0) * 0.95) * (1 + near * 1.2)

    const tg = g.createLinearGradient(qx, qy, hx, hy)
    tg.addColorStop(0, `rgba(${B.cs},0)`)
    tg.addColorStop(1, `rgba(255,255,255,${Math.min(1, pal * 0.72).toFixed(3)})`)
    g.strokeStyle = tg
    g.lineWidth = Math.max(0.6, s * 1.5 * (1 + near))
    g.beginPath(); g.moveTo(qx, qy); g.lineTo(hx, hy); g.stroke()

    const hr = Math.max(1, s * 2.4)
    const hg = g.createRadialGradient(hx, hy, 0, hx, hy, hr * 3.4)
    hg.addColorStop(0, `rgba(255,255,255,${Math.min(1, pal).toFixed(3)})`)
    hg.addColorStop(0.3, `rgba(${B.cs},${Math.min(1, pal * 0.6).toFixed(3)})`)
    hg.addColorStop(1, `rgba(${B.cs},0)`)
    g.fillStyle = hg; g.beginPath(); g.arc(hx, hy, hr * 3.4, 0, 6.283); g.fill()

    if (opt.glyphs && s > 0.86 && e.gate > 0.72 && p > 0.40 && p < 0.60) {
      const ga = Math.sin(((p - 0.40) / 0.20) * Math.PI) * 0.85
      if (e.gi === 0) glyphPerson(g, hx, hy - 15 * s, s * 1.15, B.cs, ga)
      else glyphMatch(g, hx, hy - 15 * s, s * 1.15, B.cs, ga)
    }
  }

  /* 접속 시퀀스 — dive 0→1.
       0 ~ .60  파고들기: 카메라가 망 속으로. 노드가 스쳐 지나가며 늘어난다
     .60 ~ .86  흰빛 상승 (DOM 의 wash 가 받는다)
     .86 ~ 1    착지 */
  const dive = { push: 0, streak: 0 }
  function calcDive() {
    const d = Math.max(0, Math.min(1, diveV))
    const e = d * d * (3 - 2 * d) // smoothstep
    dive.push = e * 3.05
    dive.streak = Math.pow(d, 1.6) * 152
  }

  function draw() {
    if (ctx === null) return
    const t = reduced ? 14000 : Date.now() - t0
    calcDive()
    const iw = intro.w
    const iout = intro.out
    mx += (tx - mx) * 0.055
    my += (ty - my) * 0.055

    const ry = t * 0.0000375 + mx * 0.42
    const rx = Math.sin(t * 0.000021) * 0.12 + my * 0.30
    const cY = Math.cos(ry), sY = Math.sin(ry), cX = Math.cos(rx), sX = Math.sin(rx)
    const CX = W / 2, CY = H / 2, spread = Math.max(W, H) * 0.80, F = 2.6
    let i: number, n: Node

    for (i = 0; i < N; i++) {
      n = nodes[i]
      const ox = n.bx + Math.sin(t * n.s1 + n.p1) * n.amp
      const oy = n.by + Math.cos(t * n.s1 * 1.21 + n.p2) * n.amp
      const oz = n.bz + Math.sin(t * n.s1 * 0.83 + n.p3) * n.amp
      const x1 = ox * cY + oz * sY
      const z1 = oz * cY - ox * sY
      const y1 = oy * cX - z1 * sX
      const z2 = z1 * cX + oy * sX
      /* 다이브 — z 를 당겨 카메라가 망 속으로 들어간다. 가까워질수록 s 가 커져
         노드가 화면 밖으로 밀려나고, 그게 "지나쳐 간다"로 읽힌다. */
      const den = F + z2 + 1.35 - dive.push
      n.vis = den > 0.30
      const s = n.vis ? F / den : 0
      n.S = s
      n.X = CX + x1 * spread * s * 0.62
      n.Y = CY + y1 * spread * s * 0.44
      n.str = dive.streak
    }

    const R = Math.min(W, H) * 0.36
    for (i = 0; i < N; i++) {
      n = nodes[i]
      let tdx = 0, tdy = 0, f = 0
      if (hasPointer && opt.magnet > 0 && !reduced) {
        const ddx = n.X - px, ddy = n.Y - py
        const d = Math.sqrt(ddx * ddx + ddy * ddy)
        if (d < R) {
          f = Math.pow(1 - d / R, 2.1)
          const puls = 1 + Math.sin(t * 0.0042 - d * 0.013) * 0.36
          const amp = f * opt.magnet * 68 * puls * n.S
          const ang = Math.atan2(ddy, ddx) + 1.18 * f
          tdx = Math.cos(ang) * amp
          tdy = Math.sin(ang) * amp
        }
      }
      n.near = f
      n.dx += (tdx - n.dx) * 0.13
      n.dy += (tdy - n.dy) * 0.13
      n.X += n.dx; n.Y += n.dy
      let L2 = 0
      while (L2 < LAYER.length - 1 && n.S > LAYER[L2].max) L2++
      n.band = L2
    }

    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.globalCompositeOperation = 'source-over'
    ctx.globalAlpha = 1
    if (canFilter) ctx.filter = 'none'
    ctx.fillStyle = `rgb(${opt.base})`
    ctx.fillRect(0, 0, el.width, el.height)

    ctx.globalCompositeOperation = 'lighter'
    const DW = el.width, DH = el.height, DS = Math.max(DW, DH)
    for (const B2 of NEB) {
      const nx = (B2.x + Math.sin(t * B2.sp + B2.ph) * 0.09) * DW + mx * 34 * dpr
      const ny = (B2.y + Math.cos(t * B2.sp * 1.3 + B2.ph) * 0.07) * DH + my * 26 * dpr
      const nr = B2.r * DS * 0.5
      const ng = ctx.createRadialGradient(nx, ny, 0, nx, ny, nr)
      ng.addColorStop(0, `rgba(${B2.c},${B2.a})`)
      ng.addColorStop(0.5, `rgba(${B2.c},${(B2.a * 0.30).toFixed(3)})`)
      ng.addColorStop(1, `rgba(${B2.c},0)`)
      ctx.fillStyle = ng
      ctx.beginPath(); ctx.arc(nx, ny, nr, 0, 6.283); ctx.fill()
    }
    ctx.globalCompositeOperation = 'source-over'

    for (let Lp = 0; Lp < LAYER.length; Lp++) {
      const g = lay[Lp].g
      if (g === null) continue
      const sc = dpr * LAYER[Lp].res
      g.setTransform(1, 0, 0, 1, 0, 0)
      g.clearRect(0, 0, lay[Lp].cv.width, lay[Lp].cv.height)
      g.setTransform(sc, 0, 0, sc, 0, 0)
      g.globalCompositeOperation = 'lighter'

      for (const e of edges) {
        if (Math.min(nodes[e.a].band, nodes[e.b].band) === Lp) drawEdge(g, e, t)
      }
      for (i = 0; i < N; i++) if (nodes[i].band === Lp) drawNode(g, nodes[i], t)

      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.globalCompositeOperation = 'source-over'
      if (canFilter) ctx.filter = LAYER[Lp].blur > 0 ? `blur(${(LAYER[Lp].blur * opt.dof * dpr).toFixed(2)}px)` : 'none'
      ctx.globalAlpha = 1 - iw * 0.42 * (1 - iout)
      ctx.drawImage(lay[Lp].cv, 0, 0, el.width, el.height)
      ctx.globalAlpha = 1
      if (canFilter) ctx.filter = 'none'

      if (LAYER[Lp].fog > 0) {
        ctx.fillStyle = `rgba(${opt.base},${LAYER[Lp].fog.toFixed(2)})`
        ctx.fillRect(0, 0, el.width, el.height)
      }
    }

    if (opt.bloom > 0 && canFilter && bloomG !== null) {
      const bg = bloomG
      bg.setTransform(1, 0, 0, 1, 0, 0)
      bg.clearRect(0, 0, bloomCv.width, bloomCv.height)
      bg.setTransform(dpr * 0.5, 0, 0, dpr * 0.5, 0, 0)
      bg.globalCompositeOperation = 'lighter'
      for (i = 0; i < N; i++) {
        n = nodes[i]
        if (!n.vis || n.S < 0.66) continue
        const br = Math.max(0.8, n.r * n.S * 2.0 * (1 + n.near))
        bg.fillStyle = `rgba(${n.cs},${Math.min(1, Math.pow(n.S, 2.2) * (n.hub ? 0.95 : 0.62)).toFixed(3)})`
        bg.beginPath(); bg.arc(n.X, n.Y, br, 0, 6.283); bg.fill()
      }
      /* 흐르는 펄스도 발광체다 — 블룸에 넣어야 선을 지나는 신호가 실제로 빛난다 */
      if (!reduced) {
        for (const be of edges) {
          const BA = nodes[be.a], BB = nodes[be.b]
          if (!BA.vis || !BB.vis) continue
          const bs = (BA.S + BB.S) * 0.5
          if (bs < 0.74) continue
          const bp = (t * be.sp + be.ph) % 1
          bg.fillStyle = `rgba(${BB.cs},${Math.min(1, Math.pow(bs, 2.0) * 0.8).toFixed(3)})`
          bg.beginPath()
          bg.arc(BA.X + (BB.X - BA.X) * bp, BA.Y + (BB.Y - BA.Y) * bp, Math.max(0.8, bs * 2.0), 0, 6.283)
          bg.fill()
        }
      }
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.filter = `blur(${(19 * dpr * 0.5).toFixed(1)}px)`
      ctx.globalCompositeOperation = 'lighter'
      ctx.globalAlpha = Math.min(1, 0.8 * opt.bloom)
      ctx.drawImage(bloomCv, 0, 0, el.width, el.height)
      ctx.globalAlpha = 1
      ctx.filter = 'none'
      ctx.globalCompositeOperation = 'source-over'
    }
  }

  function resize() {
    const r = el.getBoundingClientRect()
    W = Math.max(1, Math.round(r.width))
    H = Math.max(1, Math.round(r.height))
    el.width = Math.round(W * dpr)
    el.height = Math.round(H * dpr)
    sizeAll()
    draw()
  }

  function onMove(ev: PointerEvent) {
    const r = el.getBoundingClientRect()
    if (!r.width || !r.height) return
    hasPointer = true
    const lx = ev.clientX - r.left, ly = ev.clientY - r.top
    tx = Math.max(-1.3, Math.min(1.3, (lx / r.width - 0.5) * 2))
    ty = Math.max(-1.3, Math.min(1.3, (ly / r.height - 0.5) * 2))
    px = lx * dpr; py = ly * dpr
  }

  function onLeave() { hasPointer = false; tx = 0; ty = 0 }
  function frame() { if (dead) return; draw(); raf = requestAnimationFrame(frame) }

  const ro = new ResizeObserver(resize)
  ro.observe(el)
  window.addEventListener('resize', resize)
  resize()

  /* prefers-reduced-motion 이면 한 장만 그리고 멈춘다 — 정지 화면은 남기되
     초당 60번 도는 루프는 아예 시작하지 않는다 (05-design §5) */
  if (!reduced) {
    document.addEventListener('pointermove', onMove, { passive: true })
    document.addEventListener('pointerleave', onLeave)
    frame()
  }

  return {
    setDive(d) { diveV = d; if (reduced) draw() },
    setIntro(v) { intro = v; if (reduced) draw() },
    stop() {
      dead = true
      if (raf !== null) cancelAnimationFrame(raf)
      ro.disconnect()
      window.removeEventListener('resize', resize)
      document.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerleave', onLeave)
    },
  }
}
