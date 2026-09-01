import type { ReactElement, ReactNode } from 'react'
import { createElement } from 'react'

/* 최소 마크다운 (굵게 · 불릿) — LLM 답변의 **…** 와 "- " 가 생 기호로 노출되던
   것을 그린다. 딱 이 둘만 — 헤딩·링크·코드는 프롬프트에서 막는 게 맞고, 여기서
   더 그리지 않는다. 담당자용 아르(ArChat)와 지원자용 아르(ArScheduleChat) 가
   같이 쓴다. */

export function mdInline(text: string): ReactNode[] {
  return text
    .split(/\*\*(.+?)\*\*/g)
    .map((part, i) => (i % 2 === 1 ? createElement('b', { key: i }, part) : part))
}

export function mdBlocks(text: string): ReactElement[] {
  const out: ReactElement[] = []
  let para: string[] = []
  let list: string[] = []

  const flushPara = () => {
    if (para.length === 0) return
    out.push(createElement('p', { key: out.length }, mdInline(para.join('\n'))))
    para = []
  }
  const flushList = () => {
    if (list.length === 0) return
    out.push(
      createElement(
        'ul',
        { key: out.length },
        list.map((line, i) => createElement('li', { key: i }, mdInline(line))),
      ),
    )
    list = []
  }

  for (const line of text.split('\n')) {
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line)
    if (bullet) {
      flushPara()
      list.push(bullet[1])
    } else if (line.trim() === '') {
      flushPara()
      flushList()
    } else {
      flushList()
      para.push(line)
    }
  }
  flushPara()
  flushList()
  return out
}
