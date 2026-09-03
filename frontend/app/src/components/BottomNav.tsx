import { NavLink } from 'react-router-dom'
import styles from './BottomNav.module.css'

const ICON_POSTINGS = (
  <>
    <path d="M6 3.5h8l4 4v13H6z" />
    <path d="M14 3.5v4h4" />
    <path d="M9 12h6M9 15.5h6" />
  </>
)
const ICON_APPLICANTS = (
  <>
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3.8 19.5c0-2.9 2.3-5.2 5.2-5.2s5.2 2.3 5.2 5.2" />
    <circle cx="16.8" cy="9" r="2.4" />
    <path d="M15.6 14.6c2.6.4 4.6 2.4 4.6 4.9" />
  </>
)
const ICON_HOME = (
  <>
    <path d="M3 10.5L12 3l9 7.5V20a1 1 0 0 1-1 1H15v-5h-6v5H4a1 1 0 0 1-1-1z" />
  </>
)
const ICON_CALENDAR = (
  <>
    <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
    <path d="M3.5 9.5h17M8 3.5v3M16 3.5v3" />
    <path d="M7.5 13h2M11 13h2M14.5 13h2M7.5 16.5h2M11 16.5h2" />
  </>
)
const ICON_MORE = (
  <>
    <line x1="4" y1="7" x2="20" y2="7" />
    <line x1="4" y1="12" x2="20" y2="12" />
    <line x1="4" y1="17" x2="20" y2="17" />
  </>
)

function Svg({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  )
}

export default function BottomNav() {
  return (
    <nav className={styles.bar} aria-label="하단 내비게이션">
      <NavLink to="/postings" className={({ isActive }) => `${styles.tab} ${isActive ? styles.active : ''}`}>
        <Svg>{ICON_POSTINGS}</Svg>
        <span>공고</span>
      </NavLink>
      <NavLink to="/applicants" className={({ isActive }) => `${styles.tab} ${isActive ? styles.active : ''}`}>
        <Svg>{ICON_APPLICANTS}</Svg>
        <span>지원자</span>
      </NavLink>
      <NavLink to="/dashboard" className={({ isActive }) => `${styles.homeTab} ${isActive ? styles.homeActive : ''}`}>
        <Svg>{ICON_HOME}</Svg>
        <span>홈</span>
      </NavLink>
      <NavLink to="/calendar" className={({ isActive }) => `${styles.tab} ${isActive ? styles.active : ''}`}>
        <Svg>{ICON_CALENDAR}</Svg>
        <span>캘린더</span>
      </NavLink>
      <NavLink to="/more" className={({ isActive }) => `${styles.tab} ${isActive ? styles.active : ''}`}>
        <Svg>{ICON_MORE}</Svg>
        <span>더보기</span>
      </NavLink>
    </nav>
  )
}
