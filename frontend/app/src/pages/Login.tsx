import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import styles from './Login.module.css'

interface FromState {
  from?: { pathname: string }
}

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    try {
      await login(email, password)
      // 보호 라우트가 넘겨 준 원래 목적지로. 없으면 대시보드.
      const to = (location.state as FromState | null)?.from?.pathname ?? '/dashboard'
      navigate(to, { replace: true })
    } catch (err) {
      /* 401 은 서버 문구("이메일 또는 비밀번호가...")를 그대로 보여 준다 —
         어느 쪽이 틀렸는지 화면이 추측하면 계정 존재 여부가 새어 나간다. */
      setError(err instanceof ApiError ? err.message : '로그인하지 못했습니다')
      setPending(false)
    }
  }

  const disabled = pending || email.trim() === '' || password.trim() === ''

  return (
    <div className={styles.page}>
      <form className={styles.card} onSubmit={handleSubmit}>
        <h1 className={styles.logo}><span className={styles.seed}>A</span>rda</h1>

        <label className={styles.label}>
          이메일
          <input
            className={styles.input}
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@company.com"
            disabled={pending}
          />
        </label>

        <label className={styles.label}>
          비밀번호
          <input
            className={styles.input}
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호"
            disabled={pending}
          />
        </label>

        {error && <p className={styles.error} role="alert">{error}</p>}

        <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={disabled}>
          {pending ? '로그인 중…' : '로그인'}
        </button>
      </form>
    </div>
  )
}
