import { useState } from 'react'
import type { Cell, Project } from '../api'
import { Badge, Card, Cite, CredBadge, cx } from '../ui'

const CELL: Record<Cell['overlap'], { cls: string; label: string }> = {
  full: { cls: 'bg-stop-soft text-stop', label: 'done' },
  partial: { cls: 'bg-wait-soft text-wait', label: 'partly' },
  none: { cls: 'bg-go-soft/40 text-go', label: 'open' },
  unverified: { cls: 'bg-sunken text-muted line-through', label: 'unverified' },
}

export default function NoveltyView({ p }: { p: Project }) {
  const [sel, setSel] = useState<{ pid: string; cell: Cell } | null>(null)
  const n = p.novelty
  if (!n) return <p className="text-muted">The novelty matrix appears after the literature review.</p>
  const papers = new Map(p.papers.map((x) => [x.id, x]))
  return (
    <div className="space-y-6">
      <Card className="scroll-thin overflow-x-auto p-6">
        <table className="w-full min-w-[800px] border-separate border-spacing-1 text-sm">
          <thead>
            <tr>
              <th className="w-[34%] text-left align-bottom"><span className="eyebrow">Closest paper</span></th>
              {n.components.map((c) => (
                <th key={c.id} className="align-bottom text-left font-normal">
                  <div className="font-mono text-xs text-muted">{c.id}{c.core ? ' · core' : ''}</div>
                  <div className="line-clamp-3 text-xs">{c.text}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {n.papers.map((r) => {
              const paper = papers.get(r.paper_id)
              return (
                <tr key={r.paper_id}>
                  <td className="rounded-lg bg-sunken/60 p-2 align-top">
                    <div className="flex items-center gap-2"><Cite id={r.paper_id} /><CredBadge c={paper?.credibility} /><Badge>{r.relation}</Badge></div>
                    <div className="mt-1 line-clamp-2 text-xs">{paper?.title}</div>
                    <div className="mt-1 text-[11px] text-muted">Differs: {r.difference}</div>
                  </td>
                  {r.cells.map((c) => (
                    <td key={c.component} className="align-top">
                      <button onClick={() => setSel({ pid: r.paper_id, cell: c })}
                        className={cx('h-full min-h-[64px] w-full rounded-lg p-2 text-left text-xs transition hover:brightness-125', CELL[c.overlap].cls,
                          sel?.pid === r.paper_id && sel.cell.component === c.component && 'ring-2 ring-ink/40')}>
                        <div className="font-semibold">{CELL[c.overlap].label}</div>
                        <div className="mt-0.5 line-clamp-3 opacity-80">{c.note}</div>
                      </button>
                    </td>
                  ))}
                </tr>
              )
            })}
            <tr>
              <td className="p-2 text-xs font-semibold">Best verified overlap</td>
              {n.components.map((c) => <td key={c.id} className="p-2"><Badge tone={c.best === 'full' ? 'stop' : c.best === 'partial' ? 'wait' : 'go'}>{c.best === 'none' ? 'open' : c.best}</Badge></td>)}
            </tr>
          </tbody>
        </table>
        <p className="mt-4 text-xs text-muted">
          Every “done” / “partly” cell needs a verbatim quote from the paper that we found in its text. {n.unverified_claims} claimed overlap(s) had no matching quote and were downgraded to “unverified” (not counted). A second, stricter judge re-checks every “done” cell: same mechanism in a different setting counts as “partly”{n.strict_downgrades ? ` (${n.strict_downgrades} downgraded)` : ''}.
        </p>
      </Card>
      {sel && (
        <Card className="animate-rise p-6">
          <div className="flex items-center gap-2"><Cite id={sel.pid} /><span className="font-mono text-xs text-muted">{sel.cell.component}</span><Badge>{CELL[sel.cell.overlap].label}</Badge>
            {sel.cell.verified && <Badge tone="go">quote verified in paper</Badge>}{sel.cell.claimed && <Badge tone="stop">model claimed “{sel.cell.claimed}” but the quote was not found</Badge>}
            {sel.cell.strict && <Badge tone="wait">strict judge downgraded “full” → {sel.cell.strict.verdict}: {sel.cell.strict.why}</Badge>}</div>
          <p className="mt-3 text-sm">{sel.cell.note}</p>
          {sel.cell.quote && <blockquote className="mt-3 border-l-2 border-line pl-3 text-sm italic text-muted">“{sel.cell.quote}”</blockquote>}
        </Card>
      )}
    </div>
  )
}
