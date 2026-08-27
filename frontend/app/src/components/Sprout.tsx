/* 아르 캐릭터. mockup.html 의 .agchar SVG 를 그대로 옮겼다.
   모션(listen·think·confirm 등)은 에이전트 패널과 함께 옮긴다 — 지금은 정지 상태. */
export default function Sprout({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" role="img" aria-hidden="true">
      <circle cx="12" cy="15" r="7" fill="var(--sprout)" />
      <path d="M12 8 C 12 4, 8 3, 6 4 C 7 7, 10 8, 12 8" fill="var(--leaf)" />
      <path d="M12 8 C 12 5, 16 3.5, 18 4.5 C 17 7.5, 13 8, 12 8" fill="var(--sprout)" />
      <circle cx="9.5" cy="14.5" r="1" fill="var(--text)" />
      <circle cx="14.5" cy="14.5" r="1" fill="var(--text)" />
      <path d="M10 17.5 q2 1.5 4 0" stroke="var(--text)" strokeWidth="1" fill="none" strokeLinecap="round" />
    </svg>
  )
}
