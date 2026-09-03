import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useToast } from '../components/Toast'
import PageHead from '../components/PageHead'
import styles from './More.module.css'

const ROLE_LABEL: Record<string, string> = { admin: '관리자', member: '팀원' }

function Icon({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={styles.icon}>
      {children}
    </svg>
  )
}

function ChevronRight() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={styles.chevron}>
      <path d="M9 18l6-6-6-6" />
    </svg>
  )
}

export default function More() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const wip = () => toast.show('ok', '준비 중인 기능입니다')

  if (!user) return null

  const initial = user.name.charAt(0)

  return (
    <main className="page-content">
      <PageHead title="더보기" />

      <div className={styles.content}>
        {/* 사용자 카드 */}
        <div className={styles.userCard}>
          <div className={styles.avatar}>{initial}</div>
          <div className={styles.userInfo}>
            <span className={styles.userName}>{user.name}</span>
            <span className={styles.userMeta}>{ROLE_LABEL[user.role] ?? user.role} · {user.email}</span>
          </div>
        </div>

        {/* 메뉴 그룹 1 */}
        <div className={styles.group}>
          <button type="button" className={styles.item} onClick={() => navigate('/evaluations')}>
            <Icon><path d="M12 3.8l2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6-4.9 2.6.9-5.5-4-3.9 5.5-.8z" /></Icon>
            <span className={styles.itemLabel}>평가 현황</span>
            <ChevronRight />
          </button>
        </div>

        {/* 메뉴 그룹 2 */}
        <div className={styles.group}>
          <button type="button" className={styles.item} onClick={() => navigate('/settings')}>
            <Icon>
              <circle cx="12" cy="12" r="3.2" />
              <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1z" />
            </Icon>
            <span className={styles.itemLabel}>설정</span>
            <ChevronRight />
          </button>
          <div className={styles.divider} />
          <button type="button" className={styles.item} onClick={wip}>
            <Icon>
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </Icon>
            <span className={styles.itemLabel}>알림</span>
            <span className={styles.itemSub}>켬</span>
            <ChevronRight />
          </button>
        </div>

        {/* 로그아웃 */}
        <div className={styles.group}>
          <button type="button" className={`${styles.item} ${styles.logout}`} onClick={handleLogout}>
            <Icon>
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </Icon>
            <span className={styles.itemLabel}>로그아웃</span>
          </button>
        </div>

        <p className={styles.version}>Arda 0.1.0</p>
      </div>
    </main>
  )
}
