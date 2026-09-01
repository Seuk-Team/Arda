import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { auth as authApi } from '../api/endpoints'
import { ApiError, getToken, setToken } from '../api/client'
import type { User } from '../api/types'

interface AuthValue {
  user: User | null
  /* 새로고침 직후 토큰으로 나를 확인하는 동안. 이걸 안 두면 이미 로그인한
     사용자가 새로고침할 때마다 로그인 화면이 한 번 깜빡인다. */
  loading: boolean
  /* 확인이 401 이 아닌 이유로 실패했을 때(서버 다운·네트워크). 로그아웃과 구분해야 한다 —
     서버가 잠깐 죽은 걸 로그아웃으로 취급하면 멀쩡한 토큰을 두고 로그인 화면으로 튕긴다
     (errors.py 가 403 에 대해 경고하는 것과 같은 실수다). */
  error: ApiError | null
  retry: () => void
  /* 내 정보를 다시 읽어 컨텍스트에 반영한다. 설정에서 이름을 바꾸면 사이드바·
     서명 등 사방에 뿌려진 이름이 같이 바뀌어야 한다 (G4). */
  refresh: () => Promise<void>
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthValue | null>(null)

/* 로컬 개발에서는 로그인 화면을 건너뛴다 — 화면 하나 보려고 매번 로그인하지 않게.
   import.meta.env.DEV 는 vite dev 에서만 참이고 빌드 번들에서는 이 상수가 죽은 코드로
   제거된다. 배포에 새어나갈 수 없다.
   토큰이 있으면(한 번 로그인했으면) 그쪽이 우선이고, 없으면 이 사용자로 화면만 연다 —
   토큰이 없으니 API 는 401 을 주고, 데이터가 필요한 화면은 §6 에러 상태로 뜬다. */
const DEV_USER: User | null = import.meta.env.DEV
  ? { id: 0, email: 'dev@local', name: '개발', role: 'admin' }
  : null

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(getToken() === null ? DEV_USER : null)
  const [loading, setLoading] = useState(getToken() !== null)
  const [error, setError] = useState<ApiError | null>(null)
  /* 값을 바꿔 부트스트랩을 다시 돌리는 용도 */
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (getToken() === null) return
    let alive = true
    setLoading(true)
    setError(null)
    authApi
      .me()
      .then((me) => {
        if (alive) setUser(me)
      })
      .catch((err) => {
        if (!alive) return
        if (!(err instanceof ApiError)) throw err
        // 401 이면 토큰이 죽은 것이고 client 가 이미 지웠다 — 조용히 로그아웃 상태.
        // 그 외(서버 오류·네트워크)는 아직 로그아웃이 아니다. 토큰을 두고 에러로 알린다.
        if (err.code !== 'UNAUTHORIZED') setError(err)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [attempt])

  const retry = useCallback(() => setAttempt((n) => n + 1), [])

  const refresh = useCallback(async () => {
    /* 토큰이 없으면 부를 것이 없다 — 로컬 개발의 DEV_USER 상태다 */
    if (getToken() === null) return
    setUser(await authApi.me())
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const { access_token } = await authApi.login(email, password)
    setToken(access_token)
    setError(null)
    setUser(await authApi.me())
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    setError(null)
  }, [])

  const value = useMemo(
    () => ({ user, loading, error, retry, refresh, login, logout }),
    [user, loading, error, retry, refresh, login, logout],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth 는 AuthProvider 안에서만 쓴다')
  return v
}
