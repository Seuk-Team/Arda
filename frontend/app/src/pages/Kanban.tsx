import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { applications, stages as stagesApi } from '../api/endpoints'
import type { ApplicationListItem, Stage } from '../api/types'
import { useToast } from '../components/Toast'
import { STAGE_LABEL, careerText, withRo } from '../lib/stage'
import styles from './Kanban.module.css'

/* 칸반 뷰 (D2·D3) — 05-design §0.5 "칸반 뷰 토글(소수 인원 단계용, 드래그 유지)".
   목업에 그려진 화면이 아니라 §0.5·§6 서술을 근거로 만든 것이다.

   §7 이 전제하는 10만 건에서 한 칸에 전건을 담을 수는 없다. 칸마다 앞에서
   COLUMN_LIMIT 명만 받고 나머지는 "외 N명" 으로 남긴다 — 칸반은 소수 인원
   단계를 옮기는 곳이고, 많은 쪽은 목록에서 일괄로 옮긴다. */

const COLUMNS: Stage[] = ['applied', 'screening', 'interview', 'accepted', 'rejected']
const COLUMN_LIMIT = 50

interface Props {
  postingId: number
  /* 목록·퍼널과 같은 데이터를 보고 있으므로 바뀌면 같이 다시 센다 */
  onChanged: () => void
  tick: number
}

interface Column {
  items: ApplicationListItem[]
  total: number
}

export default function Kanban({ postingId, onChanged, tick }: Props) {
  const { show } = useToast()

  const [cols, setCols] = useState<Record<string, Column> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragId, setDragId] = useState<number | null>(null)
  const [overStage, setOverStage] = useState<Stage | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const ac = new AbortController()
    setError(null)
    Promise.all(
      COLUMNS.map((s) =>
        applications.search(
          { posting_id: postingId, stage: s, limit: COLUMN_LIMIT, with_total: true },
          ac.signal,
        ),
      ),
    )
      .then((res) => {
        const next: Record<string, Column> = {}
        COLUMNS.forEach((s, i) => {
          next[s] = { items: res[i].items, total: res[i].total ?? res[i].items.length }
        })
        setCols(next)
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '칸반을 불러오지 못했습니다')
      })
    return () => ac.abort()
  }, [postingId, tick])

  /* 낙관적 업데이트 — 카드를 먼저 옮기고 서버 응답을 기다린다.
     실패하면 되돌리고 토스트로 알린다 (§6). 조용히 되돌아가면 옮긴 줄 안다. */
  async function move(id: number, from: Stage, to: Stage) {
    if (from === to || cols === null || busy) return

    const card = cols[from].items.find((c) => c.id === id)
    if (!card) return

    /* 불합격은 사유가 필수라(D8) 드래그만으로는 보낼 수 없다.
       칸반에서 사유를 받을 자리가 없어 목록·상세로 보낸다. */
    if (to === 'rejected') {
      show('fail', '불합격은 사유가 필요합니다. 목록이나 상세 패널에서 옮겨 주세요.')
      return
    }

    const before = cols
    const optimistic: Record<string, Column> = {
      ...cols,
      [from]: { items: cols[from].items.filter((c) => c.id !== id), total: cols[from].total - 1 },
      [to]: { items: [{ ...card, current_stage: to }, ...cols[to].items], total: cols[to].total + 1 },
    }
    setCols(optimistic)
    setBusy(true)

    try {
      await stagesApi.change(id, to)
      show('ok', `${card.name} — ${withRo(STAGE_LABEL[to])} 옮겼습니다.`)
      onChanged()
    } catch (err) {
      setCols(before) // 되돌린다
      show('fail', err instanceof ApiError ? err.message : '단계를 바꾸지 못했습니다')
    } finally {
      setBusy(false)
    }
  }

  if (error !== null) return <p className={styles.state} role="alert">{error}</p>
  if (cols === null) return <p className={styles.state}>불러오는 중…</p>

  return (
    <div className={styles.board}>
      {COLUMNS.map((s) => {
        const col = cols[s]
        const rest = col.total - col.items.length
        return (
          <section
            key={s}
            className={`${styles.col} ${overStage === s ? styles.colOver : ''}`}
            onDragOver={(e) => {
              e.preventDefault()
              setOverStage(s)
            }}
            onDragLeave={() => setOverStage((cur) => (cur === s ? null : cur))}
            onDrop={(e) => {
              e.preventDefault()
              setOverStage(null)
              const id = Number(e.dataTransfer.getData('text/plain'))
              const from = e.dataTransfer.getData('application/x-stage') as Stage
              if (id) move(id, from, s)
            }}
          >
            <header className={styles.colHead}>
              <span className={styles.colName}>{STAGE_LABEL[s]}</span>
              <span className={styles.colCount}>{col.total}</span>
            </header>

            <div className={styles.cards}>
              {col.items.map((a) => (
                <article
                  key={a.id}
                  className={`${styles.card} ${dragId === a.id ? styles.dragging : ''}`}
                  draggable={!busy}
                  onDragStart={(e) => {
                    e.dataTransfer.setData('text/plain', String(a.id))
                    e.dataTransfer.setData('application/x-stage', s)
                    e.dataTransfer.effectAllowed = 'move'
                    setDragId(a.id)
                  }}
                  onDragEnd={() => setDragId(null)}
                >
                  <div className={styles.cardName}>{a.name}</div>
                  <div className={styles.cardSub}>
                    {careerText(a.career_years)}
                    {a.avg_score !== null && ` · ${a.avg_score.toFixed(1)}`}
                  </div>

                  {/* 드래그 대체 수단 (§10) — 마우스를 못 쓰는 경우에도 옮길 수 있어야 한다 */}
                  <label className={styles.moveLabel}>
                    <span className="sr-only">{a.name} 단계 변경</span>
                    <select
                      className={styles.move}
                      value={s}
                      disabled={busy}
                      onChange={(e) => move(a.id, s, e.target.value as Stage)}
                    >
                      {COLUMNS.map((t) => (
                        <option key={t} value={t}>{STAGE_LABEL[t]}</option>
                      ))}
                    </select>
                  </label>
                </article>
              ))}

              {col.items.length === 0 && <p className={styles.empty}>없음</p>}
              {rest > 0 && (
                <p className={styles.more}>외 {rest.toLocaleString()}명 — 목록에서 일괄로 옮기세요</p>
              )}
            </div>
          </section>
        )
      })}
    </div>
  )
}
