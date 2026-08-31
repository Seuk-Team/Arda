import { useCallback, useEffect, useState } from 'react'
import PageHead from '../components/PageHead'
import { useAuth } from '../auth/AuthContext'
import { useToast } from '../components/Toast'
import { api, ApiError } from '../api/client'
import { ROLE_LABEL } from '../lib/stage'
import styles from './Settings.module.css'

/* 내 계정 / 사용자·권한(관리자) / 메일 템플릿 (05-design §0.5)
   + 면접 가능 시간 — 면접관에게만 보인다(ADR-0016). */
const TABS = ['내 계정', '사용자·권한', '메일 템플릿'] as const
const AVAILABILITY_TAB = '면접 가능 시간'

/* 사용자 목록 API 가 아직 없다 (02-api.md 인증 절에 signup/login/me 뿐).
   관리자 화면이라 만들어 낼 수 없어 목데이터를 유지한다. */
const USERS = [
  { id: 1, name: '김채용', email: 'admin@arda.com', role: '관리자', active: true },
  { id: 2, name: '이서연', email: 'recruiter1@arda.com', role: '채용담당자', active: true },
  { id: 3, name: '박정호', email: 'reviewer1@arda.com', role: '면접관', active: true },
  { id: 4, name: '최민지', email: 'recruiter2@arda.com', role: '채용담당자', active: true },
  { id: 5, name: '한도윤', email: 'reviewer2@arda.com', role: '면접관', active: false },
]

/* 메일 문구는 아직 확정되지 않았다. §12-2 대로 임의로 채우지 않는다. */
const MAIL_STAGES = ['서류 검토', '면접', '최종 합격', '불합격'] as const
const DRAFT = '(문구 작성 중)'

export default function Settings() {
  const { user } = useAuth()
  const [tab, setTab] = useState<string>('내 계정')
  const [stage, setStage] = useState<(typeof MAIL_STAGES)[number]>('서류 검토')

  /* 가용 시간은 면접관 본인 것만 등록된다 — 서버도 대상이 면접관이 아니면 422 다.
     admin 이 남의 것을 대신 넣는 경로는 API 에는 있지만 화면은 아직 없다. */
  const tabs: string[] = user?.role === 'interviewer' ? [...TABS, AVAILABILITY_TAB] : [...TABS]

  return (
    <>
      <PageHead title="설정" />
      <main className="page-content">
        <div className={styles.tabs} role="tablist">
          {tabs.map((t) => (
            <button
              key={t}
              role="tab"
              type="button"
              aria-selected={t === tab}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </div>

        {tab === '내 계정' && (
          <div role="tabpanel" className={styles.form}>
            <div className={styles.field}>
              <label htmlFor="f-name">이름</label>
              <input className={styles.input} id="f-name" type="text" value={user?.name ?? ''} readOnly />
            </div>
            <div className={styles.field}>
              <label htmlFor="f-email">이메일</label>
              <input className={styles.input} id="f-email" type="email" value={user?.email ?? ''} readOnly />
            </div>
            <div className={styles.field}>
              <label htmlFor="f-role">역할</label>
              {/* 역할은 관리자가 사용자·권한에서 바꾼다 — 여기서는 읽기 전용 */}
              <input
                className={styles.input}
                id="f-role"
                type="text"
                value={user ? ROLE_LABEL[user.role] : ''}
                disabled
              />
            </div>
            {/* 값은 GET /auth/me 다. 고치는 API 가 아직 없어(02-api.md 인증 절)
                메일 템플릿 탭과 같은 방식으로 저장을 잠가 둔다. */}
            <p className={styles.note}>내 정보 수정 API가 아직 없어 저장할 수 없습니다.</p>
            <div className={styles.formActions}>
              <button type="button" className="btn btn-primary" disabled>저장</button>
            </div>
          </div>
        )}

        {tab === '사용자·권한' && (
          <div role="tabpanel">
            <div className={styles.rowActions}>
              <button type="button" className="btn btn-primary">사용자 추가</button>
            </div>
            <div className={styles.panel}>
              <div className={`${styles.row} ${styles.thead}`}>
                <span>이름</span>
                <span>이메일</span>
                <span>역할</span>
                <span>상태</span>
              </div>
              {USERS.map((u) => (
                <div key={u.id} className={`${styles.row} ${styles.item}`}>
                  <span className={styles.name}>{u.name}</span>
                  <span className={styles.sub}>{u.email}</span>
                  <span className={u.role === '관리자' ? styles.admin : undefined}>{u.role}</span>
                  <span className={u.active ? styles.on : styles.off}>
                    {u.active ? '활성' : '비활성'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === '메일 템플릿' && (
          <div role="tabpanel" className={styles.mail}>
            <nav className={styles.stageNav}>
              {MAIL_STAGES.map((s) => (
                <button
                  key={s}
                  type="button"
                  className={s === stage ? styles.stageOn : undefined}
                  onClick={() => setStage(s)}
                >
                  {s}
                </button>
              ))}
            </nav>

            <div className={styles.mailBody}>
              <div className={styles.field}>
                <label htmlFor="tpl-subject">제목</label>
                <input className={styles.input} id="tpl-subject" type="text" value={DRAFT} readOnly />
              </div>
              <div className={styles.field}>
                <label htmlFor="tpl-body">본문</label>
                <textarea className={styles.textarea} id="tpl-body" rows={8} value={DRAFT} readOnly />
              </div>
              <p className={styles.note}>{stage} 단계 메일 문구는 아직 확정 전입니다.</p>
              <div className={styles.formActions}>
                <button type="button" className="btn btn-primary" disabled>저장</button>
              </div>
            </div>
          </div>
        )}

        {tab === AVAILABILITY_TAB && user && <Availability userId={user.id} />}
      </main>
    </>
  )
}

/* ── 면접 가능 시간 (ADR-0016) ──────────────────────────────────────
   담당자가 일정 제안을 만들 때 여기 등록된 구간에서 후보 슬롯을 뽑는다.
   이게 비어 있으면 제안 생성이 422 로 막힌다 — 그래서 빈 상태 문구가 중요하다. */

interface Slot {
  id: number
  start_at: string
  end_at: string
}

/* datetime-local 은 시간대가 없는 문자열이다. 서버는 시간대 없는 값을 거절하므로
   (그래야 슬롯이 밀리지 않는다) 브라우저 지역 시간으로 해석해 ISO 로 바꾼다. */
function toIso(local: string): string {
  return new Date(local).toISOString()
}

function fmtRange(startIso: string, endIso: string): string {
  const start = new Date(startIso)
  const end = new Date(endIso)
  const day = start.toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'short',
  })
  const time = (d: Date) => d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
  // 자정을 넘기는 구간은 끝 날짜도 보여 준다
  const sameDay = start.toDateString() === end.toDateString()
  return sameDay
    ? `${day} ${time(start)} ~ ${time(end)}`
    : `${day} ${time(start)} ~ ${end.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' })} ${time(end)}`
}

function Availability({ userId }: { userId: number }) {
  const { show } = useToast()
  const [items, setItems] = useState<Slot[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [saving, setSaving] = useState(false)

  /* 에러는 성공했을 때 지운다 — 먼저 비우면 다시 불러오는 동안 화면이 한 번
     깜빡인다(에러 문구가 사라졌다가 다시 뜬다). */
  const load = useCallback(async () => {
    try {
      /* 지난 구간은 후보가 될 수 없으니 보여 줄 이유도 없다 */
      const res = await api.get<{ items: Slot[] }>(`/interviewers/${userId}/availability`, {
        query: { from: new Date().toISOString() },
      })
      setItems(res.items)
      setError(null)
    } catch (err) {
      setItems([])
      setError(err instanceof ApiError ? err.message : '가용 시간을 불러오지 못했습니다')
    }
  }, [userId])

  useEffect(() => {
    void load()
  }, [load])

  async function add(e: React.FormEvent) {
    e.preventDefault()
    if (new Date(start) >= new Date(end)) {
      show('fail', '종료 시각이 시작보다 앞섭니다')
      return
    }
    setSaving(true)
    try {
      await api.post(`/interviewers/${userId}/availability`, {
        start_at: toIso(start),
        end_at: toIso(end),
      })
      setStart('')
      setEnd('')
      await load()
      show('ok', '가능 시간을 등록했습니다')
    } catch (err) {
      show('fail', err instanceof ApiError ? err.message : '등록하지 못했습니다')
    } finally {
      setSaving(false)
    }
  }

  async function remove(id: number) {
    try {
      await api.delete(`/availability/${id}`)
      await load()
      show('ok', '삭제했습니다')
    } catch (err) {
      show('fail', err instanceof ApiError ? err.message : '삭제하지 못했습니다')
    }
  }

  return (
    <div role="tabpanel">
      <p className={styles.note}>
        등록한 시간대에서 담당자가 면접 후보 시간을 만들어 지원자에게 보냅니다. 비워 두면 제안을
        만들 수 없습니다.
      </p>

      <form className={styles.slotForm} onSubmit={add}>
        <div className={styles.field}>
          <label htmlFor="av-start">시작</label>
          <input
            className={styles.input}
            id="av-start"
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            disabled={saving}
            required
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="av-end">종료</label>
          <input
            className={styles.input}
            id="av-end"
            type="datetime-local"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            disabled={saving}
            required
          />
        </div>
        <button type="submit" className="btn btn-primary" disabled={saving || !start || !end}>
          {saving ? '등록 중…' : '추가'}
        </button>
      </form>

      {items === null && <p className={styles.note}>불러오는 중입니다…</p>}
      {error && <p className={styles.error} role="alert">{error}</p>}
      {items !== null && items.length === 0 && !error && (
        <p className={styles.note}>등록된 가능 시간이 없습니다.</p>
      )}

      {items !== null && items.length > 0 && (
        <div className={styles.panel}>
          {items.map((slot) => (
            <div key={slot.id} className={`${styles.slotRow} ${styles.item}`}>
              <span>{fmtRange(slot.start_at, slot.end_at)}</span>
              <button type="button" className="btn btn-secondary" onClick={() => void remove(slot.id)}>
                삭제
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
