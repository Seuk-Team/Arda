/* 02-api.md 의 경로를 함수 하나로 감싼다. 화면은 경로 문자열을 모른다. */
import { api } from './client'
import type {
  ApplicationDetail,
  ApplicationIntegrity,
  AssignedApplications,
  BulkStageOut,
  Publication,
  Note,
  Posting,
  PostingStatus,
  Interview,
  ScheduleStatus,
  SearchResult,
  StageChangeOut,
  Stage,
  SummaryPosting,
  TokenResponse,
  User,
  UserItem,
  MailTemplate,
  EmailLogItem,
  ResumeDiff,
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

  /* 상태·마감일만 바꾼다 — 공고 마감·다시 열기 (PATCH /postings/{id}, 02-api.md).
     보낸 필드만 반영되고(exclude_unset) 응답은 바뀐 공고 전체다. 집계는 실리지 않는다 */
  update: (id: number, body: { status?: PostingStatus; deadline?: string | null }) =>
    api.patch<Posting>(`/postings/${id}`, body),
}

interface SearchQuery {
  q?: string
  /* 여러 개를 주면 OR 다 — "종료" 칩이 합격·불합격을 한 번에 보낸다 */
  stage?: Stage | Stage[]
  posting_id?: number
  /* 서버가 받는 값은 둘뿐이다 (backend/app/api/search.py SORTS).
     경력 순은 없다 — 필요하면 백엔드에 먼저 요청해야 한다 */
  sort?: 'created_at' | 'score'
  order?: 'desc' | 'asc'
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

  /* 이력서 변동 요약 (2026-09-17, PR #320). 동일 인물의 가장 최근 이전 지원과 비교.
     이전 지원이 없으면 changed=false + summary="이전 지원 이력이 없습니다." 로 온다
     (404 아님 · 프론트가 조용히 배지를 숨기기 좋게). */
  priorResumeDiff: (id: number, signal?: AbortSignal) =>
    api.get<ResumeDiff>(`/applications/${id}/resume-diff/prior`, { signal }),
}

export const summary = {
  /* 종합 평가 (2026-09-14): 공고별 지원자 · 서류 + 면접 자동 점수 · 등급 · 요약.
     상세와 달리 대시보드성 · 한 번에 모든 공고 아래 지원자를 준다. */
  list: (signal?: AbortSignal) =>
    api.get<SummaryPosting[]>('/summary', { signal }),
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

export const integrity = {
  /* 지원자 하나의 제출물 무결성 (ADR-0028).
     **목록 화면에서 부르지 않는다** — 볼 때마다 S3 에서 원본을 다시 읽어
     지문을 새로 뜬다. 20명 목록에서 부르면 S3 를 20번 읽는다.
     상세에서 한 번 부르는 자리다. */
  get: (applicationId: number, signal?: AbortSignal) =>
    api.get<ApplicationIntegrity>(`/applications/${applicationId}/integrity`, { signal }),

  /* 사슬 머리를 공개 체인에 올린 기록 — 지원자별이 아니라 전체 사슬에 대한 것.
     covered_through_seq 보다 seq 가 작거나 같은 고리가 이미 체인에 올라가 있다. */
  publications: (signal?: AbortSignal) =>
    api.get<Publication[]>('/integrity/publications', { signal }),
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
  ActiveInterview,
  AgentChatRequest,
  AgentChatResponse,
  AgentConfirmRequest,
  AgentConfirmResponse,
  AgentHistoryMessage,
  InterviewSession,
  InterviewSessionDetail,
} from './types'

export const interviews = {
  /* 만들면 **지원자에게 링크 메일이 나간다** (2026-09-18). 링크만 뽑아 두려면 notify: false */
  create: (applicationId: number, notify = true) =>
    api.post<InterviewSession>(`/applications/${applicationId}/interview-sessions`, { notify }),

  /* 링크 메일 재발송 — **같은 세션·같은 링크**. 새로 만들면 앱이 가장 먼저 만든 방으로 들어간다 */
  sendLink: (sessionId: number) =>
    api.post<InterviewSession>(`/interview-sessions/${sessionId}/send`, {}),

  list: (applicationId: number, signal?: AbortSignal) =>
    api.get<InterviewSession[]>(`/applications/${applicationId}/interview-sessions`, { signal }),

  setQuestions: (sessionId: number, questions: string[]) =>
    api.put<InterviewSession>(`/interview-sessions/${sessionId}/questions`, { questions }),

  detail: (sessionId: number, signal?: AbortSignal) =>
    api.get<InterviewSessionDetail>(`/interview-sessions/${sessionId}`, { signal }),

  /* 세션 삭제 (2026-09-10). 자식 표(turns·findings) 도 함께 지운다.
     끝난 세션도 지울 수 있다 — 담당자가 옛것 정리하는 자리다. */
  remove: (sessionId: number) =>
    api.delete<void>(`/interview-sessions/${sessionId}`),

  /* 지금 진행 중인 면접들. 대시보드가 실시간 분석으로 바로 들어가는 데 쓴다 */
  active: (signal?: AbortSignal) =>
    api.get<ActiveInterview[]>('/interview-sessions/active', { signal }),
}

export const agent = {
  /* 자연어 한 마디. 대화 이력은 화면이 들고 매번 같이 보낸다 (서버는 저장하지 않는다) */
  chat: (message: string, history: AgentHistoryMessage[], signal?: AbortSignal, applicationId?: number) =>
    api.post<AgentChatResponse>(
      '/agent/chat',
      { message, history, application_id: applicationId ?? null } satisfies AgentChatRequest,
      { signal },
    ),

  /* 확인 카드에서 [확인]을 눌렀을 때만 부른다. 쓰기 도구는 이 경로로만 실행된다 */
  confirm: (tool_name: string, args: Record<string, unknown>, signal?: AbortSignal) =>
    api.post<AgentConfirmResponse>(
      '/agent/confirm',
      { tool_name, arguments: args } satisfies AgentConfirmRequest,
      { signal },
    ),

  /* AI 요약 재생성 (M2). 기존 요약을 덮어쓴다 — 몇 초 걸리는 LLM 호출이다.
     실패 사유가 갈린다: **503** 은 백엔드(키·모델) 문제, **422** 는 응답을 못 읽은
     것. 화면이 둘을 구분해 말해야 담당자가 "내 탓인가" 를 묻지 않는다.
     (2026-09-12: 화면의 "다시 생성" 버튼에 핸들러가 없어 요청이 아예 나가지
     않았다 — 서버 로그에 호출 0건이었다.) */
  regenerateSummary: (applicationId: number) =>
    api.post<{ summary: string; model: string | null }>(
      `/agent/applications/${applicationId}/summarize`,
      {},
    ),
}

/* ── 인적성(사전 성향) 설문 (ADR-0027) ─────────────────────────────
   맨 위 import 블록을 건드리지 않으려고 여기서 따로 들여온다 (agent 와 같은 이유). */
import type { AptitudeBulkSendOut, AptitudeDetail, AptitudeSessionOut } from './types'

export const aptitude = {
  /* 공고 단위 일괄 발송 — "아직 안 받은 전원에게". 빠진 건수가 이유별로 돌아온다 */
  bulkSend: (postingId: number) =>
    api.post<AptitudeBulkSendOut>(`/postings/${postingId}/aptitude/send`, {}),

  /* 개별 발송·재발송 — 매번 새 세션. 접수·서류검토 단계가 아니면 422 */
  sendOne: (applicationId: number) =>
    api.post<AptitudeSessionOut>(`/applications/${applicationId}/aptitude/send`, {}),

  /* 담당자 조회 — 최신 세션의 응답·통계·AI 요약. 없으면 status:"none" */
  detail: (applicationId: number, signal?: AbortSignal) =>
    api.get<AptitudeDetail>(`/applications/${applicationId}/aptitude`, { signal }),
}

/* 지원자 본인용 (ADR-0033). **담당자 토큰과 섞이지 않게 `applicant: true` 로 부른다.** */
import type { ApplicantLoginOut, ApplicantMe } from './types'

export const applicantAuth = {
  /* 실패는 전부 401 한 가지다 — 없는 이메일·틀린 생년월일을 서버가 구별해 주지
     않는다. 화면에서도 사유를 지어내면 안 된다. 5회 틀리면 429(15분).

     **비밀번호를 정한 계정은 생년월일로 401 이다**(2026-09-16). 그것도 같은
     401 이라 화면이 "비밀번호를 정하셨네요"라고 말해 주면 안 된다 — 서버가
     감춘 것을 화면이 드러내는 꼴이다. */
  login: (email: string, birth_date: string) =>
    api.post<ApplicantLoginOut>(
      '/public/applicant/login',
      { email, birth_date },
      { auth: false },
    ),

  /** 비밀번호 갈래. 같은 경로에 본문만 다르다 */
  loginWithPassword: (email: string, password: string) =>
    api.post<ApplicantLoginOut>(
      '/public/applicant/login',
      { email, password },
      { auth: false },
    ),

  /* 비밀번호 설정 링크를 메일로 보낸다.

     **지원 이력이 없어도 202 다.** 있고 없고를 알려 주면 "이 사람이 여기
     지원했나"를 떠보는 도구가 된다(ADR-0033 원칙). 그래서 화면도 결과에 따라
     문구를 가르지 않는다 — 언제나 "메일을 보냈어요" 하나다. */
  requestPasswordSetup: (email: string) =>
    api.post<void>(
      '/public/applicant/password-setup-request',
      { email },
      { auth: false },
    ),

  /* 링크가 살아 있는지 보고 누구 것인지 받는다. 만료·사용됨은 410 이다 —
     **둘을 나누지 않는다**(같은 410, 같은 문구). */
  passwordToken: (token: string, signal?: AbortSignal) =>
    api.get<{ email: string }>(
      `/public/applicant/set-password/${encodeURIComponent(token)}`,
      { auth: false, signal },
    ),

  /* 비밀번호를 정한다. 성공하면 그 이메일의 남은 토큰은 전부 죽는다.
     길이 위반은 422, 죽은 링크는 410. */
  setPassword: (token: string, password: string) =>
    api.post<void>(
      `/public/applicant/set-password/${encodeURIComponent(token)}`,
      { password },
      { auth: false },
    ),

  me: (signal?: AbortSignal) =>
    api.get<ApplicantMe>('/applicant/me', { applicant: true, signal }),
}

/* ── 비밀번호 규칙 (2026-09-16 백엔드 계약) ──────────────────────
 *
 * **글자 수가 아니라 바이트다.** 저장소가 쓰는 bcrypt 는 72바이트를 넘는
 * 입력을 말없이 자른다 — 그 뒤는 무엇을 치든 같은 비밀번호가 된다. 한글은
 * 글자당 3바이트라 24자쯤이 한계다. 서버가 422 로 막지만, 제출하고 나서
 * 알게 되면 늦으므로 화면이 먼저 막는다. */
export const PASSWORD_MIN = 8
export const PASSWORD_MAX = 64
export const PASSWORD_MAX_BYTES = 72

/** 비밀번호가 규칙에 맞는가. 맞으면 null, 아니면 사유 한 줄 */
export function passwordProblem(password: string): string | null {
  if (password.length < PASSWORD_MIN) return `${PASSWORD_MIN}자 이상이어야 합니다`
  if (password.length > PASSWORD_MAX) return `${PASSWORD_MAX}자 이하여야 합니다`
  if (new TextEncoder().encode(password).length > PASSWORD_MAX_BYTES) {
    return `너무 깁니다 — 한글은 24자까지입니다`
  }
  return null
}
