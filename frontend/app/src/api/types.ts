/* 백엔드 app/schemas/ 의 응답 모델을 그대로 옮긴 것.
   필드명을 바꾸지 않는다 — 서버가 주는 이름이 곧 이 이름이어야 대조가 쉽다
   (frontend.md: "목데이터 필드명은 01-erd.md와 동일하게"). */

export interface User {
  id: number
  email: string
  name: string
  role: 'admin' | 'member'
  /* 비활성 계정은 로그인도 기존 토큰도 막힌다 (A4). 옛 응답에는 없어 선택이다 */
  is_active?: boolean
}

/* 설정 > 사용자·권한 (A4) */
export interface UserItem {
  id: number
  name: string
  email: string
  role: 'admin' | 'member'
  is_active: boolean
  created_at: string
}

/* 설정 > 메일 템플릿 (G4).
   source 는 "지금 나가는 문구가 기본값인가 수정본인가" — 저장소가 둘이라
   이 구분이 화면에 없으면 자기가 고친 게 반영됐는지 알 수 없다. */
export interface MailTemplate {
  stage: 'applied' | 'interview' | 'accepted' | 'rejected'
  subject: string
  body: string
  source: 'default' | 'custom'
  updated_at: string | null
  updated_by_name: string | null
}

/* 발송 이력 한 줄 (G4). 자동·수동을 한 목록에서 본다 */
export interface EmailLogItem {
  id: number
  to_email: string
  stage: string
  status: 'queued' | 'sent' | 'failed'
  actor_kind: 'human' | 'agent' | 'system'
  actor_name: string | null
  subject: string | null
  body: string | null
  sent_at: string | null
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export type PostingStatus = 'draft' | 'open' | 'closed'

export interface Posting {
  id: number
  title: string
  description: string | null
  status: PostingStatus
  deadline: string | null // date (YYYY-MM-DD)
  created_by: number | null
  created_at: string
  updated_at: string
  application_count: number
  /* 서버가 응답 시점에 계산해 준다. 마감일이 없으면 null, 지났으면 음수 */
  d_day: number | null
}

/* 단계 코드. 01-erd.md 의 applications.current_stage 와 같은 값 */
export type Stage = 'applied' | 'screening' | 'interview' | 'accepted' | 'rejected'

export interface ApplicationListItem {
  id: number
  job_posting_id: number
  name: string
  email: string
  current_stage: Stage
  career_years: number | null
  created_at: string
  /* sort=score 일 때만 채워진다. 평가가 없으면 null — 0 이 아니다 */
  avg_score: number | null
}

export interface SearchResult {
  items: ApplicationListItem[]
  /* with_total=false 로 부르면 null. "0건"이 아니라 "세지 않았다"는 뜻 (H5) */
  total: number | null
  took_ms: number
  next_cursor: string | null
}

export interface AssignedApplications {
  assignments: Assignment[]
  count: number
}

export interface Assignment {
  id: number
  application_id: number
  interviewer_id: number
  assigned_by: number
  created_at: string
}

export interface FileOut {
  id: number
  filename: string
  kind: string
  size_bytes: number
  content_type: string
  created_at: string
}

export interface ApplicationDetail {
  id: number
  job_posting_id: number
  name: string
  email: string
  phone: string
  education: string | null
  career_years: number | null
  skills: string[] | null
  self_intro: string | null
  ai_summary: string | null
  current_stage: Stage
  created_at: string
  avg_score: number | null
  files?: FileOut[]
}

export interface Note {
  id: number
  application_id: number
  author_id: number
  author_name: string
  body: string
  created_at: string
  updated_at: string
}

export interface StageChangeOut {
  application_id: number
  from_stage: Stage
  to_stage: Stage
  changed_by: number
  changed_at: string
  /* 지원자에게 통지 메일이 큐에 올라갔는지 (G1) */
  mail_queued: boolean
}

export interface BulkStageOut {
  changed: number
  changed_ids: number[]
  /* 이미 그 단계였던 건. 실패가 아니다 */
  skipped: number[]
  mail_queued: number
}

/* ── 면접 일정 (ADR-0016) ─────────────────────────────────────── */

export interface ScheduleSlotPublic {
  id: number
  start_at: string
  end_at: string
}

/* GET /applications/{id}/schedule-proposals — 최신 제안 상태. 제안이 없으면 404 */
export interface ScheduleStatus {
  status: 'proposed' | 'confirmed' | 'expired' | 'canceled'
  confirmed_slot: ScheduleSlotPublic | null
  expires_at: string | null
  created_at: string
}

/* GET /schedules — 확정된 면접 목록 (면접 일정 화면) */
export interface Interview {
  proposal_id: number
  application_id: number
  applicant_name: string
  posting_title: string
  interviewer_id: number
  interviewer_name: string
  start_at: string
  end_at: string
}

/* ── 아르 에이전트 (backend/app/api/agent.py) ─────────────────── */

/* 서버가 그대로 Anthropic messages 로 넘긴다 — user/assistant 가 번갈아야 하고
   content 가 비면 안 된다 (runtime.py run_agent). */
export interface AgentHistoryMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface AgentToolCall {
  name: string
  input: Record<string, unknown>
}

/* 쓰기 도구는 실행되지 않은 채 여기로 온다. 사람이 확인해야 실행된다 (ADR-0003) */
export interface AgentPendingAction {
  tool_name: string
  arguments: Record<string, unknown>
  description: string
}

export interface AgentChatRequest {
  message: string
  history: AgentHistoryMessage[]
}

export interface AgentChatResponse {
  reply: string
  tool_calls: AgentToolCall[]
  pending_action: AgentPendingAction | null
  input_tokens: number
  output_tokens: number
  model: string
  cost_usd: number
}

export interface AgentConfirmRequest {
  tool_name: string
  arguments: Record<string, unknown>
}

export interface AgentConfirmResponse {
  ok: boolean
  result: Record<string, unknown>
}
