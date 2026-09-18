import { useEffect, useRef, useState } from 'react'
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

  /* **담당자가 기본이다** — 이 화면을 매일 켜는 사람이 담당자다(앱과 같은
     판단: mobile/lib/screens/login_screen.dart).

     예외는 `?as=applicant` 다. /my 가 토큰 없이 열렸거나 지원자가 로그아웃하면
     여기로 보내는데, 그때 담당자 칸이 떠 있으면 **방금 나간 사람이 남의 칸을
     보게 된다**(2026-09-14). */
  const [role, setRole] = useState<Role>(() =>
    new URLSearchParams(window.location.search).get('as') === 'applicant'
      ? 'applicant'
      : 'staff',
  )

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  /* 생년월일 8자리 — 지원자 칸에서만 쓴다 */
  const [birth, setBirth] = useState('')

  /* 지원자가 무엇으로 들어오는가 (2026-09-16).

     **생년월일이 계속 기본이다** — 지금 지원자는 대부분 비밀번호가 없다.
     그래도 「비밀번호로 로그인」을 **늘 보이게** 둔다: 비밀번호를 정한 계정은
     생년월일로 401 인데 그 문구가 공통이라(서버가 일부러 안 나눈다) 화면이
     이유를 알려 줄 수 없다. 길이 늘 보이면 스스로 찾을 수 있고, 늘 보이므로
     아무것도 새어 나가지 않는다. */
  const [applicantMode, setApplicantMode] = useState<'birth' | 'password'>('birth')

  /* 「비밀번호 설정 링크 받기」 — 페이지를 따로 파지 않는다. 칸이 이메일
     하나뿐이라 여기 접었다 펴는 것으로 충분하다 */
  const [setupOpen, setSetupOpen] = useState(false)
  const [setupSent, setSetupSent] = useState(false)
  const [setupPending, setSetupPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  /* 세션당 1회. 판정은 마운트 시점에 한 번만 한다 — 렌더마다 다시 물으면
     인트로가 끝나며 sessionStorage 를 쓴 직후 스스로 사라진다 */
  const [intro, setIntro] = useState(() => !introAlreadySeen())

  const stageRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<SceneHandle | null>(null)

  /* 심사자 자동 로그인 (박제 온프레미스 전용 · 2026-09-16).
     페이지 안 버튼 · URL 쿼리 두 방식 지원.
     담당자 시연 계정은 `ab@ab.com` (admin) — 백엔드 `DEMO_LOCKED_EMAILS` 에 올라 있어
     비밀번호 변경·비활성화·역할 변경이 막힌다. 심사위원이 건드려도 자동 로그인이 안 깨진다. */
  async function demoLoginStaff() {
    try {
      setError(null)
      setPending(true)
      await login('ab@ab.com', 'abc123!@#')
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '자동 로그인 실패')
      setPending(false)
    }
  }
  async function demoLoginApplicant() {
    try {
      setError(null)
      setRole('applicant')
      setPending(true)
      /* 지원자 시연 = 실제 데이터가 있는 합격자 한 명 (2026-09-16 프로덕션 덤프 기준):
         조민석 · 백엔드 공고 · 서류 pass 84점 · 이력서 2건 · AI 요약 · 면접 세션 있음.
         심사위원이 사전 성향 설문·면접 흐름을 그대로 볼 수 있어야 해서 빈 계정을 안 쓴다. */
      const res = await applicantAuth.login('fitcheck-be-01@example.com', '19950101')
      setApplicantToken(res.access_token)
      navigate('/my', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '자동 로그인 실패')
      setPending(false)
    }
  }
  const demoTriggered = useRef(false)
  useEffect(() => {
    if (demoTriggered.current) return
    const demo = new URLSearchParams(window.location.search).get('demo')
    if (!demo) return
    demoTriggered.current = true
    if (demo === 'staff') demoLoginStaff()
    else if (demo === 'applicant') demoLoginApplicant()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* 이미 로그인된 사용자가 /login 에 오면 폼을 또 보여주지 않는다.
     pending 중엔 제외 — login() 직후 setUser 가 먼저 돌면 handleSubmit 의
     navigate 와 겹치지만 둘 다 replace 라 무해하다. */
  /* 담당자가 이미 로그인돼 있으면 폼을 또 보여주지 않는다.

     **단 `?as=applicant` 로 온 사람은 예외다** — 담당자가 로그인해 둔 브라우저
     에서는 지원자가 자기 현황을 볼 길이 아예 없어진다(2026-09-14). */
  if (!loading && !pending && user && role !== 'applicant') {
    const to = (location.state as FromState | null)?.from?.pathname ?? '/dashboard'
    return <Navigate to={to} replace />
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setPending(true)

    if (role === 'applicant') {
      try {
        const res =
          applicantMode === 'password'
            ? await applicantAuth.loginWithPassword(email.trim(), password)
            : await applicantAuth.login(email.trim(), birth)
        setApplicantToken(res.access_token)
        navigate('/my', { replace: true })
      } catch (err) {
        /* **사유를 지어내지 않는다.** 없는 이메일·틀린 생년월일·생년월일이
           없는 옛 지원서가 전부 같은 401 인 것이 서버의 설계다 — 화면이
           "그런 이메일이 없습니다"라고 쓰면 지원 사실 자체가 새어 나간다.

           2026-09-16: **「비밀번호를 정하셨네요」도 마찬가지로 못 쓴다.**
           비밀번호를 정한 계정이 생년월일로 들어오면 같은 401 인데, 화면이
           그걸 갈라 말하면 서버가 감춘 것을 드러내는 꼴이다. */
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
    /* 칸을 옮기면 설정 패널도 접는다 — 담당자 칸에 지원자용 안내가 남아 있으면
       담당자가 자기 것인 줄 안다 */
    setSetupOpen(false)
    setSetupSent(false)
  }

  /* 비밀번호 설정 링크를 메일로 보낸다.

     **결과에 따라 문구를 가르지 않는다.** 서버가 지원 이력이 없어도 202 를
     주는 것과 같은 이유다 — "그 이메일은 없습니다"라고 하면 이 화면이 "이
     사람이 여기 지원했나"를 떠보는 도구가 된다(ADR-0033). */
  async function sendSetupLink() {
    const to = email.trim()
    if (to === '' || setupPending) return
    setSetupPending(true)
    setError(null)
    try {
      await applicantAuth.requestPasswordSetup(to)
    } catch {
      /* 실패해도 같은 화면을 보여 준다. 여기서 갈라 말하면 위 원칙이 깨진다 —
         정말 못 보냈으면 지원자는 메일이 안 오는 것으로 알게 되고, 다시
         누르면 된다 */
    } finally {
      setSetupPending(false)
      setSetupSent(true)
    }
  }

  const disabled =
    pending ||
    email.trim() === '' ||
    (role === 'staff'
      ? password.trim() === ''
      : applicantMode === 'password'
        ? password.trim() === ''
        : birth.length !== 8)

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
            ) : applicantMode === 'password' ? (
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

            {/* 지원자 칸에만 — 두 갈래를 오가는 길과 링크 받는 길.
                **늘 보인다**: 401 이 왜 났는지 화면이 말해 줄 수 없으므로
                (서버가 사유를 안 나눈다) 길이 늘 열려 있어야 한다 */}
            {role === 'applicant' && (
              <div className={styles.alt}>
                <button
                  type="button"
                  className={styles.altLink}
                  onClick={() => {
                    setApplicantMode(applicantMode === 'birth' ? 'password' : 'birth')
                    setError(null)
                  }}
                  disabled={pending}
                >
                  {applicantMode === 'birth' ? '비밀번호로 로그인' : '생년월일로 로그인'}
                </button>
                <span className={styles.altDot} aria-hidden="true">
                  ·
                </span>
                <button
                  type="button"
                  className={styles.altLink}
                  onClick={() => {
                    setSetupOpen(!setupOpen)
                    setSetupSent(false)
                  }}
                  disabled={pending}
                >
                  비밀번호 설정 링크 받기
                </button>
              </div>
            )}

            {role === 'applicant' && setupOpen && (
              <div className={styles.setup}>
                {setupSent ? (
                  /* **보냈는지 안 보냈는지 가르지 않는다** — 지원 이력이 없어도
                     서버가 202 를 주는 것과 같은 이유다 */
                  <p className={styles.setupBody}>
                    메일을 보냈습니다. 지원할 때 쓰신 이메일이라면 링크가 도착합니다.
                    링크는 7일 동안 쓸 수 있습니다.
                  </p>
                ) : (
                  <>
                    <p className={styles.setupBody}>
                      위 이메일로 비밀번호를 정할 수 있는 링크를 보내 드립니다.
                      이미 정하신 분이 다시 정할 때도 같은 길입니다.
                    </p>
                    <button
                      type="button"
                      className={styles.setupSend}
                      onClick={() => void sendSetupLink()}
                      disabled={setupPending || email.trim() === ''}
                    >
                      {setupPending
                        ? '보내는 중…'
                        : email.trim() === ''
                          ? '이메일을 먼저 적어 주세요'
                          : '링크 보내기'}
                    </button>
                  </>
                )}
              </div>
            )}
          </div>

          <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={disabled}>
            {pending ? '로그인 중…' : '로그인'}
          </button>

          {/* 심사자용 데모 자동 로그인 (박제 온프레미스 전용) */}
          <div style={{
            marginTop: 24,
            paddingTop: 16,
            borderTop: '1px solid rgba(255,255,255,0.08)',
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}>
            <p style={{ margin: 0, fontSize: 12, color: 'rgba(255,255,255,0.5)', textAlign: 'center' }}>
              심사자 데모 · 별도 입력 없이 즉시 진입
            </p>
            <button
              type="button"
              className="btn"
              style={{ width: '100%', background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.85)' }}
              onClick={demoLoginStaff}
              disabled={pending}
            >
              담당자 데모 로그인
            </button>
            <button
              type="button"
              className="btn"
              style={{ width: '100%', background: 'rgba(255,255,255,0.06)', color: 'rgba(255,255,255,0.85)' }}
              onClick={demoLoginApplicant}
              disabled={pending}
            >
              지원자 데모 로그인
            </button>
          </div>
        </form>
      </div>

      {intro && (
        <LoginIntro stageRef={stageRef} sceneRef={sceneRef} onDone={() => setIntro(false)} />
      )}
    </div>
  )
}
