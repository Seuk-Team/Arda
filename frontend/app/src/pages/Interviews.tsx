import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import PageHead from '../components/PageHead'
import { ApiError } from '../api/client'
import { schedules } from '../api/endpoints'
import type { Interview } from '../api/types'
import styles from './Interviews.module.css'

/* 담당자 관점 캘린더 (05-design §0.5 — 2026-08-31 팀장 결정으로 월 그리드 도입).
   데이터는 확정된 일정 제안뿐이다 (ADR-0016). 이 화면에서 일정을 등록·수정·삭제하지
   않는다 — 채용 흐름에서 확정된 것이 GET /schedules 로 들어올 뿐이다.
   회차 컬럼은 여전히 없다: 면접 라운드 개념이 스키마에 없어 지어낼 수 없다.

   셀 넘침(하루 15건)은 "셀에 3건 + +N건, 날짜 클릭 = 그날 목록"으로 푼다.
   그날 목록은 기존 면접 일정 테이블을 그대로 쓴다 — 시각·지원자·공고·면접관. */

function startOfToday() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

function startOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function addDays(d: Date, n: number) {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

/* 달을 옮길 때 말일을 넘기지 않게 자른다 — 8.31 에서 +1달이 10.1 로 튀면 안 된다 */
function addMonths(d: Date, n: number) {
  const last = new Date(d.getFullYear(), d.getMonth() + n + 1, 0).getDate()
  return new Date(d.getFullYear(), d.getMonth() + n, Math.min(d.getDate(), last))
}

/* 주 시작은 일요일 — 국내 달력 관행 */
function startOfWeek(d: Date) {
  return addDays(d, -d.getDay())
}

function dayKey(d: Date) {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

function fmt(d: Date) {
  return dayKey(d).replaceAll('-', '.')
}

function fmtMonth(d: Date) {
  return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}`
}

function fmtMd(d: Date) {
  return fmt(d).slice(5)
}

const DOW = ['일', '월', '화', '수', '목', '금', '토']

/* 면접은 한국에서 열린다 — 지원자 페이지와 같은 이유로 KST 고정 (Schedule.tsx) */
const timeFmt = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false,
})

const dateFmt = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
})

function hhmm(iso: string): string {
  return timeFmt.format(new Date(iso))
}

/* 어느 칸에 들어갈 면접인지도 시각과 같은 KST 기준으로 정한다 — 자정 근처 면접이
   칸을 넘나들지 않게. 그리드 칸 키(dayKey)는 브라우저 로컬 날짜라, KST 밖에서 열면
   하루 어긋날 수 있다. 사용 환경이 국내라 그 경우를 따로 다루지 않는다. */
function isoDayKey(iso: string): string {
  const parts = dateFmt.formatToParts(new Date(iso))
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  return `${get('year')}-${get('month')}-${get('day')}`
}

const NARROW = '(max-width: 768px)'

export default function Interviews() {
  const navigate = useNavigate()
  const [params] = useSearchParams()

  /* sel = 목록에 펼쳐 볼 날짜, view = 그리드가 그리는 달. 둘을 나눠 두면
     달을 넘겨도 어느 날을 보고 있었는지가 유지된다 */
  const [sel, setSel] = useState(startOfToday)
  const [view, setView] = useState(() => startOfMonth(startOfToday()))

  const [list, setList] = useState<Interview[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  /* "내 면접만" — 목록은 로그인한 전원에게 전부 보인다(A3 폐지). 자기 면접만
     추려 보고 싶을 때 쓰는 체크이고, 거르는 주체는 이제 서버가 아니라 이 값이다 */
  const [mine, setMine] = useState(false)

  /* 768 이하는 월 그리드가 안 들어간다 (§9) → 주간 스트립 + 그날 목록.
     가로 스크롤로 밀어 넣지 않는다 */
  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(NARROW).matches,
  )

  useEffect(() => {
    const mq = window.matchMedia(NARROW)
    const on = () => setNarrow(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  /* 그리드는 항상 6주 42칸이다 — 달마다 높이가 널뛰지 않게. 요청도 이 범위로 한 번만
     보내고 날짜별로 나눈다(그날 목록은 추가 요청 없이 이 데이터에서 뽑는다) */
  const gridStart = useMemo(() => startOfWeek(startOfMonth(view)), [view])
  const days = useMemo(
    () => Array.from({ length: 42 }, (_, i) => addDays(gridStart, i)),
    [gridStart],
  )

  useEffect(() => {
    const ac = new AbortController()
    setList(null)

    schedules
      .interviews({ from: gridStart.toISOString(), to: addDays(gridStart, 42).toISOString(), mine }, ac.signal)
      .then((res) => { setList(res.items); setError(null) })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setList([])
        setError(err instanceof ApiError ? err.message : '면접 일정을 불러오지 못했습니다')
      })

    return () => ac.abort()
  }, [gridStart, mine])

  const byDay = useMemo(() => {
    const map = new Map<string, Interview[]>()
    for (const iv of list ?? []) {
      const key = isoDayKey(iv.start_at)
      const bucket = map.get(key)
      if (bucket) bucket.push(iv)
      else map.set(key, [iv])
    }
    for (const bucket of map.values()) bucket.sort((a, b) => a.start_at.localeCompare(b.start_at))
    return map
  }, [list])

  /* 대시보드에서 한 시간대를 눌러 넘어오면 그 슬롯만 남긴다.
     URL 의 ?slot= 은 초기값이고, 이후에는 화면 안에서 고른다 */
  const [slot, setSlot] = useState<string | null>(() => params.get('slot'))
  const [ddOpen, setDdOpen] = useState(false)

  useEffect(() => {
    if (!ddOpen) return
    const close = () => setDdOpen(false)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [ddOpen])

  const ofDay = byDay.get(dayKey(sel)) ?? []
  const shown = slot ? ofDay.filter((iv) => hhmm(iv.start_at).slice(0, 2) === slot.slice(0, 2)) : ofDay

  /* 고를 수 있는 시간대는 그 날 실제로 면접이 있는 시(hour)뿐이다.
     없는 시간을 목록에 두면 눌러 놓고 빈 화면만 본다. */
  const hours = [...new Set(ofDay.map((iv) => hhmm(iv.start_at).slice(0, 2)))].sort()

  /* 방향키로 옮긴 날짜에 포커스를 따라가게 한다 (§10 — 그리드는 키보드로 이동 가능) */
  const cells = useRef(new Map<string, HTMLButtonElement>())
  const [focusKey, setFocusKey] = useState<string | null>(null)

  useEffect(() => {
    if (focusKey === null) return
    cells.current.get(focusKey)?.focus()
    setFocusKey(null)
  }, [focusKey])

  const jump = useCallback((next: Date, focus = false) => {
    setSel(next)
    /* 그리드 밖으로 나가면 그 날이 있는 달로 넘어간다 */
    setView((v) => {
      const gs = startOfWeek(startOfMonth(v))
      return next >= gs && next < addDays(gs, 42) ? v : startOfMonth(next)
    })
    if (focus) setFocusKey(dayKey(next))
  }, [])

  const today = startOfToday()
  const todayKey = dayKey(today)
  const selKey = dayKey(sel)

  /* 좁은 화면에서는 선택한 날이 든 한 주만 띄운다 */
  const weekStart = startOfWeek(sel)
  const cellDays = narrow
    ? Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))
    : days

  function onGridKey(e: React.KeyboardEvent<HTMLDivElement>) {
    const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }
    if (e.key in step) {
      e.preventDefault()
      jump(addDays(sel, step[e.key]), true)
      return
    }
    if (e.key === 'Home') {
      e.preventDefault()
      jump(startOfWeek(sel), true)
      return
    }
    if (e.key === 'End') {
      e.preventDefault()
      jump(addDays(startOfWeek(sel), 6), true)
      return
    }
    if (e.key === 'PageUp' || e.key === 'PageDown') {
      e.preventDefault()
      jump(addMonths(sel, e.key === 'PageUp' ? -1 : 1), true)
    }
  }

  /* 좁은 화면의 ‹ › 는 주, 넓은 화면에서는 달을 옮긴다. 달을 옮기면 그 달 1일이
     선택된다 — 그리드에 안 보이는 날의 목록이 아래 남아 있으면 헷갈린다 */
  function move(n: number) {
    if (narrow) {
      jump(addDays(sel, n * 7))
      return
    }
    const next = startOfMonth(addMonths(startOfMonth(view), n))
    setView(next)
    setSel(next.getFullYear() === today.getFullYear() && next.getMonth() === today.getMonth() ? today : next)
  }

  function goToday() {
    setView(startOfMonth(today))
    setSel(today)
  }

  const loading = list === null && error === null
  /* 42칸에는 앞뒤 달이 물려 있다. 머리의 건수는 라벨(그 달)과 어긋나지 않게
     이번 달 것만 센다 — 지난 달 칸의 칩까지 더해 놓으면 숫자를 못 믿는다 */
  const monthCount = useMemo(() => {
    const prefix = `${view.getFullYear()}-${String(view.getMonth() + 1).padStart(2, '0')}`
    return (list ?? []).filter((iv) => isoDayKey(iv.start_at).startsWith(prefix)).length
  }, [list, view])

  /* 좁은 화면은 라벨이 한 주라 건수도 그 주 것을 센다 */
  const count = narrow
    ? cellDays.reduce((n, d) => n + (byDay.get(dayKey(d))?.length ?? 0), 0)
    : monthCount

  return (
    <>
      <PageHead title="캘린더" />
      <main className="page-content">
      <div className={styles.daybar}>
        <button
          className={styles.dayNav}
          aria-label={narrow ? '이전 주' : '이전 달'}
          onClick={() => move(-1)}
        >
          ‹
        </button>
        <button
          className={styles.dayNav}
          aria-label={narrow ? '다음 주' : '다음 달'}
          onClick={() => move(1)}
        >
          ›
        </button>
        <span className={styles.dayLabel}>
          {narrow ? `${fmtMd(weekStart)} ~ ${fmtMd(addDays(weekStart, 6))}` : fmtMonth(view)}
        </span>
        {loading
          ? <span className={styles.skelPill} aria-hidden="true" />
          : <span className={styles.dayCount}>{count}건</span>}

        <label className={styles.mine}>
          <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
          내 면접만
        </label>
        <button className={styles.dayToday} onClick={goToday}>오늘</button>
      </div>

      {error !== null && <p className={styles.empty} role="alert">{error}</p>}

      {/* data-morph-target — 대시보드 축소판이 확장돼 앉는 자리 (MorphNav) */}
      <div className={styles.calPanel} data-morph-target="calendar">
        <div className={styles.dow} aria-hidden="true">
          {DOW.map((d) => <span key={d} className={styles.dowCell}>{d}</span>)}
        </div>

        {/* 방향키 이동은 칸 하나만 탭 순서에 두고(로빙 tabindex) 여기서 받는다 */}
        <div
          className={styles.grid}
          aria-label="면접 캘린더"
          aria-busy={loading}
          onKeyDown={onGridKey}
        >
          {cellDays.map((d) => {
            const key = dayKey(d)
            const items = byDay.get(key) ?? []
            const outside = d.getMonth() !== view.getMonth()
            const cls = [
              styles.cell,
              narrow ? styles.cellNarrow : '',
              outside && !narrow ? styles.outside : '',
              key === todayKey ? styles.today : '',
              key === selKey ? styles.selected : '',
            ].filter(Boolean).join(' ')

            return (
              <button
                key={key}
                type="button"
                ref={(el) => {
                  if (el) cells.current.set(key, el)
                  else cells.current.delete(key)
                }}
                className={cls}
                tabIndex={key === selKey ? 0 : -1}
                aria-pressed={key === selKey}
                aria-current={key === todayKey ? 'date' : undefined}
                aria-label={`${fmt(d)} ${DOW[d.getDay()]}요일, ${items.length ? `면접 ${items.length}건` : '면접 없음'}`}
                onClick={() => jump(d)}
              >
                <span className={styles.date}>{d.getDate()}</span>

                {narrow
                  ? items.length > 0 && <span className={styles.count}>{items.length}</span>
                  : (
                    <>
                      {items.slice(0, 3).map((iv) => (
                        /* 판단 전 정보라 색을 주지 않는다 (§1) */
                        <span key={iv.proposal_id} className={styles.chip}>
                          <span className={styles.chipTime}>{hhmm(iv.start_at)}</span>
                          <span className={styles.chipName}>{iv.applicant_name}</span>
                        </span>
                      ))}
                      {items.length > 3 && <span className={styles.more}>+{items.length - 3}건</span>}
                    </>
                  )}
              </button>
            )
          })}
        </div>
      </div>

      {list !== null && monthCount === 0 && error === null && (
        <p className={styles.monthEmpty}>
          {mine
            ? `${fmtMonth(view)}에 내 면접이 없습니다.`
            : `${fmtMonth(view)}에 잡힌 면접이 없습니다. 확정된 일정만 표시됩니다.`}
        </p>
      )}

      <div className={styles.dayHead}>
        <span className={styles.dayTitle}>{fmt(sel)} ({DOW[sel.getDay()]})</span>
        <span className={styles.dayCount}>{shown.length}건</span>

        <div className={`${styles.dd} ${ddOpen ? styles.ddOpen : ''}`}>
          <button
            type="button"
            className={styles.ddBtn}
            aria-haspopup="listbox"
            aria-expanded={ddOpen}
            onClick={(e) => { e.stopPropagation(); setDdOpen((v) => !v) }}
          >
            {slot ? `${slot.slice(0, 2)}시` : '시간대'}
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
          </button>
          <ul className={styles.ddMenu} role="listbox">
            <li
              role="option"
              aria-selected={slot === null}
              className={slot === null ? styles.ddSel : undefined}
              onClick={() => { setSlot(null); setDdOpen(false) }}
            >
              전체
            </li>
            {hours.map((h) => (
              <li
                key={h}
                role="option"
                aria-selected={slot?.slice(0, 2) === h}
                className={slot?.slice(0, 2) === h ? styles.ddSel : undefined}
                onClick={() => { setSlot(`${h}:00`); setDdOpen(false) }}
              >
                {h}시
              </li>
            ))}
          </ul>
        </div>

        {slot && (
          <button
            type="button"
            className={styles.slotChip}
            aria-label="시간대 필터 해제 — 그 날 전체 보기"
            onClick={() => setSlot(null)}
          >
            {slot} 면접만 <span aria-hidden="true">✕</span>
          </button>
        )}
      </div>

      <div className={`${styles.panel} cardify-panel`}>
        <table className={styles.table}>
          <thead className="cardify-head">
            <tr>
              <th>시각</th>
              <th>지원자</th>
              <th>공고</th>
              <th>면접관</th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? [0, 1, 2].map((i) => (
                <tr key={i}>
                  {[0, 1, 2, 3].map((c) => (
                    <td key={c}><span className={styles.skelRow} /></td>
                  ))}
                </tr>
              ))
              : shown.map((iv) => (
                /* 행 클릭 = 그 지원자가 있는 공고 화면 (05-design §0.5 진입점) */
                <tr
                  key={iv.proposal_id}
                  className="cardify"
                  onClick={() => navigate(`/applicants?q=${encodeURIComponent(iv.applicant_name)}`)}
                >
                  <td data-card-title="" className={styles.num}>{hhmm(iv.start_at)}</td>
                  <td data-label="지원자" className={styles.name}>{iv.applicant_name}</td>
                  <td data-label="공고" className={styles.posting}>{iv.posting_title}</td>
                  <td data-label="면접관" className={styles.sub}>{iv.interviewer_name}</td>
                </tr>
              ))}
          </tbody>
        </table>

        {!loading && shown.length === 0 ? (
          <p className={styles.empty}>
            {slot
              ? '이 시간대에 잡힌 면접이 없습니다.'
              : mine
                ? '이 날짜에 내 면접이 없습니다.'
                : '이 날짜에 잡힌 면접이 없습니다. 확정된 일정만 표시됩니다.'}
          </p>
        ) : (
          shown.length > 0 && (
            <div className={styles.foot}>
              <span>{shown.length}건 중 1–{shown.length}</span>
            </div>
          )
        )}
      </div>
      </main>
    </>
  )
}
