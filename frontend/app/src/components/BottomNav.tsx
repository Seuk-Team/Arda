import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
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
    <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
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
    <circle cx="5" cy="12" r="1.2" />
    <circle cx="12" cy="12" r="1.2" />
    <circle cx="19" cy="12" r="1.2" />
  </>
)
const ICON_EVALUATIONS = <path d="M12 3.8l2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6-4.9 2.6.9-5.5-4-3.9 5.5-.8z" />
const ICON_SETTINGS = (
  <>
    <circle cx="12" cy="12" r="3.2" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1z" />
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
  const [moreOpen, setMoreOpen] = useState(false)
  const { logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    setMoreOpen(false)
    logout()
    navigate('/login')
  }

  return (
    <>
      {moreOpen && (
        <div className={styles.scrim} onClick={() => setMoreOpen(false)}>
          <div className={styles.sheet} onClick={e => e.stopPropagation()}>
            <NavLink to="/evaluations" className={styles.sheetLink} onClick={() => setMoreOpen(false)}>
              <Svg>{ICON_EVALUATIONS}</Svg>
              평가 현황
            </NavLink>
            <NavLink to="/postings" className={styles.sheetLink} onClick={() => setMoreOpen(false)}>
              <Svg>{ICON_POSTINGS}</Svg>
              채용 공고
            </NavLink>
            <NavLink to="/settings" className={styles.sheetLink} onClick={() => setMoreOpen(false)}>
              <Svg>{ICON_SETTINGS}</Svg>
              설정
            </NavLink>
            <button type="button" className={styles.sheetLogout} onClick={handleLogout}>
              로그아웃
            </button>
          </div>
        </div>
      )}

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
        </NavLink>
        <NavLink to="/calendar" className={({ isActive }) => `${styles.tab} ${isActive ? styles.active : ''}`}>
          <Svg>{ICON_CALENDAR}</Svg>
          <span>캘린더</span>
        </NavLink>
        <button
          type="button"
          className={`${styles.tab} ${moreOpen ? styles.active : ''}`}
          onClick={() => setMoreOpen(v => !v)}
          aria-expanded={moreOpen}
        >
          <Svg>{ICON_MORE}</Svg>
          <span>더보기</span>
        </button>
      </nav>
    </>
  )
}
