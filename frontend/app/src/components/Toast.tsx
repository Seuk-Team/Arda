import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import styles from './Toast.module.css'

/* 단계 이동 성공·실패를 알린다 (05-design §6 — "실패 롤백이 조용히 지나가면 안 된다").
   낙관적 업데이트를 되돌릴 때 화면만 슬쩍 되돌아가면 담당자는 옮긴 줄 안다. */

type Tone = 'ok' | 'fail'

interface Toast {
  id: number
  tone: Tone
  text: string
}

interface ToastValue {
  show: (tone: Tone, text: string) => void
}

const Ctx = createContext<ToastValue | null>(null)

/* 실패는 읽을 시간이 더 필요하다 */
const LIFETIME = { ok: 2500, fail: 5000 }

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])

  const show = useCallback((tone: Tone, text: string) => {
    const id = Date.now() + Math.random()
    setItems((prev) => [...prev, { id, tone, text }])
    window.setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id))
    }, LIFETIME[tone])
  }, [])

  const value = useMemo(() => ({ show }), [show])

  return (
    <Ctx.Provider value={value}>
      {children}
      {/* aria-live 로 읽어 준다 — 화면을 안 보고 있어도 결과를 알아야 한다 */}
      <div className={styles.wrap} role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`${styles.toast} ${t.tone === 'fail' ? styles.fail : styles.ok}`}>
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}

export function useToast() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useToast 는 ToastProvider 안에서만 쓴다')
  return v
}
