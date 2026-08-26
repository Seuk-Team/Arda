import { NavLink } from 'react-router-dom'
import styles from './Sidebar.module.css'

const NAV = [
  { to: '/dashboard', label: '대시보드' },
  { to: '/postings', label: '채용 공고' },
  { to: '/applicants', label: '지원자' },
  { to: '/evaluations', label: '평가 현황' },
  { to: '/settings', label: '설정' },
] as const

export default function Sidebar() {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.logo}>Arda</div>
      <nav className={styles.nav}>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `${styles.link} ${isActive ? styles.active : ''}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
