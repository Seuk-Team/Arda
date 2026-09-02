import { useCallback, useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, ReactElement, ReactNode } from 'react'
import { ApiError } from '../api/client'
import { agent } from '../api/endpoints'
import type { AgentHistoryMessage, AgentPendingAction, AgentToolCall } from '../api/types'
import { STAGE_LABEL } from '../lib/stage'
import { useToast } from './Toast'
import Sprout from './Sprout'
import styles from './ArChat.module.css'

/* 아르 에이전트 채팅 (ADR-0009 확인 카드 · ADR-0003 "AI는 추천까지, 확정은 사람").
   패널 셸(열고 닫기·3D 캐릭터)은 바깥이 그린다 — 여기는 그 안에 들어가는 대화 하나다.
   쓰기 도구는 절대 스스로 실행하지 않는다: 서버가 pending_action 을 주면 확인 카드를
   띄우고, 사람이 [확인]을 누를 때만 /agent/confirm 을 부른다. */

export type ArMotion = 'idle' | 'listen' | 'think' | 'ask' | 'confirm' | 'fail'

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
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState<'chat' | 'confirm' | null>(null)
  /* 성공·실패 직후 잠깐 짓는 표정. 지나면 평상시 모션으로 돌아간다 */
  const [flash, setFlash] = useState<'confirm' | 'fail' | null>(null)

  const seq = useRef(0)
  const streamRef = useRef<HTMLDivElement>(null)
  const fieldRef = useRef<HTMLTextAreaElement>(null)

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
  }, [items, pending, busy])

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
    setPending(null)
    setFlash(null)
    push({ kind: 'user', text: message })
    setBusy('chat')

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      const res = await agent.chat(message, history, ctrl.signal)

      if (res.tool_calls.length > 0) push({ kind: 'log', lines: res.tool_calls.map(logLine) })
      if (res.reply.trim()) push({ kind: 'ar', text: res.reply })
      if (res.pending_action) setPending(res.pending_action)

      /* 이력의 assistant 자리는 비울 수 없다 — 답변이 없으면 확인 요청 문장을 대신 넣는다 */
      const assistant = res.reply.trim() || res.pending_action?.description || '(확인 대기)'
      setHistory((prev) => [...prev, { role: 'user', content: message }, { role: 'assistant', content: assistant }])
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      push({ kind: 'error', text: errorText(err) })
      setFlash('fail')
    } finally {
      abortRef.current = null
      setBusy(null)
    }
  }

  async function confirmPending() {
    if (!pending || busy) return
    const action = pending
    setBusy('confirm')

    try {
      const res = await agent.confirm(action.tool_name, action.arguments)
      setPending(null)
      /* 무엇이 바뀌었는지 아르가 말한다 — 실행 로그는 숨겨져 있어 이게 유일한 확인 */
      push({ kind: 'ar', text: confirmSummary(action, res.result) })
      setFlash('confirm')
      show('ok', `${toolLabel(action.tool_name)}을(를) 실행했습니다`)
    } catch (err) {
      /* 실패해도 카드를 지운다 — 남겨 두면 누를 때마다 같은 오류가 쌓인다
         (2026-09-02 실측: 빨간 박스 5개). 이유는 아르 말풍선으로. 다시 하려면 새로 요청. */
      const text = errorText(err)
      setPending(null)
      push({ kind: 'ar', text: confirmFailureText(action, text) })
      setFlash('fail')
      show('fail', text)
    } finally {
      setBusy(null)
    }
  }

  function cancelPending() {
    if (!pending) return
    setPending(null)
    push({ kind: 'log', lines: ['취소했습니다 — 아무것도 실행하지 않았습니다'] })
    fieldRef.current?.focus()
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    /* 한글 조합 중 Enter 는 확정용이다 — 여기서 보내면 마지막 글자가 잘린다 */
    if (e.key !== 'Enter' || e.shiftKey || e.nativeEvent.isComposing) return
    e.preventDefault()
    void send()
  }

  const locked = busy !== null

  return (
    <div className={styles.root}>
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
