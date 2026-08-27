import { useState } from 'react'
import PageHead from '../components/PageHead'
import styles from './Settings.module.css'

/* 내 계정 / 사용자·권한(관리자) / 메일 템플릿 (05-design §0.5) */
const TABS = ['내 계정', '사용자·권한', '메일 템플릿'] as const

const USERS = [
  { id: 1, name: '김채용', email: 'admin@arda.com', role: '관리자', active: true },
  { id: 2, name: '이서연', email: 'recruiter1@arda.com', role: '채용담당자', active: true },
  { id: 3, name: '박정호', email: 'reviewer1@arda.com', role: '면접관', active: true },
  { id: 4, name: '최민지', email: 'recruiter2@arda.com', role: '채용담당자', active: true },
  { id: 5, name: '한도윤', email: 'reviewer2@arda.com', role: '면접관', active: false },
]

/* 메일 문구는 아직 확정되지 않았다. §12-2 대로 임의로 채우지 않는다. */
const MAIL_STAGES = ['서류 검토', '면접', '최종 합격', '불합격'] as const
const DRAFT = '(문구 작성 중)'

export default function Settings() {
  const [tab, setTab] = useState<(typeof TABS)[number]>('내 계정')
  const [stage, setStage] = useState<(typeof MAIL_STAGES)[number]>('서류 검토')

  return (
    <>
      <PageHead title="설정" />
      <main className="page-content">
        <div className={styles.tabs} role="tablist">
          {TABS.map((t) => (
            <button
              key={t}
              role="tab"
              type="button"
              aria-selected={t === tab}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </div>

        {tab === '내 계정' && (
          <div role="tabpanel" className={styles.form}>
            <div className={styles.field}>
              <label htmlFor="f-name">이름</label>
              <input className={styles.input} id="f-name" type="text" defaultValue="김채용" />
            </div>
            <div className={styles.field}>
              <label htmlFor="f-email">이메일</label>
              <input className={styles.input} id="f-email" type="email" defaultValue="admin@arda.com" />
            </div>
            <div className={styles.field}>
              <label htmlFor="f-role">역할</label>
              {/* 역할은 관리자가 사용자·권한에서 바꾼다 — 여기서는 읽기 전용 */}
              <input className={styles.input} id="f-role" type="text" defaultValue="관리자" disabled />
            </div>
            <div className={styles.formActions}>
              <button type="button" className="btn btn-primary">저장</button>
            </div>
          </div>
        )}

        {tab === '사용자·권한' && (
          <div role="tabpanel">
            <div className={styles.rowActions}>
              <button type="button" className="btn btn-primary">사용자 추가</button>
            </div>
            <div className={styles.panel}>
              <div className={`${styles.row} ${styles.thead}`}>
                <span>이름</span>
                <span>이메일</span>
                <span>역할</span>
                <span>상태</span>
              </div>
              {USERS.map((u) => (
                <div key={u.id} className={`${styles.row} ${styles.item}`}>
                  <span className={styles.name}>{u.name}</span>
                  <span className={styles.sub}>{u.email}</span>
                  <span className={u.role === '관리자' ? styles.admin : undefined}>{u.role}</span>
                  <span className={u.active ? styles.on : styles.off}>
                    {u.active ? '활성' : '비활성'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === '메일 템플릿' && (
          <div role="tabpanel" className={styles.mail}>
            <nav className={styles.stageNav}>
              {MAIL_STAGES.map((s) => (
                <button
                  key={s}
                  type="button"
                  className={s === stage ? styles.stageOn : undefined}
                  onClick={() => setStage(s)}
                >
                  {s}
                </button>
              ))}
            </nav>

            <div className={styles.mailBody}>
              <div className={styles.field}>
                <label htmlFor="tpl-subject">제목</label>
                <input className={styles.input} id="tpl-subject" type="text" value={DRAFT} readOnly />
              </div>
              <div className={styles.field}>
                <label htmlFor="tpl-body">본문</label>
                <textarea className={styles.textarea} id="tpl-body" rows={8} value={DRAFT} readOnly />
              </div>
              <p className={styles.note}>{stage} 단계 메일 문구는 아직 확정 전입니다.</p>
              <div className={styles.formActions}>
                <button type="button" className="btn btn-primary" disabled>저장</button>
              </div>
            </div>
          </div>
        )}
      </main>
    </>
  )
}
