import { useId } from 'react'

/* Arda 워드마크의 그림 부분.
   노드 다섯 개와 그 연결선이 이루는 형태가 곧 A 다 — 네트워크이면서 이니셜이다.
   색은 배경 노드망의 팔레트(시안 → 블루 → 바이올렛)를 그대로 세로로 흘린다.

   2026-09-04 — 새싹 타일을 대신한다. 타일은 세 가지가 어긋나 있었다: 의미(유기체
   vs 데이터망), 색온도(웜 옐로우그린 vs 쿨 네온), 재질(화면의 모든 것이 빛인데
   타일만 불투명한 사각형).

   그라데이션 id 는 useId 로 뽑는다 — 사이드바와 로그인에 동시에 서면 문서 안에
   같은 id 가 둘이 되고, SVG 는 먼저 나온 것만 참조해 하나가 검게 죽는다. */
export default function BrandMark({
  size = 28,
  halo = false,
  className,
}: {
  size?: number
  /* 뒤에 깔리는 발광. 배경이 어두운 로그인 화면에서만 쓴다 —
     사이드바는 이미 유리 위라 헤일로까지 얹으면 번진다 */
  halo?: boolean
  className?: string
}) {
  const uid = useId()
  const net = `arda-net-${uid}`
  const glow = `arda-halo-${uid}`

  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 28 28"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={net} x1="14" y1="3" x2="14" y2="25.5" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#67E8F9" />
          <stop offset=".52" stopColor="#60A5FA" />
          <stop offset="1" stopColor="#A78BFA" />
        </linearGradient>
        {halo && (
          <radialGradient id={glow} cx=".5" cy=".5" r=".5">
            <stop offset="0" stopColor="#7DD3FC" stopOpacity=".42" />
            <stop offset=".55" stopColor="#60A5FA" stopOpacity=".12" />
            <stop offset="1" stopColor="#60A5FA" stopOpacity="0" />
          </radialGradient>
        )}
      </defs>
      {halo && <circle cx="14" cy="15" r="14" fill={`url(#${glow})`} />}
      <path
        d="M14 5.6 L9.6 16 M9.6 16 L5.4 22.5 M14 5.6 L18.4 16 M18.4 16 L22.6 22.5 M9.6 16 L18.4 16"
        stroke={`url(#${net})`}
        strokeWidth="1.5"
        strokeLinecap="round"
        opacity=".9"
      />
      {/* 꼭짓점 노드 — 심을 흰빛으로 올려 배경의 노드와 같은 재질로 읽히게 한다 */}
      <circle cx="14" cy="5.6" r="2.9" fill={`url(#${net})`} />
      <circle cx="14" cy="5.6" r="1.15" fill="#fff" />
      <circle cx="5.4" cy="22.5" r="2.2" fill={`url(#${net})`} />
      <circle cx="22.6" cy="22.5" r="2.2" fill={`url(#${net})`} />
      {halo && <circle cx="5.4" cy="22.5" r=".85" fill="#fff" />}
      {halo && <circle cx="22.6" cy="22.5" r=".85" fill="#fff" />}
      <circle cx="9.6" cy="16" r="1.9" fill={`url(#${net})`} />
      <circle cx="18.4" cy="16" r="1.9" fill={`url(#${net})`} />
    </svg>
  )
}
