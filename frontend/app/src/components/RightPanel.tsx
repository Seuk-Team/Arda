import { createContext, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

/* 화면 오른쪽에 서는 패널은 한 번에 하나다 (2026-09-01).
   아르 에이전트·캘린더의 그날 일정·지원자 상세·평가 패널이 모두 오른쪽 끝을 쓰는데, 각자 상태를
   들고 있으면 동시에 열려 나란히 붙는다. 어느 것이 열려 있는지를 여기 한 곳에
   두고 나중에 연 쪽이 이기게 한다.

   아르는 닫아도 언마운트하지 않는다 — 대화 이력이 날아가므로 open=false 로
   폭 0 + inert 가 될 뿐이다 (SidePanel rail). */

export type RightPanelId = 'ar' | 'day' | 'applicant' | 'evaluation'

interface RightPanel {
  active: RightPanelId | null
  open: (id: RightPanelId) => void
  /* 같은 것을 다시 부르면 닫는다 */
  toggle: (id: RightPanelId) => void
  /* 자기 것일 때만 닫는다 — 이미 다른 패널로 넘어갔으면 건드리지 않는다 */
  close: (id: RightPanelId) => void
}

const Ctx = createContext<RightPanel | null>(null)

export function useRightPanel(): RightPanel {
  const ctx = useContext(Ctx)
  if (ctx === null) throw new Error('useRightPanel 은 RightPanelProvider 안에서만 쓴다')
  return ctx
}

export function RightPanelProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<RightPanelId | null>(null)

  const value = useMemo<RightPanel>(() => ({
    active,
    open: (id) => setActive(id),
    toggle: (id) => setActive((cur) => (cur === id ? null : id)),
    close: (id) => setActive((cur) => (cur === id ? null : cur)),
  }), [active])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
