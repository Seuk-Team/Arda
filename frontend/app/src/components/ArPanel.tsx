/* 아르 에이전트 패널. ADR-0009 개정(2026-08-31) — 화면 우측이 아니라
   좌측 사이드바 바로 오른쪽에 붙는 "두 번째 사이드바"다.
   사이드바 하단 3D 정사각형이 오른쪽으로 늘어나 패널이 되는 확장으로 읽힌다.
   껍데기(폭·테두리·닫기·Esc·포커스 복원)는 SidePanel(variant="rail")이,
   본문(채팅)은 ArChat.tsx(다른 오너)가 채운다 — 여기는 둘을 잇기만 한다. */
import type { RefObject } from 'react'
import SidePanel from './SidePanel'
import ArChat, { type ArMotion } from './ArChat'

export type { ArMotion }

interface Props {
  open: boolean
  onClose: () => void
  /* 채팅 상태 → 사이드바 정사각형 안 아르의 모션 */
  onMotion: (motion: ArMotion) => void
  /* 닫을 때 포커스를 되돌릴 곳 (사이드바의 아르 정사각형 버튼) */
  triggerRef: RefObject<HTMLButtonElement | null>
}

export default function ArPanel({ open, onClose, onMotion, triggerRef }: Props) {
  return (
    <SidePanel
      variant="rail"
      id="ar-panel"
      open={open}
      onClose={onClose}
      label="아르 에이전트"
      title="아르"
      subtitle="에이전트"
      closeLabel="아르 패널 닫기"
      triggerRef={triggerRef}
    >
      {/* 초기 포커스는 채팅 입력창 — 열자마자 바로 시킬 수 있어야 한다(focusOn).
          닫혀도 언마운트하지 않는다: 언마운트하면 대화 이력이 날아간다.
          폭 0 + overflow hidden 으로 가려지고, inert 가 포커스·클릭을 막는다. */}
      <ArChat onMotion={onMotion} focusOn={open} />
    </SidePanel>
  )
}
