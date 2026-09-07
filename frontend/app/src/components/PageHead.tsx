import type { ReactNode } from 'react'
import AccountMenu from './AccountMenu'
import styles from './PageHead.module.css'

/* 화면 제목 띠. mockup.html 의 .head 규격 (§12-1 시안 복제).
   액션 버튼은 목업처럼 이 띠 안 오른쪽에 놓는다.

   meta 는 제목 바로 옆에 붙는 요약 숫자 자리다 (대시보드가 쓴다) —
   숫자 카드 한 줄을 따로 두면 세로를 그만큼 먹는데, 그 줄이 하는 일은
   "지금 몇 건인가" 한 마디뿐이라 제목 띠 안으로 들어가는 편이 낫다. */
export default function PageHead({
  title,
  meta,
  actions,
}: {
  title: string
  meta?: ReactNode
  actions?: ReactNode
}) {
  return (
    /* data-pagehead — 화면 전환이 제목 띠를 함께 페이드시킬 때 잡는 손잡이 */
    <header className={styles.head} data-pagehead="">
      <h1 className={styles.title}>{title}</h1>
      {meta}
      {/* 남는 폭은 이 칸이 먹는다 — 제목이 flex 로 늘어나면 meta 가 오른쪽 끝으로 밀린다 */}
      <span className={styles.spacer} aria-hidden="true" />
      {actions && <div className={styles.actions}>{actions}</div>}
      {/* 계정 묶음은 늘 맨 오른쪽 — 화면마다 자리가 바뀌면 찾는 데 시간이 든다.
          사이드바 바닥에서 여기로 올렸다 (2026-09-05) */}
      <AccountMenu />
    </header>
  )
}
