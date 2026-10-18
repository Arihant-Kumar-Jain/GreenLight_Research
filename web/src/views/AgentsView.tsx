import { useMemo, useState } from 'react'
import type { Project, TraceEvent } from '../api'
import { agentStats, plural, researchStats } from '../research'
import { Badge, Card, cx, SectionTitle, type Tone } from '../ui'

type Node = { name: string; parent: string | null; last: number; first: number; done: boolean; depth: number; x: number; y: number }

const KIND: Record<string, { tone: Tone; label: string }> = {
  llm: { tone: 'info', label: 'LLM' }, tool: { tone: 'go', label: 'TOOL' }, source: { tone: 'neutral', label: 'API' },
  spawn: { tone: 'wait', label: 'SPAWN' }, done: { tone: 'go', label: 'DONE' }, compress: { tone: 'wait', label: 'COMPRESS' },
  guard: { tone: 'stop', label: 'GUARD' }, budget: { tone: 'stop', label: 'BUDGET' }, info: { tone: 'neutral', label: 'INFO' },
  error: { tone: 'stop', label: 'ERROR' }, rerank: { tone: 'info', label: 'RERANK' },
}

function color(name: string) {
  if (name.startsWith('Scout')) return 'var(--go)'
  if (/Lead|Orchestrator/.test(name)) return 'var(--info)'
  if (/Critic|Skeptic|Auditor|Checker/.test(name)) return 'var(--stop)'
  if (/Speaker|Proponent|Chamber/.test(name)) return 'var(--wait)'
  return 'var(--muted)'
}

function buildGraph(events: TraceEvent[]) {
  const nodes = new Map<string, Node>()
  for (const e of events) {
    let n = nodes.get(e.agent)
    if (!n) {
      n = { name: e.agent, parent: e.parent && e.parent !== e.agent ? e.parent : null, last: e.ts, first: e.ts, done: false, depth: 0, x: 0, y: 0 }
      nodes.set(e.agent, n)
    }
    n.last = e.ts
    if (e.kind === 'done') n.done = true
  }
  for (const n of nodes.values()) if (n.parent && !nodes.has(n.parent)) n.parent = null
  const depth = (n: Node, seen = 0): number => (n.parent && seen < 8 ? depth(nodes.get(n.parent)!, seen + 1) + 1 : 0)
  const levels: Node[][] = []
  for (const n of [...nodes.values()].sort((a, b) => a.first - b.first)) {
    n.depth = depth(n)
    ;(levels[n.depth] ??= []).push(n)
  }
  const W = 1100
  levels.forEach((lv, d) => lv.forEach((n, i) => { n.x = ((i + 0.5) / lv.length) * W; n.y = 50 + d * 110 }))
  return { nodes: [...nodes.values()], height: 50 + levels.length * 110 }
}

export default function AgentsView({ p, events }: { p: Project; events: TraceEvent[] }) {
  const [filter, setFilter] = useState<string>('all')
  const [agent, setAgent] = useState<string | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const { nodes, height } = useMemo(() => buildGraph(events), [events])
  const now = events.length ? events[events.length - 1].ts : 0
  const byName = new Map(nodes.map((n) => [n.name, n]))
  const r = useMemo(() => researchStats(p, events), [p, events])
  const nodeLabel = (name: string) => {
    const a = agentStats(name, p.papers, events)
    const parts = [a.papers && plural(a.papers, 'paper'), a.searches && plural(a.searches, 'search', 'searches'), a.passages && plural(a.passages, 'passage')]
    return parts.filter(Boolean).join(' · ') || (byName.get(name)?.done ? 'done' : 'working')
  }
  const shown = events.filter((e) => (filter === 'all' || e.kind === filter) && (!agent || e.agent === agent)).slice(-400).reverse()

  return (
    <div className="space-y-6">
      <Card className="overflow-hidden p-0">
        <div className="flex items-center justify-between px-6 pt-5">
          <SectionTitle>Agent swarm · {nodes.length} agents</SectionTitle>
          <div className="flex flex-wrap justify-end gap-x-4 gap-y-1 text-[13px] text-muted">
            <span><b className="font-semibold text-ink">{plural(r.papers, 'paper')}</b> found ({r.relevant} relevant)</span>
            <span><b className="font-semibold text-ink">{r.read}</b> read in full</span>
            <span><b className="font-semibold text-ink">{plural(r.passages, 'passage')}</b> retrieved</span>
            <span><b className="font-semibold text-ink">{plural(r.searches, 'search', 'searches')}</b></span>
            <span><b className="font-semibold text-ink">{plural(r.findings, 'finding')}</b> noted</span>
          </div>
        </div>
        <div className="scroll-thin overflow-x-auto">
          <svg viewBox={`0 0 1100 ${Math.max(height, 160)}`} className="min-w-[900px]" style={{ width: '100%' }}>
            {nodes.filter((n) => n.parent).map((n) => {
              const par = byName.get(n.parent!)!
              const live = p.running && now - n.last < 8 && !n.done
              return <path key={`e-${n.name}`} d={`M${par.x},${par.y + 16} C${par.x},${(par.y + n.y) / 2} ${n.x},${(par.y + n.y) / 2} ${n.x},${n.y - 16}`}
                fill="none" stroke={live ? color(n.name) : 'var(--line)'} strokeWidth={live ? 1.6 : 1.2} className={live ? 'edge-live' : ''} />
            })}
            {nodes.map((n) => {
              const live = p.running && now - n.last < 8 && !n.done
              const sel = agent === n.name
              return (
                <g key={n.name} transform={`translate(${n.x},${n.y})`} className="cursor-pointer" onClick={() => setAgent(sel ? null : n.name)}>
                  {live && <circle r="9" fill="none" stroke={color(n.name)} strokeWidth="2" className="node-pulse" />}
                  <circle r="9" fill={n.done ? color(n.name) : 'var(--surface)'} stroke={color(n.name)} strokeWidth={sel ? 4 : 2} />
                  <text y="-18" textAnchor="middle" fontSize="12" fill="var(--ink)" fontWeight={600}>{n.name.length > 30 ? n.name.slice(0, 29) + '…' : n.name}</text>
                  <text y="28" textAnchor="middle" fontSize="10" fill="var(--muted)">{nodeLabel(n.name)}</text>
                </g>
              )
            })}
            {!nodes.length && <text x="550" y="80" textAnchor="middle" fill="var(--muted)">No agent activity yet.</text>}
          </svg>
        </div>
      </Card>

      <Card className="p-6">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <h3 className="eyebrow mr-2">Live trace</h3>
          {['all', 'llm', 'tool', 'source', 'rerank', 'spawn', 'compress', 'guard', 'error'].map((k) => (
            <button key={k} onClick={() => setFilter(k)} className={cx('rounded-full border px-2.5 py-0.5 text-xs', filter === k ? 'border-go text-go' : 'border-line text-muted')}>{k}</button>
          ))}
          {agent && <button onClick={() => setAgent(null)} className="rounded-full bg-info-soft px-2.5 py-0.5 text-xs text-info">agent: {agent} ✕</button>}
        </div>
        <div className="scroll-thin max-h-[640px] space-y-1 overflow-y-auto font-mono text-[12px]">
          {shown.map((e) => {
            const k = KIND[e.kind] ?? KIND.info
            return (
              <div key={e.id} className="rounded-lg px-2 py-1 hover:bg-sunken">
                <button className="flex w-full items-start gap-2 text-left" onClick={() => setOpen(open === e.id ? null : e.id)}>
                  <span className="w-14 shrink-0 text-muted">{new Date(e.ts * 1000).toLocaleTimeString([], { hour12: false })}</span>
                  <Badge tone={k.tone} className="w-[70px] justify-center">{k.label}</Badge>
                  <span className="w-48 shrink-0 truncate" style={{ color: color(e.agent) }}>{e.agent}</span>
                  <span className="min-w-0 flex-1 truncate text-ink">{e.title}</span>
                  <span className="shrink-0 text-muted">
                    {e.kind === 'llm' && e.latency_ms != null && `${(e.latency_ms / 1000).toFixed(1)}s`}
                    {(e.kind === 'tool' || e.kind === 'source') && e.latency_ms != null && `${(e.latency_ms / 1000).toFixed(1)}s`}
                  </span>
                </button>
                {open === e.id && (
                  <div className="ml-16 mt-1 whitespace-pre-wrap break-words rounded-lg bg-sunken p-3 text-[11.5px] text-muted">
                    {e.model && <div className="mb-1 text-info">{e.provider}: {e.model}</div>}
                    {e.detail || '(no detail)'}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </Card>
    </div>
  )
}
