import type { ApplicationDetail, Evaluation, Posting } from '../api/types'

/* 평가 현황 목록 — 왼쪽 공고 레일 + 오른쪽 줄 목록.
   Evaluations.tsx 가 데이터를 모으고 여기서는 그리기만 한다.

   부르는 API 는 전부 이미 열려 있다:
     GET /interviewers/{me}/applications → 배정 + 배정일
     GET /applications/{id}             → evaluations[] · avg_score
     GET /users                         → evaluator_id → 이름
     GET /postings                      → 공고 이름
   백엔드 변경 없음. */

/* 최고−최저가 이만큼 벌어지면 '의견 갈림'. 1~5 척도에서 2 는 "좋다"와 "보통"이
   아니라 "뽑자"와 "아니다" 만큼의 거리다 */
const SPLIT_GAP = 2

/* 배정 후 이 일수를 넘겼는데 내가 아직 안 냈으면 경과 표시 */
export const STALE_DAYS = 3

const DAY = 24 * 60 * 60 * 1000

export interface QueueItem {
  applicationId: number
  assignedAt: string
  detail: ApplicationDetail
}

/* 같은 성씨가 흔해 이니셜만으로는 구분이 안 된다 — 이름을 해시해 색을 고정한다.
   같은 사람은 어느 화면에서든 같은 색이다 */
const PAL: [string, string][] = [
  ['rgba(34,211,238,.20)', '#7DD3FC'],
  ['rgba(167,139,250,.20)', '#C4B5FD'],
  ['rgba(52,211,153,.20)', '#6EE7B7'],
  ['rgba(251,191,36,.18)', '#FCD34D'],
  ['rgba(96,165,250,.20)', '#93C5FD'],
  ['rgba(240,163,143,.18)', '#F0A38F'],
]

export function avatarOf(name: string): { ini: string; bg: string; fg: string } {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
  const [bg, fg] = PAL[h % PAL.length]
  return { ini: name.slice(0, 2), bg, fg }
}

function daysSince(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / DAY)
}

export interface Row {
  item: QueueItem
  postingId: number
  postingTitle: string
  /* 내가 낸 평가. 없으면 아직 내 차례다 */
  mine: Evaluation | null
  others: Evaluation[]
  days: number
  split: boolean
  /* 표시용 점수 문자열. 갈렸으면 "5.0 / 2.0" 처럼 양끝을 보여 준다 —
     평균 3.5 하나만 적으면 "무난함" 으로 읽혀 갈린 사실이 지워진다 */
  scoreText: string
  scoreTone: 'ok' | 'warn' | 'none'
  sub: string
}

export function buildRows(
  queue: QueueItem[],
  postings: Map<number, Posting>,
  meId: number,
): Row[] {
  return queue.map((item) => {
    const evals = item.detail.evaluations ?? []
    const mine = evals.find((e) => e.evaluator_id === meId) ?? null
    const others = evals.filter((e) => e.evaluator_id !== meId)
    const scores = evals.map((e) => e.score)
    const lo = Math.min(...scores)
    const hi = Math.max(...scores)
    const split = scores.length >= 2 && hi - lo >= SPLIT_GAP
    const days = daysSince(item.assignedAt)

    let scoreText = '미착수'
    let scoreTone: Row['scoreTone'] = 'none'
    let sub = ''
    if (split) {
      scoreText = `${hi.toFixed(1)} / ${lo.toFixed(1)}`
      scoreTone = 'warn'
    } else if (scores.length > 0) {
      scoreText = (item.detail.avg_score ?? scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1)
      scoreTone = mine === null ? 'none' : 'ok'
      if (mine === null) sub = `${others.length}명 제출`
    }

    return {
      item,
      postingId: item.detail.job_posting_id,
      postingTitle: postings.get(item.detail.job_posting_id)?.title ?? '—',
      mine,
      others,
      days,
      split,
      scoreText,
      scoreTone,
      sub,
    }
  })
}

export interface Group {
  id: number | 'all'
  title: string
  done: number
  total: number
}

/* 왼쪽 레일 — 고르는 곳이면서 진행률 표시다. '전체' 가 맨 위에 있어
   공고를 가로지르는 시야를 잃지 않는다 */
export function buildGroups(rows: Row[]): Group[] {
  const byPosting = new Map<number, Row[]>()
  for (const r of rows) {
    const list = byPosting.get(r.postingId) ?? []
    list.push(r)
    byPosting.set(r.postingId, list)
  }
  const done = (list: Row[]) => list.filter((r) => r.mine !== null).length
  return [
    { id: 'all', title: '전체', done: done(rows), total: rows.length },
    ...[...byPosting.entries()].map(([id, list]) => ({
      id,
      title: list[0].postingTitle,
      done: done(list),
      total: list.length,
    })),
  ]
}
