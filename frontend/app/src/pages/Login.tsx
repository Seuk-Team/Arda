import { useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import BrandMark from '../components/BrandMark'
import NetworkField from '../components/NetworkField'
import LoginIntro, { introAlreadySeen } from '../components/LoginIntro'
import { useDive } from '../components/DiveTransition'
import type { SceneHandle } from '../lib/networkScene'
import styles from './Login.module.css'

interface FromState {
  from?: { pathname: string }
}

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, loading, login } = useAuth()
  const dive = useDive()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  /* 세션당 1회. 판정은 마운트 시점에 한 번만 한다 — 렌더마다 다시 물으면
     인트로가 끝나며 sessionStorage 를 쓴 직후 스스로 사라진다 */
  const [intro, setIntro] = useState(() => !introAlreadySeen())

  const stageRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<SceneHandle | null>(null)

  /* 이미 로그인된 사용자가 /login 에 오면 폼을 또 보여주지 않는다.
     pending 중엔 제외 — login() 직후 setUser 가 먼저 돌면 handleSubmit 의
     navigate 와 겹치지만 둘 다 replace 라 무해하다. */
  if (!loading && !pending && user) {
    const to = (location.state as FromState | null)?.from?.pathname ?? '/dashboard'
    return <Navigate to={to} replace />
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)
    try {
      /* 접속 시퀀스가 요청을 감싼다 — 응답을 기다리는 동안 망 속으로 파고들고
         응답이 오면 착지한다. 그래서 로딩 표시가 따로 없다 (DiveTransition). */
      await dive.run(() => login(email, password))
      // 보호 라우트가 넘겨 준 원래 목적지로. 없으면 대시보드.
      const to = (location.state as FromState | null)?.from?.pathname ?? '/dashboard'
      navigate(to, { replace: true })
      /* 도착 화면이 그려진 뒤 흰빛을 걷는다 */
      dive.clear()
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
      <NetworkField onReady={(s) => { sceneRef.current = s }} />
      {/* 가장자리를 눌러 가운데 카드를 세운다 */}
      <div className={styles.vignette} aria-hidden="true" />

      <div className={styles.stage} ref={stageRef}>
        <form className={styles.card} onSubmit={handleSubmit}>
          <div className={styles.head}>
            <h1 className={styles.logo}>
              <BrandMark size={30} halo className={styles.logoMark} />
              Arda
            </h1>
            <p className={styles.sub}>채용 관리</p>
          </div>

          <div className={styles.fields}>
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
          </div>

          <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={disabled}>
            {pending ? '로그인 중…' : '로그인'}
          </button>
        </form>
      </div>

      {intro && (
        <LoginIntro stageRef={stageRef} sceneRef={sceneRef} onDone={() => setIntro(false)} />
      )}
    </div>
  )
}
