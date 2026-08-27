import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import styles from './Sidebar.module.css'
import Sprout from './Sprout'

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
  interviews: (
    <>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <path d="M3.5 9.5h17M8 3.5v3M16 3.5v3" />
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
  { to: '/interviews', label: '면접 일정', icon: 'interviews' },
  { to: '/evaluations', label: '평가 현황', icon: 'evaluations' },
  { to: '/settings', label: '설정', icon: 'settings' },
] as const

const ME = { name: '김채용', role: '채용담당자' }

export default function Sidebar() {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.logo}>Arda</div>

      <nav className={styles.nav}>
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

      {/* 아르 상주 슬롯. 에이전트 패널은 아직 React 로 안 옮겨서 자리만 잡아 둔다. */}
      <div className={styles.agent}>
        <Sprout className={styles.agentChar} />
        <span><b>아르</b></span>
      </div>

      <div className={styles.me}>
        <div>
          <div className={styles.meName}>{ME.name}</div>
          <div className={styles.meRole}>{ME.role}</div>
        </div>
        <div className={styles.avatar}>{ME.name.charAt(0)}</div>
      </div>
    </aside>
  )
}
