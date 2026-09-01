/* 아르 캐릭터 아이콘.
   원래는 mockup.html 의 .agchar SVG 였는데, 사이드바에 3D 아르(ArViewer)가 들어온
   뒤로 같은 캐릭터가 자리마다 다른 그림이 됐다. 2026-09-01 에 3D 를 정면으로 한 장
   렌더해 박제한 PNG 로 통일했다 (§3 동종 요소 동일 규격).

   왜 3D 를 그대로 안 쓰나: 아르 말풍선마다 아이콘이 하나씩 붙는다. ArViewer 는
   인스턴스마다 WebGL 컨텍스트를 하나씩 잡아서 말풍선 열 개면 컨텍스트 열 개다 —
   브라우저 한도(보통 8~16)에 바로 걸린다. 정지 그림 하나면 몇 개를 붙이든 같다.

   원본은 public/ar.glb 이고 뽑는 법은 /dev/ar 에서 캔버스를 96×96 으로 잘라 저장. */
export default function Sprout({ className }: { className?: string }) {
  return <img className={className} src="/ar-icon.png" alt="" aria-hidden="true" />
}
