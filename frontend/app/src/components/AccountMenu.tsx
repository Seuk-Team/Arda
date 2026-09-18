import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ROLE_LABEL } from '../lib/stage'
import styles from './AccountMenu.module.css'

/* 우측 상단 계정 묶음. 사이드바 바닥에 있던 프로필을 여기로 올렸다 —
   바닥은 눈이 마지막에 가는 자리인데 거기 있는 것이 늘 보이는 정보였다.

   ## 2026-09-18 — 로그아웃을 여기로 올린다 (09-05 결정 개정)

   09-05 에는 **"프로필은 자주 눌리는 자리라 되돌릴 수 없는 항목을 두면
   오조작이 난다"** 는 이유로 로그아웃을 '내 계정' 화면 안쪽에 뒀었다.

   그 전제가 틀렸다. **로그아웃은 되돌릴 수 없는 일이 아니다** — 되돌리는
   비용이 다시 로그인 한 번이다. Settings 쪽 주석도 같은 말을 하고 있었고
   (확인 모달을 안 세운 이유가 정확히 그것이다), 앱의 내 정보도 "되돌릴 수
   있는 일이라 삭제와 같은 무게를 주지 않는다" 고 적어 두고 메뉴에 두고 있다.
   한 서비스 안에서 같은 동작을 두 가지로 판단하고 있었던 셈이다.

   그리고 **담당자 웹만 예외였다.** 지원자 웹(MyShell)도 앱 더보기도 이미
   계정 메뉴 한 자리에 두고 있어서, 나가려는 사람이 담당자 웹에서만 두 단계를
   더 눌러야 했다.

   **로그아웃은 이제 여기 한 자리뿐이다** — '내 계정' 화면에서는 뺐다. 같은
   동작이 두 군데 있으면 어느 쪽이 진짜인지 갈린다(지원자 웹과 같은 규칙).
   오조작 걱정은 자리로 던다: 구분선 아래 맨 끝, 다른 항목과 붙지 않게.

   설정 화면은 라우트를 쪼개지 않고 탭만 지정한다. 쪼개면 모바일 '더보기'가
   가리키는 /settings 가 admin 전용이 되어 member 는 내 계정에 못 들어간다. */
const TABS = {
  account: '내 계정',
  admin: '사용자·권한',
} as const

const ICONS = {
  account: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4.5 20a7.5 7.5 0 0 1 15 0',
  admin: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H9a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V9a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.51 1z',
  /* 지원자 웹(MyShell)·앱 더보기와 같은 문 모양이다 — 같은 동작은 같은 그림 */
  leave: 'M16 17l5-5-5-5M21 12H9M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4',
} as const

export default function AccountMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  /* 바깥 클릭·Esc 로 닫는다. 열려 있을 때만 듣는다 — 안 그러면 모든 화면의
     모든 클릭이 이 핸들러를 지난다 */
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  /* 부트스트랩 중에는 아무것도 그리지 않는다. 목업 이름을 대신 쓰지 않는다 (§6) */
  if (!user) return null

  const go = (tab: string) => {
    setOpen(false)
    navigate(`/settings?tab=${encodeURIComponent(tab)}`)
  }

  return (
    <div className={styles.box} ref={boxRef}>
      {/* 평소에는 아바타와 이름만. 역할·메일은 눌렀을 때 메뉴 머리에서 말한다 —
          늘 보이는 자리에 세 줄을 쌓으면 제목 띠가 무거워진다 */}
      <button
        type="button"
        className={`${styles.trigger} ${open ? styles.on : ''}`}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${user.name} 계정 메뉴`}
      >
        <span className={styles.avatar} aria-hidden="true">{user.name.charAt(0)}</span>
        <span className={styles.name}>{user.name}</span>
        <svg className={styles.caret} viewBox="0 0 24 24" aria-hidden="true">
          <path d={open ? 'M6 14l6-6 6 6' : 'M6 10l6 6 6-6'} />
        </svg>
      </button>

      {open && (
        <div className={styles.menu} role="menu">
          {/* 누구로 로그인해 있는지 — 계정 메뉴가 첫째로 답해야 할 것이다 */}
          <div className={styles.who}>
            <span className={styles.whoAvatar} aria-hidden="true">{user.name.charAt(0)}</span>
            <span className={styles.whoText}>
              <span className={styles.whoName}>
                {user.name}
                <span className={styles.role}>{ROLE_LABEL[user.role]}</span>
              </span>
              <span className={styles.whoMail}>{user.email}</span>
            </span>
          </div>

          <div className={styles.sep} role="separator" />

          <button type="button" role="menuitem" className={styles.item} onClick={() => go(TABS.account)}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS.account} /></svg>
            내 계정
          </button>

          {/* member 에게는 이 항목이 통째로 없다 — 눌러서 권한 없다고 답하는 것보다
              애초에 안 보이는 편이 낫다 */}
          {user.role === 'admin' && (
            <button type="button" role="menuitem" className={styles.item} onClick={() => go(TABS.admin)}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS.admin} /></svg>
              설정
            </button>
          )}

          {/* 나가는 것. **구분선 아래 맨 끝**이라 위 항목을 누르려다 스치지 않는다.
              확인 모달은 세우지 않는다 — 되돌리는 비용이 다시 로그인 한 번이라
              모달을 세울 무게가 아니다(모바일 '더보기'·지원자 웹과 같은 동작).
              빨간 테두리도 두르지 않는다: 적갈은 불합격에만 쓴다 (05-design §1) */}
          <div className={styles.sep} role="separator" />

          <button
            type="button"
            role="menuitem"
            className={`${styles.item} ${styles.leave}`}
            onClick={() => {
              setOpen(false)
              logout()
              navigate('/login', { replace: true })
            }}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS.leave} /></svg>
            로그아웃
          </button>
        </div>
      )}
    </div>
  )
}
