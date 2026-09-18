import { useCallback, useEffect, useRef, useState } from 'react'
import type { DragEvent, KeyboardEvent, ReactElement, ReactNode } from 'react'
import { api, ApiError } from '../api/client'
import { agent } from '../api/endpoints'
import type { AgentChoice, AgentHistoryMessage, AgentPendingAction, AgentToolCall } from '../api/types'
import { STAGE_LABEL } from '../lib/stage'
import { useToast } from './Toast'
import Sprout from './Sprout'
import styles from './ArChat.module.css'

/* 아르 에이전트 채팅 (ADR-0009 확인 카드 · ADR-0003 "AI는 추천까지, 확정은 사람").
   패널 셸(열고 닫기·3D 캐릭터)은 바깥이 그린다 — 여기는 그 안에 들어가는 대화 하나다.
   쓰기 도구는 절대 스스로 실행하지 않는다: 서버가 pending_action 을 주면 확인 카드를
   띄우고, 사람이 [확인]을 누를 때만 /agent/confirm 을 부른다. */

export type ArMotion = 'idle' | 'listen' | 'think' | 'ask' | 'confirm' | 'fail'

/* 이력서 드래그·드롭 접수 (A안 · 2026-09-17)
   담당자가 아르 채팅 창에 이력서 PDF/DOCX 를 떨어뜨리면
   1) 파일을 S3 로 올린다 (공개 지원 폼과 같은 presign 경로 재사용)
   2) 아르에게 "이 이력서로 지원자 접수해줘 (s3_key + filename)" 를 자동으로 말한다
   3) 아르가 담당자에게 공고·이름·연락처를 물으면 담당자가 답한다
   4) 확인 카드 → 승인 → create_application 실행 → 요약·앵커 자동 트리거

   백엔드는 s3_key 만 받는다 — 텍스트 추출은 접수 뒤 요약 chain 이 한다. */
const DROP_EXT = /\.(pdf|docx|hwpx|hwp|txt)$/i
const DROP_MAX_BYTES = 20 * 1024 * 1024  // 20MB — 공개 지원 폼과 같은 상한
// 자기소개서로 볼 파일 이름 힌트. 이력서·자소서 두 개를 함께 떨어뜨렸을 때 어느 것이
// 자소서인지 파일명으로 가른다 (못 가르면 첫째=이력서·둘째=자소서 순).
const COVER_HINT = /(자소서|자기소개|커버|cover)/i

async function uploadDropped(file: File): Promise<{ s3_key: string; content_type: string }> {
  /* 공개 지원 폼과 같은 presign 경로. 담당자 인증이 있어도 여기서는 auth: false 를 유지 —
     같은 서버 로직·검증을 그대로 재사용하는 자리라 별도 관리자 엔드포인트를 새로 만들지 않는다. */
  const contentType = file.type || 'application/octet-stream'
  const presign = await api.post<{ upload_url: string; s3_key: string }>(
    '/public/files/presign-upload',
    { filename: file.name, content_type: contentType, kind: 'resume', size_bytes: file.size },
    { auth: false },
  )
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', presign.upload_url)
    xhr.setRequestHeader('Content-Type', contentType)
    xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(`올리지 못했습니다 (${xhr.status})`)))
    xhr.onerror = () => reject(new Error('올리지 못했습니다'))
    xhr.send(file)
  })
  return { s3_key: presign.s3_key, content_type: contentType }
}

/* 실행 로그에 쓰는 도구 이름. TOOLS.md 의 도구 목록과 같은 순서 */
const TOOL_LABELS: Record<string, string> = {
  /* 읽기 */
  search_applications: '지원자 검색',
  get_application: '지원자 상세 조회',
  list_postings: '공고 목록 조회',
  search_users: '내부 사용자 검색',
  list_availability: '가용 시간 조회',
  get_schedule_status: '일정 상태 조회',
  list_interviews: '면접 일정 조회',
  /* 쓰기 — 확인 카드를 거친다 */
  change_stage: '단계 변경',
  assign_interviewer: '면접관 배정',
  create_schedule_proposal: '면접 일정 제안',
  draft_email: '메일 초안',
}

function toolLabel(name: string) {
  return TOOL_LABELS[name] ?? name
}

/* ── 확인 카드 실행 결과를 아르 말로 ───────────────────────────
   실행 로그는 숨겼으므로(2026-09-02), 실행됐다는 사실과 무엇이 바뀌었는지는 아르가
   말풍선으로 알린다. 실패도 빨간 박스가 아니라 이유를 설명한다. */
function stageKr(code: unknown): string {
  return typeof code === 'string' && code in STAGE_LABEL
    ? STAGE_LABEL[code as keyof typeof STAGE_LABEL]
    : String(code ?? '')
}

/* _describe_action 형식 "이름 (학력)을(를) … 합니다" 에서 앞부분만 */
function subjectOf(action: AgentPendingAction): string {
  const i = action.description.indexOf('을(를)')
  return i > 0 ? action.description.slice(0, i).trim() : ''
}

function confirmSummary(action: AgentPendingAction, result: Record<string, unknown>): string {
  const who = subjectOf(action)
  if (action.tool_name === 'change_stage') {
    const from = stageKr(result.from_stage)
    const to = stageKr(result.to_stage)
    const mail = result.mail_queued ? ' 안내 메일이 발송 대기열에 들어갔어요.' : ''
    return `${who ? `${who} 님을 ` : ''}${from} → ${to} 단계로 변경했어요.${mail}`
  }
  if (action.tool_name === 'send_email') return `${who ? `${who} 님에게 ` : ''}메일을 보냈어요.`
  return `${toolLabel(action.tool_name)}을(를) 완료했어요.`
}

function confirmFailureText(action: AgentPendingAction, raw: string): string {
  /* 서버 메시지의 단계 코드(applied 등)를 화면 라벨로 */
  const pretty = raw.replace(/\b(applied|screening|interview|accepted|rejected)\b/g, (m) => stageKr(m))
  return `${toolLabel(action.tool_name)}을(를) 실행하지 못했어요. ${pretty}`
}

/* 확인 응답 감지 — pending 카드가 살아있을 때만 매치한다.
   4B 가 채팅 경로로 확인 응답을 처리하면 이전 도구 결과의 id 를 재추론하다
   지어내는 실패가 있었다 (id=123, id=2 사례. 2026-09-02 실측). LLM 을 다시
   부르지 않고 저장된 arguments 그대로 confirm 하는 편이 정확하고 빠르다.

   규칙:
   - CONFIRM_HEAD: 확인 단어로 문장 시작 + 그 뒤 자유 텍스트 허용 (word boundary)
     "응", "응 변경해줘", "네 진행할게요", "좋아, 그렇게 해" 다 잡는다
   - CANCEL_ANYWHERE: 부정 신호가 메시지 어디에 있어도 취소 우선
     "응 아니 취소해줘" 는 취소로 (CONFIRM_HEAD 도 매치되지만 CANCEL 이 이김) */
const CONFIRM_HEAD = /^\s*(응|네|넵|예|좋아요?|해줘|해|맞아요?|진행(?:해줘|할게요?|해)?|ㅇㅇ|ㅇㅋ|ok|okay|yes|yep|y|어)(?:\s|[.,!~?]|$)/i
const CANCEL_ANYWHERE = /(아니(?:야|요|에요)?|취소|안\s?할래|안\s?해|안\s?됨|nope|\bno\b)/i

function classifyConfirmReply(message: string): 'confirm' | 'cancel' | null {
  if (CANCEL_ANYWHERE.test(message)) return 'cancel'
  if (CONFIRM_HEAD.test(message)) return 'confirm'
  return null
}

/* 인자를 한 줄로. 값이 길면 자른다 (§7 — 극단값 전제) */
function summarizeInput(input: Record<string, unknown>) {
  const parts = Object.entries(input).map(([k, v]) => {
    const text = typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean'
      ? String(v)
      : JSON.stringify(v)
    return `${k}=${text.length > 40 ? `${text.slice(0, 40)}…` : text}`
  })
  return parts.join(' · ')
}

function logLine(call: AgentToolCall) {
  const args = summarizeInput(call.input)
  return args ? `${toolLabel(call.name)} — ${args}` : toolLabel(call.name)
}

/* 에러는 종류를 구분해 말한다 — 권한·인증·네트워크·서버는 사용자가 할 일이 다르다 */
function errorText(err: unknown) {
  if (err instanceof ApiError) {
    if (err.code === 'NETWORK') return '서버에 연결하지 못했습니다. 네트워크를 확인해 주세요.'
    if (err.status === 403 || err.code === 'FORBIDDEN') return '이 작업을 할 권한이 없습니다.'
    if (err.status === 401 || err.code === 'UNAUTHORIZED') return '로그인이 만료됐습니다. 다시 로그인해 주세요.'
    if (err.status >= 500) return '서버가 응답하지 못했습니다. 잠시 뒤 다시 시도해 주세요.'
    return err.message
  }
  return '요청을 처리하지 못했습니다.'
}

/* ── 최소 마크다운 (굵게 · 불릿) ─────────────────────────────
   LLM 답변의 **…** 와 "- " 가 생 기호로 노출되던 것을 그린다 (2026-08-31).
   딱 이 둘만 — 헤딩·링크·코드는 프롬프트에서 막는 게 맞고, 여기서 더 그리지 않는다. */
function mdInline(text: string): ReactNode[] {
  return text
    .split(/\*\*(.+?)\*\*/g)
    .map((part, i) => (i % 2 === 1 ? <b key={i}>{part}</b> : part))
}

function mdBlocks(text: string): ReactElement[] {
  const out: ReactElement[] = []
  let para: string[] = []
  let list: string[] = []

  const flushPara = () => {
    if (para.length === 0) return
    out.push(<p key={out.length}>{mdInline(para.join('\n'))}</p>)
    para = []
  }
  const flushList = () => {
    if (list.length === 0) return
    out.push(
      <ul key={out.length}>
        {list.map((line, i) => <li key={i}>{mdInline(line)}</li>)}
      </ul>,
    )
    list = []
  }

  for (const line of text.split('\n')) {
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line)
    if (bullet) {
      flushPara()
      list.push(bullet[1])
    } else if (line.trim() === '') {
      flushPara()
      flushList()
    } else {
      flushList()
      para.push(line)
    }
  }
  flushPara()
  flushList()
  return out
}

type Body =
  | { kind: 'user'; text: string }
  | { kind: 'ar'; text: string }
  | { kind: 'log'; lines: string[] }
  | { kind: 'error'; text: string }

type Item = Body & { id: number }

export default function ArChat({
  onMotion,
  focusOn = false,
}: {
  onMotion?: (m: ArMotion) => void
  /* false→true 로 바뀔 때 입력창에 포커스를 준다. 패널 셸이 열림 상태를 그대로 넘긴다 —
     셸은 이 컴포넌트 내부의 textarea 를 직접 알 필요가 없다. */
  focusOn?: boolean
}): ReactElement {
  const { show } = useToast()

  const [items, setItems] = useState<Item[]>([
    { id: 0, kind: 'ar', text: '안녕하세요! 저는 **아르**예요.\n지원자 검색, 단계 변경, 면접 일정 같은 채용 업무를 도와드려요.' },
  ])
  /* 서버로 보내는 대화 이력. Anthropic 규칙상 user/assistant 가 번갈아야 하고 빈 내용은
     안 되므로, 성공한 왕복만 한 쌍씩 쌓는다 (실패한 요청은 넣지 않는다). */
  const [history, setHistory] = useState<AgentHistoryMessage[]>([])
  const [pending, setPending] = useState<AgentPendingAction | null>(null)
  /* 동명이인 선택지 — 서버가 choices 를 주면 아르 말풍선 아래 버튼으로. 다음 요청이
     나가면 비운다 (버튼이 남아 있으면 이미 지나간 질문에 답하게 된다). */
  const [choices, setChoices] = useState<AgentChoice[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState<'chat' | 'confirm' | null>(null)
  /* 성공·실패 직후 잠깐 짓는 표정. 지나면 평상시 모션으로 돌아간다 */
  const [flash, setFlash] = useState<'confirm' | 'fail' | null>(null)

  const seq = useRef(0)
  const streamRef = useRef<HTMLDivElement>(null)
  const fieldRef = useRef<HTMLTextAreaElement>(null)

  /* 드래그·드롭 상태. `depth` 로 dragEnter/dragLeave 중첩을 센다 — 자식 요소를 지나갈 때마다
     leave 가 나서 오버레이가 깜빡거리는 것을 막는다. */
  const [dropOver, setDropOver] = useState(false)
  const [dropBusy, setDropBusy] = useState<string | null>(null)  // 업로드 중인 파일명
  const dropDepth = useRef(0)

  const push = useCallback((body: Body) => {
    seq.current += 1
    setItems((prev) => [...prev, { ...body, id: seq.current }])
  }, [])

  /* ── 모션 ────────────────────────────────────────────────
     상태에서 모션을 끌어내고 바뀔 때만 알린다 — 렌더마다 부르면 부모가 흔들린다. */
  const motion: ArMotion = busy
    ? 'think'
    : (flash ?? (pending ? 'ask' : draft.trim() ? 'listen' : 'idle'))

  const motionCb = useRef(onMotion)
  useEffect(() => {
    motionCb.current = onMotion
  }, [onMotion])
  useEffect(() => {
    motionCb.current?.(motion)
  }, [motion])

  /* 패널은 닫혀도 언마운트되지 않으므로 열릴 때만 포커스를 가져온다 */
  useEffect(() => {
    if (focusOn) fieldRef.current?.focus()
  }, [focusOn])

  useEffect(() => {
    if (!flash) return
    const t = window.setTimeout(() => setFlash(null), 1600)
    return () => window.clearTimeout(t)
  }, [flash])

  /* 새 메시지에서 하단 고정. 패널 밖으로 스크롤이 새지 않게 하는 건 CSS 쪽(overscroll) */
  useEffect(() => {
    const el = streamRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [items, pending, choices, busy])

  /* 요청 중에 패널이 닫히면 fetch 를 놓아 준다 */
  const abortRef = useRef<AbortController | null>(null)
  useEffect(() => () => abortRef.current?.abort(), [])

  async function send() {
    const message = draft.trim()
    if (!message || busy) return

    /* 레버 ① 확인 응답 규칙 라우터 — pending 카드가 살아있고 사용자가
       확인/취소로 답했으면 LLM 을 다시 부르지 않는다. 저장된 arguments 로
       바로 confirm (또는 취소). 4B 재추론에서 id 를 지어내는 실패를 원천 차단.
       매치 안 되면 아래 기존 LLM 흐름으로 이어간다. */
    if (pending) {
      const kind = classifyConfirmReply(message)
      if (kind === 'confirm') {
        setDraft('')
        push({ kind: 'user', text: message })
        await confirmPending()
        return
      }
      if (kind === 'cancel') {
        setDraft('')
        push({ kind: 'user', text: message })
        cancelPending()
        return
      }
    }

    setDraft('')
    await submit(message, message)
  }

  /* 선택지 카드 — 카드 안 확인 버튼 클릭 = 서버가 pending 을 미리 붙여 왔으면
     agent.confirm 직접 (원샷), 아니면 원래 요청을 id 와 함께 다시 보내 서버가
     pending 을 만들게 (폴백, LLM 경로 등). 담당자가 "이름 → 목록 → id 재입력 →
     확인 카드 → 확인" 네 걸음이던 것을 카드 딸깍 하나로 (2026-09-09). */
  function choose(c: AgentChoice) {
    if (busy) return
    if (c.pending_action) {
      const action = c.pending_action
      push({ kind: 'user', text: `${c.label} — ${action.description}` })
      setChoices([])
      void runConfirm(action)
      return
    }
    void submit(c.message, `${c.label} 선택`, c.application_id ?? undefined)
  }

  /* message: 서버로 가는 글 · shown: 말풍선·이력에 남는 글. 보통은 같고 선택지만 다르다 */
  async function submit(message: string, shown: string, applicationId?: number) {
    setPending(null)
    setChoices([])
    setFlash(null)
    push({ kind: 'user', text: shown })
    setBusy('chat')

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      const res = await agent.chat(message, history, ctrl.signal, applicationId)

      if (res.tool_calls.length > 0) push({ kind: 'log', lines: res.tool_calls.map(logLine) })
      if (res.reply.trim()) push({ kind: 'ar', text: res.reply })
      if (res.pending_action) setPending(res.pending_action)
      if (res.choices?.length) setChoices(res.choices)

      /* 이력의 assistant 자리는 비울 수 없다 — 답변이 없으면 확인 요청 문장을 대신 넣는다 */
      const assistant = res.reply.trim() || res.pending_action?.description || '(확인 대기)'
      setHistory((prev) => [...prev, { role: 'user', content: shown }, { role: 'assistant', content: assistant }])
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      push({ kind: 'error', text: errorText(err) })
      setFlash('fail')
    } finally {
      abortRef.current = null
      setBusy(null)
    }
  }

  /* 실행 본체. 확인 카드(pending)와 선택 카드(choice.pending_action) 둘 다 여기로.
     예전엔 confirmPending 이 이 로직을 갖고 있어 카드 원샷 실행 경로에서 재사용
     못 했다. 실패해도 카드는 이미 지운 뒤라 여기서 다시 다루지 않는다. */
  async function runConfirm(action: AgentPendingAction) {
    if (busy) return
    setBusy('confirm')
    try {
      const res = await agent.confirm(action.tool_name, action.arguments)
      /* 무엇이 바뀌었는지 아르가 말한다 — 실행 로그는 숨겨져 있어 이게 유일한 확인 */
      push({ kind: 'ar', text: confirmSummary(action, res.result) })
      setFlash('confirm')
      show('ok', `${toolLabel(action.tool_name)}을(를) 실행했습니다`)
    } catch (err) {
      /* 이유는 아르 말풍선으로. 다시 하려면 새로 요청. 카드는 이미 이 함수 밖에서 지웠다. */
      const text = errorText(err)
      push({ kind: 'ar', text: confirmFailureText(action, text) })
      setFlash('fail')
      show('fail', text)
    } finally {
      setBusy(null)
    }
  }

  async function confirmPending() {
    if (!pending || busy) return
    const action = pending
    /* 실행 시작 전에 카드를 지운다 — 실패해도 카드를 남기지 않는다 (2026-09-02 실측:
       남겨 두면 누를 때마다 같은 오류가 쌓여 빨간 박스 5개). */
    setPending(null)
    await runConfirm(action)
  }

  function cancelPending() {
    if (!pending) return
    setPending(null)
    push({ kind: 'log', lines: ['취소했습니다 — 아무것도 실행하지 않았습니다'] })
    fieldRef.current?.focus()
  }

  /* ── 이력서 드래그·드롭 (2026-09-17) ─────────────────────────────
     dragEnter/leave 는 자식 요소를 지나갈 때마다 나니 depth 로 카운트해서 오버레이가
     깜빡이지 않게 한다. 드롭 파일이 여러 개면 첫 번째만 받는다 (아르 채팅은 하나에
     이력서 하나씩 접수하는 자리라 두 개 이상 받는 것은 UX 상 혼란). */
  function onDragEnter(e: DragEvent<HTMLDivElement>) {
    if (busy || dropBusy !== null) return
    if (!Array.from(e.dataTransfer.types).includes('Files')) return
    e.preventDefault()
    dropDepth.current += 1
    setDropOver(true)
  }
  function onDragOver(e: DragEvent<HTMLDivElement>) {
    if (busy || dropBusy !== null) return
    if (!Array.from(e.dataTransfer.types).includes('Files')) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }
  function onDragLeave() {
    dropDepth.current = Math.max(0, dropDepth.current - 1)
    if (dropDepth.current === 0) setDropOver(false)
  }
  async function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    dropDepth.current = 0
    setDropOver(false)
    if (busy || dropBusy !== null) return

    /* 이력서·자소서를 함께 떨어뜨릴 수 있다 — 여러 파일을 다 받는다 (예전엔 [0] 하나만).
       create_application 은 이력서 1 + 자소서 1 을 받으므로 앞 두 개만 쓴다. */
    const dropped = Array.from(e.dataTransfer.files || [])
    if (dropped.length === 0) return
    for (const f of dropped) {
      if (!DROP_EXT.test(f.name)) {
        push({ kind: 'error', text: `${f.name}: PDF · DOCX · HWPX · TXT 만 접수할 수 있어요.` })
        setFlash('fail')
        return
      }
      if (f.size > DROP_MAX_BYTES) {
        push({ kind: 'error', text: `${f.name}: 파일이 20MB 를 넘어요.` })
        setFlash('fail')
        return
      }
    }
    const picked = dropped.slice(0, 2)
    if (dropped.length > 2) {
      push({ kind: 'error', text: '이력서·자소서 두 개까지 받아요. 앞 두 개만 접수할게요.' })
    }

    setDropBusy(picked.map((f) => f.name).join(', '))
    try {
      const uploaded = await Promise.all(
        picked.map(async (f) => ({ file: f, ...(await uploadDropped(f)) })),
      )
      /* 이력서 vs 자소서 구분: 파일명 힌트로 가르고, 못 가르면 첫째=이력서·둘째=자소서 */
      let resume = uploaded[0]
      let cover = uploaded[1]
      if (uploaded.length === 2) {
        const coverIdx = uploaded.findIndex((u) => COVER_HINT.test(u.file.name))
        if (coverIdx >= 0) {
          cover = uploaded[coverIdx]
          resume = uploaded[coverIdx === 0 ? 1 : 0]
        }
      }

      const fileLine = (label: string, u: typeof resume) =>
        [
          `${label} filename: ${u.file.name}`,
          `${label}_s3_key: ${u.s3_key}`,
          `${label} content_type: ${u.content_type}`,
          `${label} size_bytes: ${u.file.size}`,
        ].join('\n')

      const shown =
        picked.length === 2
          ? `📎 ${picked.map((f) => f.name).join(', ')} 을 접수 대상으로 드롭했어요.`
          : `📎 ${picked[0].name} 을 접수 대상으로 드롭했어요.`
      const message = [
        cover
          ? '지원자 이력서·자기소개서 파일을 접수해 주세요.'
          : '지원자 이력서 파일을 접수해 주세요.',
        fileLine('resume', resume),
        ...(cover ? [fileLine('cover_letter', cover)] : []),
        '',
        '어느 공고에 접수할지, 지원자 이름·이메일·전화번호를 이 자리에서 물어봐 주세요.',
        '모두 확인되면 create_application 으로 접수 확인 카드를 띄우고(resume_s3_key' +
          (cover ? '·cover_letter_s3_key 둘 다' : '') +
          '), 승인되면 요약과 무결성 앵커도 자동으로 시작해 주세요.',
      ].join('\n')
      await submit(message, shown)
    } catch (err) {
      push({ kind: 'error', text: err instanceof Error ? err.message : '파일을 올리지 못했습니다.' })
      setFlash('fail')
    } finally {
      setDropBusy(null)
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    /* 한글 조합 중 Enter 는 확정용이다 — 여기서 보내면 마지막 글자가 잘린다 */
    if (e.key !== 'Enter' || e.shiftKey || e.nativeEvent.isComposing) return
    e.preventDefault()
    void send()
  }

  const locked = busy !== null || dropBusy !== null

  return (
    <div
      className={`${styles.root} ${dropOver ? styles.dropOver : ''}`}
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      {/* 드롭 오버레이 — 실제로 드롭 대상이 되는 시각 신호. 자식 이벤트를 가로채지 않게
          pointer-events 는 CSS 에서 none 으로 둔다. */}
      {dropOver && (
        <div className={styles.dropOverlay} aria-hidden="true">
          <div className={styles.dropCard}>
            <span className={styles.dropIcon}>📎</span>
            <span className={styles.dropTitle}>이력서 접수</span>
            <span className={styles.dropSub}>PDF · DOCX · HWPX · TXT · 20MB 이하</span>
          </div>
        </div>
      )}

      {dropBusy !== null && (
        <p className={styles.dropStatus} role="status">
          <span className={styles.spinner} aria-hidden="true" />
          {dropBusy} 올리는 중…
        </p>
      )}
      <div className={styles.stream} ref={streamRef} aria-live="polite" aria-busy={locked}>
        {items.map((item) => {
          if (item.kind === 'user') return <p key={item.id} className={styles.user}>{item.text}</p>
          /* 아르 말은 아이콘 + 앰버 점선 말풍선 가로 배치 (시안 #agSurface) */
          if (item.kind === 'ar') return (
            <div key={item.id} className={styles.arRow}>
              <Sprout className={styles.arIcon} />
              {/* ul 이 들어갈 수 있어 p 가 아니라 div — 문단·불릿은 mdBlocks 가 나눈다 */}
              <div className={styles.ar}>{mdBlocks(item.text)}</div>
            </div>
          )
          if (item.kind === 'error') return <p key={item.id} className={styles.error}>{item.text}</p>
          // 실행 로그(도구 호출 흔적) 는 담당자 UX 상 노이즈라 숨긴다 — 2026-09-02 결정.
          // 데이터는 그대로 남기고 렌더링만 스킵해서 필요시 되살릴 수 있게 둔다.
          return null
        })}

        {/* 동명이인 선택지 — 아르 말풍선 아래, 아이콘 자리만큼 들여서 카드 줄.
            카드 안 확인 버튼 클릭 = 서버가 pending 을 첨부해 왔으면 원샷 실행 (agent.confirm),
            아니면 폴백으로 원래 요청을 id 와 함께 재전송. 앰버 점선은 §1 규약 (확정 대기). */}
        {choices.length > 0 && (
          <div className={styles.arRow} role="group" aria-label="선택">
            <span className={styles.arIcon} aria-hidden="true" />
            <div className={styles.choices}>
              {choices.map((c) => {
                // 공고 선택 카드(이력서 드롭 접수)면 다르게 그린다.
                const isPosting = c.posting_id != null
                // pending 이 있으면 실제로 실행할 문장을 그대로 (서버 _describe_action 결과),
                // 없으면 "이어가기"/"이 공고로 접수" 라벨
                const actionLabel = c.pending_action
                  ? c.pending_action.description
                  : isPosting
                    ? '이 공고로 접수'
                    : '이 지원자로 이어가기'
                // 이름 옆 메타 한 줄. 없는 조각은 뺀다
                const meta: string[] = []
                if (isPosting) {
                  if (typeof c.applicant_count === 'number') meta.push(`지원자 ${c.applicant_count}명`)
                } else {
                  if (c.stage_label) meta.push(`단계 · ${c.stage_label}`)
                  if (typeof c.career_years === 'number') meta.push(`경력 ${c.career_years}년`)
                  if (c.education) meta.push(c.education)
                }
                return (
                  <div key={c.posting_id ?? c.application_id ?? c.label} className={styles.choiceCard}>
                    <p className={styles.choiceHead}><b>{c.label}</b></p>
                    {c.email && <p className={styles.choiceEmail}>{c.email}</p>}
                    {meta.length > 0 && <p className={styles.choiceMeta}>{meta.join(' · ')}</p>}
                    <div className={styles.choiceActions}>
                      <button
                        type="button"
                        className={`btn btn-primary ${styles.choiceBtn}`}
                        disabled={locked}
                        onClick={() => choose(c)}
                      >
                        {actionLabel}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* 쓰기 도구는 여기서 멈춘다. 앰버 점선 = AI 제안 (§1 불변 규약) */}
        {pending && (
          <div className={styles.arRow}>
            <Sprout className={styles.arIcon} />
            <div className={styles.ask}>
              <p className={styles.askBody}>{pending.description}</p>
              {/* 메일 발송만 전문을 펼친다 (G4). 다른 쓰기 도구는 한 줄 요약으로
                  충분하지만(단계는 되돌릴 수 있다), **나간 메일은 못 되돌린다** —
                  승인하는 사람이 실제로 나갈 제목·본문을 읽고 눌러야 한다. */}
              {pending.tool_name === 'send_email' && (
                <div className={styles.mailPreview}>
                  <p className={styles.mailSubject}>{String(pending.arguments.subject ?? '')}</p>
                  <pre className={styles.mailBody}>{String(pending.arguments.body ?? '')}</pre>
                </div>
              )}
              {/* 버튼은 말풍선 안에 — 시안과 같은 순서(확인 · 취소) */}
              <div className={styles.askActions}>
                <button
                  type="button"
                  className={`btn btn-primary ${styles.askBtn}`}
                  onClick={() => void confirmPending()}
                  disabled={busy === 'confirm'}
                >
                  확인
                </button>
                <button
                  type="button"
                  className={`btn btn-secondary ${styles.askBtn}`}
                  onClick={cancelPending}
                  disabled={busy === 'confirm'}
                >
                  취소
                </button>
              </div>
            </div>
          </div>
        )}

        {busy && (
          <p className={styles.waiting}>
            <span className={styles.spinner} aria-hidden="true" />
            {busy === 'chat' ? '생각하는 중…' : '실행하는 중…'}
          </p>
        )}
      </div>

      <div className={styles.composer}>
        <label className="sr-only" htmlFor="ar-chat-field">아르에게 시킬 일</label>
        <textarea
          id="ar-chat-field"
          ref={fieldRef}
          className={styles.field}
          rows={1}
          /* 서버가 2000자에서 422 로 막는다 (ChatRequest.message) — 여기서 먼저 막는다 */
          maxLength={2000}
          value={draft}
          placeholder="무엇이든 시키세요…"
          disabled={locked}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
        {/* 음성 입력은 자리만 잡아 둔다 — 아직 붙이지 않았으므로 눌리지 않는다.
            시안(#agSurface)의 마이크 SVG 그대로. */}
        <button
          type="button"
          className={styles.mic}
          disabled
          aria-label="음성 입력 — 준비 중"
          title="음성 입력 — 준비 중"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
          </svg>
        </button>
      </div>
    </div>
  )
}
