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
/* 지원자 토큰. **담당자 토큰과 자리를 나눈다** — 한 브라우저에서 담당자로 보다가
   지원자 화면을 열면 서로를 덮어써서 둘 중 하나가 조용히 로그아웃된다.
   서버도 토큰 종류를 갈라 보므로(ADR-0031) 섞이면 그냥 401 이 난다. */
const APPLICANT_TOKEN_KEY = 'arda-applicant-token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    // 사생활 보호 모드 등에서 접근 자체가 던진다. 토큰이 없는 것과 같게 다룬다.
    return null
  }
}

export function getApplicantToken(): string | null {
  try {
    return localStorage.getItem(APPLICANT_TOKEN_KEY)
  } catch {
    return null
  }
}

export function setApplicantToken(token: string | null) {
  try {
    if (token === null) localStorage.removeItem(APPLICANT_TOKEN_KEY)
    else localStorage.setItem(APPLICANT_TOKEN_KEY, token)
  } catch {
    /* 저장 못 해도 이번 세션은 굴러가야 한다 */
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
  /* 지원자 토큰으로 부른다 (ADR-0031). 담당자 토큰과 섞이지 않게 따로 고른다. */
  applicant?: boolean
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

/* 로컬 개발 폴백 — 서버가 없거나(NETWORK) 401 이면 목 데이터로 대신 응답한다
   (AuthContext DEV_USER 와 같은 원리). DEV 분기 안의 동적 import 라 배포 번들에는
   mock.ts 가 아예 들어가지 않는다. 처리 못 하는 경로면 undefined — 원래 에러로 간다. */
async function devMock(method: string, path: string, query?: RequestOptions['query']) {
  if (!import.meta.env.DEV) return undefined
  const { mockResponse } = await import('./mock')
  return mockResponse(method, path, query)
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, auth = true, applicant = false, signal } = options

  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth) {
    const token = applicant ? getApplicantToken() : getToken()
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
    const mocked = await devMock(method, path, query)
    if (mocked !== undefined) return mocked as T
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
    if (res.status === 401 && applicant) {
      /* 지원자 쪽 401 은 **지원자 토큰만** 지운다. 여기서 담당자 토큰을 건드리면
         담당자가 보던 화면이 같이 로그아웃된다. 목 폴백도 태우지 않는다 —
         지원자 로그인은 실패가 곧 정보라 가짜 성공을 만들면 안 된다. */
      setApplicantToken(null)
      throw new ApiError(code, message, res.status, requestId)
    }
    if (res.status === 401) {
      /* 목이 받아 주면 토큰은 건드리지 않는다 — 로컬에서 실서버가 살아나면
         다음 요청부터 자연히 실데이터로 돌아간다 */
      const mocked = await devMock(method, path, query)
      if (mocked !== undefined) return mocked as T
      onUnauthorized()
    }
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
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'PUT', body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'DELETE' }),
}

/* WebSocket 주소를 만든다. **`api.*` 와 같은 곳을 보게 하려는 것**이 목적이다 —
   화면마다 주소를 조립하면 로컬·배포에서 한쪽만 틀린 채로 오래 간다.

   `BASE` 가 절대 주소면(배포) 그 호스트로 직접 붙고, 비어 있으면(로컬)
   지금 페이지의 출처로 붙어 vite 프록시를 탄다. Vercel rewrite 는 WebSocket 을
   넘기지 못하므로 **배포에서는 반드시 절대 주소여야 한다.** */
export function wsUrl(path: string): string {
  const base = BASE || window.location.origin
  const url = new URL(PREFIX + path, base)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}
