/* 02-api.md 의 경로를 함수 하나로 감싼다. 화면은 경로 문자열을 모른다. */
import { api } from './client'
import type {
  ApplicationDetail,
  AssignedApplications,
  BulkStageOut,
  Note,
  Posting,
  Interview,
  ScheduleStatus,
  SearchResult,
  StageChangeOut,
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

  get: (id: number, signal?: AbortSignal) => api.get<Posting>(`/postings/${id}`, { signal }),
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

export const schedules = {
  /* 확정된 면접 목록. 면접관 계정은 서버가 본인 건만 준다 (A3) */
  interviews: (
    query: { from?: string; to?: string; mine?: boolean },
    signal?: AbortSignal,
  ) => api.get<{ items: Interview[]; count: number }>('/schedules', { query, signal }),

  /* 최신 일정 제안 상태 — 대시보드·상세 패널 칩 용도. 제안이 없으면 404 */
  latest: (applicationId: number, signal?: AbortSignal) =>
    api.get<ScheduleStatus>(`/applications/${applicationId}/schedule-proposals`, { signal }),
}

export const notes = {
  list: (applicationId: number, signal?: AbortSignal) =>
    api.get<Note[]>(`/applications/${applicationId}/notes`, { signal }),
  create: (applicationId: number, body: string) =>
    api.post<Note>(`/applications/${applicationId}/notes`, { body }),
}

export const stages = {
  /* 단계 변경 (D3). rejected 는 사유가 없으면 422 다 (D8) */
  change: (applicationId: number, to_stage: Stage, reason?: string) =>
    api.patch<StageChangeOut>(`/applications/${applicationId}/stage`, { to_stage, reason: reason || null }),

  /* 여러 명 한 번에 (D9). 전부 성공하거나 전부 롤백된다 */
  bulk: (application_ids: number[], to_stage: Stage, reason?: string) =>
    api.post<BulkStageOut>('/applications/bulk-stage', { application_ids, to_stage, reason: reason || null }),
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

/* ── 아르 에이전트 (agent.py) ─────────────────────────────────
   맨 위 import 블록을 건드리지 않으려고 여기서 따로 들여온다 — 같은 파일을 여럿이 고친다. */
import type {
  AgentChatRequest,
  AgentChatResponse,
  AgentConfirmRequest,
  AgentConfirmResponse,
  AgentHistoryMessage,
} from './types'

export const agent = {
  /* 자연어 한 마디. 대화 이력은 화면이 들고 매번 같이 보낸다 (서버는 저장하지 않는다) */
  chat: (message: string, history: AgentHistoryMessage[], signal?: AbortSignal) =>
    api.post<AgentChatResponse>('/agent/chat', { message, history } satisfies AgentChatRequest, { signal }),

  /* 확인 카드에서 [확인]을 눌렀을 때만 부른다. 쓰기 도구는 이 경로로만 실행된다 */
  confirm: (tool_name: string, args: Record<string, unknown>, signal?: AbortSignal) =>
    api.post<AgentConfirmResponse>(
      '/agent/confirm',
      { tool_name, arguments: args } satisfies AgentConfirmRequest,
      { signal },
    ),
}
