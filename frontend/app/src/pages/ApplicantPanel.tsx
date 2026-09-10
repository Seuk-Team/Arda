import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'
import { applications, aptitude as aptitudeApi, evaluations, files as filesApi, interviews as interviewsApi, mail as mailApi, notes as notesApi, stages } from '../api/endpoints'
import type { ApplicationDetail, AptitudeDetail, EmailLogItem, FileOut, InterviewSession, InterviewSessionDetail, Note, Stage, StageHistoryItem } from '../api/types'
import SidePanel from '../components/SidePanel'
import IntegrityBadge from '../components/IntegrityBadge'
import { STAGE_LABEL, careerText, fmtDate, fmtDateShort } from '../lib/stage'
import styles from './ApplicantPanel.module.css'

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
  } catch { /* JSON 아니면 원문 표시 */ }
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
          <ul className={styles.ailist}>{parsed.fit!.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </div>
      )}
      {(parsed.concerns?.length ?? 0) > 0 && (
        <div>
          <p className={styles.ailabel}>확인 필요</p>
          <ul className={styles.ailist}>{parsed.concerns!.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </div>
      )}
    </div>
  )
}

const ORDER: Stage[] = ['applied', 'screening', 'interview', 'accepted']

function nextStages(from: Stage): Stage[] {
  if (from === 'rejected') return [...ORDER]
  const i = ORDER.indexOf(from)
  const out: Stage[] = []
  if (i > 0) out.push(ORDER[i - 1])
  if (i >= 0 && i + 1 < ORDER.length) out.push(ORDER[i + 1])
  out.push('rejected')
  return out
}

const PROGRESS_STAGES: Stage[] = ['applied', 'screening', 'interview', 'accepted']
const PROGRESS_LABEL: Record<string, string> = { applied: '접수', screening: '서류', interview: '면접', accepted: '합격' }


/* ── 탭 ──────────────────────────────────────────────────
   판단 재료(개요) · 도구(면접·메모) · 로그(이력) 를 가른다.
   예전에는 열 개 섹션이 세로 한 줄에 같은 무게로 쌓여 있었다. */
type TabKey = 'overview' | 'interview' | 'notes' | 'history'
type AptitudeStatus = AptitudeDetail['status']

const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: '개요' },
  { key: 'interview', label: '면접' },
  { key: 'notes', label: '메모' },
  { key: 'history', label: '이력' },
]

/* 헤더 한 줄 요약 — 이름 아래에서 "누구인지" 를 한 번에 말한다.
   없는 값은 빼고 잇는다. 줄표만 남은 자리를 만들지 않는다. */
function headLine(d: ApplicationDetail): string {
  const parts: string[] = []
  if (d.skills?.length) parts.push(d.skills[0])
  if (d.career_years !== null) parts.push(careerText(d.career_years))
  if (d.education) parts.push(d.education)
  parts.push(`${fmtDateShort(d.created_at)} 지원`)
  return parts.join(' · ')
}

/* 진행 바. **읽는 것이다** — role="img" 로 두고 클릭을 받지 않는다.
   패널에서 제일 큰 요소를 누를 수 있게 하면, 메일까지 나가는 동작이
   스크롤하다 빗나간 손가락에 걸린다. 동작은 옆의 버튼 하나뿐이다. */
function StageTrack({
  current, editing = false, target = null, canPick, onPick,
}: {
  current: Stage
  /* 고르는 상태인가. 평소에는 읽는 것이라 클릭을 받지 않는다 */
  editing?: boolean
  target?: Stage | null
  canPick?: (s: Stage) => boolean
  onPick?: (s: Stage) => void
}) {
  const rejected = current === 'rejected'
  const curIdx = PROGRESS_STAGES.indexOf(current)
  const label = rejected
    ? '불합격'
    : `진행 ${curIdx + 1} / ${PROGRESS_STAGES.length} · ${PROGRESS_LABEL[current] ?? current}`

  return (
    <div className={styles.track} role={editing ? undefined : 'img'} aria-label={editing ? undefined : label}>
      {PROGRESS_STAGES.map((s, i) => {
        const cls = `${styles.trackStep} ${i < curIdx ? styles.trackDone : ''} ${i === curIdx ? (s === 'accepted' ? styles.trackAccepted : styles.trackNow) : ''}`

        if (!editing) return <div key={s} className={cls}><b>{PROGRESS_LABEL[s]}</b></div>

        /* 갈 수 있는 곳은 기존 규칙(nextStages) 그대로다 — 여기서 넓히지 않는다.
           못 가는 칸은 지우지 않고 흐리게 둔다: 사라지면 칸이 밀린다. */
        const pickable = canPick?.(s) ?? false
        return (
          <button
            key={s}
            type="button"
            role="radio"
            data-stage={s}
            aria-checked={target === s}
            className={`${cls} ${styles.trackPick} ${target === s ? styles.trackSel : ''}`}
            disabled={!pickable}
            onClick={() => onPick?.(s)}
          >
            <b>{PROGRESS_LABEL[s]}</b>
          </button>
        )
      })}
      {/* 불합격은 램프 밖이다 — 진행의 끝이 아니라 종료라서 칸을 따로 세운다.
          고르는 중에는 StageChanger 의 버튼이 이 자리를 대신한다 */}
      {rejected && !editing && (
        <div className={`${styles.trackStep} ${styles.trackRejected}`}>
          <b>불합격</b>
        </div>
      )}
    </div>
  )
}

/* 단계 변경 — 뜨는 메뉴가 아니라 **진행 바가 잠깐 고를 수 있는 상태**가 된다.
   (2026-09-10, 시안 C)

   ## 왜 팝오버가 아닌가

   보는 자리와 고르는 자리가 같아야 "지금 면접이니 다음은 합격" 이 한 번에
   읽힌다. 메뉴를 띄우면 진행 바를 보고 → 메뉴를 열고 → 머릿속에서 다시
   맞춰야 한다. 500px 패널이 1275px 아래에서 오버레이가 되는 것도 있어서,
   그 안에 팝오버를 얹으면 위치·z-index·바깥 클릭을 전부 따로 맞춰야 한다.

   ## 왜 평소에는 안 눌리는가

   진행 바는 패널에서 제일 큰 요소다. 늘 눌리면 스크롤하다·탭 누르려다
   빗나간 손가락에 **메일까지 나가는 동작**이 걸린다. 그래서 [단계 변경] 을
   눌러야 잠깐 고를 수 있는 상태가 된다 — 크면서도 안전하다.

   ## 왜 불합격은 칸이 아닌가

   칸으로 넣으면 4칸 → 5칸이 되면서 방금 보던 칸이 눈앞에서 밀린다. 되돌리기
   어려운 동작에서 제일 하면 안 되는 일이다. 불합격은 진행의 끝이 아니라
   **종료**라 램프 밖에 두는 것이 의미상으로도 맞다(StageTrack 도 그렇게 그린다). */
function StageChanger({
  current, busy, error, onCommit,
}: {
  current: Stage
  busy: boolean
  error: string | null
  onCommit: (to: Stage, reason: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [target, setTarget] = useState<Stage | null>(null)
  const [reason, setReason] = useState('')
  const rowRef = useRef<HTMLDivElement>(null)

  /* 어디로 갈 수 있는지는 기존 규칙 그대로다 — 이 화면이 새로 넓히지 않는다 */
  const allowed = nextStages(current)
  const canPick = (s: Stage) => allowed.includes(s)

  const stop = useCallback(() => {
    setEditing(false)
    setTarget(null)
    setReason('')
  }, [])

  /* 지원자가 바뀌거나 단계가 옮겨지면 고르던 것을 버린다 */
  useEffect(() => { stop() }, [current, stop])

  /* Esc 는 **고르기만** 취소한다. SidePanel 도 Esc 로 패널을 닫는데(버블 단계
     document 리스너), 그대로 두면 단계를 고르다 Esc 를 눌렀을 때 패널째 닫힌다.
     캡처 단계에서 먼저 잡아 막는다 — 안쪽 상태가 있으면 그것부터 물러난다. */
  useEffect(() => {
    if (!editing) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      stop()
    }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [editing, stop])

  /* 화살표로 고를 수 있는 칸 사이를 옮긴다 (radiogroup 의 관례) */
  function onArrow(e: React.KeyboardEvent) {
    if (!editing) return
    const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1
      : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0
    if (step === 0) return
    e.preventDefault()
    const i = target === null ? -1 : allowed.indexOf(target)
    const next = allowed[(i + step + allowed.length) % allowed.length]
    setTarget(next)
    rowRef.current?.querySelector<HTMLElement>(`[data-stage="${next}"]`)?.focus()
  }

  const rejecting = target === 'rejected'
  const ready = target !== null && (!rejecting || reason.trim() !== '')

  return (
    <>
      <div
        className={styles.stagerow}
        ref={rowRef}
        role={editing ? 'radiogroup' : undefined}
        aria-label={editing ? '옮길 단계 고르기' : undefined}
        onKeyDown={onArrow}
      >
        <StageTrack
          current={current}
          editing={editing}
          target={target}
          canPick={canPick}
          onPick={setTarget}
        />

        {/* 버튼 자리는 **가장 넓은 상태로 미리 잡아 둔다**(.stageActions min-width).
            안 그러면 고르기로 들어갈 때 불합격 버튼이 자리를 뺏어 진행 바가
            줄어들고, 방금 보던 칸이 눈앞에서 밀린다 — 되돌리기 어려운 동작에서
            제일 하면 안 되는 일이다. */}
        <span className={styles.stageActions}>
          {editing && canPick('rejected') && (
            <button
              type="button"
              role="radio"
              data-stage="rejected"
              aria-checked={rejecting}
              className={`${styles.rejBtn} ${rejecting ? styles.rejOn : ''}`}
              disabled={busy}
              onClick={() => setTarget('rejected')}
            >
              불합격
            </button>
          )}

          {!editing && (
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => setEditing(true)}>
              단계 변경
            </button>
          )}
        </span>
      </div>

      {editing && (
        <div className={`${styles.confirmBar} ${target === null ? '' : rejecting ? styles.confirmDanger : styles.confirmArmed}`}>
          <div className={styles.confirmTop}>
            {target === null ? (
              <span className={styles.confirmHint}>옮길 칸을 누르세요</span>
            ) : (
              <span className={styles.confirmFlow}>
                <span className={`${styles.badge} ${styles.badgeNow}`}>{STAGE_LABEL[current] ?? current}</span>
                <span aria-hidden="true">→</span>
                <span className={`${styles.badge} ${target === 'accepted' ? styles.badgeOk : target === 'rejected' ? styles.badgeDanger : ''}`}>
                  {STAGE_LABEL[target] ?? target}
                </span>
              </span>
            )}
            {/* 취소는 여기 있다 — 진행 바 줄에 두면 불합격 바로 옆이라
                취소하려다 불합격을 누른다. 줄의 역할도 이렇게 갈린다:
                위는 "어디로", 아래는 "확정할까 말까" */}
            <span className={styles.confirmActions}>
              <button type="button" className="btn btn-secondary" disabled={busy} onClick={stop}>취소</button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || !ready}
                onClick={() => { if (target !== null) onCommit(target, reason.trim()) }}
              >
                {busy ? '옮기는 중…' : '확정'}
              </button>
            </span>
          </div>

          {/* 지금 서버는 단계 변경과 메일이 별개 호출이라 "나갑니다" 는 사실이
              아니다. 이어서 보낼 수 있다고만 적는다 (연락처의 메일 보내기). */}
          {target !== null && MAIL_AFTER[target] !== undefined && (
            <p className={styles.confirmMail}>
              <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M4 6h16v12H4z" /><path d="M4 7l8 6 8-6" />
              </svg>
              {MAIL_AFTER[target]}
            </p>
          )}

          {rejecting && (
            <textarea
              className={styles.confirmReason}
              rows={2}
              aria-label="불합격 사유"
              placeholder="불합격 사유 — 적어야 옮길 수 있습니다"
              value={reason}
              disabled={busy}
              onChange={(e) => setReason(e.target.value)}
            />
          )}

          {error && <p className={styles.err} role="alert">{error}</p>}
        </div>
      )}
    </>
  )
}

/* 옮긴 뒤 이어서 보낼 수 있는 메일. 단계 변경이 메일을 보내지는 않는다 */
const MAIL_AFTER: Partial<Record<Stage, string>> = {
  accepted: '합격 안내 메일을 이어서 보낼 수 있습니다',
  rejected: '불합격 안내 메일을 이어서 보낼 수 있습니다',
}

/* ── 개요 탭 ────────────────────────────────────────────
   평가 → 아르 요약 → 지원 정보 → 연락처 → 첨부 → 인적성 검사.
   판단에 쓰는 것만 모았다. */
function OverviewTab({
  detail, applicationId, onScored, onMailSent,
}: {
  detail: ApplicationDetail
  applicationId: number
  onScored: () => void
  onMailSent: () => void
}) {
  return (
    <>
      <EvalRow detail={detail} applicationId={applicationId} onScored={onScored} />

      <hr className={styles.rule} />

      {detail.ai_summary && (
        <>
          <div className={styles.secRow2}>
            <p className={styles.secLabel}>아르의 요약</p>
            <button type="button" className={styles.linkBtn}>다시 생성</button>
          </div>
          {/* 테두리를 두르지 않는다 — 카드 안에 또 박스가 있으면 선이 겹친다.
              구분선만으로 충분하다 */}
          <AiSummaryBody raw={detail.ai_summary} />
          <hr className={styles.rule} />
        </>
      )}

      <p className={styles.secLabel}>지원 정보</p>
      <div className={styles.grid3}>
        <div className={styles.cell}>
          <dt>학력</dt><dd>{detail.education ?? '기재 없음'}</dd>
        </div>
        <div className={styles.cell}>
          <dt>경력</dt><dd className={styles.cellNum}>{careerText(detail.career_years)}</dd>
        </div>
        <div className={styles.cell}>
          {/* TODO 서버가 ApplicationDetail 에 posting_title 을 주면 제목을 쓴다.
              지금은 job_posting_id 만 온다(다른 응답 타입에는 이미 있는 필드다). */}
          <dt>공고</dt><dd className={styles.cellNum}>#{detail.job_posting_id}</dd>
        </div>
        {(detail.skills?.length ?? 0) > 0 && (
          <div className={`${styles.cell} ${styles.cellWide}`}>
            <dt>기술</dt>
            {/* TODO 공고 요건과 일치하는 기술만 accent 로 칠하는 설계인데,
                JobPosting 에 요건/기술 필드가 없다. 올 때까지 전부 중립이다. */}
            <dd className={styles.chips}>
              {detail.skills!.map((t) => <span key={t} className={styles.chip}>{t}</span>)}
            </dd>
          </div>
        )}
      </div>

      {/* 전화와 이메일은 원래 한 덩어리다 — 갈라 두면 둘 다 어색해진다 */}
      <ContactBlock detail={detail} applicationId={applicationId} onSent={onMailSent} />

      <hr className={styles.rule} />

      <FilesSection detail={detail} applicationId={applicationId} />

      <AptitudeSection applicationId={applicationId} />
    </>
  )
}

/* 평가 — 없으면 줄표 대신 행동을 둔다 */
function EvalRow({
  detail, applicationId, onScored,
}: {
  detail: ApplicationDetail
  applicationId: number
  onScored: () => void
}) {
  const [open, setOpen] = useState(false)
  const [score, setScore] = useState(0)
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit() {
    if (score < 1) return
    setBusy(true); setErr(null)
    try {
      await evaluations.create(applicationId, score, comment.trim() || undefined)
      setOpen(false); setScore(0); setComment('')
      onScored()
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : '평가를 남기지 못했습니다')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className={styles.evalRow}>
        {detail.avg_score === null ? (
          <span className={styles.state}>아직 평가 없음</span>
        ) : (
          <span className={styles.stars}>
            <Stars value={detail.avg_score} />
            <span className={styles.score}>
              {detail.avg_score.toFixed(1)}
              <small> / 5.0 · 평가 {detail.eval_count ?? 0}명</small>
            </span>
          </span>
        )}
        <button type="button" className={styles.btnSm} onClick={() => setOpen(!open)}>
          {open ? '닫기' : '평가하기'}
        </button>
      </div>

      {open && (
        <div className={styles.reasonBox}>
          <label htmlFor="eval-score">점수</label>
          <div className={styles.actions} style={{ justifyContent: 'flex-start' }}>
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                id={n === 1 ? 'eval-score' : undefined}
                className={styles.btnSm}
                aria-pressed={score === n}
                disabled={busy}
                onClick={() => setScore(n)}
              >
                {n}
              </button>
            ))}
          </div>
          <textarea
            className={styles.input}
            rows={2}
            aria-label="평가 의견"
            placeholder="의견 (선택)"
            value={comment}
            disabled={busy}
            onChange={(e) => setComment(e.target.value)}
          />
          <div className={styles.actions}>
            <button type="button" className={styles.btnStage} disabled={busy || score < 1} onClick={() => void submit()}>
              {busy ? '남기는 중…' : '등록'}
            </button>
          </div>
          {err && <p className={styles.err} role="alert">{err}</p>}
        </div>
      )}
    </>
  )
}

function Stars({ value }: { value: number }) {
  return (
    <span aria-hidden="true" className={styles.stars}>
      {[1, 2, 3, 4, 5].map((n) => (
        <svg key={n} viewBox="0 0 24 24" fill={n <= Math.round(value) ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth={n <= Math.round(value) ? 0 : 1.6} opacity={n <= Math.round(value) ? 1 : .35}>
          <path d="M12 2l3 6.6 7 .8-5.2 4.8 1.4 7L12 17.8 5.8 21.2l1.4-7L2 9.4l7-.8z" />
        </svg>
      ))}
    </span>
  )
}

/* 연락처 + 메일 — 단계와 무관한 메일은 주소가 있는 자리에서 보낸다.
   단계 메일은 단계 변경 드롭다운이 맡는다(둘의 역할이 갈린다). */
function ContactBlock({
  detail, applicationId, onSent,
}: {
  detail: ApplicationDetail
  applicationId: number
  onSent: () => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <div className={styles.contact}>
        <span className={styles.clab}>
          <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M22 16.9v3a2 2 0 01-2.2 2 19.8 19.8 0 01-8.6-3.1 19.5 19.5 0 01-6-6A19.8 19.8 0 012.1 4.2 2 2 0 014.1 2h3a2 2 0 012 1.7c.1.9.4 1.8.7 2.7a2 2 0 01-.5 2.1L8.1 9.9a16 16 0 006 6l1.4-1.2a2 2 0 012.1-.5c.9.3 1.8.6 2.7.7a2 2 0 011.7 2z" />
          </svg>
          전화
        </span>
        <span className={styles.cval}>{detail.phone || '기재 없음'}</span>

        <span className={styles.clab}>
          <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M4 6h16v12H4z" /><path d="M4 7l8 6 8-6" />
          </svg>
          이메일
        </span>
        <span className={styles.cval}>
          {detail.email}
          <button type="button" className={styles.btnSm} aria-expanded={open} onClick={() => setOpen(!open)}>
            메일 보내기
          </button>
        </span>
      </div>

      {open && (
        <MailSection
          applicationId={applicationId}
          onSent={() => { onSent(); setOpen(false) }}
          onCancel={() => setOpen(false)}
        />
      )}
    </>
  )
}

/* 첨부 + 무결성. 예전에는 '제출물 무결성' 이 독립 섹션이라 설명 세 줄이
   매번 자리를 차지했다 — 배지는 라벨 옆으로, 설명은 툴팁으로 옮겼다. */
function FilesSection({ detail, applicationId }: { detail: ApplicationDetail; applicationId: number }) {
  const files = detail.files ?? []
  return (
    <>
      <div className={styles.secRow2}>
        <p className={styles.secLabel}>
          첨부 파일
          <IntegrityBadge key={applicationId} applicationId={applicationId} compact />
        </p>
      </div>
      {files.length === 0
        ? <p className={styles.state}>첨부 파일 없음</p>
        : <FileList files={files} />}
    </>
  )
}

/* ── 메모 탭 ───────────────────────────────────────────── */
function NotesTab({
  notes, draft, saving, error, onDraft, onSubmit,
}: {
  notes: Note[] | null
  draft: string
  saving: boolean
  error: string | null
  onDraft: (v: string) => void
  onSubmit: () => void
}) {
  return (
    <>
      {notes?.map((n) => (
        <div key={n.id} className={styles.note}>
          <div className={styles.nmeta}>
            <span className={styles.nauthor}>{n.author_name}</span>
            <span className={styles.ndate}>{fmtDate(n.created_at)}</span>
          </div>
          <p className={styles.nbody}>{n.body}</p>
        </div>
      ))}
      {notes?.length === 0 && <p className={styles.state}>아직 메모가 없습니다.</p>}
      <textarea
        className={styles.input}
        rows={3}
        aria-label="메모 입력"
        placeholder="메모 남기기"
        value={draft}
        disabled={saving}
        onChange={(e) => onDraft(e.target.value)}
      />
      <div className={styles.actions}>
        <button type="button" className="btn btn-primary" disabled={saving || draft.trim() === ''} onClick={onSubmit}>
          등록
        </button>
      </div>
      {error && <p className={styles.err} role="alert">{error}</p>}
    </>
  )
}

/* ── 이력 탭 ───────────────────────────────────────────
   단계 이력과 메일·시스템 발송 이력을 한 자리에 모았다.
   둘 다 "무슨 일이 있었나" 라서 따로 둘 이유가 없었다. */
function HistoryTab({
  history, applicationId, refreshKey, onFailed,
}: {
  history: StageHistoryItem[]
  applicationId: number
  refreshKey: number
  onFailed: (n: number) => void
}) {
  return (
    <>
      <p className={styles.secLabel}>단계 이력</p>
      {history.length === 0
        ? <p className={styles.state}>이력이 없습니다.</p>
        : history.map((h) => (
          <div key={h.id} className={styles.hrow}>
            <span className={styles.hdate}>{fmtDateShort(h.created_at)}</span>
            <span className={styles.hbody}>
              {h.from_stage ? (STAGE_LABEL[h.from_stage as Stage] ?? h.from_stage) : '접수'}
              {' → '}
              {STAGE_LABEL[h.to_stage as Stage] ?? h.to_stage}
            </span>
          </div>
        ))}

      <hr className={styles.rule} />

      <MailHistorySection applicationId={applicationId} refreshKey={refreshKey} onFailed={onFailed} />
    </>
  )
}

interface Props {
  applicationId: number
  onClose: () => void
  onChanged: () => void
}

export default function ApplicantPanel({ applicationId, onClose, onChanged }: Props) {
  const [detail, setDetail] = useState<ApplicationDetail | null>(null)
  const [noteList, setNoteList] = useState<Note[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)


  const [mailHistoryKey, setMailHistoryKey] = useState(0)

  /* 탭은 URL 이 아니라 로컬 상태다 — Settings 는 ?tab= 을 쓰지만 그건 페이지고,
     이건 패널이라 지원자를 바꾸면 개요부터 다시 보는 편이 맞다. */
  const [tab, setTab] = useState<TabKey>('overview')

  /* 탭 라벨 배지 — 안 열어봐도 조치가 필요한 것을 알 수 있어야 한다.
     각 상태는 해당 탭의 자식이 들고 있어서 여기로 올려 받는다. */
  const [ivStatus, setIvStatus] = useState<string | null>(null)
  const [mailFailed, setMailFailed] = useState(0)

  useEffect(() => {
    const ac = new AbortController()
    setDetail(null)
    setNoteList(null)
    setError(null)
    setActionError(null)
    setDraft('')
    setTab('overview')
    setIvStatus(null)
    setMailFailed(0)

    Promise.all([
      applications.detail(applicationId, ac.signal),
      notesApi.list(applicationId, ac.signal),
    ])
      .then(([d, n]) => { setDetail(d); setNoteList(n) })
      .catch((err) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.code === 'UNAUTHORIZED') return
        setError(err instanceof ApiError ? err.message : '지원자를 불러오지 못했습니다')
      })
    return () => ac.abort()
  }, [applicationId])

  /* 평가를 남긴 뒤 평점·평가 수를 다시 받는다 */
  const reloadDetail = useCallback(async () => {
    try { setDetail(await applications.detail(applicationId)) }
    catch { /* 실패해도 화면은 그대로 둔다 — 다음에 열 때 갱신된다 */ }
  }, [applicationId])

  /* 사유는 StageChanger 가 확정 전에 받아 온다 — 여기서 다시 묻지 않는다 */
  async function changeStage(to: Stage, why: string) {
    if (!detail) return
    setSaving(true)
    setActionError(null)
    try {
      await stages.change(applicationId, to, to === 'rejected' ? why : undefined)
      setDetail({ ...detail, current_stage: to })
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

  function tabBadge(key: TabKey) {
    if (key === 'interview') {
      /* 완료면 배지가 없다 — 조치가 끝난 것은 알릴 이유가 없다 */
      if (ivStatus === null || ivStatus === 'done') return null
      const tone = ivStatus === 'expired' ? styles.badgeDanger : styles.badgeWarn
      return <span className={`${styles.badge} ${styles.tabBadge} ${tone}`}>{IV_STATUS_LABEL[ivStatus] ?? ivStatus}</span>
    }
    if (key === 'notes') {
      const n = noteList?.length ?? 0
      return n === 0 ? null : <span className={`${styles.badge} ${styles.tabBadge}`}>{n}</span>
    }
    if (key === 'history') {
      return mailFailed === 0
        ? null
        : <span className={`${styles.badge} ${styles.tabBadge} ${styles.badgeDanger}`}>실패 {mailFailed}</span>
    }
    return null
  }

  return (
    <SidePanel variant="content" wide onClose={onClose} label="지원자 상세" closeLabel="상세 닫기">
      {error !== null && <p className={styles.state} role="alert">{error}</p>}
      {error === null && detail === null && <p className={styles.state}>불러오는 중…</p>}

      {detail && (
        <>
          <div className={styles.mobileNav}>
            <button type="button" className={styles.backBtn} onClick={onClose} aria-label="닫기">
              <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M15 18l-6-6 6-6" />
              </svg>
              {detail.name}
            </button>
          </div>

          {/* 고정 헤더 — 스크롤해도 누구를 보고 있는지, 어느 단계인지가 안 사라진다 */}
          <div className={styles.phead}>
            <div className={styles.ptop}>
              <span className={styles.avatar} aria-hidden="true">{detail.name.charAt(0)}</span>
              <div className={styles.pwho}>
                <div className={styles.pnameRow}>
                  <span className={styles.pname}>{detail.name}</span>
                  <span className={`${styles.stageBadge} ${styles[`tone_${detail.current_stage}`] ?? ''}`}>
                    {STAGE_LABEL[detail.current_stage] ?? detail.current_stage}
                  </span>
                </div>
                <p className={styles.pmeta}>{headLine(detail)}</p>
              </div>
            </div>

            <StageChanger
              current={detail.current_stage}
              busy={saving}
              error={actionError}
              onCommit={(to, why) => void changeStage(to, why)}
            />
            <div className={styles.tabs} role="tablist" aria-label="지원자 상세 탭">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  role="tab"
                  id={`aptab-${t.key}`}
                  aria-selected={tab === t.key}
                  aria-controls={`appanel-${t.key}`}
                  className={`${styles.tab} ${tab === t.key ? styles.tabOn : ''}`}
                  onClick={() => setTab(t.key)}
                >
                  {t.label}
                  {tabBadge(t.key)}
                </button>
              ))}
            </div>
          </div>

          <div
            className={styles.tabPanel}
            role="tabpanel"
            id={`appanel-${tab}`}
            aria-labelledby={`aptab-${tab}`}
          >
            {tab === 'overview' && (
              <OverviewTab
                detail={detail}
                applicationId={applicationId}
                onScored={reloadDetail}
                onMailSent={() => setMailHistoryKey((k) => k + 1)}
              />
            )}

            {tab === 'interview' && (
              ['interview', 'accepted', 'rejected'].includes(detail.current_stage)
                ? <InterviewSection applicationId={applicationId} onStatus={setIvStatus} />
                : (
                  <p className={styles.gate}>
                    <strong>아직 면접 단계가 아닙니다</strong>
                    단계를 면접으로 옮기면 여기서 AI 면접을 만들 수 있습니다.
                  </p>
                )
            )}

            {tab === 'notes' && (
              <NotesTab
                notes={noteList}
                draft={draft}
                saving={saving}
                error={actionError}
                onDraft={setDraft}
                onSubmit={addNote}
              />
            )}

            {tab === 'history' && (
              <HistoryTab
                history={detail.stage_history ?? []}
                applicationId={applicationId}
                refreshKey={mailHistoryKey}
                onFailed={setMailFailed}
              />
            )}
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
      /* 새 탭으로 연다 — 현재 탭을 떠나면 목록 스크롤·열린 패널·필터가 날아간다.
         noopener 는 보안이기도 하다: 지원자가 올린 파일 URL 은 믿을 수 없는 출처라
         새 탭이 window.opener 로 이 페이지를 건드릴 수 있으면 안 된다. */
      window.open(res.download_url, '_blank', 'noopener,noreferrer')
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : '파일을 열지 못했습니다')
    } finally {
      setDownloading((prev) => { const s = new Set(prev); s.delete(fileId); return s })
    }
  }

  return (
    <>
      <div className={styles.files}>
        {files.map((f) => (
          <button
            key={f.id}
            type="button"
            className={styles.fileCard}
            disabled={downloading.has(f.id)}
            onClick={() => open(f.id)}
            title={f.filename}
          >
            <svg className={styles.fileIcon} viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><path d="M14 2v6h6" />
            </svg>
            <span className={styles.fmain}>
              <span className={styles.fnameNew}>{f.filename}</span>
              <span className={styles.fmetaNew}>{KIND_LABEL[f.kind] ?? f.kind} · {fmtBytes(f.size_bytes)}</span>
            </span>
            {/* 새 탭에서 열린다는 표시 */}
            <svg className={styles.fileIcon} viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7">
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" /><path d="M15 3h6v6" /><path d="M10 14L21 3" />
            </svg>
          </button>
        ))}
      </div>
      {err && <p className={styles.err} role="alert">{err}</p>}
    </>
  )
}

/* ── AI 면접 ── */

const IV_STATUS_LABEL: Record<string, string> = {
  pending: '대기 중', in_progress: '진행 중', done: '완료', expired: '만료',
}

/* 사전 성향 설문 (ADR-0027) — 응답 통계·원문과 아르의 관찰 요약.
   요약은 응답 사실의 재서술뿐이다(유형 판정·점수 없음) — 판단 재료는
   통계·원문이고, 그래서 원문을 요약과 나란히 펼 수 있게 둔다.
   미응답은 불이익이 아니다 — 문구도 그렇게 쓴다. */
function AptitudeSection({ applicationId, onStatus }: { applicationId: number; onStatus?: (s: AptitudeStatus | null) => void }) {

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
      setErr(e instanceof ApiError ? e.message : '인적성 검사 링크를 보내지 못했습니다')
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

  useEffect(() => { onStatus?.(detail?.status ?? null) }, [detail, onStatus])

  if (failed || detail === null) return null

  /* 배지는 **실제 제출 여부만** 본다 — 단계와 무관하다. 지원자가 앱에서
     제출을 마쳐야 '응답 완료' 고, 링크를 받았든 열어만 봤든 그 전은 전부
     '미응답' 이다 (ADR-0027, 지원자는 앱 인적성 탭에서 응답한다). */
  const done = detail.status === 'done'

  return (
    <details className={`${styles.sec} ${styles.fold}`}>
      <summary className={styles.foldSummary}>
        <span className={styles.secLabel}>인적성 검사</span>
        <span className={`${styles.badge} ${done ? styles.badgeOk : ''}`}>
          {done ? '응답 완료' : '미응답'}
        </span>
      </summary>

      {detail.status === 'none' && (
        <>
          <p className={styles.state}>발송 이력이 없습니다. 응답은 선택 사항 — 미응답은 불이익이 되지 않습니다.</p>
          <div className={styles.actions}>
            <button type="button" className={styles.btnStage} disabled={sending} onClick={send}>
              {sending ? '보내는 중…' : '검사 링크 보내기'}
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
    </details>
  )
}

function InterviewSection({ applicationId, onStatus }: { applicationId: number; onStatus?: (s: string | null) => void }) {

  const [sessions, setSessions] = useState<InterviewSession[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [expandedDetail, setExpandedDetail] = useState<InterviewSessionDetail | null>(null)
  const [questions, setQuestions] = useState<Record<number, string>>({})
  const [savingQ, setSavingQ] = useState<Record<number, boolean>>({})

  const load = useCallback(async () => {
    try { setSessions(await interviewsApi.list(applicationId)) } catch { setSessions([]) }
  }, [applicationId])

  useEffect(() => { void load() }, [load])

  /* 탭을 안 열어도 '대기 중' 을 알 수 있어야 한다 — 가장 최근 세션의 상태를 올린다 */
  useEffect(() => {
    if (!onStatus) return
    onStatus(sessions === null || sessions.length === 0 ? null : sessions[0].status)
  }, [sessions, onStatus])

  async function create() {
    setCreating(true); setErr(null)
    try { await interviewsApi.create(applicationId); await load() }
    catch (e) { setErr(e instanceof ApiError ? e.message : 'AI 면접을 만들지 못했습니다') }
    finally { setCreating(false) }
  }

  async function copyUrl(url: string) {
    try { await navigator.clipboard.writeText(url) } catch { /* ignore */ }
  }

  async function saveQuestions(sessionId: number) {
    const qs = (questions[sessionId] ?? '').split('\n').map((s) => s.trim()).filter(Boolean)
    setSavingQ((prev) => ({ ...prev, [sessionId]: true })); setErr(null)
    try { await interviewsApi.setQuestions(sessionId, qs) }
    catch (e) { setErr(e instanceof ApiError ? e.message : '질문을 저장하지 못했습니다') }
    finally { setSavingQ((prev) => ({ ...prev, [sessionId]: false })) }
  }

  /** 끝나지 않은 세션이 하나라도 있는가 — 있으면 새로 만들지 못하게 막는다 */
  const hasOpen = (sessions ?? []).some((s) => s.status !== 'done' && s.status !== 'expired')

  async function toggleExpand(session: InterviewSession) {
    if (expandedId === session.id) { setExpandedId(null); setExpandedDetail(null); return }
    setExpandedId(session.id); setExpandedDetail(null)
    try { setExpandedDetail(await interviewsApi.detail(session.id)) } catch { /* ignore */ }
  }

  return (
    <div className={styles.sec}>
      <h2>AI 면접</h2>
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.btnStage}
          disabled={creating || hasOpen}
          onClick={create}
        >
          {creating ? '만드는 중…' : 'AI 면접 만들기'}
        </button>
      </div>
      {/* 끝나지 않은 세션이 있으면 못 만들게 한다.
          **누를 때마다 새 행이 생긴다**(백엔드가 일부러 그렇게 한다 — 옛 링크를
          죽이지 않으려고). 그런데 앱은 끝나지 않은 것 중 **가장 먼저 만든 것**을
          잡는다(`applicant_summary_screen.dart` 의 `open.first`). 그래서 두 번
          누르면 담당자가 보고 있는 세션과 지원자가 들어간 세션이 갈린다 —
          2026-09-10 실측에서 관전 화면이 끝까지 "기다리는 중"이었던 원인이다. */}
      {hasOpen && (
        <p className={styles.state}>
          진행 중이거나 아직 시작하지 않은 면접이 있습니다. 그것을 쓰거나, 끝난 뒤에 새로
          만들어 주세요 — 여러 개를 만들면 지원자는 가장 먼저 만든 것으로 들어갑니다.
        </p>
      )}
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
              <button type="button" className={styles.ivCopy} onClick={() => copyUrl(s.url)}>링크 복사</button>
              {/* 실시간 면접(사람 ↔ 사람). 끝난 면접에는 안 보인다 —
                  들어가 봐야 방이 안 열린다(서버가 session_closed 로 막는다).
                  같은 세션·같은 토큰을 쓰므로 AI 면접과 자리를 나누지 않는다. */}
              {!isDone && (
                <>
                  {/* **새 탭에서 연다** (2026-09-09 · cloverky 지적).
                      이 둘은 레이아웃 밖 전체 화면이라, 같은 탭에서 열면 보던
                      지원자 화면을 통째로 덮는다 — 돌아오려면 뒤로가기를 눌러야
                      하고, 그 사이 면접방은 닫힌다. 면접을 보는 동안 담당자는
                      지원자 정보를 계속 봐야 하므로 창을 나누는 것이 맞다. */}
                  <a
                    className={styles.ivCopy}
                    href={`/interview-watch/${s.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    실시간 분석 보기
                  </a>
                  <a
                    className={styles.ivCopy}
                    href={`/interview-room/${s.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    화상 면접방
                  </a>
                </>
              )}
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
                  placeholder={
                    // **기본 질문 같은 것은 없다.** 비워 두면 지원자가 시작할 때
                    // 서버가 422 로 막는다("준비된 질문이 없습니다 — 담당자에게
                    // 문의해 주세요"). 문구가 반대로 적혀 있어 2026-09-10 에
                    // 면접이 시작조차 되지 않았다.
                    '질문을 한 줄에 하나씩 입력하세요\n(하나 이상 저장해야 면접을 시작할 수 있습니다)'
                  }
                  value={questions[s.id] ?? ''}
                  disabled={savingQ[s.id]}
                  onChange={(e) => setQuestions((prev) => ({ ...prev, [s.id]: e.target.value }))}
                />
                <div className={styles.actions}>
                  <button type="button" className="btn" disabled={savingQ[s.id]}
                    onClick={() => saveQuestions(s.id)}>
                    {savingQ[s.id] ? '저장 중…' : '질문 저장'}
                  </button>
                </div>
              </>
            )}
            {isExpanded && (
              <div className={styles.ivTurns}>
                {expandedDetail === null && <p className={styles.state}>불러오는 중…</p>}
                {expandedDetail?.turns.length === 0 && <p className={`${styles.state} ${styles.ivEmpty}`}>답변이 없습니다.</p>}
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

/* ── 메일 (프리셋 + 작성) ── */

const MAIL_PRESETS: { stage: string; label: string }[] = [
  { stage: 'interview', label: '면접 안내' },
  { stage: 'applied', label: '접수 확인' },
  { stage: 'accepted', label: '최종 합격' },
  { stage: 'rejected', label: '불합격' },
]

function MailSection({ applicationId, onSent, onCancel }: { applicationId: number; onSent: () => void; onCancel: () => void }) {
  const [open, setOpen] = useState(false)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function prefill(stage: string) {
    setErr(null)
    try {
      const res = await mailApi.preview(applicationId, stage)
      setSubject(res.subject); setBody(res.body); setOpen(true)
    } catch (e) { setErr(e instanceof ApiError ? e.message : '문구를 불러오지 못했습니다') }
  }

  async function send() {
    setBusy(true)
    try {
      await mailApi.send(applicationId, { subject, body })
      setConfirming(false); setOpen(false); setSubject(''); setBody('')
      onSent()
    } catch (e) { setErr(e instanceof ApiError ? e.message : '발송하지 못했습니다') }
    finally { setBusy(false) }
  }

  return (
    <div className={styles.mailbox}>
      {/* 단계는 안 바뀐다 — 단계를 옮기는 메일은 헤더의 '단계 변경' 이 맡는다.
          한 메뉴가 두 가지 일을 하던 것을 갈랐다. */}
      <div className={styles.mailtop}>
        <p className={styles.secLabel}>메일 보내기</p>
        <span className={styles.mailnote}>단계는 바뀌지 않습니다</span>
      </div>
      {!open && (
        <div className={styles.mailPresets}>
          {MAIL_PRESETS.map((p) => (
            <button key={p.stage} type="button"
              className={p.stage === 'rejected' ? styles.btnReject : styles.btnStage}
              onClick={() => prefill(p.stage)}>{p.label}</button>
          ))}
        </div>
      )}
      {open && (
        <>
          <input className={styles.input} aria-label="메일 제목" value={subject}
            disabled={busy} onChange={(e) => setSubject(e.target.value)} />
          <textarea className={styles.input} rows={10} aria-label="메일 본문"
            value={body} disabled={busy} onChange={(e) => setBody(e.target.value)} />
          <div className={styles.actions}>
            <button type="button" className="btn" disabled={busy} onClick={() => { setOpen(false); onCancel() }}>취소</button>
            <button type="button" className="btn btn-primary"
              disabled={busy || subject.trim() === '' || body.trim() === ''}
              onClick={() => setConfirming(true)}>보내기</button>
          </div>
        </>
      )}
      {err && <p className={styles.err} role="alert">{err}</p>}
      {confirming && (
        <div className={styles.mailScrim} role="presentation" onClick={() => setConfirming(false)}>
          <div className={styles.mailModal} role="dialog" aria-modal="true"
            aria-label="메일 발송 확인" onClick={(e) => e.stopPropagation()}>
            <p className={styles.mailWarn}>이 내용 그대로 지원자에게 발송됩니다. 되돌릴 수 없습니다.</p>
            <p className={styles.mailSubject}>{subject}</p>
            <pre className={styles.mailPreview}>{body}</pre>
            <div className={styles.actions}>
              <button type="button" className="btn" disabled={busy} onClick={() => setConfirming(false)}>취소</button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={send}>
                {busy ? '보내는 중…' : '발송'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── 시스템 (메일 이력) ── */

const MAIL_STATUS_LABEL: Record<string, string> = { queued: '대기', sent: '발송됨', failed: '실패' }

function MailHistorySection({ applicationId, refreshKey, onFailed }: { applicationId: number; refreshKey: number; onFailed?: (n: number) => void }) {
  const [history, setHistory] = useState<EmailLogItem[] | null>(null)

  const load = useCallback(async () => {
    try { const res = await mailApi.history(applicationId); setHistory(res.items) }
    catch { setHistory([]) }
  }, [applicationId])

  useEffect(() => { void load() }, [load, refreshKey])

  const failed = (history ?? []).filter((m) => m.status === 'failed').length

  /* 실패 건수는 탭 라벨의 배지가 된다 — 이력을 안 열어도 보여야 한다 */
  useEffect(() => { onFailed?.(failed) }, [failed, onFailed])

  if (!history || history.length === 0) return <p className={styles.state}>발송 이력이 없습니다.</p>

  return (
    <>
      <div className={styles.secRow2}>
        <p className={styles.secLabel}>발송 이력</p>
        {failed > 0 && <span className={`${styles.badge} ${styles.badgeDanger}`}>실패 {failed}</span>}
      </div>
      {history.map((m) => (
        <div key={m.id} className={styles.hrow}>
          <span className={styles.hdate}>{fmtDateShort(m.sent_at ?? m.created_at)}</span>
          <span className={styles.hbody}>
            {m.subject ?? `${STAGE_LABEL[m.stage as Stage] ?? m.stage} 자동 안내`}
            {' '}
            <span className={`${styles.mailStatus} ${m.status === 'failed' ? styles.mailFailed : m.status === 'sent' ? styles.mailSent : ''}`}>
              {MAIL_STATUS_LABEL[m.status] ?? m.status}
            </span>
          </span>
        </div>
      ))}
    </>
  )
}
