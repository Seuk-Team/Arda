import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { stages as stagesApi, summary as summaryApi } from '../api/endpoints'
import type { Stage, SummaryApplicant, SummaryPosting } from '../api/types'
import AccountMenu from '../components/AccountMenu'
import styles from './Summary.module.css'

/* ai_summary 는 프로덕션 DB 에 JSON 문자열로 저장돼 있다 (요약 프롬프트가 구조화된
   JSON 을 뱉는다 · ApplicantPanel 참고). `gist` 가 핵심 한 줄이고, 나머지는 강점·경험·
   우려 등 리스트. 파싱 실패 시엔 그대로 원문을 폴백으로 보여준다. */
interface ParsedSummary {
  insufficient?: boolean
  gist?: string
  fit?: string[]
  concerns?: string[]
  key_skills?: string[]
  key_experiences?: string[]
}

function parseAiSummary(raw: string | null): ParsedSummary | null {
  if (!raw) return null
  let s = raw.trim()
  if (s.startsWith('```')) {
    s = s.replace(/^```[a-zA-Z]*\n?/, '')
    if (s.endsWith('```')) s = s.slice(0, -3)
    s = s.trim()
  }
  try {
    const j: unknown = JSON.parse(s)
    if (j !== null && typeof j === 'object' && !Array.isArray(j)) return j as ParsedSummary
  } catch { /* JSON 아니면 원문으로 취급 */ }
  return null
}

function summaryPreview(raw: string | null): string {
  const parsed = parseAiSummary(raw)
  if (parsed) {
    if (parsed.insufficient) return '자기소개 자료 부족 — 요약 생성 안 됨'
    if (parsed.gist) return parsed.gist.slice(0, 80) + (parsed.gist.length > 80 ? '…' : '')
  }
  if (raw) return raw.slice(0, 80) + (raw.length > 80 ? '…' : '')
  return '요약 없음'
}

/* 종합 평가 (2026-09-14) — 공고별 지원자 · 서류 + 면접 자동 점수 · 등급 · 요약.

   담당자가 "이 공고의 지원자들이 어느 수준이고 누가 강한가" 를 **한 눈에** 본다.
   지원자 상세는 카드 클릭 시 /applicants 로 이동 (기존 패널 재사용).

   왜 새 페이지가 필요했나:
     `/applicants` 는 지원자 목록 + 우측 패널이라 지원자 하나씩만 상세하게 본다.
     "공고별 전체 지원자를 서로 비교하며 훑는" 경험이 없었다. 자동 심사 · 면접
     점수 · 요약을 각각 다른 화면에 흩뿌려 놔 총평이 안 잡혔다. 이 페이지가
     그 총평을 조립한다.
*/

export default function Summary() {
  const [state, setState] = useState<
    | { kind: 'loading' }
    | { kind: 'ready'; data: SummaryPosting[] }
    | { kind: 'error'; message: string }
  >({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    summaryApi
      .list(controller.signal)
      .then((data) => setState({ kind: 'ready', data }))
      .catch((err) => {
        if (err?.name === 'AbortError') return
        setState({ kind: 'error', message: err?.message ?? '불러오지 못했습니다' })
      })
    return () => controller.abort()
  }, [])

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <div className={styles.headText}>
          <h1 className={styles.title}>종합 평가</h1>
          <p className={styles.sub}>공고별 지원자 · 서류 + 면접 자동 점수 · 종합 등급 · 요약</p>
        </div>
        {/* 다른 화면(PageHead)과 같은 자리에 계정 메뉴 — 여긴 자체 헤더라 빠져 있었다 */}
        <AccountMenu />
      </header>

      {state.kind === 'loading' && <p className={styles.state}>불러오는 중…</p>}
      {state.kind === 'error' && <p className={styles.err}>{state.message}</p>}
      {state.kind === 'ready' && (
        state.data.length === 0 ? (
          <p className={styles.state}>아직 공고가 없습니다.</p>
        ) : (
          <div className={styles.postings}>
            {state.data.map((p) => (
              <PostingBlock key={p.id} posting={p} />
            ))}
          </div>
        )
      )}
    </div>
  )
}

function PostingBlock({ posting }: { posting: SummaryPosting }) {
  /* 공고 블록은 **접힌 채로** 시작한다 (2026-09-15 팀장 요청). 공고가 여럿이면 다 펼쳐진
     표가 한 화면을 넘겨 어느 공고를 보고 있는지 잃는다 — 머리(지원자·평가 완료·평균)만
     훑고 볼 공고를 골라 연다. 지원자 행 안의 상세(<details>)는 원래부터 접혀 있다. */
  const [expanded, setExpanded] = useState(false)

  /* 판정 뒤 로컬 반영 (2026-09-15). 서버가 200 이면 이 지원자의 current_stage 만 바꿔
     정렬·뱃지가 바로 반영된다. 새로고침 없이 다음 사람으로 넘어갈 수 있다.
     실패 시엔 ApplicantRow 가 에러를 자기 안에서 보여 준다 — 여기서 낙관적 갱신을
     하지 않는다(되돌리기 어려운 동작이라 실패했는데 성공한 것처럼 보이면 안 된다). */
  const [decided, setDecided] = useState<Record<number, Stage>>({})
  const onLocalStageChange = (id: number, to: Stage) =>
    setDecided((prev) => ({ ...prev, [id]: to }))
  const applicantsForRender: SummaryApplicant[] = posting.applicants.map((a) =>
    decided[a.id] ? { ...a, current_stage: decided[a.id] } : a,
  )

  /* 2026-09-14: 점수가 높은 사람이 위로, 불합격은 맨 아래. 팀에서 "합격 후보를 먼저
     본다" 는 요구에 맞춤. 정렬 키:
       (1) rejected 는 뒤로 (current_stage === 'rejected' 또는 doc_decision === 'reject')
       (2) final_score 내림차순 (null 은 부여 안 됨 · 뒤로)
       (3) 이름 오름차순 (동점 안정 정렬) */
  const sortedApplicants = [...applicantsForRender].sort((x, y) => {
    const rejX = x.current_stage === 'rejected' || x.doc_decision === 'reject' ? 1 : 0
    const rejY = y.current_stage === 'rejected' || y.doc_decision === 'reject' ? 1 : 0
    if (rejX !== rejY) return rejX - rejY
    const scoreX = x.final_score ?? -1
    const scoreY = y.final_score ?? -1
    if (scoreX !== scoreY) return scoreY - scoreX
    return x.name.localeCompare(y.name, 'ko')
  })
  const graded = posting.applicants.filter((a) => a.final_score !== null).length
  const avgFinal = posting.applicants.length
    ? posting.applicants
        .filter((a) => a.final_score !== null)
        .reduce((s, a) => s + (a.final_score ?? 0), 0) /
      (posting.applicants.filter((a) => a.final_score !== null).length || 1)
    : 0

  return (
    <section className={styles.posting}>
      <header className={styles.postingHead}>
        <button
          type="button"
          className={styles.toggle}
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          <span className={styles.chev} aria-hidden>{expanded ? '▾' : '▸'}</span>
          <span className={styles.postingTitle}>{posting.title}</span>
          <span className={`${styles.badge} ${styles[`status_${posting.status}`] ?? ''}`}>
            {posting.status === 'open' ? '진행 중' : posting.status === 'closed' ? '마감' : posting.status}
          </span>
        </button>
        <div className={styles.stats}>
          <span>지원자 <strong>{posting.applicant_count}</strong>명</span>
          <span>평가 완료 <strong>{graded}</strong>명</span>
          {graded > 0 && (
            <span>평균 종합 <strong>{avgFinal.toFixed(1)}</strong>점</span>
          )}
        </div>
      </header>

      {expanded && (
        posting.applicants.length === 0 ? (
          <p className={styles.state}>지원자가 아직 없습니다.</p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>지원자</th>
                <th className={styles.numCol}>서류</th>
                <th className={styles.numCol}>면접</th>
                <th className={styles.numCol}>종합</th>
                <th className={styles.numCol}>등급</th>
                <th>단계</th>
                <th>최종 판정</th>
                <th>요약 · 강점 · 우려</th>
              </tr>
            </thead>
            <tbody>
              {sortedApplicants.map((a) => (
                <ApplicantRow
                  key={a.id}
                  applicant={a}
                  onChanged={onLocalStageChange}
                />
              ))}
            </tbody>
          </table>
        )
      )}
    </section>
  )
}

function SummaryDrilldown({ applicant: a }: { applicant: SummaryApplicant }) {
  /* JSON 파싱 결과 우선 · key_skills·key_experiences 는 파싱했을 때만 옴.
     서버가 별도로 추린 strengths/concerns 는 면접 결과(interview_ai_score_detail) 에서 온다
     — 서류 요약과 별개 라 두 쪽 다 있으면 각각 보여준다. */
  const parsed = parseAiSummary(a.ai_summary)
  return (
    <div className={styles.detailsBody}>
      {parsed?.insufficient && (
        <p className={styles.summary}>자기소개서·이력서가 부족해 요약을 만들지 못했습니다.</p>
      )}
      {parsed?.gist && <p className={styles.summary}>{parsed.gist}</p>}
      {!parsed && a.ai_summary && <p className={styles.summary}>{a.ai_summary}</p>}

      {(parsed?.key_skills?.length ?? 0) > 0 && (
        <div className={styles.pointsWrap}>
          <span className={styles.pointsLabel}>기술</span>
          <ul className={styles.points}>
            {parsed!.key_skills!.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}
      {(parsed?.key_experiences?.length ?? 0) > 0 && (
        <div className={styles.pointsWrap}>
          <span className={styles.pointsLabel}>경험</span>
          <ul className={styles.points}>
            {parsed!.key_experiences!.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}
      {(parsed?.fit?.length ?? 0) > 0 && (
        <div className={styles.pointsWrap}>
          <span className={styles.pointsLabel}>적합</span>
          <ul className={styles.points}>
            {parsed!.fit!.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}
      {(parsed?.concerns?.length ?? 0) > 0 && (
        <div className={styles.pointsWrap}>
          <span className={`${styles.pointsLabel} ${styles.concernLabel}`}>우려 (서류)</span>
          <ul className={styles.points}>
            {parsed!.concerns!.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}

      {/* 서버가 추린 면접 요약. `strengths`/`concerns` 는 면접 채점의 산출물이라 서류 요약과 별개. */}
      {a.strengths.length > 0 && (
        <div className={styles.pointsWrap}>
          <span className={styles.pointsLabel}>강점 (면접)</span>
          <ul className={styles.points}>{a.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </div>
      )}
      {a.concerns.length > 0 && (
        <div className={styles.pointsWrap}>
          <span className={`${styles.pointsLabel} ${styles.concernLabel}`}>우려 (면접)</span>
          <ul className={styles.points}>{a.concerns.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </div>
      )}
    </div>
  )
}

/* 최종 판정 (2026-09-15).

   종합평가는 원래 읽기 전용이었고, 최종 합격/불합격은 /applicants 의 지원자 상세
   진행 바에서 [단계 변경]→고르기→확인→적용 4단계로 했다. 이 표에서 훑고 저 화면으로
   이동해 그 사람을 다시 찾는 흐름이 공고 하나에 지원자 7·8명이면 무거워, 여기서 바로
   결정한다. 위험을 늘리지 않는다:

     - 결정 가능한 사람은 **면접 단계(`interview`)뿐** — 서류·접수 단계의 사람을 여기서
       바로 합격시키면 단계 건너뛰기가 되어 `validate_transition` 이 409 로 튕긴다.
       그 사람은 진행 바에서 다뤄야 한다.
     - 합격은 확인창 하나, 불합격은 사유가 필수(백엔드 `require_reason` 규칙 그대로).
     - 이미 accepted/rejected 인 사람은 결과 뱃지로만 보인다 — 되돌리는 것은 지원자 상세
       에서 (드문 동작에 마찰을 남긴다).

   서버 호출은 기존 `PATCH /applications/{id}/stage` 그대로. 새 API 없음. */
function ApplicantRow({
  applicant: a,
  onChanged,
}: {
  applicant: SummaryApplicant
  onChanged: (id: number, to: Stage) => void
}) {
  const stageLabel: Record<string, string> = {
    applied: '접수', screening: '서류', interview: '면접',
    accepted: '합격', rejected: '불합격',
  }
  const [busy, setBusy] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [err, setErr] = useState<string | null>(null)

  const canDecide = a.current_stage === 'interview'
  const isAccepted = a.current_stage === 'accepted'
  const isRejected = a.current_stage === 'rejected'

  async function decide(to: Stage, reasonText?: string) {
    if (busy) return
    if (to === 'accepted' && !window.confirm(`${a.name} 님을 최종 합격으로 처리할까요?\n합격 안내 메일이 큐에 올라갑니다.`)) return
    setBusy(true)
    setErr(null)
    try {
      await stagesApi.change(a.id, to, reasonText)
      onChanged(a.id, to)
      setRejecting(false)
      setReason('')
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : '단계를 바꾸지 못했습니다')
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr className={styles.row}>
      <td>
        <Link to={`/summary/${a.id}`} className={styles.nameLink}>{a.name}</Link>
        <div className={styles.email}>{a.email}</div>
      </td>
      <td className={styles.num}>
        {a.doc_score !== null ? (
          <span className={a.doc_decision === 'pass' ? styles.ok : a.doc_decision === 'reject' ? styles.bad : ''}>
            {a.doc_score}
          </span>
        ) : <span className={styles.dim}>—</span>}
      </td>
      <td className={styles.num}>
        {a.interview_ai_score !== null ? a.interview_ai_score : <span className={styles.dim}>—</span>}
      </td>
      <td className={styles.num}>
        {a.final_score !== null ? <strong>{a.final_score.toFixed(1)}</strong> : <span className={styles.dim}>—</span>}
      </td>
      <td className={styles.num}>
        {a.grade ? (
          <span className={`${styles.grade} ${styles[`grade_${a.grade}`] ?? ''}`}>{a.grade}</span>
        ) : <span className={styles.dim}>—</span>}
      </td>
      <td>{stageLabel[a.current_stage] ?? a.current_stage}</td>
      <td className={styles.decideCell}>
        {isAccepted && <span className={`${styles.decideBadge} ${styles.decideOk}`}>합격</span>}
        {isRejected && <span className={`${styles.decideBadge} ${styles.decideBad}`}>불합격</span>}
        {canDecide && !rejecting && (
          <div className={styles.decideBtns}>
            <button
              type="button"
              className={`${styles.decideBtn} ${styles.decideBtnOk}`}
              disabled={busy}
              onClick={() => void decide('accepted')}
              title="최종 합격 (합격 안내 메일 큐 발행)"
            >
              합격
            </button>
            <button
              type="button"
              className={`${styles.decideBtn} ${styles.decideBtnBad}`}
              disabled={busy}
              onClick={() => setRejecting(true)}
              title="최종 불합격 (사유 필수)"
            >
              불합격
            </button>
          </div>
        )}
        {canDecide && rejecting && (
          <div className={styles.decideReasonRow}>
            <input
              type="text"
              className={styles.decideReason}
              placeholder="불합격 사유 (지원자에게 전달됨)"
              value={reason}
              autoFocus
              disabled={busy}
              onChange={(e) => setReason(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') { e.preventDefault(); setRejecting(false); setReason(''); setErr(null) }
                if (e.key === 'Enter' && reason.trim()) void decide('rejected', reason.trim())
              }}
            />
            <button
              type="button"
              className={`${styles.decideBtn} ${styles.decideBtnBad}`}
              disabled={busy || !reason.trim()}
              onClick={() => void decide('rejected', reason.trim())}
            >
              확정
            </button>
            <button
              type="button"
              className={styles.decideBtn}
              disabled={busy}
              onClick={() => { setRejecting(false); setReason(''); setErr(null) }}
            >
              취소
            </button>
          </div>
        )}
        {err && <p className={styles.decideErr}>{err}</p>}
      </td>
      <td>
        <details className={styles.details}>
          <summary className={styles.detailsSummary}>
            {summaryPreview(a.ai_summary)}
          </summary>
          <SummaryDrilldown applicant={a} />
        </details>
      </td>
    </tr>
  )
}
