import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageHead from '../components/PageHead'
import { useAuth } from '../auth/AuthContext'
import { useToast } from '../components/Toast'
import { api, ApiError } from '../api/client'
import { auth as authApi, mail as mailApi, users as usersApi } from '../api/endpoints'
import type { MailTemplate, UserItem } from '../api/types'
import { ROLE_LABEL } from '../lib/stage'
import styles from './Settings.module.css'

/* 내 계정 / 사용자·권한(관리자) / 메일 템플릿 (05-design §0.5)
   + 면접 가능 시간 (ADR-0016).

   역할은 admin·member 2종이다. 계정 관리와 메일 템플릿은 admin 전용이라
   그 두 탭만 감춘다. 내 계정·면접 가능 시간은 로그인한 전원에게 보인다 —
   본인 정보 수정과 가용 시간 등록은 역할과 무관하기 때문이다 (G4 결정 5).
   **역할별로 다른 화면을 따로 만들지 않는다.** 탭 구성만 갈린다. */
const MY_TAB = '내 계정'
const ADMIN_TABS = ['사용자·권한', '메일 템플릿'] as const
const AVAILABILITY_TAB = '면접 가능 시간'

/* 문구가 있는 단계 4종 (backend TEMPLATE_STAGES 와 같다).
   예전 목록의 '서류 검토'(screening)는 **대응 문구가 없는 유령 탭**이었다 —
   내부 검토 단계라 지원자에게 아무것도 보내지 않는다. */
const MAIL_STAGES: { stage: MailTemplate['stage']; label: string }[] = [
  { stage: 'applied', label: '접수 확인' },
  { stage: 'interview', label: '면접 안내' },
  { stage: 'accepted', label: '최종 합격' },
  { stage: 'rejected', label: '불합격' },
]

export default function Settings() {
  const { user } = useAuth()
  const [tab, setTab] = useState<string>(MY_TAB)

  const tabs: string[] =
    user?.role === 'admin'
      ? [MY_TAB, ...ADMIN_TABS, AVAILABILITY_TAB]
      : [MY_TAB, AVAILABILITY_TAB]

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

        {tab === MY_TAB && <MyAccount />}
        {tab === '사용자·권한' && <Users />}
        {tab === '메일 템플릿' && <MailTemplates />}
        {tab === AVAILABILITY_TAB && user && <Availability userId={user.id} />}
      </main>
    </>
  )
}

/* ── 내 계정 (G4) ───────────────────────────────────────────────────
   member 가 설정 화면에서 실제로 저장할 수 있는 유일한 곳이다. 나머지 두 탭은
   admin 전용이라, 이게 없으면 member 에게 설정은 읽기 전용 화면이었다. */

function MyAccount() {
  const { user, refresh, logout } = useAuth()
  const navigate = useNavigate()
  const { show } = useToast()
  const [name, setName] = useState(user?.name ?? '')
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [saving, setSaving] = useState(false)

  /* 로그인 직후에는 user 가 늦게 온다 — 도착하면 입력값을 맞춘다.
     사용자가 타이핑을 시작한 뒤에는 덮어쓰지 않는다(id 가 그대로면 그대로 둔다). */
  useEffect(() => {
    setName(user?.name ?? '')
  }, [user?.id, user?.name])

  const nameChanged = user != null && name.trim() !== '' && name !== user.name
  const wantsPassword = next !== ''
  const canSave = !saving && (nameChanged || wantsPassword)

  async function save() {
    setSaving(true)
    try {
      await authApi.updateMe({
        ...(nameChanged ? { name: name.trim() } : {}),
        ...(wantsPassword ? { current_password: current, new_password: next } : {}),
      })
      setCurrent('')
      setNext('')
      await refresh()
      show('ok', '저장했습니다')
    } catch (err) {
      show('fail', err instanceof ApiError ? err.message : '저장하지 못했습니다')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div role="tabpanel" className={styles.form}>
      <div className={styles.field}>
        <label htmlFor="f-name">이름</label>
        <input
          className={styles.input}
          id="f-name"
          type="text"
          value={name}
          maxLength={50}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className={styles.field}>
        {/* 이메일은 로그인 식별자다. 바꾸는 경로를 두지 않았다 */}
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

      <hr className={styles.divider} />

      <div className={styles.field}>
        <label htmlFor="f-current">현재 비밀번호</label>
        <input
          className={styles.input}
          id="f-current"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
      </div>
      <div className={styles.field}>
        <label htmlFor="f-next">새 비밀번호</label>
        <input
          className={styles.input}
          id="f-next"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
      </div>
      <p className={styles.note}>
        비밀번호를 바꿀 때만 두 칸을 채웁니다. 이름만 고칠 때는 비워 두세요.
      </p>

      <div className={styles.formActions}>
        <button type="button" className="btn btn-primary" disabled={!canSave} onClick={save}>
          {saving ? '저장 중…' : '저장'}
        </button>
      </div>

      {/* 로그아웃 — 데스크톱의 유일한 진입점이다. 모바일은 더보기(More)가 맡고
          있었는데 그 화면은 하단 탭으로만 갈 수 있고 하단 탭은 ≤768px 전용이라,
          PC 사용자는 나갈 방법이 아예 없었다.

          여기 둔 이유: 사이드바 하단 프로필은 05-design §0.5 가 "표시 전용,
          클릭 진입 없음" 으로 못박았다. 설정은 그 문서가 "내 계정" 을 품는 곳으로
          정의한 화면이라 규칙과 충돌하지 않는다.

          확인 절차는 두지 않는다 — 되돌리는 비용이 다시 로그인 한 번이라
          모달을 세울 만한 무게가 아니다. 모바일 쪽과도 같은 동작이다. */}
      <hr className={styles.divider} />

      <div className={styles.logoutRow}>
        <p className={styles.note}>
          이 브라우저에서 로그인 상태를 지웁니다. 서버의 데이터는 그대로입니다.
        </p>
        <button
          type="button"
          className={`btn ${styles.logoutBtn}`}
          onClick={() => { logout(); navigate('/login', { replace: true }) }}
        >
          로그아웃
        </button>
      </div>

    </div>
  )
}

/* ── 사용자·권한 (A4) ───────────────────────────────────────────────
   삭제가 없다 — users.id 가 작성자·평가자·배정자로 도처에 남아 있어 지우면
   이력이 부서진다. 비활성화가 그 자리를 대신한다. */

function Users() {
  const { user: me } = useAuth()
  const { show } = useToast()
  const [items, setItems] = useState<UserItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)

  const load = useCallback(async () => {
    try {
      const res = await usersApi.list()
      setItems(res.items)
      setError(null)
    } catch (err) {
      setItems([])
      setError(err instanceof ApiError ? err.message : '사용자를 불러오지 못했습니다')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function patch(id: number, body: { role?: 'admin' | 'member'; is_active?: boolean }) {
    setBusy(id)
    try {
      const updated = await usersApi.update(id, body)
      setItems((prev) => prev?.map((u) => (u.id === updated.id ? updated : u)) ?? null)
      show('ok', '변경했습니다')
    } catch (err) {
      /* 마지막 관리자 가드(409)는 실패가 아니라 정상적인 거절이다 —
         서버 문구를 그대로 보여 준다 */
      show('fail', err instanceof ApiError ? err.message : '변경하지 못했습니다')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div role="tabpanel">
      <div className={styles.rowActions}>
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
          사용자 추가
        </button>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.panel}>
        <div className={`${styles.row} ${styles.thead}`}>
          <span>이름</span>
          <span>이메일</span>
          <span>역할</span>
          <span>상태</span>
        </div>
        {items === null && <div className={`${styles.row} ${styles.item}`}><span>불러오는 중…</span></div>}
        {items?.map((u) => (
          <div key={u.id} className={`${styles.row} ${styles.item}`}>
            <span className={styles.name}>{u.name}</span>
            <span className={styles.sub}>{u.email}</span>
            <select
              className={styles.rowSelect}
              value={u.role}
              disabled={busy === u.id}
              aria-label={`${u.name} 역할`}
              onChange={(e) => patch(u.id, { role: e.target.value as 'admin' | 'member' })}
            >
              <option value="admin">{ROLE_LABEL.admin}</option>
              <option value="member">{ROLE_LABEL.member}</option>
            </select>
            <button
              type="button"
              className={u.is_active ? styles.on : styles.off}
              disabled={busy === u.id}
              onClick={() => patch(u.id, { is_active: !u.is_active })}
              title={u.is_active ? '비활성화' : '활성화'}
            >
              {u.is_active ? '활성' : '비활성'}
              {u.id === me?.id && ' (나)'}
            </button>
          </div>
        ))}
      </div>

      {adding && (
        <AddUser
          onClose={() => setAdding(false)}
          onCreated={() => {
            setAdding(false)
            void load()
          }}
        />
      )}
    </div>
  )
}

/* 계정 생성은 기존 POST /auth/signup 을 그대로 쓴다 — 같은 일을 하는 경로를
   둘로 만들지 않는다. */
function AddUser({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { show } = useToast()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<'admin' | 'member'>('member')
  const [saving, setSaving] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await authApi.signup({ name, email, password, role })
      show('ok', '계정을 만들었습니다')
      onCreated()
    } catch (err) {
      show('fail', err instanceof ApiError ? err.message : '계정을 만들지 못했습니다')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={styles.modalScrim} role="presentation" onClick={onClose}>
      <form
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-label="사용자 추가"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h2 className={styles.modalTitle}>사용자 추가</h2>
        <div className={styles.field}>
          <label htmlFor="u-name">이름</label>
          <input className={styles.input} id="u-name" value={name} required maxLength={50}
            onChange={(e) => setName(e.target.value)} />
        </div>
        <div className={styles.field}>
          <label htmlFor="u-email">이메일</label>
          <input className={styles.input} id="u-email" type="email" value={email} required
            onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className={styles.field}>
          <label htmlFor="u-password">임시 비밀번호</label>
          <input className={styles.input} id="u-password" type="password" value={password}
            required minLength={8} autoComplete="new-password"
            onChange={(e) => setPassword(e.target.value)} />
        </div>
        <div className={styles.field}>
          <label htmlFor="u-role">역할</label>
          <select className={styles.input} id="u-role" value={role}
            onChange={(e) => setRole(e.target.value as 'admin' | 'member')}>
            <option value="member">{ROLE_LABEL.member}</option>
            <option value="admin">{ROLE_LABEL.admin}</option>
          </select>
        </div>
        <div className={styles.modalActions}>
          <button type="button" className="btn" onClick={onClose}>취소</button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? '만드는 중…' : '만들기'}
          </button>
        </div>
      </form>
    </div>
  )
}

/* ── 메일 템플릿 (G4) ───────────────────────────────────────────────
   저장소가 둘이다: 코드 기본값 + DB 오버라이드. 그래서 "지금 나가는 문구가
   어느 쪽인가"(source)를 반드시 보여 준다. */

const TEMPLATE_VARS = ['{지원자명}', '{공고명}', '{회사명}', '{면접일시}', '{서명}']

function MailTemplates() {
  const { show } = useToast()
  const [items, setItems] = useState<MailTemplate[] | null>(null)
  const [stage, setStage] = useState<MailTemplate['stage']>('applied')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const current = items?.find((t) => t.stage === stage) ?? null

  const load = useCallback(async () => {
    try {
      const res = await mailApi.templates()
      setItems(res.items)
      setError(null)
    } catch (err) {
      setItems([])
      setError(err instanceof ApiError ? err.message : '문구를 불러오지 못했습니다')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  /* 탭을 옮기거나 저장·복귀로 목록이 갱신되면 편집칸을 서버 값으로 맞춘다.
     current 는 items 에서 찾은 객체라 items 가 그대로면 같은 참조다 — 타이핑
     중에는 다시 돌지 않는다. */
  useEffect(() => {
    if (current) {
      setSubject(current.subject)
      setBody(current.body)
    }
  }, [current])

  const dirty = current != null && (subject !== current.subject || body !== current.body)

  async function save() {
    setSaving(true)
    try {
      const updated = await mailApi.saveTemplate(stage, { subject, body })
      setItems((prev) => prev?.map((t) => (t.stage === stage ? updated : t)) ?? null)
      show('ok', '문구를 저장했습니다')
    } catch (err) {
      /* 허용 외 변수는 422 다. 서버가 어떤 토큰이 문제인지 알려주므로 그대로 띄운다 */
      show('fail', err instanceof ApiError ? err.message : '저장하지 못했습니다')
    } finally {
      setSaving(false)
    }
  }

  async function reset() {
    setSaving(true)
    try {
      const restored = await mailApi.resetTemplate(stage)
      setItems((prev) => prev?.map((t) => (t.stage === stage ? restored : t)) ?? null)
      show('ok', '기본 문구로 되돌렸습니다')
    } catch (err) {
      show('fail', err instanceof ApiError ? err.message : '되돌리지 못했습니다')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div role="tabpanel" className={styles.mail}>
      <nav className={styles.stageNav}>
        {MAIL_STAGES.map((s) => (
          <button
            key={s.stage}
            type="button"
            className={s.stage === stage ? styles.stageOn : undefined}
            onClick={() => setStage(s.stage)}
          >
            {s.label}
          </button>
        ))}
      </nav>

      <div className={styles.mailBody}>
        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.mailHead}>
          <span className={current?.source === 'custom' ? styles.badgeOn : styles.badge}>
            {current?.source === 'custom' ? '수정됨' : '기본 문구'}
          </span>
          {current?.source === 'custom' && current.updated_by_name && (
            <span className={styles.sub}>마지막 수정: {current.updated_by_name}</span>
          )}
        </div>

        <div className={styles.field}>
          <label htmlFor="tpl-subject">제목</label>
          <input
            className={styles.input}
            id="tpl-subject"
            type="text"
            value={subject}
            maxLength={255}
            disabled={items === null}
            onChange={(e) => setSubject(e.target.value)}
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="tpl-body">본문</label>
          <textarea
            className={styles.textarea}
            id="tpl-body"
            rows={14}
            value={body}
            disabled={items === null}
            onChange={(e) => setBody(e.target.value)}
          />
        </div>

        <p className={styles.note}>
          쓸 수 있는 변수: {TEMPLATE_VARS.join(' ')} — 그 외 중괄호는 저장할 때 거절됩니다.
          {'{서명}'}은 보낸 주체에 따라 채워집니다(담당자 이름 / 채용 에이전트 아르 / 채용팀).
        </p>

        <div className={styles.formActions}>
          <button
            type="button"
            className="btn"
            disabled={saving || current?.source !== 'custom'}
            onClick={reset}
          >
            기본 문구로 되돌리기
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={saving || !dirty}
            onClick={save}
          >
            {saving ? '저장 중…' : '저장'}
          </button>
        </div>
      </div>
    </div>
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
