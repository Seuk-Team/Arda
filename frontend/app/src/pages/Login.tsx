import { useRef, useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError, setApplicantToken } from '../api/client'
import { applicantAuth } from '../api/endpoints'
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

/* 담당자와 지원자는 **저장소도 도착지도 다르다** — 담당자는 직원 JWT 로
   대시보드, 지원자는 지원자 토큰으로 /my 다. 섞이면 남의 신분으로 요청이
   나간다(앱 주석과 같은 이유). */
type Role = 'staff' | 'applicant'

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, loading, login } = useAuth()
  const dive = useDive()

  /* **담당자가 기본이다** — 이 화면을 매일 켜는 사람이 담당자다. 지원자는
     메일 링크로 들어오거나 한 번 고르고 나면 /my 가 토큰을 기억한다(앱과 같은
     판단: mobile/lib/screens/login_screen.dart). */
  const [role, setRole] = useState<Role>('staff')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  /* 생년월일 8자리 — 지원자 칸에서만 쓴다 */
  const [birth, setBirth] = useState('')
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

    if (role === 'applicant') {
      try {
        const res = await applicantAuth.login(email.trim(), birth)
        setApplicantToken(res.access_token)
        navigate('/my', { replace: true })
      } catch (err) {
        /* **사유를 지어내지 않는다.** 없는 이메일·틀린 생년월일·생년월일이
           없는 옛 지원서가 전부 같은 401 인 것이 서버의 설계다 — 화면이
           "그런 이메일이 없습니다"라고 쓰면 지원 사실 자체가 새어 나간다. */
        setError(err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요')
        setPending(false)
      }
      return
    }

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

  /* 칸을 옮기면 실패 문구를 지운다 — 담당자 칸의 "비밀번호가 맞지 않습니다"가
     지원자 칸에 남아 있으면 방금 친 생년월일이 틀린 줄로 읽힌다 */
  function pickRole(next: Role) {
    if (next === role) return
    setRole(next)
    setError(null)
  }

  const disabled =
    pending ||
    email.trim() === '' ||
    (role === 'staff' ? password.trim() === '' : birth.length !== 8)

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
            <p className={styles.sub}>
              {role === 'staff' ? '채용 관리' : '내 지원 현황'}
            </p>
          </div>

          {/* 탭바가 아니라 선택이다 — 좌우로 넘기면 치던 입력이 사라진다 */}
          <div className={styles.roles} role="tablist" aria-label="로그인 종류">
            <button
              type="button"
              role="tab"
              aria-selected={role === 'staff'}
              className={`${styles.role} ${role === 'staff' ? styles.roleOn : ''}`}
              onClick={() => pickRole('staff')}
              disabled={pending}
            >
              담당자
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={role === 'applicant'}
              className={`${styles.role} ${role === 'applicant' ? styles.roleOn : ''}`}
              onClick={() => pickRole('applicant')}
              disabled={pending}
            >
              지원자
            </button>
          </div>

          <div className={styles.fields}>
            <label className={styles.label}>
              이메일
              <input
                className={styles.input}
                type="email"
                autoComplete={role === 'staff' ? 'username' : 'email'}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={role === 'staff' ? 'name@company.com' : '지원할 때 쓴 이메일'}
                disabled={pending}
              />
            </label>

            {role === 'staff' ? (
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
            ) : (
              <label className={styles.label}>
                생년월일 8자리
                <input
                  className={`${styles.input} ${styles.birth}`}
                  /* 비밀번호 자리라 가린다(앱과 같다). type=number 는 앞자리 0 이
                     사라져 못 쓰고, inputMode 로 폰에서 숫자 자판을 띄운다 */
                  type="password"
                  inputMode="numeric"
                  maxLength={8}
                  autoComplete="off"
                  value={birth}
                  onChange={(e) => setBirth(e.target.value.replace(/\D/g, ''))}
                  placeholder="예: 19980315"
                  disabled={pending}
                />
              </label>
            )}

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
