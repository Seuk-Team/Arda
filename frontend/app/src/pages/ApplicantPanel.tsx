import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { applications, notes as notesApi, stages } from '../api/endpoints'
import type { ApplicationDetail, Note, Stage } from '../api/types'
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

          {/* AI 제안은 앰버 점선 + "확정은 담당자가 합니다" — §1 불변 규약 */}
          {detail.ai_summary && (
            <div className={styles.sec}>
              <div className={styles.aibox}>
                <p className={styles.aicap}>AI 요약 · 확정은 담당자가 합니다</p>
                <p className={styles.aibody}>{detail.ai_summary}</p>
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
