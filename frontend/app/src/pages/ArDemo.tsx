/* 아르 3D 모션 검토용 데모. 내비 미노출 — /dev/ar 직접 진입.
   로그인 게이트 밖(데이터 접근 없음). */
import { useState } from 'react'
import ArViewer, { EXPRESSIONS, MOTIONS, type Expression, type Motion } from '../components/ArViewer'
import styles from './ArDemo.module.css'

const EXPR_LABELS: Record<Expression, string> = { ask: '질문', happy: '행복', sad: '실패' }

export default function ArDemo() {
  const [motion, setMotion] = useState<Motion>('idle')
  const [speed, setSpeed] = useState(1)
  const [expr, setExpr] = useState<Expression | undefined>(undefined) // undefined = 모션 내장 표정

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>아르 3D 모션 검토</h1>
      <ArViewer
        className={styles.viewer}
        motion={motion}
        speed={speed}
        expression={expr}
        interactive
        onMotionEnd={() => setMotion('idle')}
      />
      <div className={styles.bar}>
        {MOTIONS.map((m) => (
          <button
            key={m}
            className={`${styles.btn} ${motion === m ? styles.on : ''}`}
            onClick={() => setMotion(motion === m && m !== 'idle' ? 'idle' : m)}
          >
            {m}
          </button>
        ))}
      </div>
      <div className={styles.row}>
        <label className={styles.label}>
          속도 {speed.toFixed(2)}×
          <input
            type="range" min="0.25" max="2" step="0.25" value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
          />
        </label>
        <label className={styles.label}>
          표정
          <select
            value={expr ?? 'auto'}
            onChange={(e) => setExpr(e.target.value === 'auto' ? undefined : (e.target.value as Expression))}
          >
            <option value="auto">모션 내장</option>
            {EXPRESSIONS.map((x) => (
              <option key={x} value={x}>{EXPR_LABELS[x]}</option>
            ))}
          </select>
        </label>
      </div>
      <p className={styles.hint}>드래그 회전 · 휠 줌 · enter/confirm/fail 은 1회 재생 후 idle 복귀</p>
    </div>
  )
}
