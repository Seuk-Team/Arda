import { useCallback, useEffect, useState } from 'react'
import { ApiError, getApplicantToken, setApplicantToken } from '../api/client'
import { applicantAuth } from '../api/endpoints'
import type { ApplicantMe } from '../api/types'
import styles from './MyApplications.module.css'

/* 지원자 본인 화면 (ADR-0031) — 이메일 + 생년월일 8자리로 들어온다.

   **담당자 로그인(`/login`)과 완전히 다른 화면이다.** 같은 자리에 두면 지원자가
   담당자 계정으로 들어가려다 막히고, 담당자는 반대로 헤맨다. 실제로 그렇게 한 번
   막혔다 — 그래서 주소도 화면도 나눠 뒀다.

   토큰도 자리를 나눈다(`arda-applicant-token`). 한 브라우저에서 담당자로 보다가
   여기에 들어와도 서로를 덮어쓰지 않는다. */

type View =
  | { kind: 'login' }
  | { kind: 'loading' }
  | { kind: 'ready'; data: ApplicantMe }

export default function MyApplications() {
  const [view, setView] = useState<View>(
    getApplicantToken() ? { kind: 'loading' } : { kind: 'login' },
  )
  const [email, setEmail] = useState('')
  const [birth, setBirth] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      setView({ kind: 'ready', data: await applicantAuth.me(signal) })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      /* 토큰이 죽었으면 클라이언트가 이미 지웠다. 로그인 화면으로 되돌린다. */
      setView({ kind: 'login' })
    }
  }, [])

  useEffect(() => {
    if (!getApplicantToken()) return
    const ac = new AbortController()
    void load(ac.signal)
    return () => ac.abort()
  }, [load])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setPending(true)
    setError(null)
    try {
      const res = await applicantAuth.login(email.trim(), birth.trim())
      setApplicantToken(res.access_token)
      setView({ kind: 'loading' })
      await load()
    } catch (err) {
      /* **사유를 지어내지 않는다.** 서버가 없는 이메일과 틀린 생년월일을 구별해
         주지 않는 것이 설계다 — 화면에서 "그런 이메일이 없습니다"라고 쓰면
         서버가 안 하기로 한 일을 화면이 대신 해 버린다. */
      setError(
        err instanceof ApiError
          ? err.message
          : '잠시 후 다시 시도해 주세요',
      )
    } finally {
      setPending(false)
    }
  }

  function logout() {
    setApplicantToken(null)
    setEmail('')
    setBirth('')
    setView({ kind: 'login' })
  }

  return (
    <div className={styles.page}>
      <main className={styles.column}>
        <h1 className={styles.logo}><span className={styles.seed}>A</span>rda</h1>

        {view.kind === 'login' && (
          <form className={styles.card} onSubmit={submit}>
            <h2 className={styles.cardTitle}>지원 현황 조회</h2>
            <p className={styles.help}>
              지원할 때 쓰신 이메일과 생년월일로 확인하실 수 있습니다.
            </p>

            <label className={styles.label} htmlFor="ap-email">이메일</label>
            <input
              id="ap-email"
              className={styles.input}
              type="email"
              autoComplete="email"
              inputMode="email"
              placeholder="지원할 때 쓰신 이메일"
              value={email}
              disabled={pending}
              onChange={(e) => setEmail(e.target.value)}
            />

            <label className={styles.label} htmlFor="ap-birth">생년월일</label>
            <input
              id="ap-birth"
              className={styles.input}
              /* 숫자 8자리다. 폰에서 숫자 자판이 바로 뜨게 inputMode 를 준다 —
                 type=number 는 앞자리 0 이 사라져서 못 쓴다. */
              inputMode="numeric"
              maxLength={8}
              placeholder="19980412"
              value={birth}
              disabled={pending}
              onChange={(e) => setBirth(e.target.value.replace(/\D/g, ''))}
            />

            {error && <p className={styles.error} role="alert">{error}</p>}

            <button
              type="submit"
              className="btn btn-primary"
              disabled={pending || !email.trim() || birth.length !== 8}
            >
              {pending ? '확인 중…' : '조회하기'}
            </button>

            {/* 담당자가 잘못 들어왔을 때 나갈 길. 반대로 지원자가 담당자
                로그인으로 흘러가지 않도록 문구를 분명히 둔다. */}
            <p className={styles.foot}>
              채용 담당자이신가요? <a className={styles.link} href="/login">담당자 로그인</a>
            </p>
          </form>
        )}

        {view.kind === 'loading' && (
          <div className={styles.card} aria-busy="true">
            <div className={styles.skeleton} style={{ width: '50%' }} />
            <div className={styles.skeleton} />
          </div>
        )}

        {view.kind === 'ready' && (
          <>
            <div className={styles.card}>
              <h2 className={styles.cardTitle}>
                {view.data.name ? `${view.data.name}님의 지원 현황` : '지원 현황'}
              </h2>
              <p className={styles.help}>{view.data.email}</p>
            </div>

            {view.data.applications.length === 0 ? (
              <div className={styles.card}>
                <p className={styles.help}>접수된 지원이 없습니다.</p>
              </div>
            ) : (
              view.data.applications.map((a) => (
                <div key={a.id} className={styles.card}>
                  <p className={styles.posting}>{a.posting_title || '공고'}</p>
                  <p className={styles.stage}>{a.stage_label}</p>
                  <p className={styles.applied}>
                    {new Date(a.applied_at).toLocaleDateString('ko-KR')} 지원
                  </p>
                </div>
              ))
            )}

            <button type="button" className={styles.link} onClick={logout}>
              로그아웃
            </button>
          </>
        )}
      </main>
    </div>
  )
}
