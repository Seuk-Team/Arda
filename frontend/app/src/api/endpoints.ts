/* 02-api.md 의 경로를 함수 하나로 감싼다. 화면은 경로 문자열을 모른다. */
import { api } from './client'
import type {
  ApplicationDetail,
  AssignedApplications,
  Posting,
  SearchResult,
  Stage,
  TokenResponse,
  User,
} from './types'

export const auth = {
  login: (email: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { email, password }, { auth: false }),
  me: () => api.get<User>('/auth/me'),
}

export const postings = {
  /* GET /postings 는 봉투 없이 배열을 그대로 준다 (backend/app/api/postings.py) */
  list: (signal?: AbortSignal) => api.get<Posting[]>('/postings', { signal }),
}

interface SearchQuery {
  q?: string
  stage?: Stage
  posting_id?: number
  limit?: number
  offset?: number
  with_total?: boolean
}

export const applications = {
  /* 상세 (D4). 패널이 한 번에 그릴 수 있도록 자식까지 함께 온다 */
  detail: (id: number, signal?: AbortSignal) =>
    api.get<ApplicationDetail>(`/applications/${id}`, { signal }),

  /* 전 공고 통합 검색 (H1). 대시보드는 건수만 필요해 limit=1 로 부른다 */
  search: (query: SearchQuery = {}, signal?: AbortSignal) =>
    api.get<SearchResult>('/applications', { query: { ...query }, signal }),

  /* 단계별 건수. 목록은 필요 없고 total 만 쓰므로 limit 을 1 로 줄인다 */
  countByStage: async (stage: Stage, posting_id?: number, signal?: AbortSignal) => {
    const res = await api.get<SearchResult>('/applications', {
      query: { stage, posting_id, limit: 1, with_total: true },
      signal,
    })
    return res.total ?? 0
  },
}

export const evaluations = {
  /* 평가 작성 (E1). 점수 1~5 는 서버가 다시 검증한다 */
  create: (applicationId: number, score: number, comment?: string) =>
    api.post<unknown>(`/applications/${applicationId}/evaluations`, { score, comment: comment || null }),
}

export const assignments = {
  /* 내게 배정된 지원자 (E3). 대시보드의 "내 리뷰 대기" */
  mine: (userId: number, signal?: AbortSignal) =>
    api.get<AssignedApplications>(`/interviewers/${userId}/applications`, { signal }),
}
