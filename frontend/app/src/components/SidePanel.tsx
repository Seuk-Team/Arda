/* 옆에서 나오는 패널의 공통 껍데기.
   시안(1-right-panel.html)의 #panel-slot 이 원래 하나였다 — .dpanel(지원자 상세)과
   #agSurface(아르)가 같은 규격으로 들어가고 앞뒤만 바뀌는 구조. 코드에서 둘로 갈라져
   있던 것을 다시 하나로 모은 것이 이 파일이다. 내용은 children 이 채운다.

   두 사용처의 규격이 달라 variant 로 나눈다:
   - rail    아르 에이전트. 좌측 사이드바 오른쪽에 붙고 폭 0 ↔ 360px 로 늘어난다(border-right).
             닫혀도 언마운트하지 않는다 — 대화 이력이 날아가므로 폭 0 + inert 로 가린다.
   - content 지원자 상세. 본문 오른쪽에 420px 로 붙고(border-left) 부모가 조건부 렌더한다.
             flex 자식이라 열리면 콘텐츠를 밀어낸다 — 오버레이가 아니다. */
import { useEffect, useLayoutEffect, useRef } from 'react'
import type { ReactNode, RefObject } from 'react'
import styles from './SidePanel.module.css'

interface Props {
  variant: 'rail' | 'content'
  /* rail 은 열림 상태를 넘겨 폭·inert 를 바꾼다.
     content 는 부모가 언마운트로 닫으므로 항상 열려 있다. */
  open?: boolean
  onClose: () => void
  /* aside 의 접근성 이름 */
  label: string
  /* 닫기 버튼의 접근성 이름 */
  closeLabel: string
  /* title 을 주면 헤더 행(제목 + 부제 + 오른쪽 닫기 버튼),
     안 주면 콘텐츠 위에 떠 있는 닫기 버튼 */
  title?: string
  subtitle?: string
  /* 바깥에서 aria-controls 로 가리킬 때 */
  id?: string
  /* 닫을 때 포커스를 되돌릴 곳 */
  triggerRef?: RefObject<HTMLElement | null>
  children: ReactNode
}

export default function SidePanel({
  variant,
  open = true,
  onClose,
  label,
  closeLabel,
  title,
  subtitle,
  id,
  triggerRef,
  children,
}: Props) {
  const panelRef = useRef<HTMLElement>(null)

  /* Esc 로 닫기. 열려 있을 때만 듣는다 — 다른 오버레이의 Esc 를 뺏지 않는다. */
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  /* 닫을 때 포커스를 트리거로 복원 (DESIGN.md §3.4). 패널 안에 포커스가 있을 때만 —
     바깥을 보고 있었다면 시선을 끌어오지 않는다.
     정리 함수로 처리해야 언마운트로 닫는 content 도 같이 걸린다. useEffect 가 아니라
     useLayoutEffect 인 이유: 패널 DOM 이 지워지기 전에 activeElement 를 봐야 한다.
     포커스 트랩은 걸지 않는다 — 모달이 아니라 본문과 나란히 서는 상주 영역이라
     Tab 으로 본문까지 나갈 수 있어야 한다. */
  useLayoutEffect(() => {
    if (!open) return
    /* 두 노드 다 열려 있는 동안 그대로다 — 정리 시점에 ref 를 다시 읽지 않고 붙잡아 둔다 */
    const panel = panelRef.current
    const trigger = triggerRef?.current
    return () => {
      const active = document.activeElement
      if (active instanceof HTMLElement && panel?.contains(active)) {
        trigger?.focus()
      }
    }
  }, [open, triggerRef])

  const closeButton = (
    <button
      type="button"
      className={title === undefined ? styles.closeFloat : styles.close}
      onClick={onClose}
      aria-label={closeLabel}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 6l12 12M18 6L6 18" />
      </svg>
    </button>
  )

  return (
    <aside
      ref={panelRef}
      id={id}
      className={`${styles.panel} ${styles[variant]} ${open ? styles.open : ''}`}
      aria-label={label}
      /* 닫힌 폭 0 안에 포커스가 갇히지 않게 */
      inert={!open}
    >
      <div className={styles.inner}>
        {title === undefined ? (
          closeButton
        ) : (
          <header className={styles.head}>
            <b className={styles.title}>{title}</b>
            {subtitle !== undefined && <span className={styles.sub}>{subtitle}</span>}
            {closeButton}
          </header>
        )}

        <div className={styles.body}>{children}</div>
      </div>
    </aside>
  )
}
