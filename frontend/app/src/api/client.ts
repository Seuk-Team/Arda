/* 서버와 이야기하는 단 하나의 창구.
   화면은 fetch 를 직접 부르지 않는다 — 토큰 주입·에러 해석이 화면마다 흩어지면
   401 처리 같은 게 화면마다 조금씩 달라진다. */

/* 기본은 같은 출처(빈 문자열)다 — 개발은 vite 프록시, 배포는 Vercel rewrite 가
   /api 를 API 서버로 넘긴다. 배포 API 에 CORS 미들웨어가 없어서 브라우저가 직접
   부르면 preflight 에서 막히기 때문이다(백엔드 이슈). 절대 주소가 필요하면
   VITE_API_BASE 로 넣는다. */
const BASE = import.meta.env.VITE_API_BASE ?? ''
const PREFIX = '/api/v1'

const TOKEN_KEY = 'arda-token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    // 사생활 보호 모드 등에서 접근 자체가 던진다. 토큰이 없는 것과 같게 다룬다.
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token === null) localStorage.removeItem(TOKEN_KEY)
    else localStorage.setItem(TOKEN_KEY, token)
  } catch {
    /* 저장 못 해도 이번 세션은 굴러가야 한다 */
  }
}

/* 백엔드 errors.py 의 ErrorCode 와 같은 값. 화면은 이 값으로 분기한다. */
export type ApiErrorCode =
  | 'NOT_FOUND'
  | 'VALIDATION_FAILED'
  | 'CONFLICT'
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'GONE'
  | 'INTERNAL'
  /* 서버에 닿지도 못한 경우. 서버가 주는 코드가 아니라 이쪽에서 붙인다 */
  | 'NETWORK'

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status: number
  readonly requestId?: string

  constructor(code: ApiErrorCode, message: string, status: number, requestId?: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.requestId = requestId
  }
}

interface RequestOptions {
  method?: string
  body?: unknown
  query?: Record<string, string | number | boolean | undefined>
  /* 공개 엔드포인트(C·F 일부)는 토큰을 붙이지 않는다 */
  auth?: boolean
  signal?: AbortSignal
}

function buildUrl(path: string, query?: RequestOptions['query']) {
  // BASE 가 비면 같은 출처다. URL 은 절대 주소를 요구하므로 현재 출처를 바탕으로 만든다.
  const url = new URL(BASE + PREFIX + path, window.location.origin)
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined) url.searchParams.set(k, String(v))
  }
  return url.toString()
}

/* 401 이면 토큰이 죽은 것이므로 지운다. 화면 이동까지 여기서 하지는 않는다 —
   라우터를 아는 건 컴포넌트 쪽이고, 여기서 location 을 건드리면 테스트가 어려워진다. */
function onUnauthorized() {
  setToken(null)
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, auth = true, signal } = options

  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth) {
    const token = getToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }

  let res: Response
  try {
    res = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    })
  } catch (err) {
    // 취소는 에러가 아니다 — 부른 쪽이 알아서 무시하도록 그대로 던진다.
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError('NETWORK', '서버에 연결하지 못했습니다', 0)
  }

  if (res.status === 204) return undefined as T

  if (!res.ok) {
    // 에러 본문은 {code, message, request_id} 가 계약이지만, 게이트웨이가 끼어들면
    // HTML 이 올 수도 있다. 파싱 실패를 다시 예외로 만들지 않는다.
    let code: ApiErrorCode = 'INTERNAL'
    let message = '요청을 처리하지 못했습니다'
    let requestId: string | undefined
    try {
      const data = await res.json()
      if (typeof data?.code === 'string') code = data.code as ApiErrorCode
      if (typeof data?.message === 'string') message = data.message
      if (typeof data?.request_id === 'string') requestId = data.request_id
    } catch {
      /* 본문이 JSON 이 아니면 위 기본값을 쓴다 */
    }
    if (res.status === 401) onUnauthorized()
    throw new ApiError(code, message, res.status, requestId)
  }

  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'DELETE' }),
}
