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

  return (
    <div className={styles.page}>
      <form className={styles.card} onSubmit={handleSubmit}>
        <h1 className={styles.logo}>Arda</h1>
        <p className={styles.sub}>채용 관리 시스템</p>

        <label className={styles.label}>
          이메일
          <input
            className={styles.input}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="name@company.com"
            required
          />
        </label>

        <label className={styles.label}>
          비밀번호
          <input
            className={styles.input}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호 입력"
            required
          />
        </label>

        <button type="submit" className="btn btn-primary" style={{ width: '100%', marginTop: 8 }}>
          로그인
        </button>
      </form>
    </div>
  )
}
