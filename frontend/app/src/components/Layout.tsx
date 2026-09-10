import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import BottomNav from './BottomNav'
import ArPanel, { type ArMotion } from './ArPanel'
import { useRightPanel } from './RightPanel'
import type { Motion } from './ArViewer'
import styles from './Layout.module.css'

/* three.js 가 초기 번들의 대부분이었다. 아르는 전 화면에 상주하지만 첫 페인트에
   필요한 건 아니라 별도 청크로 뺀다 — 타입만 정적으로 가져온다. */
const ArViewer = lazy(() => import('./ArViewer'))

/* 맥은 ⌘, 나머지는 Ctrl. 라벨에만 쓰므로 userAgent 로 충분하다. */
const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const AR_HINT = IS_MAC ? '⌘K' : 'Ctrl+K'

export default function Layout() {
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
    <div className={styles.shell}>
      <Sidebar />
      <main className={styles.main}>
        <Outlet />
      </main>

      {/* 아르 — 화면 좌하단 상주 (2026-09-10, 우하단에서 옮김).
          사이드바 정사각형에서 떼어낸 것은 그대로다: 접힌 폭(64px)에서
          정사각형이 뭉개졌고 좁은 열을 내비와 다퉜다. 떠 있으면 폭에 안 매인다.
          원 전체가 패널 토글이다 (ADR-0009 개정). */}
      <button
        ref={arButtonRef}
        type="button"
        className={styles.arDock}
        onClick={toggleAr}
        onMouseEnter={() => setArHovered(true)}
        onMouseLeave={() => setArHovered(false)}
        onFocus={() => setArHovered(true)}
        onBlur={() => setArHovered(false)}
        aria-label={`아르 에이전트 ${arOpen ? '닫기' : '열기'} (${AR_HINT})`}
        title={`아르 에이전트 ${arOpen ? '닫기' : '열기'} (${AR_HINT})`}
        aria-expanded={arOpen}
        aria-controls="ar-panel"
      >
        {/* 폴백은 같은 크기의 빈 칸 — 청크가 늦게 와도 원이 흔들리지 않는다 */}
        <Suspense fallback={<span className={styles.arView} />}>
          {/* 커서가 이 원 위에 있을 때만 따라본다. 벗어나면 정면으로 돌아온다 */}
          <ArViewer className={styles.arView} motion={shownMotion} track={arHovered} />
        </Suspense>
      </button>
      {/* 단축키 안내 — 아르 옆에 조용히. ⌘K 는 ADR-0009 가 정한 진입점이다.
          열려 있는 동안은 감춘다: 여는 방법을 알려 주는 글자라 이미 열렸으면 할 말이 없다 */}
      {!arOpen && <span className={`n ${styles.arHint}`} aria-hidden="true">{AR_HINT}</span>}
      {/* 2026-09-01 — 사이드바 옆(왼쪽)에서 화면 오른쪽 끝으로 옮겼다 */}
      <ArPanel open={arOpen} onClose={closeAr} onMotion={onMotion} triggerRef={arButtonRef} />
      <BottomNav />
    </div>
  )
}
