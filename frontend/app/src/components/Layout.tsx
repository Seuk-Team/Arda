import { useCallback, useEffect, useRef, useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import Sidebar from './Sidebar'
import ArPanel, { type ArMotion } from './ArPanel'
import MorphNav from './MorphNav'
import { useRightPanel } from './RightPanel'
import { useAuth } from '../auth/AuthContext'
import type { Motion } from './ArViewer'
import styles from './Layout.module.css'

export default function Layout() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  /* 열림 상태는 오른쪽 패널 한 자리를 나눠 쓰는 쪽들이 같이 본다 (RightPanel) */
  const { active, toggle, close } = useRightPanel()
  const arOpen = active === 'ar'
  /* 마운트 직후 enter 를 1회 재생하고 ArViewer 가 알아서 idle 로 돌아온다.
     이후 값은 ArChat 이 onMotion 으로 밀어 넣는다. */
  const [motion, setMotion] = useState<Motion>('enter')
  const [arHovered, setArHovered] = useState(false)
  const arButtonRef = useRef<HTMLButtonElement>(null)

  /* hover 반응은 쉬고 있을 때만 — 채팅이 돌고 있으면 그 모션을 덮지 않는다 */
  const shownMotion: Motion = motion === 'idle' && arHovered ? 'listen' : motion

  const toggleAr = useCallback(() => toggle('ar'), [toggle])
  const closeAr = useCallback(() => close('ar'), [close])
  const onMotion = useCallback((m: ArMotion) => setMotion(m), [])

  /* 전역 Ctrl+K (맥 ⌘K) — ADR-0009 가 확정한 진입점.
     입력창 안에서도 먹어야 해서 대상 필터를 두지 않고, 브라우저 기본 동작(검색 바 등)은 막는다.
     Esc 닫기는 ArPanel 이 맡는다. */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return
      if (e.key.toLowerCase() !== 'k') return
      e.preventDefault()
      toggle('ar')
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [toggle])

  return (
    /* 화면 전환(대시보드 축소판 → 캘린더)은 라우트 밖에서 살아 있어야 한다 —
       떠나는 화면이 언마운트된 뒤에도 도형이 남아 이어져야 하기 때문 */
    <MorphNav>
      <div className={styles.shell}>
        <Sidebar
          arOpen={arOpen}
          arMotion={shownMotion}
          onToggleAr={toggleAr}
          onArHover={setArHovered}
          arButtonRef={arButtonRef}
        />
        {/* 전환이 페이드아웃·페이드인 대상으로 잡는 본문 껍데기 */}
        <main className={styles.main} data-morph-shell="">
          <button type="button" className={styles.logoutBtn} onClick={handleLogout}>
            로그아웃
          </button>
          <Outlet />
        </main>
        {/* 2026-09-01 — 사이드바 옆(왼쪽)에서 화면 오른쪽 끝으로 옮겼다 */}
        <ArPanel open={arOpen} onClose={closeAr} onMotion={onMotion} triggerRef={arButtonRef} />
      </div>
    </MorphNav>
  )
}
