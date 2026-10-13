import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageHead from '../components/PageHead'
import { useToast } from '../components/Toast'
import { ApiError } from '../api/client'
import { postings as postingsApi } from '../api/endpoints'
import type { Posting, PostingPublicLink, ScreeningMode } from '../api/types'
import styles from './Postings.module.css'

const STATUS_LABEL: Record<Posting['status'], string> = {
  draft: '작성중',
  open: '진행중',
  closed: '마감',
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return iso.slice(0, 10).replaceAll('-', '.')
}

function deadlineText(p: Posting): string {
  if (p.deadline === null) return '상시'
  if (p.d_day === null) return fmtDate(p.deadline)
  const dday = p.d_day >= 0 ? `D-${p.d_day}` : `D+${-p.d_day}`
  return `${fmtDate(p.deadline)} · ${dday}`
}

const STAGES = [
  { key: 'applied',   label: '접수', color: 'var(--stage-1)' },
  { key: 'screening', label: '서류', color: 'var(--stage-2)' },
  { key: 'interview', label: '면접', color: 'var(--stage-3)' },
  { key: 'accepted',  label: '합격', color: 'var(--stage-4)' },
]

const NARROW_MQ = '(max-width: 768px)'

/* 오늘(로컬 기준) YYYY-MM-DD. 서버가 지난 날짜를 거절하므로(_reject_past)
   date 입력의 min 으로 걸어 둔다 — 제출하고 나서 에러로 알려 주는 것보다 낫다 */
function todayISO(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export default function Postings() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<Posting[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(NARROW_MQ).matches,
  )

  useEffect(() => {
    const mq = window.matchMedia(NARROW_MQ)
    const on = () => setNarrow(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  useEffect(() => {
    const ac = new AbortController()
    setError(null)
    postingsApi
      .list(ac.signal)
      .then(setRows)
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '공고를 불러오지 못했습니다')
      })
    return () => ac.abort()
  }, [])

  return (
    <>
      <PageHead
        title="채용 공고"
        actions={
          <button
            type="button"
            className={styles.addBtn}
            aria-label="공고 등록"
            onClick={() => setCreating(true)}
          >
            +
          </button>
        }
      />
      {creating && (
        <NewPostingModal
          onClose={() => setCreating(false)}
          /* 목록 맨 앞에 끼워 넣는다 — 서버 정렬도 등록일 내림차순이라 다시 불러올 필요가 없다 */
          onCreated={(p) => setRows((prev) => (prev === null ? [p] : [p, ...prev]))}
        />
      )}
      <main className="page-content">
        {narrow ? (
          <div className={styles.cardList}>
            {rows?.map((p) => {
              const sc = p.stage_counts ?? {}
              const total = Object.values(sc).reduce((a, b) => a + b, 0)
              return (
                <div
                  key={p.id}
                  className={styles.card}
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(`/postings/${p.id}`)}
                  onKeyDown={(e) => e.key === 'Enter' && navigate(`/postings/${p.id}`)}
                >
                  <div className={styles.cardTop}>
                    <span className={styles.cardTitle}>{p.title}</span>
                    <span className={`badge ${p.status === 'open' ? 'badge-open' : 'badge-closed'}`}>
                      {STATUS_LABEL[p.status]}
                    </span>
                  </div>
                  <p className={styles.cardSub}>
                    지원자 {p.application_count}명 · 마감 {deadlineText(p)}
                  </p>
                  {total > 0 && (
                    <>
                      <div
                        className={styles.bar}
                        style={{
                          gridTemplateColumns: STAGES.map((s) => `minmax(6px, ${sc[s.key] ?? 0}fr)`).join(' '),
                        }}
                      >
                        {STAGES.map((s) => (
                          <div key={s.key} className={styles.barSeg} style={{ background: s.color }} />
                        ))}
                      </div>
                      <div className={styles.stageCounts}>
                        {STAGES.map((s, i) => (
                          <span key={s.key} className={styles.stageItem}>
                            <span className={styles.stageDot} style={{ background: s.color }} />
                            {s.label} {sc[s.key] ?? 0}
                            {i < STAGES.length - 1 && <span className={styles.sep}> · </span>}
                          </span>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )
            })}
            {error !== null && <p className={styles.state} role="alert">{error}</p>}
            {error === null && rows === null && <p className={styles.state}>불러오는 중…</p>}
            {error === null && rows?.length === 0 && (
              <p className={styles.state}>등록된 공고가 없습니다.</p>
            )}
          </div>
        ) : (
          <div className={styles.panel}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>공고명</th>
                  <th>상태</th>
                  <th className={styles.num}>지원자</th>
                  <th className={styles.num}>마감</th>
                  <th className={styles.num}>등록일</th>
                </tr>
              </thead>
              <tbody>
                {rows?.map((p) => (
                  <tr key={p.id} className={styles.clickable} onClick={() => navigate(`/postings/${p.id}`)}>
                    <td className={styles.name}>{p.title}</td>
                    <td>
                      <span className={`badge ${p.status === 'open' ? 'badge-open' : 'badge-closed'}`}>
                        {STATUS_LABEL[p.status]}
                      </span>
                    </td>
                    <td className={styles.num}>{p.application_count}명</td>
                    <td className={styles.num}>{deadlineText(p)}</td>
                    <td className={styles.num}>{fmtDate(p.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {error !== null && <p className={styles.state} role="alert">{error}</p>}
            {error === null && rows === null && <p className={styles.state}>불러오는 중…</p>}
            {error === null && rows?.length === 0 && (
              <p className={styles.state}>등록된 공고가 없습니다.</p>
            )}
          </div>
        )}
      </main>
    </>
  )
}

/* ── 공고 등록 (+) ──────────────────────────────────────────────────
   두 단계다. ① 공고를 만들고 ② 공개 지원 링크를 발급해 보여 준다.
   한 화면에 붙인 이유: 지원 링크를 받는 길이 여기 말고 없는데, 등록만 하고 닫으면
   방금 만든 공고로 지원을 받을 방법이 없다 — 담당자가 "그래서 어디로 지원하라고 하지"
   에서 막힌다. 그래서 등록의 끝을 "링크를 손에 쥔 상태"로 둔다. */
function NewPostingModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (p: Posting) => void
}) {
  const { show } = useToast()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [deadline, setDeadline] = useState('')
  const [threshold, setThreshold] = useState(60)
  const [mode, setMode] = useState<ScreeningMode>('auto')
  const [open, setOpen] = useState(true)
  const [saving, setSaving] = useState(false)
  /* 만들어진 공고 + 링크. 채워지면 폼 대신 ② 단계를 그린다 */
  const [done, setDone] = useState<{ posting: Posting; link: PostingPublicLink | null } | null>(null)
  const [copied, setCopied] = useState(false)

  /* 링크를 보여 주는 ② 단계에서는 Escape·바깥 클릭으로 닫히지 않게 한다.
     발급된 링크를 다시 보여 주는 화면이 아직 없어서, 복사 전에 실수로 닫으면
     그 링크를 되찾을 길이 담당자에게 없다 — 닫기 버튼을 누르게 한다 */
  const dismissable = done === null

  useEffect(() => {
    if (!dismissable) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [dismissable, onClose])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (saving) return
    setSaving(true)
    try {
      const posting = await postingsApi.create({
        title: title.trim(),
        description: description.trim() || null,
        status: open ? 'open' : 'draft',
        deadline: deadline || null, // 비우면 상시 접수 (B4)
        pass_threshold: threshold,
        screening_mode: mode,
      })
      onCreated(posting)
      /* 링크 발급은 공고가 열려 있을 때만 의미가 있다 — 작성중이면 공개 링크가 지원을 안 받는다.
         발급이 실패해도 공고는 이미 만들어졌으므로 등록 자체를 실패로 되돌리지 않는다 */
      let link: PostingPublicLink | null = null
      if (posting.status === 'open') {
        try {
          link = await postingsApi.publicLink(posting.id)
        } catch {
          show('fail', '공고는 등록됐지만 지원 링크를 받지 못했습니다')
        }
      }
      setDone({ posting, link })
      show('ok', '공고를 등록했습니다')
    } catch (err) {
      show('fail', err instanceof ApiError ? err.message : '공고를 등록하지 못했습니다')
    } finally {
      setSaving(false)
    }
  }

  /* 입력칸을 골라 execCommand 로 복사한다. navigator.clipboard 가 권한에 막히는
     환경(조직 정책·일부 내장 브라우저)이 실제로 있어서, 그때 쓰는 예비 경로다 */
  function copyBySelection(): boolean {
    const el = document.getElementById('p-link')
    if (!(el instanceof HTMLInputElement)) return false
    el.select()
    try {
      return document.execCommand('copy')
    } catch {
      return false
    }
  }

  async function copyLink() {
    if (done?.link == null) return
    let ok = false
    try {
      await navigator.clipboard.writeText(done.link.url)
      ok = true
    } catch {
      ok = copyBySelection()
    }
    if (ok) {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
      return
    }
    /* 둘 다 막혔으면 복사한 척하지 않는다. 주소는 이미 골라 둔 상태라
       Ctrl+C 한 번이면 끝난다 */
    show('fail', '복사가 막혀 있습니다. 주소를 골라 뒀으니 Ctrl+C 를 눌러 주세요')
  }

  return (
    <div
      className={styles.modalScrim}
      role="presentation"
      onClick={dismissable ? onClose : undefined}
    >
      {done === null ? (
        <form
          className={styles.modal}
          role="dialog"
          aria-modal="true"
          aria-label="공고 등록"
          onClick={(e) => e.stopPropagation()}
          onSubmit={submit}
        >
          <h2 className={styles.modalTitle}>공고 등록</h2>

          <div className={styles.field}>
            <label htmlFor="p-title">공고명</label>
            <input
              className={styles.input}
              id="p-title"
              value={title}
              required
              maxLength={200}
              autoFocus
              placeholder="백엔드 개발자 (Python·FastAPI)"
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="p-desc">공고 내용</label>
            <textarea
              className={styles.textarea}
              id="p-desc"
              rows={6}
              value={description}
              placeholder={'주요 업무\n- …\n\n자격 요건\n- …'}
              onChange={(e) => setDescription(e.target.value)}
            />
            <p className={styles.hint}>지원자가 지원 화면에서 그대로 보게 됩니다.</p>
          </div>

          <div className={styles.row}>
            <div className={styles.field}>
              <label htmlFor="p-deadline">마감일</label>
              <input
                className={styles.input}
                id="p-deadline"
                type="date"
                value={deadline}
                min={todayISO()}
                onChange={(e) => setDeadline(e.target.value)}
              />
              <p className={styles.hint}>비우면 상시 접수</p>
            </div>
            <div className={styles.field}>
              <label htmlFor="p-threshold">서류 통과 기준</label>
              <input
                className={styles.input}
                id="p-threshold"
                type="number"
                min={0}
                max={100}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
              />
              <p className={styles.hint}>100점 만점</p>
            </div>
          </div>

          <div className={styles.field}>
            <label htmlFor="p-mode">서류 심사</label>
            <select
              className={styles.input}
              id="p-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as ScreeningMode)}
            >
              <option value="auto">자동 — 기준 이상이면 면접으로, 미만이면 불합격으로</option>
              <option value="manual">수동 — 점수만 매기고 단계는 담당자가 옮김</option>
            </select>
          </div>

          <label className={styles.check}>
            <input type="checkbox" checked={open} onChange={(e) => setOpen(e.target.checked)} />
            <span>
              바로 지원을 받습니다
              <em className={styles.checkHint}>
                끄면 「작성중」으로 저장되고 지원 링크가 생기지 않습니다
              </em>
            </span>
          </label>

          <div className={styles.modalActions}>
            <button type="button" className="btn" onClick={onClose}>취소</button>
            <button type="submit" className="btn btn-primary" disabled={saving || title.trim() === ''}>
              {saving ? '등록하는 중…' : '등록'}
            </button>
          </div>
        </form>
      ) : (
        <div
          className={styles.modal}
          role="dialog"
          aria-modal="true"
          aria-label="공고 등록 완료"
          onClick={(e) => e.stopPropagation()}
        >
          <h2 className={styles.modalTitle}>등록했습니다</h2>
          <p className={styles.doneTitle}>{done.posting.title}</p>

          {done.link !== null ? (
            <>
              <div className={styles.field}>
                <label htmlFor="p-link">지원 링크</label>
                <input className={styles.input} id="p-link" readOnly value={done.link.url}
                  onFocus={(e) => e.currentTarget.select()} />
                <p className={styles.hint}>
                  이 주소를 받은 사람은 <b>로그인 없이</b> 지원서를 냅니다.
                </p>
              </div>
              <div className={styles.modalActions}>
                <button type="button" className="btn" onClick={copyLink}>
                  {copied ? '복사했습니다' : '링크 복사'}
                </button>
                <button type="button" className="btn btn-primary" onClick={onClose}>닫기</button>
              </div>
            </>
          ) : (
            <>
              <p className={styles.hint}>
                「작성중」으로 저장했습니다. 공고를 열면 지원 링크가 생깁니다.
              </p>
              <div className={styles.modalActions}>
                <button type="button" className="btn btn-primary" onClick={onClose}>닫기</button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
