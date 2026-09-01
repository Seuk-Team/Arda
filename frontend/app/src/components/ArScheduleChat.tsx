/* 지원자용 일정 페이지의 "채팅 중심" 레이아웃.
   클로드 채팅처럼 화면 전체가 아르와의 대화이고, 면접 시간 선택은 대화 속
   카드로 들어간다. FAQ 응답은 부모(Schedule.tsx)가 넘겨준 onAsk 로 위임한다 —
   이 컴포넌트는 UI 만, 네트워크는 부모가. */
import { useEffect, useRef, useState } from 'react'
import ArViewer from './ArViewer'
import { mdBlocks } from '../lib/markdown'
import styles from './ArScheduleChat.module.css'

interface PublicSlot {
  id: number
  start_at: string
  end_at: string
}

interface Props {
  status: 'proposed' | 'confirmed' | 'expired'
  applicantName: string
  postingTitle: string
  expiresAt: string | null
  slots: PublicSlot[]
  confirmedSlot: PublicSlot | null
  pending: boolean
  notice: string | null
  onConfirm: (slotId: number) => void
  /* FAQ 질문 → 답변. 부모가 토큰 알고 API 호출. 실패 시 예외를 던진다 */
  onAsk: (question: string) => Promise<string>
}

interface Msg {
  id: number
  who: 'ar' | 'me'
  text: string
  /* 아르 답변이 오는 동안 표시할 자리 홀더. 자기가 아직 응답 대기 중임을 표시 */
  pending?: boolean
}

const THINKING = '생각 중이에요…'
const FALLBACK_ERROR = '지금 답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요.'

/* Schedule.tsx 와 같은 표기 규칙 (05-design §2) — 한국 시간 고정 */
const dayFmt = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short',
})
const timeFmt = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false,
})

function fmtDay(iso: string): string {
  const parts = dayFmt.formatToParts(new Date(iso))
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  return `${get('year')}.${get('month')}.${get('day')} (${get('weekday')})`
}

function fmtTime(iso: string): string {
  return timeFmt.format(new Date(iso))
}

export default function ArScheduleChat({
  status, applicantName, postingTitle, expiresAt, slots, confirmedSlot,
  pending, notice, onConfirm, onAsk,
}: Props) {
  const [picked, setPicked] = useState<number | null>(null)
  const [items, setItems] = useState<Msg[]>([])
  const [draft, setDraft] = useState('')
  /* 모바일 상단 고정 일정 카드 접기 — 채팅 공간을 넓힐 수 있게 (데스크톱 무관) */
  const [folded, setFolded] = useState(false)
  /* 스크롤바는 스크롤하는 동안만 보인다 — 멈추면 0.7초 뒤 사라짐 */
  const [scrolling, setScrolling] = useState(false)
  const scrollTimer = useRef<number | null>(null)

  function onScroll() {
    setScrolling(true)
    if (scrollTimer.current !== null) window.clearTimeout(scrollTimer.current)
    scrollTimer.current = window.setTimeout(() => setScrolling(false), 700)
  }

  useEffect(() => () => {
    if (scrollTimer.current !== null) window.clearTimeout(scrollTimer.current)
  }, [])

  /* PC 에서도 터치처럼 마우스 드래그로 채팅을 위아래로 움직인다 */
  const msgsRef = useRef<HTMLDivElement>(null)
  const drag = useRef<{ startY: number; startTop: number } | null>(null)

  function onMouseDown(e: React.MouseEvent) {
    if (e.button !== 0 || !msgsRef.current) return
    drag.current = { startY: e.clientY, startTop: msgsRef.current.scrollTop }
  }

  function onMouseMove(e: React.MouseEvent) {
    if (!drag.current || !msgsRef.current) return
    if (e.buttons !== 1) {
      drag.current = null
      return
    }
    e.preventDefault() /* 드래그 중 텍스트 선택 방지 */
    msgsRef.current.scrollTop = drag.current.startTop - (e.clientY - drag.current.startY)
  }

  function endDrag() {
    drag.current = null
  }
  const seq = useRef(1)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [items])

  const [asking, setAsking] = useState(false)

  async function send() {
    const text = draft.trim()
    if (!text || asking) return
    setDraft('')
    const myId = seq.current++
    const arId = seq.current++
    setItems((prev) => [
      ...prev,
      { id: myId, who: 'me', text },
      { id: arId, who: 'ar', text: THINKING, pending: true },
    ])
    setAsking(true)
    try {
      const answer = await onAsk(text)
      setItems((prev) => prev.map((m) =>
        m.id === arId ? { ...m, text: answer, pending: false } : m,
      ))
    } catch {
      setItems((prev) => prev.map((m) =>
        m.id === arId ? { ...m, text: FALLBACK_ERROR, pending: false } : m,
      ))
    } finally {
      setAsking(false)
    }
  }

  /* 어느 공고인지가 첫 문장에 들어간다 — 상단 헤더 대신 대화로 안내 */
  const greeting =
    status === 'proposed'
      ? `안녕하세요 ${applicantName} 님, 아르예요!\n지원하신 「${postingTitle}」 공고의 면접 일정을 안내드려요.\n편하신 시간을 골라 주세요. 궁금한 점은 채팅으로 물어보셔도 돼요.`
      : status === 'confirmed'
        ? `안녕하세요 ${applicantName} 님, 아르예요!\n지원하신 「${postingTitle}」 공고의 면접 일정이 확정되어 있어요. 궁금한 점은 채팅으로 물어보세요.`
        : `안녕하세요 ${applicantName} 님, 아르예요!\n지원하신 「${postingTitle}」 공고의 일정 선택 기한이 지났어요. 궁금한 점을 남겨 주시면 담당자에게 전달할게요.`

  /* 슬롯을 날짜별로 묶는다 — Schedule.tsx 카드 레이아웃과 같은 규칙 */
  const byDay = new Map<string, PublicSlot[]>()
  for (const s of slots) {
    const day = fmtDay(s.start_at)
    byDay.set(day, [...(byDay.get(day) ?? []), s])
  }

  /* 일정 블록 — 데스크톱은 왼쪽 패널(지원자 아래), 모바일은 대화 속 카드.
     같은 JSX 를 두 자리에 그리고 CSS 가 화면 폭에 따라 한쪽만 보여준다. */
  const scheduleBlock =
    status === 'proposed' ? (
      <section className={styles.scheduleCard} aria-label="면접 시간 선택">
        {[...byDay.entries()].map(([day, daySlots]) => (
          <div key={day}>
            <h3 className={styles.day}>{day}</h3>
            <div className={styles.slots} role="radiogroup" aria-label={day}>
              {daySlots.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  role="radio"
                  aria-checked={picked === s.id}
                  className={picked === s.id ? `${styles.slot} ${styles.slotPicked}` : styles.slot}
                  onClick={() => setPicked(s.id)}
                  disabled={pending}
                >
                  <span className={styles.num}>{fmtTime(s.start_at)} ~ {fmtTime(s.end_at)}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
        {notice && <p className={styles.notice} role="alert">{notice}</p>}
        <button
          type="button"
          className="btn btn-primary"
          disabled={picked === null || pending}
          onClick={() => picked !== null && onConfirm(picked)}
        >
          {pending ? '확정 중…' : '이 시간으로 확정'}
        </button>
        <p className={styles.caption}>확정 후에는 담당자를 통해서만 변경할 수 있습니다.</p>
      </section>
    ) : status === 'confirmed' && confirmedSlot ? (
      <section className={styles.confirmedCard}>
        <h2 className={styles.confirmedTitle}>면접 일정이 확정되었습니다</h2>
        <p className={styles.confirmedWhen}>
          {fmtDay(confirmedSlot.start_at)}{' '}
          <span className={styles.num}>
            {fmtTime(confirmedSlot.start_at)} ~ {fmtTime(confirmedSlot.end_at)}
          </span>
        </p>
      </section>
    ) : null

  return (
    <div className={styles.page}>
      {/* 데스크톱 전용 왼쪽 패널 — 큰 아르 + 전형 정보. 모바일은 CSS 로 숨긴다 */}
      <aside className={styles.side}>
        <h1 className={styles.logo}><span className={styles.seed}>A</span>rda</h1>
        <ArViewer motion="ask" expression="ask" className={styles.sideAr} />
        <dl className={styles.sideMeta}>
          <div className={styles.sideRow}>
            <dt>포지션</dt>
            <dd>{postingTitle}</dd>
          </div>
          <div className={styles.sideRow}>
            <dt>지원자</dt>
            <dd>{applicantName}</dd>
          </div>
          {status === 'proposed' && expiresAt && (
            <div className={styles.sideRow}>
              <dt>선택 기한</dt>
              <dd><span className={styles.num}>{fmtDay(expiresAt)}</span></dd>
            </div>
          )}
        </dl>
        {scheduleBlock}
      </aside>

      <div className={styles.main}>
      <header className={styles.head}>
        <h1 className={styles.logo}><span className={styles.seed}>A</span>rda</h1>
      </header>

      {/* 일정 블록 (모바일 자리) — 채팅이 길어져도 보이게 상단 고정.
          접으면 요약 바만 남아 채팅 공간이 넓어진다. 스크롤은 아래 메시지
          영역만 한다. 데스크톱에서는 왼쪽 패널 쪽만 보인다 */}
      {scheduleBlock && (
        <div className={styles.mobileSchedule}>
          <button
            type="button"
            className={styles.foldBar}
            aria-expanded={!folded}
            onClick={() => setFolded((v) => !v)}
          >
            <span>
              {status === 'confirmed' && confirmedSlot
                ? <>면접 확정 · <span className={styles.num}>{fmtDay(confirmedSlot.start_at)} {fmtTime(confirmedSlot.start_at)}</span></>
                : '면접 일정 선택'}
            </span>
            <span aria-hidden="true" className={styles.chev}>{folded ? '▾' : '▴'}</span>
          </button>
          {!folded && scheduleBlock}
        </div>
      )}

      <div
        ref={msgsRef}
        className={scrolling ? `${styles.msgs} ${styles.msgsScrolling}` : styles.msgs}
        onScroll={onScroll}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={endDrag}
        onMouseLeave={endDrag}
      >
        {/* 아르의 모든 메시지 옆에 같은 얼굴이 붙는다 — 3D 뷰어 대신 정지
            이미지(ar-face.png)라 메시지가 많아져도 WebGL 부담이 없다 */}
        <div className={styles.arRow}>
          <img className={styles.avatar} src={`${import.meta.env.BASE_URL}ar-face.png`} alt="" />
          <div className={styles.msgAr}>{mdBlocks(greeting)}</div>
        </div>
        {items.map((m) => (
          m.who === 'ar' ? (
            <div key={m.id} className={styles.arRow}>
              <img className={styles.avatar} src={`${import.meta.env.BASE_URL}ar-face.png`} alt="" />
              {/* 대기 중은 원문(생각 중이에요…) 그대로. 응답이 오면 최소 마크다운
                  (굵게·불릿)을 그린다. div 인 이유는 ul 이 들어갈 수 있어서 */}
              <div
                className={m.pending ? `${styles.msgAr} ${styles.msgPending}` : styles.msgAr}
                aria-live={m.pending ? 'polite' : undefined}
              >
                {m.pending ? m.text : mdBlocks(m.text)}
              </div>
            </div>
          ) : (
            <p key={m.id} className={styles.msgMe}>{m.text}</p>
          )
        ))}
        <div ref={endRef} />
      </div>

      <form className={styles.inputRow} onSubmit={(e) => { e.preventDefault(); send() }}>
        <input
          className={styles.input}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={asking ? '답변을 기다리는 중…' : '궁금한 점을 입력하세요'}
          aria-label="질문 입력"
          maxLength={500}
          disabled={asking}
        />
        <button type="submit" className="btn btn-primary" disabled={!draft.trim() || asking}>
          {asking ? '전송 중' : '보내기'}
        </button>
      </form>
      </div>
    </div>
  )
}
