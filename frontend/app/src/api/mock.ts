/* 로컬 개발용 목 데이터 (2026-08-31) — 서버가 없거나(NETWORK) 토큰이 죽어(401)
   실데이터를 못 받을 때 client.ts 가 이걸로 대신 응답한다. AuthContext 의 DEV_USER 와
   같은 원리: import.meta.env.DEV 분기 안에서만 동적 import 되므로 배포 번들에서는
   분기째 제거된다 — 배포에 새어나갈 수 없다.
   필드명은 01-erd.md / types.ts 계약 그대로. 읽기(GET)와 로그인·에이전트 응답만 목이고,
   쓰기(단계 변경·평가·메모)는 목 없이 원래 에러를 그대로 낸다 — 성공한 척하면
   화면이 실서버에서 안 도는 걸 늦게 알게 된다. */
import type {
  AgentChatResponse,
  ApplicationDetail,
  ApplicationListItem,
  AssignedApplications,
  Interview,
  Note,
  Posting,
  ScheduleStatus,
  SearchResult,
  Stage,
  TokenResponse,
  User,
} from './types'

/* 날짜는 전부 "오늘" 기준 상대값 — 언제 열어도 이번 주 캘린더에 면접이 보인다 */
function at(dayOffset: number, h: number, m = 0): string {
  const d = new Date()
  d.setDate(d.getDate() + dayOffset)
  d.setHours(h, m, 0, 0)
  return d.toISOString()
}

const USER: User = { id: 0, email: 'dev@local', name: '개발', role: 'admin' }

const POSTINGS: Posting[] = [
  {
    id: 1, title: '프론트엔드 개발자 (React)', description: null, status: 'open',
    deadline: null, created_by: 0, created_at: at(-20, 9), updated_at: at(-1, 9),
    application_count: 6, d_day: 12,
    stage_counts: { applied: 3, screening: 2, interview: 1, accepted: 0, rejected: 0 },
  },
  {
    id: 2, title: '백엔드 개발자 (Python·FastAPI)', description: null, status: 'open',
    deadline: null, created_by: 0, created_at: at(-18, 9), updated_at: at(-2, 9),
    application_count: 5, d_day: 5,
    stage_counts: { applied: 2, screening: 1, interview: 1, accepted: 1, rejected: 0 },
  },
  {
    id: 3, title: '데이터 엔지니어', description: null, status: 'closed',
    deadline: null, created_by: 0, created_at: at(-40, 9), updated_at: at(-10, 9),
    application_count: 2, d_day: null,
    stage_counts: { applied: 0, screening: 0, interview: 1, accepted: 1, rejected: 0 },
  },
]

function app(
  id: number, job_posting_id: number, name: string, current_stage: Stage,
  career_years: number | null, createdDaysAgo: number,
): ApplicationListItem {
  return {
    id, job_posting_id, name, current_stage, career_years,
    email: `applicant${id}@example.com`,
    created_at: at(-createdDaysAgo, 10),
    avg_score: null,
  }
}

const APPS: ApplicationListItem[] = [
  app(101, 1, '최민서', 'applied', 2, 1),
  app(102, 2, '이준호', 'applied', null, 0),
  app(103, 1, '한지우', 'screening', 3, 4),
  app(104, 2, '박지민', 'screening', 5, 4),
  app(105, 1, '오세라', 'screening', 1, 3),
  app(106, 2, '김도현', 'interview', 4, 6),
  app(107, 1, '이서연', 'interview', 2, 7),
  app(108, 1, '정우진', 'interview', 6, 7),
  app(109, 2, '송하은', 'interview', 3, 5),
  app(110, 1, '백서준', 'accepted', 4, 12),
  app(111, 2, '남태윤', 'rejected', 2, 10),
]

const postingTitle = (id: number) => POSTINGS.find((p) => p.id === id)?.title ?? ''

function iv(
  proposal_id: number, application_id: number, dayOffset: number, h: number, m: number,
  interviewer_name: string,
): Interview {
  const a = APPS.find((x) => x.id === application_id)
  return {
    proposal_id, application_id,
    applicant_name: a?.name ?? '', posting_title: postingTitle(a?.job_posting_id ?? 0),
    interviewer_id: 0, interviewer_name,
    start_at: at(dayOffset, h, m), end_at: at(dayOffset, h + 1, m),
  }
}

/* 오늘 6건 — 축소판이 4건에서 끊고 "외 2건 →" 을 그리는지 보이는 개수 */
const INTERVIEWS: Interview[] = [
  iv(901, 107, 0, 10, 0, '유하늘'),
  iv(902, 108, 0, 11, 0, '유하늘'),
  iv(903, 106, 0, 14, 0, '장보라'),
  iv(904, 109, 0, 15, 30, '장보라'),
  iv(905, 103, 0, 16, 30, '유하늘'),
  iv(906, 104, 0, 17, 30, '장보라'),
  iv(907, 106, 2, 10, 0, '장보라'),
  iv(908, 107, 2, 14, 0, '유하늘'),
  iv(909, 109, 4, 11, 0, '장보라'),
]

/* 면접 단계 지원자별 일정 상태. 없는 id 는 "제안 중" 폴백 —
   여기서 undefined 를 돌려주면 대시보드 load() 전체가 에러로 죽는다 */
const SCHEDULE_STATUS: Record<number, ScheduleStatus> = {
  106: { status: 'confirmed', confirmed_slot: { id: 1, start_at: at(0, 14), end_at: at(0, 15) }, expires_at: null, created_at: at(-2, 9) },
  107: { status: 'confirmed', confirmed_slot: { id: 2, start_at: at(0, 10), end_at: at(0, 11) }, expires_at: null, created_at: at(-2, 9) },
  108: { status: 'proposed', confirmed_slot: null, expires_at: at(2, 18), created_at: at(-1, 9) },
  109: { status: 'confirmed', confirmed_slot: { id: 3, start_at: at(0, 15, 30), end_at: at(0, 16, 30) }, expires_at: null, created_at: at(-1, 9) },
}

const FALLBACK_STATUS: ScheduleStatus = {
  status: 'proposed', confirmed_slot: null, expires_at: at(3, 18), created_at: at(-1, 9),
}

function searchApps(query: Query): SearchResult {
  let items = APPS
  if (typeof query.stage === 'string') items = items.filter((a) => a.current_stage === query.stage)
  if (query.posting_id !== undefined) items = items.filter((a) => a.job_posting_id === Number(query.posting_id))
  if (typeof query.q === 'string' && query.q !== '') {
    const q = String(query.q)
    items = items.filter((a) => a.name.includes(q) || a.email.includes(q))
  }
  const total = items.length
  const offset = query.offset === undefined ? 0 : Number(query.offset)
  const limit = query.limit === undefined ? 20 : Number(query.limit)
  return {
    items: items.slice(offset, offset + limit),
    total: query.with_total ? total : null,
    took_ms: 2,
    next_cursor: null,
  }
}

function detail(a: ApplicationListItem): ApplicationDetail {
  return {
    ...a,
    phone: '010-0000-0000',
    education: '학사',
    skills: ['TypeScript', 'React'],
    self_intro: '(로컬 목 데이터) 자기소개서 본문입니다.',
    ai_summary: '(로컬 목 데이터) 공고 요건과의 적합 지점 요약입니다.',
  }
}

const AGENT_REPLY: AgentChatResponse = {
  reply: '지금은 **로컬 목 데이터** 모드예요 — 서버 없이 화면만 확인하는 상태입니다.\n- 조회 화면은 고정된 더미로 채워집니다\n- 단계 변경 같은 쓰기 작업은 실서버가 있어야 동작해요',
  tool_calls: [], pending_action: null,
  input_tokens: 0, output_tokens: 0, model: 'mock', cost_usd: 0,
}

type Query = Record<string, string | number | boolean | undefined>

let announced = false

/* 처리할 수 있으면 응답 본문을, 아니면 undefined (원래 에러가 그대로 던져진다) */
export function mockResponse(method: string, path: string, query: Query = {}): unknown {
  const serve = (body: unknown): unknown => {
    if (!announced) {
      announced = true
      console.info('[arda] 서버 응답이 없어 로컬 목 데이터로 그립니다 (dev 전용 — api/mock.ts)')
    }
    return body
  }

  if (method === 'POST') {
    if (path === '/auth/login') return serve({ access_token: 'dev-mock-token', token_type: 'bearer' } satisfies TokenResponse)
    if (path === '/agent/chat') return serve(AGENT_REPLY)
    return undefined
  }
  if (method !== 'GET') return undefined

  if (path === '/auth/me') return serve(USER)
  if (path === '/postings') return serve(POSTINGS)

  const posting = /^\/postings\/(\d+)$/.exec(path)
  if (posting) return serve(POSTINGS.find((p) => p.id === Number(posting[1])) ?? POSTINGS[0])

  if (path === '/applications') return serve(searchApps(query))

  if (path === '/schedules') {
    const from = typeof query.from === 'string' ? query.from : null
    const to = typeof query.to === 'string' ? query.to : null
    const items = INTERVIEWS.filter(
      (i) => (from === null || i.start_at >= from) && (to === null || i.start_at < to),
    )
    return serve({ items, count: items.length })
  }

  const proposal = /^\/applications\/(\d+)\/schedule-proposals$/.exec(path)
  if (proposal) return serve(SCHEDULE_STATUS[Number(proposal[1])] ?? FALLBACK_STATUS)

  const noteList = /^\/applications\/(\d+)\/notes$/.exec(path)
  if (noteList) return serve([] satisfies Note[])

  const appDetail = /^\/applications\/(\d+)$/.exec(path)
  if (appDetail) {
    const a = APPS.find((x) => x.id === Number(appDetail[1]))
    return a === undefined ? undefined : serve(detail(a))
  }

  if (/^\/interviewers\/\d+\/applications$/.test(path)) {
    return serve({
      assignments: [
        { id: 1, application_id: 106, interviewer_id: 0, assigned_by: 0, created_at: at(-1, 9) },
        { id: 2, application_id: 109, interviewer_id: 0, assigned_by: 0, created_at: at(-1, 9) },
      ],
      count: 2,
    } satisfies AssignedApplications)
  }

  return undefined
}
