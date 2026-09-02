import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { AptitudePublic } from '../api/types'
import styles from './Aptitude.module.css'

/* 지원자용 사전 성향 설문 공개 페이지 (ADR-0027) — 로그인 없음, 메일 링크의
   토큰이 곧 인증. Interview.tsx 와 같은 껍데기 패턴.

   전 문항 필수(서버도 422 로 거른다) — 제출 버튼은 다 고르기 전엔 잠긴다.
   응답은 선택 사항이고 불이익이 없다는 안내를 화면에도 그대로 쓴다. */

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; data: AptitudePublic }
  | { kind: 'invalid' }
  | { kind: 'error'; message: string }

export default function Aptitude() {
  const { token } = useParams<{ token: string }>()
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [values, setValues] = useState<Record<string, number>>({})
  const [pending, setPending] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const data = await api.get<AptitudePublic>(`/public/aptitude/${token}`, { auth: false })
      setState({ kind: 'ready', data })
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setState({ kind: 'invalid' })
      else setState({ kind: 'error', message: err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요' })
    }
  }, [token])

  useEffect(() => { void load() }, [load])

  async function submit(data: AptitudePublic) {
    setPending(true)
    setNotice(null)
    try {
      await api.post(
        `/public/aptitude/${token}/submit`,
        { answers: data.questions.map((q) => ({ key: q.key, value: values[q.key] })) },
        { auth: false },
      )
      await load()
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : '잠시 후 다시 시도해 주세요')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className={styles.page}>
      <main className={styles.column}>
        <h1 className={styles.logo}><span className={styles.seed}>A</span>rda</h1>

        {state.kind === 'loading' && (
          <div className={styles.card} aria-busy="true">
            <div className={styles.skeleton} style={{ width: '60%' }} />
            <div className={styles.skeleton} style={{ width: '40%' }} />
            <div className={styles.skeleton} />
          </div>
        )}

        {state.kind === 'invalid' && (
          <div className={styles.card}>
            <h2 className={styles.noticeTitle}>유효하지 않은 링크입니다</h2>
            <p className={styles.noticeBody}>안내 메일의 링크를 다시 확인해 주세요.</p>
          </div>
        )}

        {state.kind === 'error' && (
          <div className={`${styles.card} ${styles.cardDanger}`} role="alert">
            <h2 className={styles.noticeTitle}>불러오지 못했습니다</h2>
            <p className={styles.noticeBody}>{state.message}</p>
            <button type="button" className="btn btn-secondary"
              onClick={() => { setState({ kind: 'loading' }); void load() }}>
              다시 시도
            </button>
          </div>
        )}

        {state.kind === 'ready' && (() => {
          const d = state.data
          const answered = d.questions.filter((q) => values[q.key] !== undefined).length
          const allAnswered = d.questions.length > 0 && answered === d.questions.length
          return (
            <>
              <p className={styles.posting}>{d.posting_title}</p>

              {d.status === 'expired' && (
                <div className={styles.card}>
                  <h2 className={styles.noticeTitle}>만료된 링크입니다</h2>
                  <p className={styles.noticeBody}>설문 링크의 유효 기간이 지났습니다. 담당자에게 문의해 주세요.</p>
                </div>
              )}

              {d.status === 'done' && (
                <div className={styles.card}>
                  <h2 className={styles.noticeTitle}>응답이 제출되었습니다</h2>
                  <p className={styles.noticeBody}>{d.applicant_name}님, 참여해 주셔서 감사합니다.</p>
                </div>
              )}

              {d.status === 'pending' && (
                <>
                  <div className={styles.card}>
                    <h2 className={styles.cardTitle}>{d.applicant_name}님, 안녕하세요</h2>
                    <p className={styles.noticeBody}>
                      {d.posting_title} 채용 검토에 참고할 간단한 성향 설문입니다.
                      각 문장이 평소의 나와 얼마나 가까운지 골라 주세요. 정답은 없습니다.
                    </p>
                    <p className={styles.noticeSub}>
                      이 설문은 선택 사항이며, 응답하지 않으셔도 전형 진행에 불이익이 없습니다.
                    </p>
                    <div className={styles.legend} aria-hidden="true">
                      <span>1 = {d.likert_labels['1'] ?? '전혀 그렇지 않다'}</span>
                      <span>5 = {d.likert_labels['5'] ?? '매우 그렇다'}</span>
                    </div>
                  </div>

                  {d.questions.map((q, i) => (
                    <fieldset key={q.key} className={styles.qcard}>
                      <legend className={styles.qtext}>
                        <span className={styles.qnum}>{i + 1}</span> {q.text}
                      </legend>
                      <div className={styles.scale} role="radiogroup" aria-label={q.text}>
                        {[1, 2, 3, 4, 5].map((v) => (
                          <label
                            key={v}
                            className={`${styles.opt} ${values[q.key] === v ? styles.optOn : ''}`}
                            title={d.likert_labels[String(v)] ?? String(v)}
                          >
                            <input
                              type="radio"
                              name={q.key}
                              value={v}
                              checked={values[q.key] === v}
                              disabled={pending}
                              onChange={() => setValues((prev) => ({ ...prev, [q.key]: v }))}
                            />
                            <span>{v}</span>
                          </label>
                        ))}
                      </div>
                    </fieldset>
                  ))}

                  <div className={styles.card}>
                    <p className={styles.progress}>{answered} / {d.questions.length} 문항 응답</p>
                    {notice && <p className={styles.error} role="alert">{notice}</p>}
                    <div className={styles.actions}>
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={pending || !allAnswered}
                        onClick={() => void submit(d)}
                      >
                        {pending ? '제출 중…' : '응답 제출'}
                      </button>
                    </div>
                  </div>
                </>
              )}
            </>
          )
        })()}
      </main>
    </div>
  )
}
