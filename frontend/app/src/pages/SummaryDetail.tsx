import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { applications, aptitude as aptitudeApi, files as filesApi, interviews } from '../api/endpoints'
import type {
  ApplicationDetail,
  AptitudeDetail,
  InterviewSession,
  InterviewSessionDetail,
} from '../api/types'
import styles from './SummaryDetail.module.css'

/* 종합 평가 · 지원자 한 명의 서류·인적성·면접 종합 (2026-09-14).

   `/summary` 표에서 이름 클릭 → 이 페이지. 세 섹션 (서류·인적성·면접) 을 각자
   장·단점 위주로 보여 준다. 담당자 판단(최종 합격/불합격) 이 이 화면 앞에서
   난다. 데이터는 세 개 REST 로 병렬 호출 · 3~4 개 API 가 이미 있어 새 조인
   엔드포인트를 만들지 않았다 (한 번 열 때만 3 요청 · 부담 없음). */

interface ParsedAiSummary {
  insufficient?: boolean
  gist?: string
  fit?: string[]
  concerns?: string[]
  key_skills?: string[]
  key_experiences?: string[]
}

function parseAiSummary(raw: string | null | undefined): ParsedAiSummary | null {
  if (!raw) return null
  let s = raw.trim()
  if (s.startsWith('```')) {
    s = s.replace(/^```[a-zA-Z]*\n?/, '')
    if (s.endsWith('```')) s = s.slice(0, -3)
    s = s.trim()
  }
  try {
    const j: unknown = JSON.parse(s)
    if (j !== null && typeof j === 'object' && !Array.isArray(j)) return j as ParsedAiSummary
  } catch { /* 원문 폴백 */ }
  return null
}

export default function SummaryDetail() {
  const { applicationId } = useParams<{ applicationId: string }>()
  const nav = useNavigate()
  const id = Number(applicationId)

  const [app, setApp] = useState<ApplicationDetail | null>(null)
  const [aptitude, setAptitude] = useState<AptitudeDetail | null>(null)
  const [interviewList, setInterviewList] = useState<InterviewSession[] | null>(null)
  const [interviewDetail, setInterviewDetail] = useState<InterviewSessionDetail | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!Number.isFinite(id)) return
    const controller = new AbortController()
    Promise.all([
      applications.detail(id, controller.signal).catch(() => null),
      aptitudeApi.detail(id, controller.signal).catch(() => null),
      interviews.list(id, controller.signal).catch(() => null),
    ])
      .then(([a, apt, ivList]) => {
        setApp(a as ApplicationDetail | null)
        setAptitude(apt as AptitudeDetail | null)
        setInterviewList(ivList as InterviewSession[] | null)
        // 가장 최근 종료된 면접의 상세를 이어서 부른다.
        const lastDone = (ivList as InterviewSession[] | null)?.find((s) => s.status === 'done')
        if (lastDone) {
          return interviews.detail(lastDone.id, controller.signal).catch(() => null)
        }
        return null
      })
      .then((d) => setInterviewDetail(d as InterviewSessionDetail | null))
      .catch((e) => {
        if (e?.name === 'AbortError') return
        setErr(e?.message ?? '불러오지 못했습니다')
      })
    return () => controller.abort()
  }, [id])

  const parsedDoc = useMemo(() => parseAiSummary(app?.ai_summary ?? null), [app])

  if (err) {
    return <div className={styles.page}><p className={styles.err}>{err}</p></div>
  }
  if (!app) {
    return <div className={styles.page}><p className={styles.state}>불러오는 중…</p></div>
  }

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <button type="button" onClick={() => nav('/summary')} className={styles.back}>
          ← 종합 평가
        </button>
        <div className={styles.headBody}>
          <h1 className={styles.name}>{app.name}</h1>
          <p className={styles.meta}>
            {app.email}
            {app.career_years !== null && ` · 경력 ${app.career_years}년`}
            {app.education && ` · ${app.education}`}
          </p>
          <div className={styles.scoreBoard}>
            <ScorePill label="서류" value={app.doc_score ?? null} />
            <ScorePill label="면접" value={app.interview_ai_score ?? null} />
            <ScorePill label="종합" value={app.final_score ?? null} strong />
            {app.grade && (
              <span className={`${styles.grade} ${styles[`grade_${app.grade}`] ?? ''}`}>{app.grade}</span>
            )}
          </div>
        </div>
      </header>

      <IntroAndResumeSection app={app} />
      <DocumentSection parsed={parsedDoc} app={app} />
      <AptitudeSection aptitude={aptitude} />
      <InterviewSection list={interviewList} detail={interviewDetail} />
    </div>
  )
}

function ScorePill({ label, value, strong = false }: { label: string; value: number | null; strong?: boolean }) {
  return (
    <div className={`${styles.pill} ${strong ? styles.pillStrong : ''}`}>
      <span className={styles.pillLabel}>{label}</span>
      <span className={styles.pillValue}>
        {value === null || value === undefined ? '—' : typeof value === 'number' ? value.toFixed(value >= 10 ? 0 : 1) : value}
      </span>
    </div>
  )
}

function IntroAndResumeSection({ app }: { app: ApplicationDetail }) {
  /* 담당자가 서류·인적성·면접 요약을 보다가 "원문은 뭐라고 쓰여 있었지?" 를 바로 확인할
     수 있게 자기소개서(자체 텍스트) 와 이력서(브라우저 내장 뷰어로 보기) 를 상단에 붙인다.
     자기소개서는 몇 백 자 이내면 그대로 보이고, 길면 접힘 · 이력서는 클릭 시 새 탭에 미리보기.

     **다운로드는 일부러 안 준다.** 이력서는 블록체인 앵커로 원본 무결성이 걸려 있어서
     저장·수정 흐름이 없다 (ADR-0028). 백엔드도 `Content-Disposition: inline` 을 주므로
     브라우저 PDF 뷰어가 열리고, 그 안에서 저장 버튼을 누를 이유가 없다. */
  const resumeFile = (app.files ?? []).find((f) => f.kind === 'resume')

  const openResume = async () => {
    if (!resumeFile) return
    try {
      const { download_url } = await filesApi.presignDownload(resumeFile.id)
      // 새 탭에서 열어 브라우저 PDF 뷰어로 미리보기 (담당자 화면은 그대로 남는다).
      // noopener 로 새 탭이 opener 를 못 잡게 — 이력서 링크가 신뢰 경계 밖 리소스를 여는 셈이다.
      window.open(download_url, '_blank', 'noopener,noreferrer')
    } catch { /* 발급 실패 시 조용히 무시 · 담당자가 다시 시도 가능 */ }
  }

  if (!app.self_intro && !resumeFile) return null

  return (
    <section className={styles.section}>
      <header className={styles.sectionHead}>
        <h2 className={styles.sectionTitle}>제출 서류</h2>
        <span className={styles.sectionMeta}>
          {resumeFile && (
            <button type="button" className={styles.linkOut} onClick={openResume}>
              이력서 보기 →
            </button>
          )}
        </span>
      </header>
      {app.self_intro && (
        <details className={styles.dropdown} open={app.self_intro.length < 800}>
          <summary className={styles.dropdownSummary}>자기소개서 · {app.self_intro.length}자</summary>
          <pre className={styles.selfIntro}>{app.self_intro}</pre>
        </details>
      )}
    </section>
  )
}

function DocumentSection({ parsed, app }: { parsed: ParsedAiSummary | null; app: ApplicationDetail }) {
  const strengths = (parsed?.fit ?? [])
  const weakness = [
    ...(parsed?.concerns ?? []),
    ...(app.doc_score_detail?.concerns ?? []),
  ]

  return (
    <section className={styles.section}>
      <header className={styles.sectionHead}>
        <h2 className={styles.sectionTitle}>서류</h2>
        <span className={styles.sectionMeta}>
          {app.doc_score !== null && app.doc_score !== undefined ? `${app.doc_score}점` : '점수 없음'}
          {app.doc_score_detail?.threshold !== undefined && ` · 기준 ${app.doc_score_detail.threshold}점`}
          {app.doc_decision && (
            <span className={`${styles.decision} ${styles[`decision_${app.doc_decision}`] ?? ''}`}>
              {app.doc_decision === 'pass' ? '통과' : app.doc_decision === 'reject' ? '불합격' : '보류'}
            </span>
          )}
        </span>
      </header>

      {parsed?.insufficient && (
        <p className={styles.insufficient}>자기소개서·이력서가 부족해 요약을 만들지 못했습니다.</p>
      )}
      {parsed?.gist && <p className={styles.gist}>{parsed.gist}</p>}
      {!parsed && app.ai_summary && <p className={styles.gist}>{app.ai_summary}</p>}

      {(parsed?.key_skills?.length ?? 0) > 0 && (
        <FactBlock label="기술" items={parsed!.key_skills!} />
      )}
      {(parsed?.key_experiences?.length ?? 0) > 0 && (
        <FactBlock label="경험" items={parsed!.key_experiences!} />
      )}

      <div className={styles.prosCons}>
        <ProCon variant="pro" title="장점" items={strengths} />
        <ProCon variant="con" title="단점 / 확인 필요" items={weakness} />
      </div>

      {app.doc_score_detail && (
        <div className={styles.subScores}>
          {app.doc_score_detail.requirements !== undefined && (
            <SubScore label="요건" value={app.doc_score_detail.requirements} />
          )}
          {app.doc_score_detail.preferred !== undefined && (
            <SubScore label="우대" value={app.doc_score_detail.preferred} />
          )}
          {app.doc_score_detail.culture !== undefined && (
            <SubScore label="문화" value={app.doc_score_detail.culture} />
          )}
        </div>
      )}
    </section>
  )
}

function AptitudeSection({ aptitude }: { aptitude: AptitudeDetail | null }) {
  if (!aptitude || aptitude.status === 'none') {
    return (
      <section className={styles.section}>
        <header className={styles.sectionHead}>
          <h2 className={styles.sectionTitle}>인적성</h2>
          <span className={styles.sectionMeta}>미발송</span>
        </header>
        <p className={styles.state}>이 지원자에게는 아직 인적성 검사가 발송되지 않았습니다.</p>
      </section>
    )
  }
  if (aptitude.status === 'pending' || aptitude.status === 'expired') {
    return (
      <section className={styles.section}>
        <header className={styles.sectionHead}>
          <h2 className={styles.sectionTitle}>인적성</h2>
          <span className={styles.sectionMeta}>
            {aptitude.status === 'pending' ? '진행 전' : '만료'}
          </span>
        </header>
        <p className={styles.state}>
          {aptitude.status === 'pending'
            ? '지원자가 아직 답변을 제출하지 않았습니다.'
            : '만료된 링크입니다. 재발송해 주세요.'}
        </p>
      </section>
    )
  }

  return (
    <section className={styles.section}>
      <header className={styles.sectionHead}>
        <h2 className={styles.sectionTitle}>인적성</h2>
        <span className={styles.sectionMeta}>완료 · {aptitude.stats.length}개 카테고리</span>
      </header>
      {aptitude.ai_summary && <p className={styles.gist}>{aptitude.ai_summary}</p>}
      <div className={styles.aptGrid}>
        {aptitude.stats.map((s) => (
          <div key={s.category} className={styles.aptCat}>
            <div className={styles.aptCatLabel}>{s.label}</div>
            <div className={styles.aptCatValue}>{s.mean.toFixed(2)}</div>
            <div className={styles.aptCatCount}>{s.count}문항</div>
          </div>
        ))}
      </div>
    </section>
  )
}

function InterviewSection({ list, detail }: { list: InterviewSession[] | null; detail: InterviewSessionDetail | null }) {
  if (!list || list.length === 0) {
    return (
      <section className={styles.section}>
        <header className={styles.sectionHead}>
          <h2 className={styles.sectionTitle}>면접</h2>
          <span className={styles.sectionMeta}>세션 없음</span>
        </header>
        <p className={styles.state}>이 지원자에게 아직 면접 세션이 생성되지 않았습니다.</p>
      </section>
    )
  }

  const done = list.filter((s) => s.status === 'done')
  const inProgress = list.filter((s) => s.status === 'in_progress')

  return (
    <section className={styles.section}>
      <header className={styles.sectionHead}>
        <h2 className={styles.sectionTitle}>면접</h2>
        <span className={styles.sectionMeta}>
          완료 {done.length}건
          {inProgress.length > 0 && ` · 진행 중 ${inProgress.length}건`}
        </span>
      </header>

      {detail === null && done.length === 0 && (
        <p className={styles.state}>완료된 면접이 아직 없어 요약을 만들 수 없습니다.</p>
      )}

      {detail && (
        <>
          {detail.ai_score_detail?.answers !== undefined && (
            <p className={styles.gist}>
              답변 총평 <strong>{detail.ai_score_detail.answers}점</strong>
              {detail.ai_score_detail.truth !== null && detail.ai_score_detail.truth !== undefined && (
                <> · 진위 <strong>{detail.ai_score_detail.truth}점</strong></>
              )}
              {detail.ai_score !== null && detail.ai_score !== undefined && (
                <> · 종합 <strong>{detail.ai_score}점</strong></>
              )}
            </p>
          )}

          <div className={styles.prosCons}>
            <ProCon variant="pro" title="장점" items={detail.ai_score_detail?.strengths ?? []} />
            <ProCon variant="con" title="우려 / 확인 필요" items={detail.ai_score_detail?.concerns ?? []} />
          </div>

          {(detail.ai_score_detail?.per_question?.length ?? 0) > 0 && (
            <details className={styles.dropdown}>
              <summary className={styles.dropdownSummary}>질문별 점수 · {detail.ai_score_detail!.per_question!.length}개</summary>
              <ul className={styles.perQuestion}>
                {detail.ai_score_detail!.per_question!.map((q) => (
                  <li key={q.seq} className={styles.perQuestionItem}>
                    <span className={styles.qSeq}>Q{q.seq}</span>
                    <span className={styles.qScore}>{q.score}점</span>
                    {q.note && <span className={styles.qNote}>{q.note}</span>}
                  </li>
                ))}
              </ul>
            </details>
          )}

          {detail.turns.length > 0 && (
            <details className={styles.dropdown}>
              <summary className={styles.dropdownSummary}>답변 전사 · {detail.turns.length}턴</summary>
              <ol className={styles.turns}>
                {detail.turns.map((t) => (
                  <li key={t.seq} className={styles.turn}>
                    <p className={styles.qText}>Q{t.seq}. {t.question}</p>
                    <p className={styles.aText}>{t.transcript || <span className={styles.dim}>(답변 없음)</span>}</p>
                  </li>
                ))}
              </ol>
            </details>
          )}

          {detail.findings.length > 0 && (
            <details className={styles.dropdown}>
              <summary className={styles.dropdownSummary}>서류 vs 답변 대조 · {detail.findings.length}건</summary>
              <ul className={styles.findings}>
                {detail.findings.map((f, i) => (
                  <li key={i} className={`${styles.finding} ${styles[`finding_${f.verdict}`] ?? ''}`}>
                    <span className={styles.findingVerdict}>
                      {f.verdict === 'consistent' ? '일치' : f.verdict === 'inconsistent' ? '불일치' : '확인필요'}
                    </span>
                    <div>
                      <p className={styles.findingClaim}>{f.claim_source === 'self_intro' ? '자기소개서' : '이력서'} · {f.claim_text}</p>
                      {f.answer_text && <p className={styles.findingAnswer}>답변: {f.answer_text}</p>}
                    </div>
                  </li>
                ))}
              </ul>
            </details>
          )}

          <div className={styles.linkBar}>
            <Link to={`/interview-room/${detail.id}`} className={styles.linkOut}>
              면접방 열기 →
            </Link>
          </div>
        </>
      )}
    </section>
  )
}

function FactBlock({ label, items }: { label: string; items: string[] }) {
  return (
    <div className={styles.factBlock}>
      <span className={styles.factLabel}>{label}</span>
      <ul className={styles.factList}>
        {items.map((it, i) => <li key={i}>{it}</li>)}
      </ul>
    </div>
  )
}

function ProCon({ variant, title, items }: { variant: 'pro' | 'con'; title: string; items: string[] }) {
  return (
    <div className={`${styles.pro} ${variant === 'con' ? styles.conBox : ''}`}>
      <span className={`${styles.proLabel} ${variant === 'con' ? styles.conLabel : ''}`}>{title}</span>
      {items.length === 0 ? (
        <p className={styles.dim}>없음</p>
      ) : (
        <ul className={styles.proList}>{items.map((it, i) => <li key={i}>{it}</li>)}</ul>
      )}
    </div>
  )
}

function SubScore({ label, value }: { label: string; value: number }) {
  return (
    <div className={styles.subScore}>
      <span className={styles.subLabel}>{label}</span>
      <span className={styles.subValue}>{value}</span>
    </div>
  )
}
