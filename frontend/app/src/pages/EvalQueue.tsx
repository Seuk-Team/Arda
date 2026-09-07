import type { UserItem } from '../api/types'
import { STAGE_LABEL } from '../lib/stage'
import { STALE_DAYS, avatarOf, type Group, type Row } from '../lib/evalQueue'
import styles from './Evaluations.module.css'

/* 평가 현황 목록의 그리기 담당. 계산은 lib/evalQueue.ts 가 한다 —
   한 파일이 컴포넌트와 함수를 같이 내보내면 fast refresh 가 안 먹는다 */

export function Rail({
  groups,
  selected,
  onSelect,
}: {
  groups: Group[]
  selected: number | 'all'
  onSelect: (id: number | 'all') => void
}) {
  return (
    <nav className={styles.rail} aria-label="공고 선택">
      {groups.map((g) => (
        <button
          key={String(g.id)}
          type="button"
          className={`${styles.railItem} ${g.id === selected ? styles.railOn : ''}`}
          aria-current={g.id === selected ? 'true' : undefined}
          onClick={() => onSelect(g.id)}
        >
          <span className={styles.railTop}>
            <span className={styles.railTitle}>{g.title}</span>
            <span className={styles.railCount}>
              {g.done}/{g.total}
            </span>
          </span>
          <span className={styles.railTrack}>
            <span
              className={styles.railBar}
              style={{ width: g.total === 0 ? '0%' : `${Math.round((g.done / g.total) * 100)}%` }}
            />
          </span>
        </button>
      ))}
    </nav>
  )
}

export function QueueRow({
  row,
  users,
  current,
  onOpen,
}: {
  row: Row
  users: Map<number, UserItem>
  current: boolean
  onOpen: () => void
}) {
  const { item, mine, others, days, split } = row
  const stale = mine === null && days > STALE_DAYS

  /* 내 평가를 맨 앞에 둔다 — 이 줄에서 내가 어디 서 있는지가 먼저다.
     아바타는 셋까지, 나머지는 +n (열 폭이 고정이라 넘치면 줄이 밀린다) */
  const all = [...(mine ? [mine] : []), ...others]
  const shown = all.slice(0, 3)
  const rest = all.length - shown.length

  return (
    <div
      className={`${styles.item} ${current ? styles.cur : ''}`}
      tabIndex={0}
      role="button"
      aria-current={current ? 'true' : undefined}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen()
        }
      }}
    >
      <span className={styles.who}>
        <span className={styles.name}>{item.detail.name}</span>
        <span className={styles.sub}>
          {STAGE_LABEL[item.detail.current_stage]} · 배정 {days}일째
        </span>
      </span>

      <span className={styles.badges}>
        {/* 배지는 색만으로 뜻을 나르지 않는다 — 글자가 항상 같이 있다 */}
        {split && <span className={`${styles.badge} ${styles.badgeWarn}`}>의견 갈림</span>}
        {stale && <span className={`${styles.badge} ${styles.badgeHot}`}>{days}일 경과</span>}
      </span>

      {/* 아무도 안 냈으면 빈 칸으로 둔다 — 오른쪽 점수 칸이 이미 '미착수'라고
          말하고 있어, 여기 '평가 없음'을 또 쓰면 같은 말을 두 번 한다 */}
      <span className={styles.avatars}>
        {shown.map((e) => {
          const nm = users.get(e.evaluator_id)?.name ?? '?'
          const av = avatarOf(nm)
          return (
            <span
              key={e.id}
              className={styles.avatar}
              style={{ background: av.bg, color: av.fg }}
              title={`${nm} · ${e.score}점`}
            >
              {av.ini}
            </span>
          )
        })}
        {rest > 0 && <span className={styles.more}>+{rest}</span>}
      </span>

      <span className={styles.scoreBox}>
        <span
          className={`${styles.score} ${
            row.scoreTone === 'ok' ? styles.scoreOk : row.scoreTone === 'warn' ? styles.scoreWarn : styles.scoreNone
          }`}
        >
          {row.scoreText}
        </span>
        {row.sub !== '' && <span className={styles.scoreSub}>{row.sub}</span>}
      </span>

      <span className={mine === null ? styles.btnGo : styles.btnQuiet}>
        {mine === null ? '평가' : split ? '조정' : '보기'}
      </span>
    </div>
  )
}
