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
  UserItem,
  MailTemplate,
  EmailLogItem,
} from './types'

export const files = {
  /* 다운로드 URL 발급 (F1). 누른 시점에 발급한다 — 300초 만료라 미리 발급하면 끊긴다.
     CORS AllowedMethods 가 PUT 뿐이라 fetch 로 내려받으면 막힌다 — window.location.href 로 열 것 */
  presignDownload: (fileId: number) =>
    api.get<{ download_url: string; filename: string; expires_in: number }>(`/files/${fileId}/presign-download`),
}

export const auth = {
  login: (email: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { email, password }, { auth: false }),
  me: () => api.get<User>('/auth/me'),

  /* 내 정보 수정 (G4). 이름·비밀번호만 — 역할·이메일은 서버가 안 받는다.
     비밀번호를 바꿀 때는 current_password 가 필수다(틀리면 401). */
  updateMe: (body: { name?: string; current_password?: string; new_password?: string }) =>
    api.patch<User>('/auth/me', body),

  /* 계정 생성 (A1). 설정의 "사용자 추가"가 이것을 부른다 — 전용 경로를 새로
     만들지 않았다. production 에서는 admin 만 통과한다 */
  signup: (body: { email: string; password: string; name: string; role: 'admin' | 'member' }) =>
    api.post<User>('/auth/signup', body),
}

export const users = {
  /* 목록. 조회는 로그인 전원에게 열려 있다 (ADR-0017) */
  list: (signal?: AbortSignal) =>
    api.get<{ items: UserItem[]; count: number }>('/users', { signal }),

  /* 역할·활성 변경. admin 전용이고, 활성 admin 이 0 명이 되는 변경은 409 다 */
  update: (id: number, body: { role?: 'admin' | 'member'; is_active?: boolean }) =>
    api.patch<UserItem>(`/users/${id}`, body),
}

export const mail = {
  templates: (signal?: AbortSignal) =>
    api.get<{ items: MailTemplate[] }>('/email-templates', { signal }),

  /* 저장. 허용 외 {변수} 는 422 — 화면은 그 메시지를 그대로 보여주면 된다 */
  saveTemplate: (stage: string, body: { subject: string; body: string }) =>
    api.put<MailTemplate>(`/email-templates/${stage}`, body),

  /* 기본 문구로 복귀. 204 가 아니라 복귀한 문구가 온다 */
  resetTemplate: (stage: string) => api.delete<MailTemplate>(`/email-templates/${stage}`),

  /* 수동 발송 프리필 — 치환은 서버가 한다. 화면이 하면 미리보기와 실제가 갈린다 */
  preview: (applicationId: number, stage: string, signal?: AbortSignal) =>
    api.get<{ subject: string; body: string }>(
      `/applications/${applicationId}/emails/preview`,
      { query: { stage }, signal },
    ),

  /* 수동 발송. **수신자를 보내지 않는다** — 서버가 지원자 주소로 정한다 */
  send: (applicationId: number, body: { subject: string; body: string }) =>
    api.post<EmailLogItem>(`/applications/${applicationId}/emails`, body),

  history: (applicationId: number, signal?: AbortSignal) =>
    api.get<{ items: EmailLogItem[]; count: number }>(
      `/applications/${applicationId}/emails`,
      { signal },
    ),
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
  InterviewSession,
  InterviewSessionDetail,
} from './types'

export const interviews = {
  create: (applicationId: number) =>
    api.post<InterviewSession>(`/applications/${applicationId}/interview-sessions`, {}),

  list: (applicationId: number, signal?: AbortSignal) =>
    api.get<InterviewSession[]>(`/applications/${applicationId}/interview-sessions`, { signal }),

  setQuestions: (sessionId: number, questions: string[]) =>
    api.put<InterviewSession>(`/interview-sessions/${sessionId}/questions`, { questions }),

  detail: (sessionId: number, signal?: AbortSignal) =>
    api.get<InterviewSessionDetail>(`/interview-sessions/${sessionId}`, { signal }),
}

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
