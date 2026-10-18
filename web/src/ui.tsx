import { createContext, useContext, type ReactNode } from 'react'
import type { Credibility, Light } from './api'

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(' ')
}

export const LIGHT = {
  green: { text: 'text-go', bg: 'bg-go', soft: 'bg-go-soft', word: 'Green', call: 'Novel: pursue it' },
  amber: { text: 'text-wait', bg: 'bg-wait', soft: 'bg-wait-soft', word: 'Amber', call: 'Partly done: differentiate' },
  red: { text: 'text-stop', bg: 'bg-stop', soft: 'bg-stop-soft', word: 'Red', call: 'Already done / not worth it' },
} satisfies Record<Light, Record<string, string>>

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx('rounded-2xl border border-line bg-surface', className)}>{children}</div>
}

export function SectionTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <h3 className="eyebrow">{children}</h3>
      {right}
    </div>
  )
}

export type Tone = 'go' | 'wait' | 'stop' | 'info' | 'neutral'
const TONES: Record<Tone, string> = {
  go: 'bg-go-soft text-go', wait: 'bg-wait-soft text-wait', stop: 'bg-stop-soft text-stop',
  info: 'bg-info-soft text-info', neutral: 'bg-sunken text-muted',
}

export function Badge({ tone = 'neutral', children, className, title }: { tone?: Tone; children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cx('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap', TONES[tone], className)}>
      {children}
    </span>
  )
}

export function Button({ children, onClick, variant = 'primary', disabled, className, type = 'button', title }: {
  children: ReactNode; onClick?: () => void; variant?: 'primary' | 'ghost' | 'outline'; disabled?: boolean
  className?: string; type?: 'button' | 'submit'; title?: string
}) {
  const v = {
    primary: 'bg-go text-on-go hover:brightness-110',
    ghost: 'text-muted hover:text-ink hover:bg-sunken',
    outline: 'border border-line text-ink hover:bg-sunken',
  }[variant]
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled}
      className={cx('inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-40', v, className)}>
      {children}
    </button>
  )
}

export function credTone(c: Credibility | null | undefined): Tone {
  if (!c) return 'neutral'
  if (c.retracted) return 'stop'
  // Low confidence (e.g. too new to have citations): the score is a lower bound, so don't paint it as a warning.
  if (c.confidence === 'low') return 'neutral'
  return c.score >= 72 ? 'go' : c.score >= 55 ? 'info' : c.score >= 38 ? 'wait' : 'stop'
}

export function CredBadge({ c, onClick }: { c: Credibility | null | undefined; onClick?: () => void }) {
  if (!c) return <Badge title="Not scored yet">cred –</Badge>
  return (
    <button onClick={onClick} className="inline-flex"
      title={`Credibility ${c.score}/100, ${c.tier}, confidence ${c.confidence}${c.confidence === 'low' ? ': too little citation data to judge (often a new paper), so treat it as a lower bound' : ''}`}>
      <Badge tone={credTone(c)}>{c.retracted ? 'RETRACTED' : `${c.confidence === 'low' ? '~' : ''}${c.score}`}<span className="font-normal opacity-70">/100</span></Badge>
    </button>
  )
}

export function Meter({ value, tone = 'go' }: { value: number; tone?: Tone }) {
  const bar = { go: 'bg-go', wait: 'bg-wait', stop: 'bg-stop', info: 'bg-info', neutral: 'bg-muted' }[tone]
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-sunken">
      <div className={cx('h-full rounded-full transition-all duration-700', bar)} style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />
    </div>
  )
}

export function Typing() {
  return <span className="typing inline-flex gap-1 text-muted"><span>●</span><span>●</span><span>●</span></span>
}

// ---------------------------------------------------------------- paper drawer context (citation chips open it)

export const PaperCtx = createContext<{ open: (id: string) => void; known: Set<string> }>({ open: () => {}, known: new Set() })

export function Cite({ id }: { id: string }) {
  const { open, known } = useContext(PaperCtx)
  const ok = known.has(id)
  return (
    <button onClick={() => ok && open(id)} title={ok ? 'Open paper' : 'Unknown paper id'}
      className={cx('mx-0.5 inline-flex items-center rounded-md px-1.5 py-px align-baseline font-mono text-[11px] font-semibold',
        ok ? 'bg-info-soft text-info hover:brightness-125' : 'bg-stop-soft text-stop line-through')}>
      {id}
    </button>
  )
}

// ---------------------------------------------------------------- safe Markdown (no HTML injection)

const INLINE = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\[(?:P\d+(?:\s*[,;]\s*P\d+)*)\]|\[[^\]]+\]\((?:https?:\/\/)[^)\s]+\)|⚠️)/g

function inline(text: string, key = 0): ReactNode[] {
  // A fresh regex per call: inline() recurses for **bold** / *em*, and a shared /g regex's lastIndex would be reset by
  // the inner call, making the outer loop find the same match forever (froze the Report tab).
  const re = new RegExp(INLINE.source, 'g')
  const out: ReactNode[] = []
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const t = m[0]
    const k = `${key}-${m.index}`
    if (t.startsWith('**')) out.push(<strong key={k}>{inline(t.slice(2, -2), m.index)}</strong>)
    else if (t.startsWith('`')) out.push(<code key={k}>{t.slice(1, -1)}</code>)
    else if (/^\[P\d/.test(t)) out.push(<span key={k}>{t.slice(1, -1).split(/\s*[,;]\s*/).map((id) => <Cite key={id} id={id} />)}</span>)
    else if (t.startsWith('[')) {
      const mm = t.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
      out.push(mm ? <a key={k} href={mm[2]} target="_blank" rel="noreferrer">{mm[1]}</a> : t)
    } else if (t === '⚠️') out.push(<span key={k} className="text-wait">⚠️</span>)
    else out.push(<em key={k}>{inline(t.slice(1, -1), m.index)}</em>)
    last = m.index + t.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export function Markdown({ text, className }: { text: string; className?: string }) {
  const lines = (text || '').replace(/\r/g, '').split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const l = lines[i]
    if (!l.trim()) { i++; continue }
    const h = l.match(/^(#{1,4})\s+(.*)/)
    if (h) {
      blocks.push(h[1].length <= 2 ? <h2 key={i}>{inline(h[2], i)}</h2> : <h3 key={i}>{inline(h[2], i)}</h3>)
      i++; continue
    }
    if (/^\s*\|/.test(l)) {
      const rows: string[][] = []
      while (i < lines.length && /^\s*\|/.test(lines[i])) {
        if (!/^\s*\|[\s:|-]+\|\s*$/.test(lines[i])) rows.push(lines[i].trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim()))
        i++
      }
      blocks.push(
        <div key={`t${i}`} className="overflow-x-auto"><table><thead><tr>{rows[0]?.map((c, j) => <th key={j}>{inline(c, j)}</th>)}</tr></thead>
          <tbody>{rows.slice(1).map((r, ri) => <tr key={ri}>{r.map((c, j) => <td key={j}>{inline(c, j)}</td>)}</tr>)}</tbody></table></div>)
      continue
    }
    if (/^\s*([-*•]|\d+[.)])\s+/.test(l)) {
      const ordered = /^\s*\d/.test(l)
      const items: string[] = []
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*•]|\d+[.)])\s+/, ''))
        i++
      }
      const lis = items.map((it, j) => <li key={j}>{inline(it, j)}</li>)
      blocks.push(ordered ? <ol key={`l${i}`}>{lis}</ol> : <ul key={`l${i}`}>{lis}</ul>)
      continue
    }
    if (l.startsWith('>')) {
      const q: string[] = []
      while (i < lines.length && lines[i].startsWith('>')) { q.push(lines[i].replace(/^>\s?/, '')); i++ }
      blocks.push(<blockquote key={`q${i}`}>{inline(q.join(' '), i)}</blockquote>)
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\s*\||\s*([-*•]|\d+[.)])\s+|>)/.test(lines[i])) { para.push(lines[i]); i++ }
    if (!para.length) { para.push(lines[i]); i++ } // never stall on a line no rule claimed
    blocks.push(<p key={`p${i}`}>{inline(para.join(' '), i)}</p>)
  }
  return <div className={cx('md', className)}>{blocks}</div>
}

export function timeAgo(ts: number) {
  const s = Date.now() / 1000 - ts
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}
