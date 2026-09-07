import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ROLE_LABEL } from '../lib/stage'
import styles from './AccountMenu.module.css'

/* 우측 상단 계정 묶음. 사이드바 바닥에 있던 프로필을 여기로 올렸다 —
   바닥은 눈이 마지막에 가는 자리인데 거기 있는 것이 늘 보이는 정보였다.

   메뉴에 로그아웃을 두지 않는다. 프로필은 자주 눌리는 자리라 그 안에
   되돌릴 수 없는 항목이 있으면 오조작이 난다 — 로그아웃은 한 단계 안쪽,
   '내 계정' 화면에 있다 (2026-09-05 결정).

   설정 화면은 라우트를 쪼개지 않고 탭만 지정한다. 쪼개면 모바일 '더보기'가
   가리키는 /settings 가 admin 전용이 되어 member 는 내 계정에 못 들어간다. */
const TABS = {
  account: '내 계정',
  admin: '사용자·권한',
} as const

export default function AccountMenu() {
  const { user } = useAuth()
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
      <button
        type="button"
        className={`${styles.trigger} ${open ? styles.on : ''}`}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        /* 안쪽 글자만으로는 읽기 도구가 이름을 못 잡는다(아바타는 aria-hidden,
           이름·역할은 두 줄로 갈려 있다) — 무엇을 여는 버튼인지 직접 적는다 */
        aria-label={`${user.name} 계정 메뉴`}
      >
        <span className={styles.avatar} aria-hidden="true">{user.name.charAt(0)}</span>
        <span className={styles.who}>
          <span className={styles.name}>{user.name}</span>
          <span className={styles.role}>{ROLE_LABEL[user.role]}</span>
        </span>
        <svg className={styles.caret} viewBox="0 0 24 24" aria-hidden="true">
          <path d={open ? 'M6 14l6-6 6 6' : 'M6 10l6 6 6-6'} />
        </svg>
      </button>

      {open && (
        <div className={styles.menu} role="menu">
          <button type="button" role="menuitem" className={styles.item} onClick={() => go(TABS.account)}>
            <span className={styles.itemLabel}>내 계정</span>
            <span className={styles.itemSub}>내 정보 · 면접 가능 시간 · 로그아웃</span>
          </button>

          {/* member 에게는 이 항목이 통째로 없다 — 눌러야 권한 없다고 답하는 것보다
              애초에 안 보이는 편이 낫다 */}
          {user.role === 'admin' && (
            <button type="button" role="menuitem" className={styles.item} onClick={() => go(TABS.admin)}>
              <span className={styles.itemLabel}>설정</span>
              <span className={styles.itemSub}>사용자·권한 · 메일 템플릿</span>
            </button>
          )}
        </div>
      )}
    </div>
  )
}
