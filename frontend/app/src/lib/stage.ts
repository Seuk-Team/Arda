import type { Stage, User } from '../api/types'

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

/* 역할 코드 → 화면 문구. 역할은 2종뿐이다 —
   admin 만 배정·계정·메일 템플릿을 만지고, 조회는 로그인한 전원이 한다. */
export const ROLE_LABEL: Record<User['role'], string> = {
  admin: '관리자',
  member: '멤버',
}

/* "면접으로" / "서류 검토로" — 받침 유무로 조사를 고른다.
   한글 음절은 0xAC00 부터 28 개씩 묶이고, 그 안의 0 번이 받침 없는 글자다. */
export function withRo(word: string): string {
  const last = word.charCodeAt(word.length - 1)
  const isHangul = last >= 0xac00 && last <= 0xd7a3
  const hasBatchim = isHangul && (last - 0xac00) % 28 !== 0
  // ㄹ 받침(코드 8)은 "로" 를 쓴다 — "서울로" 처럼
  const isRieul = isHangul && (last - 0xac00) % 28 === 8
  return word + (hasBatchim && !isRieul ? '으로' : '로')
}
