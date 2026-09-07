import { useEffect, useRef } from 'react'
import { buildScene } from '../lib/networkScene'
import type { SceneHandle } from '../lib/networkScene'
import { useDive } from './DiveTransition'
import styles from './NetworkField.module.css'

/* 로그인 화면의 배경 노드망. 캔버스 한 장을 lib/networkScene 에 넘기고
   컴포넌트는 수명(마운트/언마운트)만 책임진다.

   접속 시퀀스 값은 DiveTransition 에서 구독으로 받는다 — props 로 내리면
   매 프레임 부모가 리렌더되고, 그때마다 이 컴포넌트도 같이 돈다.
   인트로 감광은 부모(로그인)가 onReady 로 받은 핸들로 직접 몬다. */
export default function NetworkField({ onReady }: { onReady?: (scene: SceneHandle) => void }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const { subscribe } = useDive()
  /* onReady 를 의존성에 넣으면 부모가 인라인 함수를 넘길 때마다 장면이
     다시 만들어진다 — 노드 배치가 매번 새로 뽑혀 화면이 튄다.
     쓰기는 효과 안에서 한다: 렌더 중에 ref 를 건드리면 동시성 렌더에서
     버려질 렌더의 값이 남는다. 효과는 선언 순서대로 돌아 아래보다 먼저 꽂힌다. */
  const readyRef = useRef(onReady)
  useEffect(() => { readyRef.current = onReady })

  useEffect(() => {
    const el = ref.current
    if (el === null) return
    const scene = buildScene(el, { density: 170, dof: 1, bloom: 1, magnet: 1, glyphs: true })
    readyRef.current?.(scene)
    const unsub = subscribe((d) => scene.setDive(d))
    /* 언마운트에서 반드시 멈춘다 — rAF 루프와 document 리스너를 남기면
       로그인 화면을 떠난 뒤에도 매 프레임 돌면서 대시보드를 느리게 만든다 */
    return () => { unsub(); scene.stop() }
  }, [subscribe])

  return <canvas ref={ref} className={styles.net} aria-hidden="true" />
}
