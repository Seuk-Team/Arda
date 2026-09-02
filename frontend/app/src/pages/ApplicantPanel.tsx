import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { applications, aptitude as aptitudeApi, files as filesApi, interviews as interviewsApi, mail as mailApi, notes as notesApi, stages } from '../api/endpoints'
import type { ApplicationDetail, AptitudeDetail, EmailLogItem, FileOut, InterviewSession, InterviewSessionDetail, Note, Stage } from '../api/types'
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
            <h2>첨부 파일</h2>
            {(detail.files?.length ?? 0) === 0
              ? <p className={styles.state}>첨부된 파일이 없습니다.</p>
              : <FileList files={detail.files!} />
            }
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

          <AptitudeSection applicationId={applicationId} />

          <InterviewSection applicationId={applicationId} />

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

const KIND_LABEL: Record<string, string> = { resume: '이력서', cover_letter: '자기소개서 파일' }

function fmtBytes(b: number) {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

function FileList({ files }: { files: FileOut[] }) {
  const [downloading, setDownloading] = useState<Set<number>>(new Set())
  const [err, setErr] = useState<string | null>(null)

  async function open(fileId: number) {
    setDownloading((prev) => new Set(prev).add(fileId))
    setErr(null)
    try {
      const res = await filesApi.presignDownload(fileId)
      /* fetch 로 내려받으면 CORS(PUT only)에 막힌다 — 링크 이동만 통과한다 */
      window.location.href = res.download_url
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : '파일을 열지 못했습니다')
    } finally {
      setDownloading((prev) => { const s = new Set(prev); s.delete(fileId); return s })
    }
  }

  return (
    <div className={styles.fileList}>
      {files.map((f) => (
        <button
          key={f.id}
          type="button"
          className={styles.fileItem}
          disabled={downloading.has(f.id)}
          onClick={() => open(f.id)}
        >
          <span className={styles.fileName}>{f.filename}</span>
          <span className={styles.fileMeta}>
            {KIND_LABEL[f.kind] ?? f.kind} · {fmtBytes(f.size_bytes)}
          </span>
        </button>
      ))}
      {err && <p className={styles.err} role="alert">{err}</p>}
    </div>
  )
}

/* ── AI 면접 ────────────────────────────────────────────────────────
   세션 목록 + 만들기 + 질문 입력(시작 전) + Q&A 열람(완료) */

const IV_STATUS_LABEL: Record<string, string> = {
  pending: '대기 중',
  in_progress: '진행 중',
  done: '완료',
  expired: '만료',
}

/* 사전 성향 설문 (ADR-0027) — 응답 통계·원문과 아르의 관찰 요약.
   요약은 응답 사실의 재서술뿐이다(유형 판정·점수 없음) — 판단 재료는
   통계·원문이고, 그래서 원문을 요약과 나란히 펼 수 있게 둔다.
   미응답은 불이익이 아니다 — 문구도 그렇게 쓴다. */
function AptitudeSection({ applicationId }: { applicationId: number }) {
  const [detail, setDetail] = useState<AptitudeDetail | null>(null)
  const [failed, setFailed] = useState(false)
  const [sending, setSending] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [showAnswers, setShowAnswers] = useState(false)
  const [copied, setCopied] = useState(false)

  const load = useCallback(async () => {
    try {
      setDetail(await aptitudeApi.detail(applicationId))
      setFailed(false)
    } catch {
      /* 구버전 서버·목 모드 — 섹션을 조용히 비운다. 패널의 다른 정보는 그대로다 */
      setFailed(true)
    }
  }, [applicationId])

  useEffect(() => { void load() }, [load])

  async function send() {
    setSending(true)
    setErr(null)
    try {
      await aptitudeApi.sendOne(applicationId)
      await load()
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : '설문을 보내지 못했습니다')
    } finally {
      setSending(false)
    }
  }

  async function copyUrl(url: string) {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* ignore */ }
  }

  if (failed || detail === null) return null

  return (
    <div className={styles.sec}>
      <h2>성향 설문</h2>

      {detail.status === 'none' && (
        <>
          <p className={styles.state}>발송 이력이 없습니다. 응답은 선택 사항 — 미응답은 불이익이 되지 않습니다.</p>
          <div className={styles.actions}>
            <button type="button" className={styles.btnStage} disabled={sending} onClick={send}>
              {sending ? '보내는 중…' : '설문 링크 보내기'}
            </button>
          </div>
        </>
      )}

      {detail.status === 'pending' && (
        <>
          <p className={styles.state}>
            응답 대기 중{detail.expires_at ? ` · ${fmtDate(detail.expires_at)}까지` : ''} — 미응답은 불이익이 되지 않습니다.
          </p>
          {detail.url && (
            <div className={styles.actions}>
              <button type="button" className={styles.btnStage} onClick={() => void copyUrl(detail.url as string)}>
                {copied ? '복사됨' : '링크 복사'}
              </button>
            </div>
          )}
        </>
      )}

      {detail.status === 'expired' && (
        <>
          <p className={styles.state}>링크가 만료되었습니다.</p>
          <div className={styles.actions}>
            <button type="button" className={styles.btnStage} disabled={sending} onClick={send}>
              {sending ? '보내는 중…' : '다시 보내기'}
            </button>
          </div>
        </>
      )}

      {detail.status === 'done' && (
        <>
          {detail.submitted_at && (
            <p className={styles.state}>{fmtDate(detail.submitted_at)} 제출</p>
          )}

          {detail.stats.length > 0 && (
            <dl className={styles.list}>
              {detail.stats.map((s) => [
                <dt key={`${s.category}-t`}>{s.label}</dt>,
                <dd key={`${s.category}-d`}>{s.mean.toFixed(1)} / 5 ({s.count}문항)</dd>,
              ])}
            </dl>
          )}

          {detail.ai_summary ? (
            <div className={styles.aibox}>
              <p className={styles.aibody}>{detail.ai_summary}</p>
            </div>
          ) : (
            <p className={styles.state}>요약이 아직 없습니다 — 통계·응답 원문으로 확인해 주세요.</p>
          )}

          <div className={styles.actions}>
            <button type="button" className={styles.btnStage} onClick={() => setShowAnswers((v) => !v)}>
              {showAnswers ? '응답 원문 접기' : `응답 원문 보기 (${detail.answers.length})`}
            </button>
          </div>
          {showAnswers && (
            <ul className={styles.ailist}>
              {detail.answers.map((a) => (
                <li key={a.question_key}>{a.question_text} — <strong>{a.value}</strong></li>
              ))}
            </ul>
          )}
        </>
      )}

      {err && <p className={styles.err} role="alert">{err}</p>}
    </div>
  )
}

function InterviewSection({ applicationId }: { applicationId: number }) {
  const [sessions, setSessions] = useState<InterviewSession[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [expandedDetail, setExpandedDetail] = useState<InterviewSessionDetail | null>(null)
  const [questions, setQuestions] = useState<Record<number, string>>({})
  const [savingQ, setSavingQ] = useState<Record<number, boolean>>({})

  const load = useCallback(async () => {
    try {
      const data = await interviewsApi.list(applicationId)
      setSessions(data)
    } catch {
      setSessions([])
    }
  }, [applicationId])

  useEffect(() => { void load() }, [load])

  async function create() {
    setCreating(true)
    setErr(null)
    try {
      await interviewsApi.create(applicationId)
      await load()
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'AI 면접을 만들지 못했습니다')
    } finally {
      setCreating(false)
    }
  }

  async function copyUrl(url: string) {
    try { await navigator.clipboard.writeText(url) } catch { /* ignore */ }
  }

  async function saveQuestions(sessionId: number) {
    const text = questions[sessionId] ?? ''
    const qs = text.split('\n').map((s) => s.trim()).filter(Boolean)
    setSavingQ((prev) => ({ ...prev, [sessionId]: true }))
    setErr(null)
    try {
      await interviewsApi.setQuestions(sessionId, qs)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : '질문을 저장하지 못했습니다')
    } finally {
      setSavingQ((prev) => ({ ...prev, [sessionId]: false }))
    }
  }

  async function toggleExpand(session: InterviewSession) {
    if (expandedId === session.id) { setExpandedId(null); setExpandedDetail(null); return }
    setExpandedId(session.id)
    setExpandedDetail(null)
    try {
      const detail = await interviewsApi.detail(session.id)
      setExpandedDetail(detail)
    } catch { /* ignore */ }
  }

  return (
    <div className={styles.sec}>
      <h2>AI 면접</h2>
      <div className={styles.actions}>
        <button type="button" className={styles.btnStage} disabled={creating} onClick={create}>
          {creating ? '만드는 중…' : 'AI 면접 만들기'}
        </button>
      </div>

      {err && <p className={styles.err} role="alert">{err}</p>}

      {sessions?.map((s) => {
        const isDone = s.status === 'done'
        const isExpanded = expandedId === s.id
        const notStarted = s.started_at === null && s.status === 'pending'
        return (
          <div key={s.id} className={styles.ivRow}>
            <div className={styles.ivHead}>
              <span className={`${styles.ivStatus} ${isDone ? styles.ivStatusDone : ''}`}>
                {IV_STATUS_LABEL[s.status] ?? s.status}
              </span>
              <button type="button" className={styles.ivCopy} onClick={() => copyUrl(s.url)}>
                링크 복사
              </button>
              {isDone && (
                <button type="button" className={styles.ivExpand} onClick={() => toggleExpand(s)}>
                  {isExpanded ? '닫기' : 'Q&A 보기'}
                </button>
              )}
            </div>

            {notStarted && (
              <>
                <textarea
                  className={styles.input}
                  rows={3}
                  placeholder={'질문을 한 줄에 하나씩 입력하세요\n(비워두면 기본 질문으로 진행됩니다)'}
                  value={questions[s.id] ?? ''}
                  disabled={savingQ[s.id]}
                  onChange={(e) => setQuestions((prev) => ({ ...prev, [s.id]: e.target.value }))}
                />
                <div className={styles.actions}>
                  <button
                    type="button"
                    className="btn"
                    disabled={savingQ[s.id]}
                    onClick={() => saveQuestions(s.id)}
                  >
                    {savingQ[s.id] ? '저장 중…' : '질문 저장'}
                  </button>
                </div>
              </>
            )}

            {isExpanded && (
              <div className={styles.ivTurns}>
                {expandedDetail === null && <p className={styles.state}>불러오는 중…</p>}
                {expandedDetail?.turns.length === 0 && (
                  <p className={`${styles.state} ${styles.ivEmpty}`}>답변이 없습니다.</p>
                )}
                {expandedDetail?.turns.map((t) => (
                  <div key={t.seq}>
                    <p className={styles.ivQ}>Q{t.seq}. {t.question}</p>
                    <p className={styles.ivA}>{t.transcript ?? '(답변 없음)'}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
      {sessions?.length === 0 && <p className={styles.state}>AI 면접이 없습니다.</p>}
    </div>
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
