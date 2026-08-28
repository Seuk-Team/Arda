/* 02-api.md 의 경로를 함수 하나로 감싼다. 화면은 경로 문자열을 모른다. */
import { api } from './client'
import type { Posting, TokenResponse, User } from './types'

export const auth = {
  login: (email: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { email, password }, { auth: false }),
  me: () => api.get<User>('/auth/me'),
}

export const postings = {
  /* GET /postings 는 봉투 없이 배열을 그대로 준다 (backend/app/api/postings.py) */
  list: (signal?: AbortSignal) => api.get<Posting[]>('/postings', { signal }),
}
