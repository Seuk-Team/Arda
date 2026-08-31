/* 아르 에이전트 패널. ADR-0009 개정(2026-08-31) — 화면 우측이 아니라
   좌측 사이드바 바로 오른쪽에 붙는 "두 번째 사이드바"다.
   사이드바 하단 3D 정사각형이 오른쪽으로 늘어나 패널이 되는 확장으로 읽힌다.
   본문(채팅)은 ArChat.tsx(다른 오너)가 채운다 — 여기는 셸만 담당. */
import { useEffect } from 'react'
import type { RefObject } from 'react'
import styles from './ArPanel.module.css'
import ArChat, { type ArMotion } from './ArChat'

export type { ArMotion }

interface Props {
  open: boolean
  onClose: () => void
  /* 채팅 상태 → 사이드바 정사각형 안 아르의 모션 */
  onMotion: (motion: ArMotion) => void
  /* 닫을 때 포커스를 되돌릴 곳 (사이드바의 아르 정사각형 버튼) */
  triggerRef: RefObject<HTMLButtonElement | null>
}

export default function ArPanel({ open, onClose, onMotion, triggerRef }: Props) {
  /* Esc 로 닫기. 열려 있을 때만 듣는다 — 다른 오버레이의 Esc 를 뺏지 않는다. */
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  /* 초기 포커스는 채팅 입력창 — 열자마자 바로 시킬 수 있어야 한다.
     닫을 때는 트리거로 복원 (DESIGN.md §3.4).
     포커스 트랩은 걸지 않는다 — 모달이 아니라 본문과 나란히 서는 상주 영역이라
     Tab 으로 본문까지 나갈 수 있어야 한다. */
  useEffect(() => {
    if (open) return
    if (document.activeElement instanceof HTMLElement && document.activeElement.closest(`.${styles.panel}`)) {
      triggerRef.current?.focus()
    }
  }, [open, triggerRef])

  return (
    <aside
      id="ar-panel"
      className={`${styles.panel} ${open ? styles.open : ''}`}
      aria-label="아르 에이전트"
      /* 닫힌 폭 0 안에 포커스가 갇히지 않게 */
      inert={!open}
    >
      <div className={styles.inner}>
        <header className={styles.head}>
          <b className={styles.title}>아르</b>
          <span className={styles.sub}>에이전트</span>
          <button
            type="button"
            className={styles.close}
            onClick={onClose}
            aria-label="아르 패널 닫기"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>

        {/* 채팅 본체는 ArChat.tsx(다른 오너)가 그린다 — 헤더·닫기는 이 셸의 몫.
            닫혀도 언마운트하지 않는다: 언마운트하면 대화 이력이 날아간다.
            폭 0 + overflow hidden 으로 가려지고, inert 가 포커스·클릭을 막는다. */}
        <div className={styles.body}>
          <ArChat onMotion={onMotion} focusOn={open} />
        </div>
      </div>
    </aside>
  )
}
