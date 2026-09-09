import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { agent } from '../api/endpoints'
import { ApiError } from '../api/client'
import type { AgentLabelVerdict, AgentTraceItem } from '../api/types'
import { useToast } from '../components/Toast'
import styles from './AgentTraceLabel.module.css'

/* 담당자 라벨 UI — Qwen QLoRA 학습 데이터 수집.

   agent_traces 표에 쌓인 대화를 훑으며 good/needs_fix/bad 로 라벨한다.
   label_verdict='good' 만 학습셋으로 넘어간다 (infra/gpu/prepare_dataset.py).

   원칙:
   - **누구나 라벨 가능** (admin 만 두면 5명 팀에서 사실상 안 쌓인다).
     서버에서 label_by · label_at 이 남으므로 나중에 특정인의 라벨만 신뢰·배제 가능.
   - **덮어쓰기** — 이력을 별도 표로 남기지 않는다 (팀 규모에 과잉).
   - **커서 페이지** — id desc + before_id. 라벨이 붙거나 새 로그가 쌓여도 어긋나지 않는다.
*/

type StatusFilter = 'unlabeled' | 'good' | 'needs_fix' | 'bad' | 'all'

const STATUS_LABELS: Record<StatusFilter, string> = {
  unlabeled: '라벨 안 됨',
  good: '좋음 (good)',
  needs_fix: '고쳐야 함 (needs_fix)',
  bad: '나쁨 (bad)',
  all: '전체',
}

const VERDICT_LABELS: Record<AgentLabelVerdict, string> = {
  good: '좋음',
  needs_fix: '고쳐야 함',
  bad: '나쁨',
}

function fmt(iso: string): string {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/* 트레이스 한 건 카드. 라벨 3버튼 + needs_fix 시 정답 텍스트 입력. */
function TraceCard({
  trace,
  onLabeled,
}: {
  trace: AgentTraceItem
  onLabeled: (updated: AgentTraceItem) => void
}) {
  const { show } = useToast()
  const [correction, setCorrection] = useState(trace.label_correction ?? '')
  const [busy, setBusy] = useState<AgentLabelVerdict | null>(null)

  async function label(verdict: AgentLabelVerdict, e?: FormEvent) {
    e?.preventDefault()
    if (busy) return
    setBusy(verdict)
    try {
      const updated = await agent.labelTrace(trace.id, {
        label_verdict: verdict,
        label_correction: verdict === 'needs_fix' ? correction.trim() || null : null,
      })
      onLabeled(updated)
      show('ok', `라벨: ${VERDICT_LABELS[verdict]}`)
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : '라벨 저장 실패'
      show('fail', msg)
    } finally {
      setBusy(null)
    }
  }

  const labelledColor = trace.label_verdict
    ? styles[`v_${trace.label_verdict}`]
    : styles.v_unlabeled

  return (
    <article className={`${styles.card} ${labelledColor}`}>
      <header className={styles.cardHead}>
        <span className={styles.id}>#{trace.id}</span>
        <span className={styles.meta}>
          {fmt(trace.created_at)} · {trace.backend || '(backend 없음)'} · {trace.model_tag || '?'}
        </span>
        {trace.label_verdict && (
          <span className={`${styles.badge} ${labelledColor}`}>
            {VERDICT_LABELS[trace.label_verdict]}
          </span>
        )}
      </header>

      <section className={styles.turn}>
        <div className={styles.turnLabel}>담당자</div>
        <pre className={styles.turnBody}>{trace.user_message}</pre>
      </section>

      {trace.tool_calls.length > 0 && (
        <section className={styles.tools}>
          <div className={styles.turnLabel}>도구 호출</div>
          <ul className={styles.toolList}>
            {trace.tool_calls.map((tc, i) => (
              <li key={i} className={styles.toolItem}>
                <b>{tc.name}</b>
                {' — '}
                <code>{JSON.stringify(tc.input)}</code>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className={styles.turn}>
        <div className={styles.turnLabel}>아르 답변</div>
        <pre className={styles.turnBody}>{trace.assistant_reply || '(빈 답변)'}</pre>
      </section>

      <footer className={styles.actions}>
        <form
          className={styles.correctionForm}
          onSubmit={(e) => void label('needs_fix', e)}
        >
          <label htmlFor={`c-${trace.id}`} className="sr-only">
            needs_fix 시 정답 (선택)
          </label>
          <textarea
            id={`c-${trace.id}`}
            className={styles.correction}
            rows={2}
            maxLength={2000}
            placeholder="needs_fix 라면 여기에 사람이 쓴 정답 (선택)"
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            disabled={busy !== null}
          />
        </form>
        <div className={styles.buttons}>
          <button
            type="button"
            className={`btn btn-primary ${styles.btnGood}`}
            onClick={() => void label('good')}
            disabled={busy !== null}
          >
            {busy === 'good' ? '…' : '✓ 좋음'}
          </button>
          <button
            type="button"
            className={`btn btn-secondary ${styles.btnFix}`}
            onClick={() => void label('needs_fix')}
            disabled={busy !== null}
          >
            {busy === 'needs_fix' ? '…' : '⚠ 고쳐야 함'}
          </button>
          <button
            type="button"
            className={`btn btn-secondary ${styles.btnBad}`}
            onClick={() => void label('bad')}
            disabled={busy !== null}
          >
            {busy === 'bad' ? '…' : '✕ 나쁨'}
          </button>
        </div>
      </footer>
    </article>
  )
}

export default function AgentTraceLabel() {
  const { show } = useToast()
  const [status, setStatus] = useState<StatusFilter>('unlabeled')
  const [items, setItems] = useState<AgentTraceItem[]>([])
  const [nextCursor, setNextCursor] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(
    async (opts: { status: StatusFilter; beforeId?: number; append: boolean }, signal?: AbortSignal) => {
      setLoading(true)
      setError(null)
      try {
        const res = await agent.listTraces(
          { status: opts.status, limit: 20, beforeId: opts.beforeId },
          signal,
        )
        setItems((prev) => (opts.append ? [...prev, ...res.items] : res.items))
        setNextCursor(res.next_cursor)
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        const msg = err instanceof ApiError ? err.message : '목록을 불러오지 못했습니다'
        setError(msg)
        show('fail', msg)
      } finally {
        setLoading(false)
      }
    },
    [show],
  )

  useEffect(() => {
    const ctrl = new AbortController()
    void load({ status, append: false }, ctrl.signal)
    return () => ctrl.abort()
  }, [status, load])

  function onLabeled(updated: AgentTraceItem) {
    setItems((prev) =>
      prev
        .map((t) => (t.id === updated.id ? updated : t))
        .filter((t) => (status === 'unlabeled' ? t.label_verdict === null : true)),
    )
  }

  return (
    <main className={styles.root}>
      <header className={styles.head}>
        <h1 className={styles.title}>아르 대화 라벨</h1>
        <p className={styles.sub}>
          <b>{items.length}</b>건 · Qwen QLoRA 학습셋에 <b>good</b> 라벨만 들어갑니다
        </p>
        <div className={styles.filter} role="tablist" aria-label="라벨 상태">
          {(Object.keys(STATUS_LABELS) as StatusFilter[]).map((s) => (
            <button
              key={s}
              type="button"
              role="tab"
              aria-selected={status === s}
              className={`btn ${status === s ? 'btn-primary' : 'btn-ghost'} ${styles.filterBtn}`}
              onClick={() => setStatus(s)}
            >
              {STATUS_LABELS[s]}
            </button>
          ))}
        </div>
      </header>

      {error && <p className={styles.error}>{error}</p>}

      {!loading && items.length === 0 && !error && (
        <p className={styles.empty}>
          {status === 'unlabeled'
            ? '라벨할 대화가 없어요. 아르에게 몇 마디 던지고 다시 오세요.'
            : `${STATUS_LABELS[status]} 상태 대화가 없습니다.`}
        </p>
      )}

      <div className={styles.list}>
        {items.map((t) => (
          <TraceCard key={t.id} trace={t} onLabeled={onLabeled} />
        ))}
      </div>

      {nextCursor !== null && (
        <div className={styles.more}>
          <button
            type="button"
            className="btn btn-ghost"
            disabled={loading}
            onClick={() => void load({ status, beforeId: nextCursor, append: true })}
          >
            {loading ? '불러오는 중…' : '더 불러오기'}
          </button>
        </div>
      )}

      {loading && items.length === 0 && <p className={styles.empty}>불러오는 중…</p>}
    </main>
  )
}
