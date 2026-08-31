import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { STAGE_LABEL, stageTone } from '../lib/stage'
import type { Stage } from '../api/types'
import styles from './Schedule.module.css'

/* 지원자용 공개 페이지 (ADR-0016) — 로그인 없음, 메일 링크의 토큰이 곧 인증.
   응답 형태는 backend/app/schemas/schedule.py 의 SchedulePublicOut 이다. */

interface PublicSlot {
  id: number
  start_at: string
  end_at: string
}

interface SchedulePublic {
  status: 'proposed' | 'confirmed' | 'expired'
  applicant_name: string
  posting_title: string
  current_stage: Stage
  expires_at: string | null
  slots: PublicSlot[]
  confirmed_slot: PublicSlot | null
}

/* 시간대는 브라우저가 아니라 한국으로 고정한다 — 면접은 한국에서 열리고,
   해외 체류 중인 지원자의 브라우저 시간대로 보여주면 서로 다른 시각을 합의하게 된다. */
const dayFmt = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short',
})
const timeFmt = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false,
})

/* 표기 통일 (05-design §2): 날짜 2026.09.02 · 요일은 (수) */
function fmtDay(iso: string): string {
  const parts = dayFmt.formatToParts(new Date(iso))
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  return `${get('year')}.${get('month')}.${get('day')} (${get('weekday')})`
}

function fmtTime(iso: string): string {
  return timeFmt.format(new Date(iso))
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; data: SchedulePublic }
  | { kind: 'invalid' } /* 404 — 링크 자체가 틀림 */
  | { kind: 'replaced' } /* 410 — 재제안으로 대체된 옛 링크 */
  | { kind: 'error'; message: string }

export default function Schedule() {
  const { token } = useParams<{ token: string }>()
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [picked, setPicked] = useState<number | null>(null)
  const [pending, setPending] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await api.get<SchedulePublic>(`/public/schedule/${token}`, { auth: false })
      setState({ kind: 'ready', data })
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setState({ kind: 'invalid' })
      else if (err instanceof ApiError && err.status === 410) setState({ kind: 'replaced' })
      else setState({ kind: 'error', message: err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요' })
    }
  }, [token])

  useEffect(() => { load() }, [load])

  async function confirm() {
    if (picked === null) return
    setPending(true)
    setNotice(null)
    try {
      const data = await api.post<SchedulePublic>(
        `/public/schedule/${token}/confirm`, { slot_id: picked }, { auth: false },
      )
      setState({ kind: 'ready', data })
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        /* 그 사이 마감·확정·만료 — 서버 문구를 보여주고 최신 상태를 다시 그린다 */
        setNotice(err.message)
        setPicked(null)
        await load()
      } else {
        setNotice(err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요')
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <div className={styles.page}>
      <main className={styles.column}>
        <h1 className={styles.logo}><span className={styles.seed}>A</span>rda</h1>
        {renderBody()}
      </main>
    </div>
  )

  function renderBody() {
    switch (state.kind) {
      case 'loading':
        return (
          <div className={styles.card} aria-busy="true">
            <div className={styles.skeleton} style={{ width: '60%' }} />
            <div className={styles.skeleton} style={{ width: '40%' }} />
            <div className={styles.skeleton} />
            <div className={styles.skeleton} />
          </div>
        )
      case 'invalid':
        return (
          <div className={styles.card}>
            <h2 className={styles.noticeTitle}>유효하지 않은 링크입니다</h2>
            <p className={styles.noticeBody}>안내 메일의 링크를 다시 확인해 주세요.</p>
          </div>
        )
      case 'replaced':
        return (
          <div className={styles.card}>
            <h2 className={styles.noticeTitle}>이 일정 제안은 더 이상 유효하지 않습니다</h2>
            <p className={styles.noticeBody}>새 안내 메일이 발송되었습니다. 최신 메일의 링크를 확인해 주세요.</p>
          </div>
        )
      case 'error':
        return (
          <div className={`${styles.card} ${styles.cardDanger}`} role="alert">
            <h2 className={styles.noticeTitle}>불러오지 못했습니다</h2>
            <p className={styles.noticeBody}>{state.message}</p>
            <button type="button" className="btn btn-secondary" onClick={() => { setState({ kind: 'loading' }); load() }}>
              다시 시도
            </button>
          </div>
        )
      case 'ready':
        return renderReady(state.data)
    }
  }

  function renderReady(data: SchedulePublic) {
    const statusCard = (
      <section className={styles.card} aria-label="전형 정보">
        <dl className={styles.meta}>
          <div className={styles.metaRow}>
            <dt>포지션</dt>
            <dd>{data.posting_title}</dd>
          </div>
          <div className={styles.metaRow}>
            <dt>지원자</dt>
            <dd>{data.applicant_name}</dd>
          </div>
          <div className={styles.metaRow}>
            <dt>전형 현황</dt>
            <dd>
              <span className={`badge ${badgeClass(data.current_stage)}`}>
                {STAGE_LABEL[data.current_stage]}
              </span>
            </dd>
          </div>
        </dl>
      </section>
    )

    if (data.status === 'confirmed' && data.confirmed_slot) {
      const s = data.confirmed_slot
      return (
        <>
          <section className={`${styles.card} ${styles.cardConfirmed}`}>
            <h2 className={styles.confirmedTitle}>면접 일정이 확정되었습니다</h2>
            <p className={styles.confirmedWhen}>
              {fmtDay(s.start_at)} <span className={styles.num}>{fmtTime(s.start_at)} ~ {fmtTime(s.end_at)}</span>
            </p>
            <p className={styles.caption}>이 페이지는 언제든 다시 열어 일정을 확인할 수 있습니다.</p>
          </section>
          {statusCard}
        </>
      )
    }

    if (data.status === 'expired') {
      return (
        <>
          <section className={styles.card}>
            <h2 className={styles.noticeTitle}>선택 기한이 지났습니다</h2>
            <p className={styles.noticeBody}>담당자에게 문의해 주시면 일정을 다시 안내드립니다.</p>
          </section>
          {statusCard}
        </>
      )
    }

    /* proposed — 슬롯 선택 */
    const byDay = new Map<string, PublicSlot[]>()
    for (const s of data.slots) {
      const day = fmtDay(s.start_at)
      byDay.set(day, [...(byDay.get(day) ?? []), s])
    }

    return (
      <>
        <header className={styles.intro}>
          <h2 className={styles.title}>면접 일정을 선택해 주세요</h2>
          <p className={styles.sub}>{data.applicant_name} 님, 아래 시간 중 편하신 때를 골라 주세요.</p>
        </header>
        {statusCard}
        <section className={styles.card} aria-label="면접 시간 선택">
          {[...byDay.entries()].map(([day, slots]) => (
            <div key={day}>
              <h3 className={styles.day}>{day}</h3>
              <div className={styles.slots} role="radiogroup" aria-label={day}>
                {slots.map((s) => (
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
            style={{ width: '100%' }}
            disabled={picked === null || pending}
            onClick={confirm}
          >
            {pending ? '확정 중…' : '이 시간으로 확정'}
          </button>
          <p className={styles.caption}>시간을 선택하면 버튼이 활성화됩니다. 확정 후에는 담당자를 통해서만 변경할 수 있습니다.</p>
        </section>
      </>
    )
  }
}

/* 색은 판단에만 (05-design §1) — 진행 중 무채, 합격 연두, 불합격 적갈 */
function badgeClass(stage: Stage): string {
  const tone = stageTone(stage)
  if (tone === 'accepted') return 'badge-open'
  if (tone === 'rejected') return `badge-closed ${'stage-rejected'}`
  return 'badge-closed'
}
