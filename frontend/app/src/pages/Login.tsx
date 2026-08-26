import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import styles from './Login.module.css'

export default function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    navigate('/postings')
  }

  const disabled = email.trim() === '' || password.trim() === ''

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
          />
        </label>

        <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={disabled}>
          로그인
        </button>
      </form>
    </div>
  )
}
