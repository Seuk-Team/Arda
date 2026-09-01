import { Suspense, lazy, useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode, RefObject } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import styles from './Sidebar.module.css'
import type { Motion } from './ArViewer'
import { useAuth } from '../auth/AuthContext'
import { ROLE_LABEL } from '../lib/stage'

/* three.js 가 초기 번들의 대부분이었다. 아르는 전 화면 사이드바에 상주하지만
   첫 페인트에 필요한 건 아니라 별도 청크로 뺀다 — 타입만 정적으로 가져온다. */
const ArViewer = lazy(() => import('./ArViewer'))

/* 맥은 ⌘, 나머지는 Ctrl. 라벨에만 쓰므로 userAgent 로 충분하다. */
const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
const AR_HINT = IS_MAC ? '⌘K' : 'Ctrl+K'

/* 아이콘은 mockup.html 사이드바에서 그대로 옮겼다 (§12-1 시안 복제).
   stroke·크기는 CSS 가 잡으므로 path 만 담는다. */
const ICONS: Record<string, ReactNode> = {
  dashboard: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
    </>
  ),
  postings: (
    <>
      <path d="M6 3.5h8l4 4v13H6z" />
      <path d="M14 3.5v4h4" />
      <path d="M9 12h6M9 15.5h6" />
    </>
  ),
  applicants: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.8 19.5c0-2.9 2.3-5.2 5.2-5.2s5.2 2.3 5.2 5.2" />
      <circle cx="16.8" cy="9" r="2.4" />
      <path d="M15.6 14.6c2.6.4 4.6 2.4 4.6 4.9" />
    </>
  ),
  /* 캘린더 — 월 그리드 화면이라 날짜 칸까지 그린다 (2026-08-31 메뉴 개편) */
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <path d="M3.5 9.5h17M8 3.5v3M16 3.5v3" />
      <path d="M7.5 13h2M11 13h2M14.5 13h2M7.5 16.5h2M11 16.5h2" />
    </>
  ),
  evaluations: <path d="M12 3.8l2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6-4.9 2.6.9-5.5-4-3.9 5.5-.8z" />,
  settings: (
    <>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1z" />
    </>
  ),
}

const NAV = [
  { to: '/dashboard', label: '대시보드', icon: 'dashboard' },
  { to: '/postings', label: '채용 공고', icon: 'postings' },
  { to: '/applicants', label: '지원자', icon: 'applicants' },
  { to: '/calendar', label: '캘린더', icon: 'calendar' },
  { to: '/evaluations', label: '평가 현황', icon: 'evaluations' },
  { to: '/settings', label: '설정', icon: 'settings' },
] as const

interface Props {
  /* 아르 패널 열림 여부 — 정사각형 버튼의 눌린 상태를 이걸로 그린다 */
  arOpen: boolean
  arMotion: Motion
  onToggleAr: () => void
  onArHover: (hovered: boolean) => void
  arButtonRef: RefObject<HTMLButtonElement | null>
}

export default function Sidebar({ arOpen, arMotion, onToggleAr, onArHover, arButtonRef }: Props) {
  /* 목업 상수를 실데이터로 교체. user 가 아직 없으면(부트스트랩 중) 스켈레톤 — §6 */
  const { user } = useAuth()

  /* 활성 표시(흰 판)를 항목이 아니라 별도 레이어로 분리한다. 화면 전환 중에는
     이 판이 다음 메뉴로 미끄러져 이동한다 (MorphNav 가 body[data-morph] 를 켠 동안만).
     평소에는 transition 이 없어 지금처럼 즉시 옮겨 붙는다. */
  const { pathname } = useLocation()
  const navRef = useRef<HTMLElement>(null)
  const [pill, setPill] = useState<{ y: number; h: number } | null>(null)
  /* 아르 칸에 커서·포커스가 올라와 있는 동안만 아르가 커서를 따라본다.
     onArHover 는 모션(listen)용이라 Layout 이 갖고 있고, 이건 뷰어에만 필요해 여기 둔다. */
  const [arHover, setArHover] = useState(false)

  useLayoutEffect(() => {
    const on = navRef.current?.querySelector<HTMLElement>('[aria-current="page"]')
    setPill(on ? { y: on.offsetTop, h: on.offsetHeight } : null)
  }, [pathname])

  return (
    <aside className={styles.sidebar}>
      <NavLink to="/dashboard" className={styles.logo}>
        Arda
      </NavLink>

      <nav className={styles.nav} ref={navRef}>
        {pill !== null && (
          <span
            className={styles.navPill}
            aria-hidden="true"
            style={{ height: pill.h, transform: `translateY(${pill.y}px)` }}
          />
        )}
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ''}`}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">{ICONS[item.icon]}</svg>
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* 아르 상주 슬롯 — 정사각형 전체가 에이전트 패널 토글 버튼이다 (ADR-0009 개정). */}
      <button
        ref={arButtonRef}
        type="button"
        className={styles.arSlot}
        onClick={onToggleAr}
        onMouseEnter={() => { onArHover(true); setArHover(true) }}
        onMouseLeave={() => { onArHover(false); setArHover(false) }}
        onFocus={() => { onArHover(true); setArHover(true) }}
        onBlur={() => { onArHover(false); setArHover(false) }}
        aria-label={`아르 에이전트 ${arOpen ? '닫기' : '열기'} (${AR_HINT})`}
        title={`아르 에이전트 ${arOpen ? '닫기' : '열기'} (${AR_HINT})`}
        aria-expanded={arOpen}
        aria-controls="ar-panel"
      >
        {/* 폴백은 같은 크기의 빈 칸 — 청크가 늦게 와도 정사각형이 흔들리지 않는다 */}
        <Suspense fallback={<span className={styles.arView} />}>
          {/* 커서가 이 칸 위에 있을 때만 따라본다. 벗어나면 정면으로 돌아온다 */}
          <ArViewer className={styles.arView} motion={arMotion} track={arHover} />
        </Suspense>
      </button>

      {/* 표시 전용 — 클릭 진입은 두지 않는다 (팀장 결정 2026-08-31) */}
      <div className={styles.me}>
        {user ? (
          <>
            <div className={styles.meText}>
              <div className={styles.meName}>{user.name}</div>
              <div className={styles.meRole}>{ROLE_LABEL[user.role]}</div>
            </div>
            <div className={styles.avatar} aria-hidden="true">
              {user.name.charAt(0)}
            </div>
          </>
        ) : (
          /* 부트스트랩 중이거나 사용자를 못 받은 상태. 목업 이름을 대신 쓰지 않는다. */
          <>
            <div className={styles.meText}>
              <div className={`${styles.meName} ${styles.skel}`} />
              <div className={`${styles.meRole} ${styles.skel} ${styles.skelShort}`} />
            </div>
            <div className={`${styles.avatar} ${styles.skel}`} />
          </>
        )}
      </div>
    </aside>
  )
}
