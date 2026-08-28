import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'
import styles from './RequireAuth.module.css'

export default function RequireAuth() {
  const { user, loading, error, retry } = useAuth()
  const location = useLocation()

  // 확인이 끝나기 전에는 아무 화면도 확정하지 않는다.
  if (loading) return null

  /* 토큰은 있는데 서버가 대답을 못 한 경우. 로그인 화면으로 보내면 사용자는
     멀쩡한 자격으로 다시 로그인을 시도하다 또 실패한다 — 무슨 일인지 말해 준다. */
  if (!user && error) {
    return (
      <div className={styles.page}>
        <div className={styles.card} role="alert">
          <p className={styles.msg}>{error.message}</p>
          <button type="button" className="btn btn-primary" onClick={retry}>다시 시도</button>
        </div>
      </div>
    )
  }

  // 로그인 뒤 원래 가려던 곳으로 되돌리려고 위치를 넘긴다.
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />

  return <Outlet />
}
