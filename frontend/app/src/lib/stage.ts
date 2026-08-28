import type { Stage } from '../api/types'

/* 단계 코드 → 화면 문구. 목업이 쓰는 말을 그대로 쓴다. */
export const STAGE_LABEL: Record<Stage, string> = {
  applied: '지원 접수',
  screening: '서류 검토',
  interview: '면접',
  accepted: '최종 합격',
  rejected: '불합격',
}

/* 색은 판단에만 (05-design §1) — 진행 중은 무채, 합격만 연두, 불합격만 적갈 */
export type StageTone = 'progress' | 'accepted' | 'rejected'

export function stageTone(stage: Stage): StageTone {
  if (stage === 'accepted') return 'accepted'
  if (stage === 'rejected') return 'rejected'
  return 'progress'
}

/* 경력 표기. 0년과 미기재를 모두 "신입"으로 본다 — 목업의 표기다 */
export function careerText(years: number | null): string {
  return years ? `${years}년` : '신입'
}

/* 서버의 ISO 날짜를 목업 표기(2026.03.12)로 */
export function fmtDate(iso: string): string {
  return iso.slice(0, 10).replaceAll('-', '.')
}

/* 역할 코드 → 화면 문구 */
export const ROLE_LABEL: Record<'admin' | 'recruiter' | 'interviewer', string> = {
  admin: '관리자',
  recruiter: '채용담당자',
  interviewer: '면접관',
}
