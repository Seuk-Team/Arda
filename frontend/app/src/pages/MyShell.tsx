import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Navigate,
  NavLink,
  useLocation,
  useNavigate,
  useSearchParams,
} from 'react-router-dom'
import { getApplicantToken, setApplicantToken } from '../api/client'
import { applicantAuth } from '../api/endpoints'
import type { ApplicantMe, MyApplication } from '../api/types'
import BrandMark from '../components/BrandMark'
import { isOver, MyContext, shortDate, tasksOf, todoCount, type TabKey } from './myApplicant'
import MyApplications from './MyApplications'
import { MyAptitude, MyInterview, MySchedule } from './MyTabs'
import styles from './MyShell.module.css'

/* 지원자 웹 셸 (ADR-0033) — 이메일 + 생년월일 8자리로 들어온다.

   **담당자 로그인(`/login`)과 완전히 다른 화면이다.** 같은 자리에 두면 지원자가
   담당자 계정으로 들어가려다 막히고, 담당자는 반대로 헤맨다. 실제로 그렇게 한 번
   막혔다 — 그래서 주소도 화면도 나눠 뒀다.

   토큰도 자리를 나눈다(`arda-applicant-token`). 한 브라우저에서 담당자로 보다가
   여기에 들어와도 서로를 덮어쓰지 않는다.

   ## 2026-09-15 — 앱과 같은 탭을 웹에도

   그 전에는 `/my` 한 장이 전부였다. 인적성을 보려면 `/aptitude/<토큰>` 이라는
   **셸 밖의 화면**으로 나갔고, 거기에는 `/my` 로 돌아오는 링크가 한 개도
   없었다 — 브라우저 뒤로 가기가 유일한 길이었다. 앱은 하단 탭 다섯으로 도는데
   (mobile/lib/screens/applicant_shell.dart) 웹만 그랬다.

   이 셸이 앱의 `ApplicantShell` 자리다:
   - `/applicant/me` 를 **한 번만** 부르고 탭에 나눠 준다 (앱과 같은 구조)
   - 사이드바가 전형 네 자리를 연다 — 현황 · 인적성 검사 · 면접 시간 · AI 면접
   - 「내 정보」는 오른쪽 위 계정 메뉴다. 사이드바는 전형을 밟는 자리고 내 정보는
     성격이 다르다 (담당자 쪽도 2026-09-05 에 설정을 내비에서 뺐다)

   **메일 링크(`/aptitude/:token` 등)는 그대로 산다.** 토큰만 들고 오는 사람이
   있고 — 로그인 없이 — 그 길을 막으면 메일이 깨진다.

   ## 어느 지원을 보는가는 주소가 들고 있다

   `?app=<id>`. 상태로 들고 있으면 탭을 옮길 때마다 처음 것으로 돌아간다.
   주소에 있으면 새로고침·뒤로 가기·링크 공유가 전부 맞는다 (지원자 목록
   필터를 URL 로 옮긴 것과 같은 이유). */

/* ── 로컬에서 화면만 보려고 열 때 ─────────────────

   `/my?preview` 로 열면 **서버를 안 부르고** 아래 표본으로 그린다.

   이 화면은 진짜 지원자 계정(이메일 + 생년월일)이 있어야 열리는데, 그 계정은
   지원 폼에 생년월일이 생긴 2026-09-08 이후에 낸 지원서만 가진다 — 화면 하나
   고치려고 매번 지원서를 새로 내야 했다.

   **`import.meta.env.DEV` 안에 있다.** vite dev 에서만 참이고 빌드 번들에서는
   이 상수가 죽은 코드로 제거되므로 배포에 새어 나갈 수 없다 — AuthContext 의
   DEV_USER 와 같은 장치이고 같은 이유다("화면 하나 보려고 매번 로그인하지 않게").

   **표본인 것을 화면에 적는다** — 값이 어디서 왔는지는 화면이 말해야 한다. */

function inDays(n: number): string {
  return new Date(Date.now() + n * 86_400_000).toISOString()
}

const PREVIEW: ApplicantMe | null = import.meta.env.DEV
  ? {
      email: 'preview@example.invalid',
      name: '최민서',
      applications: [
        {
          id: 1,
          posting_title: '프론트엔드 개발자 (React)',
          stage_label: '면접 전형 진행 중',
          applied_at: '2026-09-09T02:00:00Z',
          aptitudes: [{ token: 'p-a1', status: 'pending', expires_at: inDays(2) }],
          schedules: [{ token: 'p-s1', status: 'proposed', expires_at: inDays(6) }],
          interviews: [],
        },
        {
          id: 2,
          posting_title: '백엔드 개발자 (Python·FastAPI)',
          stage_label: '서류 검토 중',
          applied_at: '2026-09-05T02:00:00Z',
          aptitudes: [{ token: 'p-a2', status: 'done', expires_at: null }],
          schedules: [],
          interviews: [],
        },
        {
          id: 3,
          posting_title: '데이터 엔지니어',
          stage_label: '최종 합격',
          applied_at: '2026-08-21T02:00:00Z',
          aptitudes: [{ token: 'p-a3', status: 'done', expires_at: null }],
          schedules: [{ token: 'p-s3', status: 'confirmed', expires_at: null }],
          interviews: [{ token: 'p-i3', status: 'done', expires_at: null }],
        },
        {
          id: 4,
          posting_title: 'QA 엔지니어',
          stage_label: '전형 종료',
          applied_at: '2026-07-30T02:00:00Z',
          aptitudes: [{ token: 'p-a4', status: 'done', expires_at: null }],
          schedules: [],
          interviews: [],
        },
      ],
    }
  : null

type View = { kind: 'login' } | { kind: 'loading' } | { kind: 'ready'; data: ApplicantMe }

/* ── 탭 ──────────────────────────────────────────────

   앱(ApplicantTab)과 같은 네 자리다. 이름도 앱에서 가져왔다 — 사이드바에는
   짧은 이름, 상단 바에는 긴 이름(앱의 `label` · `title` 과 같은 규칙). */

interface Tab {
  /* '' 이면 `/my` 자신 */
  path: '' | TabKey
  label: string
  title: string
  icon: ReactNode
}

const TABS: Tab[] = [
  {
    path: '',
    label: '현황',
    title: '지원 현황',
    icon: <path d="M3 11l9-8 9 8M5 10v10h14V10" />,
  },
  {
    path: 'aptitude',
    label: '인적성 검사',
    title: '인적성 검사',
    icon: <path d="M9 11l3 3 8-8M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />,
  },
  {
    path: 'schedule',
    label: '면접 시간',
    title: '면접 시간 조율',
    icon: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M16 3v4M8 3v4M3 11h18" />
      </>
    ),
  },
  {
    path: 'interview',
    label: 'AI 면접',
    title: 'AI 면접',
    icon: (
      <>
        <path d="M23 7l-7 5 7 5V7z" />
        <rect x="1" y="5" width="15" height="14" rx="2" />
      </>
    ),
  },
]

export default function MyShell() {
  const [params, setParams] = useSearchParams()
  const preview = PREVIEW !== null && params.has('preview')

  const [view, setView] = useState<View>(() => {
    if (preview && PREVIEW !== null) return { kind: 'ready', data: PREVIEW }
    return getApplicantToken() ? { kind: 'loading' } : { kind: 'login' }
  })
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [menu, setMenu] = useState(false)
  /* 내 정보 — 계정 메뉴에서 연다. 갈 곳이 여기 하나라 라우트를 따로 파지 않고
     이 화면 위에 덮는다(담당자 쪽 Settings 는 사이드바가 있어 라우트다) */
  const [info, setInfo] = useState(false)
  /* 지원자 데모로 들어오면 한 번 뜨는 안내 팝업 (로그인 버튼이 sessionStorage 에
     플래그를 심는다). 실제 지원자에겐 안 뜬다. */
  const [demoNotice, setDemoNotice] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  /* 한 번이라도 연 탭 (앱의 `_opened`). 안 연 것은 만들지 않는다 — 처음부터
     넷을 다 만들면 화면을 켜는 순간 네 화면이 각자 자기 링크를 부른다 */
  const [opened, setOpened] = useState<ReadonlySet<string>>(() => new Set())

  useEffect(() => {
    try {
      if (sessionStorage.getItem('arda_demo_notice') === '1') {
        sessionStorage.removeItem('arda_demo_notice')
        setDemoNotice(true)
      }
    } catch { /* 무시 */ }
  }, [])

  /* 지금 탭. 주소만 보면 아는 값이라 이른 return 들보다 위에 둔다 —
     아래 effect 가 훅 순서를 어기지 않게 */
  const here = TABS.find((t) => t.path !== '' && pathname === `/my/${t.path}`) ?? TABS[0]

  /* 한 번이라도 받아 왔는가. **두 번째부터는 실패해도 보던 것을 뺏지 않는다** —
     탭을 옮길 때마다 부르는데, 잠깐의 네트워크 끊김으로 로그인 화면에 튕기면
     하던 일이 날아간다. 처음 받아 올 때만 로그인으로 되돌린다. */
  const got = useRef(false)

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await applicantAuth.me(signal)
      got.current = true
      setView({ kind: 'ready', data })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      if (got.current) return
      /* 토큰이 죽었으면 클라이언트가 이미 지웠다. 로그인 화면으로 되돌린다. */
      setView({ kind: 'login' })
    }
  }, [])

  /* **탭을 옮길 때마다 다시 받는다** (2026-09-15).

     셸이 한 번만 받으면, 인적성을 내고 현황으로 돌아온 지원자가 「아직 안
     하셨습니다」와 사이드바 배지 ① 을 그대로 본다 — 방금 낸 것이 화면에
     반영되지 않는다. 탭 자신은 자기 링크를 다시 부르므로 맞는 말을 하는데,
     셸만 어제 것을 들고 있어 **한 화면이 두 말을 한다.** 앱에서 홈과 탭이
     갈렸던 것과 같은 모양이다.

     `/applicant/me` 는 작은 조회고 탭 전환은 하루에 몇 번이라, 매번 부르는
     값이 낡은 화면보다 싸다. */
  useEffect(() => {
    if (preview) return
    if (!getApplicantToken()) return
    const ac = new AbortController()
    void load(ac.signal)
    return () => ac.abort()
  }, [load, preview, pathname])

  /* 연 탭을 기억해 둔다. 그리는 것은 위 `show` 가 이미 했고, 이 기록은
     **다음에 다른 탭으로 옮겼을 때 이 탭을 살려 두기 위한 것**이다 */
  useEffect(() => {
    setOpened((prev) => (prev.has(here.path) ? prev : new Set(prev).add(here.path)))
  }, [here.path])

  /* 내 정보 — Esc 로 닫는다. 바깥 클릭은 스크림이 받는다 */
  useEffect(() => {
    if (!info) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setInfo(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [info])

  /* 계정 메뉴 — 바깥을 누르거나 Esc 면 닫는다 */
  useEffect(() => {
    if (!menu) return
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenu(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenu(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [menu])

  /* **나가면 /login 으로 간다** — 들어온 문과 같은 자리다 */
  function logout() {
    setApplicantToken(null)
    setMenu(false)
    setInfo(false)
    navigate('/login?as=applicant', { replace: true })
  }

  /* **로그인 화면은 /login 하나다** (2026-09-14).

     전에는 여기에도 폼이 따로 있었다. /login 의 지원자 칸으로 들어왔는데
     로그아웃하면 생김새가 다른 폼이 떠서, **들어온 문과 나가는 문이 달랐다.**
     토큰이 없으면 /login 으로 보낸다 — `?as=applicant` 로 그쪽이 지원자 칸을
     펴 놓게 한다.

     로딩만 여기서 그린다. 토큰이 살아 있는 동안의 짧은 사이라 화면을 옮기면
     오히려 깜빡인다. */
  /* 모르는 주소는 현황으로 되돌린다 (`/my/garbage`, 옛 북마크, 오타).

     `/my/*` 하나가 아래를 다 받으므로 라우터는 이런 것도 셸에 들여보낸다.
     그냥 두면 **현황 내용이 뜨는데 사이드바에는 아무것도 선택되어 있지 않다** —
     지금 어느 탭인지 화면이 말을 못 한다(실측). 주소를 고쳐 준다. */
  if (pathname !== '/my' && !TABS.some((t) => t.path !== '' && pathname === `/my/${t.path}`)) {
    return <Navigate to={{ pathname: '/my', search: params.toString() }} replace />
  }

  if (view.kind === 'login') {
    return <Navigate to="/login?as=applicant" replace />
  }

  if (view.kind === 'loading') {
    return (
      <div className={styles.page}>
        <header className={styles.topbar}>
          <h1 className={styles.logo}>
            <BrandMark size={24} halo className={styles.logoMark} />
            Arda
          </h1>
        </header>
        <div className={styles.body}>
          <div className={styles.main}>
            <div className={styles.column}>
              <div className={styles.card} aria-busy="true">
                <div className={styles.skeleton} style={{ width: '50%' }} />
                <div className={styles.skeleton} />
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const me = view.data
  const apps = me.applications
  /* 주소가 가리키는 지원. 없거나 못 찾으면 첫 번째 — 서버가 최신 순으로 준다 */
  const wanted = Number(params.get('app'))
  const app = apps.find((a) => a.id === wanted) ?? apps[0] ?? null
  const initial = me.name ? me.name.charAt(0) : '?'

  /* 탭을 옮겨도 「보고 있는 지원」과 표본 여부는 따라간다 */
  const carry = new URLSearchParams()
  if (app !== null && apps.length > 1) carry.set('app', String(app.id))
  if (preview) carry.set('preview', '')
  const search = carry.toString()

  /* 지금 탭은 `opened` 에 들어가기 전에도 그린다 — effect 를 기다리면 탭을
     처음 열 때 한 프레임이 빈다 */
  const show = new Set(opened).add(here.path)

  const tasks = app === null ? [] : tasksOf(app)
  const todoOf = (path: TabKey) =>
    tasks.filter((t) => t.tab === path && t.tone === 'todo').length

  function pick(id: number) {
    const next = new URLSearchParams(params)
    next.set('app', String(id))
    setParams(next, { replace: true })
  }

  return (
    <div className={styles.page}>
      {/* 상단 바만 화면 끝까지 간다 */}
      <header className={styles.topbar}>
        <h1 className={styles.logo}>
          <BrandMark size={24} halo className={styles.logoMark} />
          Arda
        </h1>
        <span className={styles.divider} aria-hidden="true" />
        <span className={styles.where}>{here.title}</span>
        <span className={styles.gap} />

        <div className={styles.account} ref={menuRef}>
          <button
            type="button"
            className={`${styles.trigger} ${menu ? styles.triggerOn : ''}`}
            aria-haspopup="menu"
            aria-expanded={menu}
            aria-label={`${me.name || '내'} 계정 메뉴`}
            onClick={() => setMenu((v) => !v)}
          >
            <span className={styles.avatar} aria-hidden="true">{initial}</span>
            <span className={styles.tname}>{me.name || '지원자'}</span>
            <svg className={styles.caret} viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>

          {menu && (
            <div className={styles.menu} role="menu">
              <div className={styles.mWho}>
                <span className={styles.avatar} aria-hidden="true">{initial}</span>
                <span className={styles.mText}>
                  <span className={styles.mName}>{me.name || '지원자'}</span>
                  <span className={styles.mMail}>{me.email}</span>
                </span>
              </div>
              <div className={styles.sep} role="separator" />
              {/* 「내 정보」가 여기 있다 — 사이드바가 아니라 (2026-09-15).
                  사이드바는 전형을 밟는 자리고 내 정보는 성격이 다르다 */}
              <button
                type="button"
                role="menuitem"
                className={styles.mItem}
                onClick={() => {
                  setMenu(false)
                  setInfo(true)
                }}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="12" cy="8" r="4" />
                  <path d="M4 21c0-4 3.6-7 8-7s8 3 8 7" />
                </svg>
                내 정보
              </button>
              {/* 로그아웃은 **여기 한 자리뿐이다.** 덮개에도 두면 같은 동작이
                  두 군데 생긴다 */}
              <button type="button" role="menuitem" className={styles.mItem} onClick={logout}>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M16 17l5-5-5-5M21 12H9M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
                </svg>
                로그아웃
              </button>
            </div>
          )}
        </div>
      </header>

      <div className={styles.body}>
        <aside className={styles.side}>
          <div className={styles.sideStick}>
            {/* **둘 이상일 때만 뜬다.** 하나뿐인 사람에게 고를 것이 하나인
                목록을 보여 줄 이유가 없다 — 대부분이 그렇다 */}
            {app !== null && apps.length > 1 && (
              <Picker apps={apps} open={app} onPick={pick} />
            )}

            <nav className={styles.nav}>
              {TABS.map((t) => {
                const n = t.path === '' ? 0 : todoOf(t.path)
                return (
                  <NavLink
                    key={t.path}
                    to={{ pathname: t.path === '' ? '/my' : `/my/${t.path}`, search }}
                    end={t.path === ''}
                    className={({ isActive }) =>
                      `${styles.navItem} ${isActive ? styles.navOn : ''}`
                    }
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">{t.icon}</svg>
                    <span className={styles.navText}>{t.label}</span>
                    {n > 0 && (
                      <span className={styles.badge} aria-label={`할 일 ${n}개`}>
                        {n}
                      </span>
                    )}
                  </NavLink>
                )
              })}
            </nav>
          </div>
        </aside>

        {/* **한 번 연 탭은 살려 둔다** — 감출 뿐 버리지 않는다.

            라우트로 갈아 끼우던 것을 바꾼 것이다(2026-09-15). 갈아 끼우면
            탭을 누를 때마다 앞 화면이 통째로 사라져서:
            - **인적성에서 답하던 것이 날아갔다** (3/10 → 현황 갔다 오면 0/10, 실측)
            - **AI 면접 중에 다른 탭을 누르면 면접이 끊겼다.** 게다가 소켓·카메라만
              닫히고 `/finish` 는 안 불려(useAiInterview 는 「면접 끝내기」에서만
              부른다) 담당자 화면에 「아직 보는 중」으로 영영 남았다

            앱은 이 문제가 없다 — `IndexedStack` 이 한 번 연 탭을 살려 둔다
            (applicant_shell.dart). 같은 것을 여기서도 한다.

            안 연 탭은 만들지 않는다(앱의 `_opened` 와 같다). 처음부터 넷을 다
            만들면 화면을 켜는 순간 네 화면이 각자 자기 링크를 부른다. */}
        <div className={styles.main}>
          <MyContext.Provider value={{ me, app, preview }}>
            {TABS.filter((t) => show.has(t.path)).map((t) => (
              <div key={t.path} className={styles.pane} hidden={t.path !== here.path}>
                {t.path === '' ? (
                  <MyApplications />
                ) : t.path === 'aptitude' ? (
                  <MyAptitude />
                ) : t.path === 'schedule' ? (
                  <MySchedule />
                ) : (
                  <MyInterview />
                )}
              </div>
            ))}
          </MyContext.Provider>
        </div>
      </div>

      {info && <InfoOverlay me={me} onClose={() => setInfo(false)} />}
      {demoNotice && <DemoNoticeOverlay onClose={() => setDemoNotice(false)} />}
    </div>
  )
}

/* ── 보고 있는 지원 ──────────────────────────────────

   **여기는 공고 목록이 아니라 내가 낸 것들이다** — 서버가 내 이메일로 낸
   지원만 골라 내린다(app/talent/api/applicant_auth.py). 공고 제목만 늘어놓으면
   채용 사이트처럼 읽혀서, 줄마다 낸 날짜를 붙이고 진행 중·끝난 것으로 묶는다. */
function Picker({
  apps,
  open,
  onPick,
}: {
  apps: MyApplication[]
  open: MyApplication
  onPick: (id: number) => void
}) {
  const [on, setOn] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!on) return
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOn(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOn(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [on])

  const live = apps.filter((a) => !isOver(a.stage_label))
  const over = apps.filter((a) => isOver(a.stage_label))

  const row = (a: MyApplication) => (
    <button
      key={a.id}
      type="button"
      role="option"
      aria-selected={a.id === open.id}
      className={`${styles.pickItem} ${a.id === open.id ? styles.pickItemOn : ''}`}
      onClick={() => {
        onPick(a.id)
        setOn(false)
      }}
    >
      <span className={styles.pickText}>
        <span className={styles.pickTitle}>{a.posting_title || '공고'}</span>
        <span className={styles.pickWhen}>
          {shortDate(a.applied_at)} 지원 · {a.stage_label}
        </span>
      </span>
      {todoCount(a) > 0 && <span className={styles.badge}>{todoCount(a)}</span>}
    </button>
  )

  return (
    <div className={styles.picker} ref={boxRef}>
      <p className={styles.pickLabel}>보고 있는 지원</p>
      <button
        type="button"
        className={styles.pickBox}
        aria-haspopup="listbox"
        aria-expanded={on}
        onClick={() => setOn((v) => !v)}
      >
        <span className={styles.pickName}>{open.posting_title || '공고'}</span>
        <svg className={styles.caret} viewBox="0 0 24 24" aria-hidden="true">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {on && (
        <div className={styles.pickList} role="listbox" aria-label="보고 있는 지원">
          {live.length > 0 && (
            <>
              <p className={styles.pickGroup}>진행 중 {live.length}건</p>
              {live.map(row)}
            </>
          )}
          {over.length > 0 && (
            <>
              <p className={styles.pickGroup}>끝난 것 {over.length}건</p>
              {over.map(row)}
            </>
          )}
        </div>
      )}
    </div>
  )
}

/* ── 내 정보 ─────────────────────────────────────────

   앱의 내 정보 탭(applicant_more_screen.dart)과 같은 내용이다 — 프로필 ·
   숫자 셋 · 비밀번호. 로그아웃만 계정 메뉴에 두었다.

   ## 2026-09-18 — 「준비 중」이 거짓말이 되어 있었다

   09-16 에 지원자 비밀번호 로그인이 나갔는데(`7b46768`) 이 칸만 그대로라
   **「생년월일 8자리로 로그인합니다 · 준비 중」** 이라고 적혀 있었다. 이미
   비밀번호로 들어온 사람이 자기 화면에서 그 문장을 본다.

   **여기서 바꾸지는 않는다** — 설정·재설정이 메일 링크 한 경로이고, 앱도
   같은 말을 한다(applicant_more_screen.dart 의 「메일로」 줄). 여기에 폼을
   또 열면 두 벌을 들고 있게 된다.

   그래서 **비활성 버튼을 없애고 어디서 하는지를 적는다.** 눌리지 않는
   버튼은 그 자체로 「고장인가 아직인가」를 묻게 만든다 — 애초에 누를 것이
   없으면 그 질문이 안 생긴다.

   이미 로그인한 사람이 메일함을 안 거치고 바꾸는 길은 아직 없다. 막힌
   사람은 없어 급하지 않고, 프리즈 뒤로 미뤄 둔 것이다.

   덮개로 만든 이유: 사이드바에 자리를 안 주기로 했으니 갔다가 돌아올 길을
   따로 만들어야 한다. 덮으면 닫기만 하면 제자리다. */
function DemoNoticeOverlay({ onClose }: { onClose: () => void }) {
  return (
    <div className={styles.scrim} onClick={onClose} role="presentation">
      <div
        className={styles.sheet}
        role="dialog"
        aria-modal="true"
        aria-label="데모 안내"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.sheetHead}>
          <h2 className={styles.sheetTitle}>데모 안내</h2>
          <span className={styles.gap} />
          <button type="button" className={styles.x} onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </div>
        <div className={styles.sheetBody}>
          <p>이곳은 지원자 화면을 볼 수 있는 데모 환경입니다.</p>
          <p>
            실시간으로 면접을 테스트하고 싶으실 경우 담당자 데모로 로그인 하여
            확인 부탁드리겠습니다.
          </p>
          <button type="button" className="btn btn-primary" onClick={onClose}>
            확인
          </button>
        </div>
      </div>
    </div>
  )
}


function InfoOverlay({ me, onClose }: { me: ApplicantMe; onClose: () => void }) {
  const apps = me.applications
  const todo = apps.filter((a) => todoCount(a) > 0).length
  const won = apps.filter((a) => a.stage_label === '최종 합격').length

  return (
    <div className={styles.scrim} onClick={onClose} role="presentation">
      <div
        className={styles.sheet}
        role="dialog"
        aria-modal="true"
        aria-label="내 정보"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.sheetHead}>
          <h2 className={styles.sheetTitle}>내 정보</h2>
          <span className={styles.gap} />
          <button type="button" className={styles.x} onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </div>

        <div className={styles.sheetBody}>
          <section className={styles.section}>
            {/* 앱과 같은 숫자 셋. 0 이면 색을 쓰지 않는다 */}
            <div className={styles.stats}>
              <span className={styles.stat}>
                <span className={styles.statN}>{apps.length}</span>
                <span className={styles.statName}>낸 지원</span>
              </span>
              <span className={styles.stat}>
                <span className={`${styles.statN} ${todo > 0 ? styles.statTodo : ''}`}>
                  {todo}
                </span>
                <span className={styles.statName}>할 일</span>
              </span>
              <span className={styles.stat}>
                <span className={`${styles.statN} ${won > 0 ? styles.statWon : ''}`}>
                  {won}
                </span>
                <span className={styles.statName}>합격</span>
              </span>
            </div>
          </section>

          <section className={styles.section}>
            <h3 className={styles.sectionName}>계정</h3>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="me-name">이름</label>
              <input className={styles.input} id="me-name" value={me.name} readOnly />
            </div>
            <div className={styles.field}>
              {/* 이메일은 로그인 식별자다 — 담당자 설정과 같은 이유로 바꾸는 길을 두지 않는다 */}
              <label className={styles.label} htmlFor="me-mail">이메일</label>
              <input className={styles.input} id="me-mail" value={me.email} readOnly />
              <p className={styles.hint}>지원할 때 쓰신 주소입니다. 바꿀 수 없습니다.</p>
            </div>
          </section>

          <section className={styles.section}>
            <h3 className={styles.sectionName}>비밀번호</h3>
            <p className={styles.hint}>
              바꾸시려면 로그인 화면에서 <strong>「비밀번호 설정 링크 받기」</strong>를 눌러
              주세요. 메일로 받은 링크에서 새 비밀번호를 정합니다. 처음 정하실 때도 같은
              길입니다.
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
