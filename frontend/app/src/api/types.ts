/* 백엔드 app/schemas/ 의 응답 모델을 그대로 옮긴 것.
   필드명을 바꾸지 않는다 — 서버가 주는 이름이 곧 이 이름이어야 대조가 쉽다
   (frontend.md: "목데이터 필드명은 01-erd.md와 동일하게"). */

export interface User {
  id: number
  email: string
  name: string
  role: 'admin' | 'recruiter' | 'interviewer'
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
