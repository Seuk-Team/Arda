import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import styles from './Sidebar.module.css'
import BrandMark from './BrandMark'

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
  /* 접기 손잡이 — 판 하나에 심지. 방향은 CSS 가 뒤집지 않고 path 를 갈아 끼운다 */
  rail: (
    <>
      <rect x="3.5" y="4" width="17" height="16" rx="2" />
      <path d="M9.5 4v16" />
    </>
  ),
}

/* 접힘 상태는 새로고침해도 남아야 한다 — 매번 다시 접는 건 설정이 아니라 사고다 */
const RAIL_KEY = 'arda.sidebar.collapsed'

const NAV = [
  { to: '/dashboard', label: '대시보드', icon: 'dashboard' },
  { to: '/postings', label: '채용 공고', icon: 'postings' },
  { to: '/applicants', label: '지원자', icon: 'applicants' },
  { to: '/calendar', label: '캘린더', icon: 'calendar' },
  { to: '/evaluations', label: '평가 현황', icon: 'evaluations' },
  /* 설정은 우측 상단 계정 메뉴로 옮겼다 (2026-09-05) — 내비에는 일하는 화면만
     남긴다. 개인 설정 하나가 업무 화면들 사이에 껴 있던 것이 어색했다. */
] as const

/* 아르는 사이드바를 떠나 화면 우하단 도크로 갔다 (2026-09-07, Layout).
   접힌 폭 64px 에서는 정사각형이 48px 로 뭉개졌고, 접기 손잡이·내비와
   같은 좁은 열을 두고 다퉜다. 떠 있으면 폭에 안 매인다. */
export default function Sidebar() {
  /* 활성 표시를 항목이 아니라 별도 레이어로 분리한다 — 판 하나가 옮겨 붙는다 */
  const { pathname } = useLocation()
  const navRef = useRef<HTMLElement>(null)

  /* 접힘. localStorage 를 못 읽는 환경(사파리 프라이빗 등)에서도 죽지 않게 감싼다 */
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(RAIL_KEY) === '1'
    } catch {
      return false
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem(RAIL_KEY, collapsed ? '1' : '0')
    } catch {
      /* 저장 못 해도 이번 세션 동안은 접힌 채로 쓴다 */
    }
  }, [collapsed])
  const [pill, setPill] = useState<{ y: number; h: number } | null>(null)
  useLayoutEffect(() => {
    const on = navRef.current?.querySelector<HTMLElement>('[aria-current="page"]')
    setPill(on ? { y: on.offsetTop, h: on.offsetHeight } : null)
  }, [pathname])

  return (
    <aside className={`${styles.sidebar} ${collapsed ? styles.rail : ''}`}>
      <NavLink to="/dashboard" className={styles.logo} title="대시보드">
        <BrandMark size={26} className={styles.logoMark} />
        <span className={styles.logoText}>Arda</span>
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
            <span className={styles.linkText}>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* 접기 — 내비 바로 아래. 접힌 폭에서도 같은 자리에 남아야 다시 펼 수 있다 */}
      <button
        type="button"
        className={styles.railToggle}
        onClick={() => setCollapsed((v) => !v)}
        aria-label={collapsed ? '사이드바 펼치기' : '사이드바 접기'}
        title={collapsed ? '사이드바 펼치기' : '사이드바 접기'}
        aria-expanded={!collapsed}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">{ICONS.rail}</svg>
        <span className={styles.linkText}>접기</span>
      </button>

      {/* 내비가 바닥까지 밀리지 않게 남은 자리를 먹는다 — 아르가 있던 칸이다 */}
      <span className={styles.grow} aria-hidden="true" />

    </aside>
  )
}
