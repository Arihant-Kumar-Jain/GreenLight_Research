import { ArrowRight, Loader2, RefreshCw, Sparkles } from 'lucide-react'
import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { api, type GraphData, type GraphEdge, type Project } from '../api'
import { CLUSTER_COLORS, type EdgeKind } from '../three/PaperGraph'
import { Badge, Button, Card, Cite, CredBadge, cx, SectionTitle } from '../ui'

const PaperGraph = lazy(() => import('../three/PaperGraph'))
const hex = (n: number) => `#${n.toString(16).padStart(6, '0')}`

function describe(e: GraphEdge, me: string) {
  if (e.type === 'cites') return e.source === me ? 'cites' : 'is cited by'
  if (e.type === 'similar') return `similar (${e.weight?.toFixed(2)})`
  return e.relation ?? 'related to idea'
}

function Relation({ p, e, me }: { p: Project; e: GraphEdge; me: string }) {
  const other = e.source === me ? e.target : e.source
  const [text, setText] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const facts = e.type === 'cites' ? `${e.source} cites ${e.target} (reference: ${e.evidence ?? ''})` : e.type === 'similar' ? `abstract embeddings similar, cosine ${e.weight}` : ''
  return (
    <div className="rounded-xl bg-sunken p-3 text-sm">
      <div className="flex items-center gap-2">
        <Badge tone={e.type === 'cites' ? 'go' : e.type === 'similar' ? 'info' : 'wait'}>{describe(e, me)}</Badge>
        <Cite id={other} />
        <span className="min-w-0 flex-1 truncate text-xs text-muted">{p.papers.find((x) => x.id === other)?.title}</span>
      </div>
      {e.type === 'cites' && e.evidence && <div className="mt-2 border-l-2 border-line pl-2 text-[11px] italic text-muted">“{e.evidence}” <span className="not-italic">· via {e.via}</span></div>}
      {text ? <p className="mt-2 text-[13px] leading-relaxed">{text}</p> : (
        <button disabled={busy} onClick={async () => { setBusy(true); setText((await api.explain(p.id, me, other, facts).catch(() => ({ text: 'Failed.' }))).text); setBusy(false) }}
          className="mt-2 inline-flex items-center gap-1 text-xs text-info hover:underline">
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} Explain how they relate
        </button>
      )}
    </div>
  )
}

export default function GraphView({ p, onOpen }: { p: Project; onOpen: (id: string) => void }) {
  const [g, setG] = useState<GraphData | null>(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)
  const [colorBy, setColorBy] = useState<'cluster' | 'credibility'>('cluster')
  const [show, setShow] = useState<Record<EdgeKind, boolean>>({ cites: true, similar: true, idea: true })
  const [selected, setSelected] = useState<string | null>(null)
  const [cluster, setCluster] = useState<number | null>(null)

  const load = async (refresh = false) => {
    setLoading(true); setErr('')
    try { setG(await api.graph(p.id, refresh)) } catch (e) { setErr((e as Error).message) }
    setLoading(false)
  }
  useEffect(() => { if (p.status === 'done') load() }, [p.id, p.status]) // eslint-disable-line

  const links = useMemo(() => (g && selected ? g.edges.filter((e) => e.source === selected || e.target === selected)
    .sort((a, b) => ['cites', 'idea', 'similar'].indexOf(a.type) - ['cites', 'idea', 'similar'].indexOf(b.type)) : []), [g, selected])
  const sel = selected ? p.papers.find((x) => x.id === selected) : null
  const selNode = g?.nodes.find((n) => n.id === selected)

  if (p.status !== 'done' && !g) return <p className="text-muted">The relationship graph is built once the research run finishes.</p>
  if (!g) return (
    <div className="grid h-[60vh] place-items-center text-center text-muted">
      <div>{loading ? <><Loader2 className="mx-auto animate-spin" /><p className="mt-3 text-sm">Reading reference lists (Semantic Scholar · OpenAlex · arXiv bibliographies)…</p></> : <p className="text-stop">{err}</p>}</div>
    </div>
  )

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_400px]">
      <div>
        <Suspense fallback={<div className="h-[74vh]" />}>
          <PaperGraph data={g} colorBy={colorBy} show={show} selected={selected} cluster={cluster} onSelect={(id) => { setSelected(id); if (id) setCluster(null) }}
            className="h-[74vh] min-h-[560px] overflow-hidden rounded-3xl border border-line bg-[radial-gradient(ellipse_at_center,#0d1712_0%,#050806_70%)]" />
        </Suspense>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
          {(['cites', 'similar', 'idea'] as EdgeKind[]).map((k) => (
            <button key={k} onClick={() => setShow({ ...show, [k]: !show[k] })}
              className={cx('flex items-center gap-1.5 rounded-full border px-2.5 py-1', show[k] ? 'border-line text-ink' : 'border-line/50 opacity-40')}>
              <i className={cx('h-0.5 w-4', k === 'cites' ? 'bg-go' : k === 'similar' ? 'bg-info' : 'bg-wait')} />
              {k === 'cites' ? `cites (${g.stats.cites})` : k === 'similar' ? `similar (${g.stats.similar})` : 'closest to your idea'}
            </button>
          ))}
          <span className="ml-2">Colour:</span>
          {(['cluster', 'credibility'] as const).map((c) => (
            <button key={c} onClick={() => setColorBy(c)} className={cx('rounded-full border px-2.5 py-1', colorBy === c ? 'border-go text-go' : 'border-line')}>{c}</button>
          ))}
          <span className="ml-auto">particles flow citing → cited · drag · scroll · click a paper</span>
        </div>
      </div>

      <div className="space-y-5">
        <Card className="p-5">
          <SectionTitle right={<Button variant="ghost" onClick={() => load(true)} disabled={loading}><RefreshCw size={13} className={loading ? 'animate-spin' : ''} /></Button>}>Research map</SectionTitle>
          <p className="text-xs text-muted">{g.nodes.length} papers · reference lists from {Object.entries(g.stats.refs_via).map(([k, v]) => `${k} ${v}`).join(', ')}</p>
          <div className="mt-3 space-y-1.5">
            {g.clusters.map((c) => (
              <button key={c.id} onClick={() => { setCluster(cluster === c.id ? null : c.id); setSelected(null) }}
                className={cx('flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-sunken', cluster === c.id && 'bg-sunken ring-1 ring-line')}>
                <i className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: hex(CLUSTER_COLORS[c.id % 9]) }} />
                <span className="flex-1 truncate">{c.label}</span><span className="text-xs text-muted">{c.size}</span>
              </button>
            ))}
          </div>
        </Card>

        {sel && selNode ? (
          <Card className="animate-rise p-5">
            <div className="flex items-center gap-2"><span className="font-mono text-xs text-info">{sel.id}</span><CredBadge c={sel.credibility} />
              {selNode.relation && <Badge tone="wait">{selNode.relation}</Badge>}</div>
            <div className="mt-2 font-medium leading-snug">{sel.title}</div>
            <div className="mt-1 text-xs text-muted">{sel.year} · {sel.citations ?? '?'} citations · {selNode.n_refs} references read via {selNode.refs_via ?? 'n/a'}</div>
            <Button variant="outline" className="mt-3 w-full" onClick={() => onOpen(sel.id)}>Open paper <ArrowRight size={14} /></Button>
            <h4 className="eyebrow mb-2 mt-5">Links ({links.length})</h4>
            <div className="scroll-thin max-h-[46vh] space-y-2 overflow-y-auto pr-1">
              {links.map((e, i) => e.type === 'idea'
                ? <div key={i} className="rounded-xl bg-wait-soft/40 p-3 text-sm"><Badge tone="wait">{e.relation}</Badge><p className="mt-1 text-xs">{e.evidence}</p></div>
                : <Relation key={`${e.source}-${e.target}-${e.type}`} p={p} e={e} me={sel.id} />)}
            </div>
          </Card>
        ) : (
          <Card className="p-5 text-sm text-muted">Click a paper to see who it cites, who cites it and what it resembles, each with the evidence, and ask the agent to explain any link.</Card>
        )}
      </div>
    </div>
  )
}
