import { useCallback, useEffect, useRef, useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import ArPanel, { type ArMotion } from './ArPanel'
import type { Motion } from './ArViewer'
import styles from './Layout.module.css'

export default function Layout() {
  const [arOpen, setArOpen] = useState(false)
  /* 마운트 직후 enter 를 1회 재생하고 ArViewer 가 알아서 idle 로 돌아온다.
     이후 값은 ArChat 이 onMotion 으로 밀어 넣는다. */
  const [motion, setMotion] = useState<Motion>('enter')
  const [arHovered, setArHovered] = useState(false)
  const arButtonRef = useRef<HTMLButtonElement>(null)

  /* hover 반응은 쉬고 있을 때만 — 채팅이 돌고 있으면 그 모션을 덮지 않는다 */
  const shownMotion: Motion = motion === 'idle' && arHovered ? 'listen' : motion

  const toggleAr = useCallback(() => setArOpen((v) => !v), [])
  const closeAr = useCallback(() => setArOpen(false), [])
  const onMotion = useCallback((m: ArMotion) => setMotion(m), [])

  /* 전역 Ctrl+K (맥 ⌘K) — ADR-0009 가 확정한 진입점.
     입력창 안에서도 먹어야 해서 대상 필터를 두지 않고, 브라우저 기본 동작(검색 바 등)은 막는다.
     Esc 닫기는 ArPanel 이 맡는다. */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return
      if (e.key.toLowerCase() !== 'k') return
      e.preventDefault()
      setArOpen((v) => !v)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className={styles.shell}>
      <Sidebar
        arOpen={arOpen}
        arMotion={shownMotion}
        onToggleAr={toggleAr}
        onArHover={setArHovered}
        arButtonRef={arButtonRef}
      />
      <ArPanel open={arOpen} onClose={closeAr} onMotion={onMotion} triggerRef={arButtonRef} />
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}
