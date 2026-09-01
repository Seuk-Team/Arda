import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { applications, mail as mailApi, notes as notesApi, stages } from '../api/endpoints'
import type { ApplicationDetail, EmailLogItem, Note, Stage } from '../api/types'
import SidePanel from '../components/SidePanel'
import { STAGE_LABEL, careerText, fmtDate, stageTone } from '../lib/stage'
import styles from './ApplicantPanel.module.css'

/* 지원자 상세 패널 (D4). 페이지 이동 없이 옆에서 연다 (05-design §0.5).
   껍데기(폭·테두리·스크롤·닫기 버튼·Esc·좁은 화면 오버레이)는 SidePanel(variant="content")이
   맡는다 — 여기는 내용만: mockup.html 의 .dpanel 구성인 AI 요약 · 지원 정보 · 메모. */

const TONE_CLASS = {
  progress: styles.stageProgress,
  accepted: styles.stageAccepted,
  rejected: styles.stageRejected,
}

/* AI 요약은 JSON 문자열로 저장된다 (summarizer.py 의 combined).
   모델이 코드펜스를 감싼 옛 데이터도 있어 벗겨서 시도하고,
   그래도 못 읽으면 원문을 그대로 보여준다 (숨기는 것보단 낫다). */
interface AiSummary {
  insufficient?: boolean
  gist?: string
  fit?: string[]
  concerns?: string[]
  recommendation?: { action?: string | null; reasons?: string[]; check_points?: string[] }
}

function parseAiSummary(raw: string): AiSummary | null {
  let s = raw.trim()
  if (s.startsWith('```')) {
    s = s.replace(/^```[a-zA-Z]*\n?/, '')
    if (s.endsWith('```')) s = s.slice(0, -3)
    s = s.trim()
  }
  try {
    const j: unknown = JSON.parse(s)
    if (j !== null && typeof j === 'object' && !Array.isArray(j)) return j as AiSummary
  } catch {
    /* JSON 이 아니면 아래에서 원문 표시 */
  }
  return null
}

function AiSummaryBody({ raw }: { raw: string }) {
  const parsed = parseAiSummary(raw)
  if (parsed === null) return <p className={styles.aibody}>{raw}</p>
  if (parsed.insufficient) {
    return <p className={styles.aibody}>자기소개 등 자료가 부족해 요약을 만들지 못했습니다.</p>
  }
  return (
    <div className={styles.aiparsed}>
      {parsed.gist && <p className={styles.aibody}>{parsed.gist}</p>}
      {(parsed.fit?.length ?? 0) > 0 && (
        <div>
          <p className={styles.ailabel}>강점</p>
          <ul className={styles.ailist}>
            {parsed.fit!.map((t, i) => <li key={i}>{t}</li>)}
          </ul>
        </div>
      )}
      {(parsed.concerns?.length ?? 0) > 0 && (
        <div>
          <p className={styles.ailabel}>확인 필요</p>
          <ul className={styles.ailist}>
            {parsed.concerns!.map((t, i) => <li key={i}>{t}</li>)}
          </ul>
        </div>
      )}
      {/* 면접 확인 포인트(check_points)는 만들되 여기 그리지 않는다.
          05-design §0.5 가 이 자리의 내용을 "자소서 요지 + 공고 요건 대비 적합·우려 지점"
          으로 한정한다. 요약이 길어지면 담당자가 안 읽는다 — 짧아야 요약이다.
          값은 ai_summary 에 그대로 저장돼 있어 나중에 쓸 수 있다. */}
    </div>
  )
}

/* 지금 단계에서 갈 수 있는 곳. 규칙은 backend/app/stages.py 와 같다 —
   전진은 한 칸씩, 불합격은 어디서든, 뒤로 되돌리기도 허용.
   단계 변경은 역할로 막지 않는다 — 로그인했으면 누구나 한다. */
const ORDER: Stage[] = ['applied', 'screening', 'interview', 'accepted']

function nextStages(from: Stage): Stage[] {
  if (from === 'rejected') return [...ORDER]
  const i = ORDER.indexOf(from)
  const out: Stage[] = []
  if (i > 0) out.push(ORDER[i - 1]) // 되돌리기
  if (i >= 0 && i + 1 < ORDER.length) out.push(ORDER[i + 1])
  out.push('rejected')
  return out
}

interface Props {
  applicationId: number
  onClose: () => void
  /* 단계가 바뀌면 목록·퍼널을 다시 세라고 알린다 */
  onChanged: () => void
}

export default function ApplicantPanel({ applicationId, onClose, onChanged }: Props) {
  const [detail, setDetail] = useState<ApplicationDetail | null>(null)
  const [noteList, setNoteList] = useState<Note[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  /* 불합격은 사유가 필수다 (D8). 없이 보내면 서버가 422 로 돌려보낸다 */
  const [pendingReject, setPendingReject] = useState(false)
  const [reason, setReason] = useState('')

  useEffect(() => {
    const ac = new AbortController()
    setDetail(null)
    setNoteList(null)
    setError(null)
    setActionError(null)
    setPendingReject(false)
    setReason('')
    setDraft('')

    Promise.all([
      applications.detail(applicationId, ac.signal),
      notesApi.list(applicationId, ac.signal),
    ])
      .then(([d, n]) => {
        setDetail(d)
        setNoteList(n)
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '지원자를 불러오지 못했습니다')
      })
    return () => ac.abort()
  }, [applicationId])

  async function changeStage(to: Stage) {
    if (!detail) return
    if (to === 'rejected' && reason.trim() === '') {
      setPendingReject(true)
      return
    }
    setSaving(true)
    setActionError(null)
    try {
      await stages.change(applicationId, to, to === 'rejected' ? reason.trim() : undefined)
      setDetail({ ...detail, current_stage: to })
      setPendingReject(false)
      setReason('')
      onChanged()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : '단계를 바꾸지 못했습니다')
    } finally {
      setSaving(false)
    }
  }

  async function addNote() {
    if (draft.trim() === '') return
    setSaving(true)
    setActionError(null)
    try {
      const created = await notesApi.create(applicationId, draft.trim())
      setNoteList([created, ...(noteList ?? [])])
      setDraft('')
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : '메모를 남기지 못했습니다')
    } finally {
      setSaving(false)
    }
  }

  return (
    <SidePanel variant="content" onClose={onClose} label="지원자 상세" closeLabel="상세 닫기">
      {error !== null && <p className={styles.state} role="alert">{error}</p>}
      {error === null && detail === null && <p className={styles.state}>불러오는 중…</p>}

      {detail && (
        <>
          <div className={styles.head}>
            <span className={styles.name}>{detail.name}</span>
            <span className={TONE_CLASS[stageTone(detail.current_stage)]}>
              {STAGE_LABEL[detail.current_stage]}
            </span>
          </div>

          {/* 앰버 점선은 **확정을 기다리는 제안**의 표기다 (05-design §1). 이 요약은
              담당자가 읽는 정보이지 승인할 대상이 아니라, 다른 섹션과 같은 정보 블록으로 둔다.
              출처는 제목("아르의 요약")이 말한다. */}
          {detail.ai_summary && (
            <div className={styles.sec}>
              <h2>아르의 요약</h2>
              <div className={styles.aibox}>
                <AiSummaryBody raw={detail.ai_summary} />
              </div>
            </div>
          )}

          <div className={styles.sec}>
            <h2>지원 정보</h2>
            <dl className={styles.list}>
              <dt>연락처</dt><dd>{detail.phone || '—'}</dd>
              <dt>이메일</dt><dd>{detail.email}</dd>
              <dt>학력</dt><dd>{detail.education ?? '—'}</dd>
              <dt>경력</dt><dd>{careerText(detail.career_years)}</dd>
              <dt>기술</dt><dd>{detail.skills?.join(' · ') || '—'}</dd>
              <dt>지원일</dt><dd>{fmtDate(detail.created_at)}</dd>
              <dt>평점</dt><dd>{detail.avg_score === null ? '—' : detail.avg_score.toFixed(1)}</dd>
            </dl>
          </div>

          <div className={styles.sec}>
            <h2>단계 변경</h2>
            <div className={styles.stageBtns}>
              {nextStages(detail.current_stage).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={s === 'rejected' ? styles.btnReject : styles.btnStage}
                  disabled={saving}
                  onClick={() => changeStage(s)}
                >
                  {STAGE_LABEL[s]}
                </button>
              ))}
            </div>

            {/* 불합격은 사유 없이 보낼 수 없다 (D8) */}
            {pendingReject && (
              <div className={styles.reasonBox}>
                <label htmlFor="reject-reason">불합격 사유</label>
                <textarea
                  id="reject-reason"
                  className={styles.input}
                  rows={2}
                  value={reason}
                  disabled={saving}
                  placeholder="사유를 적어야 불합격으로 옮길 수 있습니다"
                  onChange={(e) => setReason(e.target.value)}
                />
                <div className={styles.actions}>
                  <button
                    type="button"
                    className={styles.btnReject}
                    disabled={saving || reason.trim() === ''}
                    onClick={() => changeStage('rejected')}
                  >
                    {saving ? '변경 중…' : '불합격으로 옮기기'}
                  </button>
                </div>
              </div>
            )}

            {actionError && <p className={styles.err} role="alert">{actionError}</p>}
          </div>

          <MailSection applicationId={applicationId} />

          <div className={styles.sec}>
            <h2>메모</h2>
            <textarea
              className={styles.input}
              rows={3}
              aria-label="메모 입력"
              placeholder="이 지원자에 대한 메모를 남깁니다"
              value={draft}
              disabled={saving}
              onChange={(e) => setDraft(e.target.value)}
            />
            <div className={styles.actions}>
              <button
                type="button"
                className="btn btn-primary"
                disabled={saving || draft.trim() === ''}
                onClick={addNote}
              >
                등록
              </button>
            </div>

            {noteList?.map((n) => (
              <div key={n.id} className={styles.note}>
                <div className={styles.nmeta}>
                  <span className={styles.nauthor}>{n.author_name}</span>
                  <span className={styles.ndate}>{fmtDate(n.created_at)}</span>
                </div>
                <p className={styles.nbody}>{n.body}</p>
              </div>
            ))}
            {noteList?.length === 0 && <p className={styles.state}>아직 메모가 없습니다.</p>}
          </div>
        </>
      )}
    </SidePanel>
  )
}

/* ── 메일 (G4) ──────────────────────────────────────────────────────
   단계 변경이 자동으로 보내는 것 말고, 담당자가 직접 한 통 보내는 자리다.
   설정이 아니라 여기에 둔 이유: 보낼 대상이 정해진 순간이 이 화면이다.

   **수신 주소를 화면이 다루지 않는다.** 서버가 지원자 주소로 보낸다 — 잘못
   보낸 메일은 되돌릴 수 없어서, 주소를 고를 수 있게 만드는 것 자체가 위험이다. */

const MAIL_PRESETS: { stage: string; label: string }[] = [
  { stage: 'interview', label: '면접 안내' },
  { stage: 'applied', label: '접수 확인' },
  { stage: 'accepted', label: '최종 합격' },
  { stage: 'rejected', label: '불합격' },
]

const MAIL_STATUS_LABEL: Record<string, string> = {
  queued: '대기',
  sent: '발송됨',
  failed: '실패',
}

const ACTOR_LABEL: Record<string, string> = {
  human: '담당자',
  agent: '아르',
  system: '시스템',
}

function MailSection({ applicationId }: { applicationId: number }) {
  const [history, setHistory] = useState<EmailLogItem[] | null>(null)
  const [open, setOpen] = useState(false)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await mailApi.history(applicationId)
      setHistory(res.items)
    } catch {
      setHistory([])
    }
  }, [applicationId])

  useEffect(() => {
    void load()
  }, [load])

  /* 프리필은 서버가 만든다. 화면이 치환하면 미리보기와 실제 발송이 갈린다 —
     서명 규칙(주체별)이 두 곳에 복제되기 때문이다. */
  async function prefill(stage: string) {
    setErr(null)
    try {
      const res = await mailApi.preview(applicationId, stage)
      setSubject(res.subject)
      setBody(res.body)
      setOpen(true)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : '문구를 불러오지 못했습니다')
    }
  }

  async function send() {
    setBusy(true)
    try {
      await mailApi.send(applicationId, { subject, body })
      setConfirming(false)
      setOpen(false)
      setSubject('')
      setBody('')
      await load()
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : '발송하지 못했습니다')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={styles.sec}>
      <h2>메일</h2>

      {!open && (
        <div className={styles.mailPresets}>
          {MAIL_PRESETS.map((p) => (
            <button key={p.stage} type="button" className={styles.btnStage}
              onClick={() => prefill(p.stage)}>
              {p.label}
            </button>
          ))}
        </div>
      )}

      {open && (
        <>
          <input
            className={styles.input}
            aria-label="메일 제목"
            value={subject}
            disabled={busy}
            onChange={(e) => setSubject(e.target.value)}
          />
          <textarea
            className={styles.input}
            rows={10}
            aria-label="메일 본문"
            value={body}
            disabled={busy}
            onChange={(e) => setBody(e.target.value)}
          />
          <div className={styles.actions}>
            <button type="button" className="btn" disabled={busy} onClick={() => setOpen(false)}>
              취소
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || subject.trim() === '' || body.trim() === ''}
              onClick={() => setConfirming(true)}
            >
              보내기
            </button>
          </div>
        </>
      )}

      {err && <p className={styles.err} role="alert">{err}</p>}

      {/* 발송 전 마지막 확인 — 되돌릴 수 없으므로 나갈 전문을 그대로 다시 보여 준다 */}
      {confirming && (
        <div className={styles.mailScrim} role="presentation" onClick={() => setConfirming(false)}>
          <div
            className={styles.mailModal}
            role="dialog"
            aria-modal="true"
            aria-label="메일 발송 확인"
            onClick={(e) => e.stopPropagation()}
          >
            <p className={styles.mailWarn}>이 내용 그대로 지원자에게 발송됩니다. 되돌릴 수 없습니다.</p>
            <p className={styles.mailSubject}>{subject}</p>
            <pre className={styles.mailPreview}>{body}</pre>
            <div className={styles.actions}>
              <button type="button" className="btn" disabled={busy} onClick={() => setConfirming(false)}>
                취소
              </button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={send}>
                {busy ? '보내는 중…' : '발송'}
              </button>
            </div>
          </div>
        </div>
      )}

      {history?.map((m) => (
        <div key={m.id} className={styles.note}>
          <div className={styles.nmeta}>
            <span className={styles.nauthor}>
              {ACTOR_LABEL[m.actor_kind] ?? m.actor_kind}
              {m.actor_name ? ` · ${m.actor_name}` : ''}
            </span>
            <span className={styles.ndate}>
              {MAIL_STATUS_LABEL[m.status] ?? m.status} · {fmtDate(m.sent_at ?? m.created_at)}
            </span>
          </div>
          <p className={styles.nbody}>{m.subject ?? `${STAGE_LABEL[m.stage as Stage] ?? m.stage} 자동 안내`}</p>
        </div>
      ))}
      {history?.length === 0 && <p className={styles.state}>아직 보낸 메일이 없습니다.</p>}
    </div>
  )
}
