/* 아르 색 — 시안 A안(2026-09-05)과 같은 변환이다.
   시안에서는 렌더 PNG 픽셀에 걸었고, 여기서는 같은 규칙을 glb 의 베이스컬러
   텍스처와 머티리얼 색에 건다. 값이 다르면 시안과 실물이 갈리므로 그대로 옮긴다.

   왜 머티리얼 색만 곱하지 않는가: 아르의 몸통 색은 텍스처에서 온다
   (tripo_mat_… 의 baseColorFactor 는 #e6e6e6 로 거의 흰색). 색을 곱하면
   초록 위에 시안을 씌운 탁한 청록이 되지 색이 돌지 않는다. 색상환을 돌려야 한다.

   glb 를 다시 굽지 않고 실행 중에 바꾸는 이유: 아르 디자인이 아직 확정이
   아니다. 상수 한 줄이라 되돌리기 쉽고, ar.glb 는 원본 그대로 남는다. */

/* 몸통 초록 → 시안, 뿔 분홍 → 밝은 시안. 0.55 는 원본의 대표 채도라
   그것에 견줘 새 채도를 정한다 */
const BODY = { h: 191, s: 0.78 }
const HORN = { h: 186, s: 0.88 }

/* 이보다 채도가 낮으면 건드리지 않는다 — 눈의 무채 하이라이트가 물들면
   아르가 아픈 것처럼 보인다 */
const GRAY = 0.12

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255
  g /= 255
  b /= 255
  const mx = Math.max(r, g, b)
  const mn = Math.min(r, g, b)
  const l = (mx + mn) / 2
  const d = mx - mn
  if (d === 0) return [0, 0, l]
  const s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn)
  let h: number
  if (mx === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6
  else if (mx === g) h = ((b - r) / d + 2) / 6
  else h = ((r - g) / d + 4) / 6
  return [h * 360, s, l]
}

function hue2rgb(p: number, q: number, t: number): number {
  if (t < 0) t += 1
  if (t > 1) t -= 1
  if (t < 1 / 6) return p + (q - p) * 6 * t
  if (t < 1 / 2) return q
  if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
  return p
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  const hh = (((h % 360) + 360) % 360) / 360
  if (s === 0) {
    const v = Math.round(l * 255)
    return [v, v, v]
  }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s
  const p = 2 * l - q
  return [
    Math.round(hue2rgb(p, q, hh + 1 / 3) * 255),
    Math.round(hue2rgb(p, q, hh) * 255),
    Math.round(hue2rgb(p, q, hh - 1 / 3) * 255),
  ]
}

/* 색상환 구간별 매핑. 안 걸리는 구간은 그대로 둔다 (null 반환) */
function mapHs(h: number, s: number): [number, number] | null {
  if (s < GRAY) return null
  if (h >= 55 && h <= 150) return [BODY.h, Math.min(1, s * (BODY.s / 0.55))] // 몸통 초록
  if (h >= 280 || h < 25) return [HORN.h, Math.min(1, s * (HORN.s / 0.55))] // 뿔 분홍
  if (h >= 40 && h < 55) return [HORN.h + 14, Math.min(1, s * 0.9)] // 뿔 노랑 줄무늬
  return null
}

/* 픽셀 배열을 제자리에서 고친다 (RGBA) */
export function tintPixels(px: Uint8ClampedArray): void {
  for (let i = 0; i < px.length; i += 4) {
    if (px[i + 3] === 0) continue
    const [h, s, l] = rgbToHsl(px[i], px[i + 1], px[i + 2])
    const next = mapHs(h, s)
    if (next === null) continue
    const [r, g, b] = hslToRgb(next[0], next[1], l)
    px[i] = r
    px[i + 1] = g
    px[i + 2] = b
  }
}

/* 텍스처 없는 머티리얼(줄기·잎·눈꺼풀 등)의 단색에 같은 규칙을 건다.
   three.js 의 Color 를 직접 받지 않으려고 HSL 로만 주고받는다 —
   이 파일이 three 를 안 물면 테스트가 쉽다. */
export function tintHsl(h: number, s: number, l: number): [number, number, number] | null {
  const next = mapHs(h * 360, s)
  return next === null ? null : [next[0] / 360, next[1], l]
}
