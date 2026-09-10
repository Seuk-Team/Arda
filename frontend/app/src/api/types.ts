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
  stage_counts?: Record<string, number>
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

export interface StageHistoryItem {
  id: number
  from_stage: string | null
  to_stage: string
  changed_by: number | null
  reason: string | null
  created_at: string
}

/* 평가 한 건 (backend EvaluationOut). 상세 응답이 배열로 함께 준다 —
   평가자별 점수가 있어야 '누가 냈나'와 '의견이 갈렸나'를 알 수 있다 */
export interface Evaluation {
  id: number
  evaluator_id: number
  score: number
  comment: string | null
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
  eval_count?: number
  evaluations?: Evaluation[]
  files?: FileOut[]
  stage_history?: StageHistoryItem[]
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
  /* 동명이인 선택지 버튼으로 고른 지원자 — 서버가 이름 조회를 건너뛰고 이 id 로 진행한다 */
  application_id?: number | null
}

/* 담당자가 골라야 답이 이어지는 갈림길 하나 (동명이인). 카드로 그린다.
   pending_action 이 붙어 오면 카드 안 확인 버튼 딸깍 = 즉시 실행 (agent.confirm 직접).
   없으면 폴백으로 message(원래 요청) + application_id 를 chat 에 다시 보낸다. */
export interface AgentChoice {
  /* 짧은 이름 (fallback 표시용) — 상세는 아래 필드로 */
  label: string
  application_id: number
  message: string
  /* 카드 안에 사람이 골라야 하는 만큼의 상세를 함께 준다. 서버가 label 로 이어 붙여
     오던 것을 필드로 분리해, 프론트가 정렬·강조를 마음대로 잡는다. */
  email: string | null
  stage_label: string | null
  career_years: number | null
  education: string | null
  /* 있으면 카드 안 확인 버튼 클릭 = agent.confirm(...) 직접 실행. 없으면 message
     로 chat 을 다시 보내 서버가 pending_action 을 만드는 두 단계 흐름으로 폴백. */
  pending_action: AgentPendingAction | null
}

export interface AgentChatResponse {
  reply: string
  tool_calls: AgentToolCall[]
  pending_action: AgentPendingAction | null
  choices: AgentChoice[]
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

/* ── AI 면접 (public/interview) ───────────────────────────────────── */

/* 면접 진행 보조 (ADR-0026 결정 4). **판정이 아니라 제안이다.**
   점수·확률이 없고 서버에 저장되지도 않는다 — 답변을 낸 그 응답에만 실려 온다.
   `action` 은 늘어날 수 있으므로 **모르는 값은 무시한다.** */
export interface PacingHint {
  action: string
  message: string
}

export interface InterviewPublic {
  status: 'pending' | 'in_progress' | 'done' | 'expired'
  applicant_name: string
  posting_title: string
  expires_at: string | null
  consent_required: boolean
  current_question: string | null
  question_seq: number | null
  /* 답변 직후에만 온다. 조회(GET)에는 항상 null */
  pacing: PacingHint | null
}

/* 답변 음성 업로드용 서명 URL. 이력서 업로드와 다른 경로다 —
   그쪽은 토큰 없이 누구나 부를 수 있어서 음성 형식을 얹지 않았다. */
export interface InterviewAudioUpload {
  upload_url: string
  s3_key: string
  expires_in: number
}

export interface InterviewSession {
  id: number
  application_id: number
  status: string
  token: string
  url: string
  expires_at: string | null
  consented_at: string | null
  started_at: string | null
  ended_at: string | null
  created_at: string
}

export interface InterviewTurn {
  seq: number
  question: string
  transcript: string | null
  audio_duration_sec: number | null
  /** 아르가 어느 답변에서 이 질문을 만들었나. 값이 있으면 자동생성 */
  generated_from_turn_id: number | null
}

export interface InterviewFinding {
  claim_source: string
  claim_text: string
  answer_text: string
  verdict: string
}

export interface InterviewSessionDetail extends InterviewSession {
  turns: InterviewTurn[]
  findings: InterviewFinding[]
}

/* ── 제출물 무결성 (ADR-0028) ─────────────────────────────────────
   "위조 방지"가 아니라 **위조 검출**이다. DB 를 고치는 건 누구도 막을 수
   없고, 달라지는 건 고친 사실이 드러난다는 점이다 — 문구를 그렇게 쓴다. */

/* 고리 하나 + 지금 원본과 맞춰 본 결과 */
export interface IntegrityItem {
  seq: number
  doc_type: string
  file_id: number | null
  filename: string | null
  content_sha256: string
  chain_hash: string
  anchored_at: string
  status: 'ok' | 'mismatch' | 'unreadable'
  reason: string | null
}

/* verdict 는 항목들을 한 줄로 요약한 것 — 나쁜 쪽이 이긴다.
   `none` 은 "깨끗하다"가 아니라 **"증명할 근거가 없다"** 이므로 ok 와 섞지 않는다.
   ADR-0028 이전에 접수된 지원서가 여기 해당한다. */
export type IntegrityVerdict = 'ok' | 'mismatch' | 'unreadable' | 'none'

export interface ApplicationIntegrity {
  application_id: number
  anchored: boolean
  verdict: IntegrityVerdict
  items: IntegrityItem[]
}

/* 사슬 머리를 공개 체인에 올린 기록.
   explorer_url 은 **서버가 골라 준다** — 네트워크마다 탐색기가 달라서
   프론트에서 주소를 조립하면 안 된다. */
export interface Publication {
  id: number
  network: string
  covered_through_seq: number
  chain_hash: string
  tx_hash: string | null
  block_number: number | null
  status: 'pending' | 'confirmed' | 'failed'
  error: string | null
  created_at: string
  confirmed_at: string | null
  explorer_url: string | null
  proof: string | null
}

/* ── 인적성(사전 성향) 설문 (ADR-0027) ───────────────────────────── */

export interface AptitudePublicQuestion {
  key: string
  text: string
}

export interface AptitudePublic {
  status: 'pending' | 'done' | 'expired'
  applicant_name: string
  posting_title: string
  expires_at: string | null
  /* pending 일 때만 온다 */
  questions: AptitudePublicQuestion[]
  /* JSON 키는 문자열 — "1"~"5" */
  likert_labels: Record<string, string>
}

export interface AptitudeAnswerItem {
  question_key: string
  question_text: string
  value: number
}

export interface AptitudeCategoryStat {
  category: string
  label: string
  mean: number
  count: number
}

export interface AptitudeDetail {
  status: 'none' | 'pending' | 'done' | 'expired'
  url: string | null
  expires_at: string | null
  submitted_at: string | null
  answers: AptitudeAnswerItem[]
  stats: AptitudeCategoryStat[]
  /* AI 관찰 요약 — 재서술 한 문단. 없으면(생성 전·실패) null — 통계만으로 화면이 선다 */
  ai_summary: string | null
  ai_summary_model: string | null
}

export interface AptitudeBulkSendOut {
  sent: number
  skipped_already_sent: number
  skipped_stage: number
}

export interface AptitudeSessionOut {
  id: number
  application_id: number
  status: string
  token: string
  url: string
  expires_at: string | null
  submitted_at: string | null
  created_at: string
}

/* ── 지원자 본인 로그인 (ADR-0033) ─────────────────────────────── */

export interface ApplicantLoginOut {
  access_token: string
  token_type: string
  expires_in: number
}

/* 지원자가 지금 들어갈 수 있는 면접. **끝났거나 만료된 것은 서버가 안 준다** —
   들어가 봐야 막히는 문을 화면에 보여 주지 않기 위해서다. */
/* 지금 진행 중인 면접 하나 — 대시보드가 바로 들어가는 데 쓴다.
   **이름과 공고가 같이 온다** (서버가 실어 준다). 세션 번호만으로는
   담당자가 어느 면접인지 고를 수 없다. */
export interface ActiveInterview {
  id: number
  application_id: number
  applicant_name: string
  posting_title: string
  started_at: string | null
}

export interface MyInterview {
  token: string
  status: string
  expires_at: string | null
}

/* 지원자가 보는 자기 지원 한 건.
   **단계는 내부값이 아니라 사람이 읽을 말(`stage_label`)로만 온다** —
   `rejected` 를 "불합격"으로 앞질러 말하지 않기 위해서다. */
export interface MyApplication {
  id: number
  posting_title: string
  stage_label: string
  applied_at: string
  interviews: MyInterview[]
}

export interface ApplicantMe {
  email: string
  name: string
  applications: MyApplication[]
}
