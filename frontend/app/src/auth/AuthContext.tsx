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
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
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
    () => ({ user, loading, error, retry, login, logout }),
    [user, loading, error, retry, login, logout],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth 는 AuthProvider 안에서만 쓴다')
  return v
}
