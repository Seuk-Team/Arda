import type { ReactNode } from 'react'
import AccountMenu from './AccountMenu'
import styles from './PageHead.module.css'

/* 화면 제목 띠. mockup.html 의 .head 규격 (§12-1 시안 복제).
   액션 버튼은 목업처럼 이 띠 안 오른쪽에 놓는다. */
export default function PageHead({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    /* data-pagehead — 화면 전환이 제목 띠를 함께 페이드시킬 때 잡는 손잡이 */
    <header className={styles.head} data-pagehead="">
      <h1 className={styles.title}>{title}</h1>
      {actions && <div className={styles.actions}>{actions}</div>}
      {/* 계정 묶음은 늘 맨 오른쪽 — 화면마다 자리가 바뀌면 찾는 데 시간이 든다.
          사이드바 바닥에서 여기로 올렸다 (2026-09-05) */}
      <AccountMenu />
    </header>
  )
}
