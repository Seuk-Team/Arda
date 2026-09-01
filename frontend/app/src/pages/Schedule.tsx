import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import ArScheduleChat from '../components/ArScheduleChat'
import type { Stage } from '../api/types'
import styles from './Schedule.module.css'

/* 지원자용 공개 페이지 (ADR-0016) — 로그인 없음, 메일 링크의 토큰이 곧 인증.
   응답 형태는 backend/app/schemas/schedule.py 의 SchedulePublicOut 이다.
   링크가 유효하면 화면 전체가 아르와의 대화(ArScheduleChat)이고, 일정 선택은
   그 안의 카드다. 이 파일은 로딩·에러 상태와 API 호출만 맡는다. */

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

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; data: SchedulePublic }
  | { kind: 'invalid' } /* 404 — 링크 자체가 틀림 */
  | { kind: 'replaced' } /* 410 — 재제안으로 대체된 옛 링크 */
  | { kind: 'error'; message: string }

export default function Schedule() {
  const { token } = useParams<{ token: string }>()
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
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

  async function confirm(slotId: number) {
    setPending(true)
    setNotice(null)
    try {
      const data = await api.post<SchedulePublic>(
        `/public/schedule/${token}/confirm`, { slot_id: slotId }, { auth: false },
      )
      setState({ kind: 'ready', data })
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        /* 그 사이 마감·확정·만료 — 서버 문구를 보여주고 최신 상태를 다시 그린다 */
        setNotice(err.message)
        await load()
      } else {
        setNotice(err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요')
      }
    } finally {
      setPending(false)
    }
  }

  if (state.kind === 'ready') {
    const d = state.data
    return (
      <ArScheduleChat
        status={d.status}
        applicantName={d.applicant_name}
        postingTitle={d.posting_title}
        expiresAt={d.expires_at}
        slots={d.slots}
        confirmedSlot={d.confirmed_slot}
        pending={pending}
        notice={notice}
        onConfirm={confirm}
      />
    )
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
    }
  }
}
