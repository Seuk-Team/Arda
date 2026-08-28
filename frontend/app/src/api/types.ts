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
