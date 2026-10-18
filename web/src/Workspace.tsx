import { Activity, BookOpen, Bot, Check, FileText, Grid3x3, Loader2, MessagesSquare, NotebookPen, Orbit, RotateCcw, Scale, Share2, Sparkles, Square } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type Project, type TraceEvent } from './api'
import { Logo } from './Home'
import TrafficLight from './TrafficLight'
import { Badge, Button, Card, cx, LIGHT, Markdown, PaperCtx, SectionTitle } from './ui'
import AgentsView from './views/AgentsView'
import ChamberView from './views/ChamberView'
import ChatView from './views/ChatView'
import NoveltyView from './views/NoveltyView'
import PapersView, { PaperDrawer } from './views/PapersView'
import ReportView from './views/ReportView'
import GraphView from './views/GraphView'

const PaperGalaxy = lazy(() => import('./three/PaperGalaxy'))

const TABS = [
  { id: 'overview', label: 'Verdict', icon: Sparkles },
  { id: 'agents', label: 'Agents (live)', icon: Bot },
  { id: 'galaxy', label: 'Paper galaxy', icon: Orbit },
  { id: 'graph', label: 'Relationship graph', icon: Share2 },
  { id: 'papers', label: 'Papers', icon: BookOpen },
  { id: 'novelty', label: 'Novelty matrix', icon: Grid3x3 },
  { id: 'chamber', label: 'Chamber', icon: Scale },
  { id: 'report', label: 'Report', icon: FileText },
  { id: 'chat', label: 'Chat', icon: MessagesSquare },
  { id: 'notebook', label: 'Notebook', icon: NotebookPen },
]

const STAGES = [
  ['plan', 'Plan'], ['research', 'Agent swarm research'], ['credibility', 'Read + score credibility'],
  ['novelty', 'Novelty matrix'], ['chamber', 'Chamber debate'], ['report', 'Report + citation check'],
] as const

function Stepper({ p }: { p: Project }) {
  const idx = p.status === 'done' ? STAGES.length : Math.max(0, STAGES.findIndex(([s]) => s === p.stage))
  return (
    <div className="flex flex-wrap gap-2">
      {STAGES.map(([s, label], i) => (
        <div key={s} className={cx('flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs',
          i < idx ? 'border-go/30 text-go' : i === idx && p.status !== 'error' ? 'border-info/40 text-info' : 'border-line text-muted')}>
          {i < idx ? <Check size={12} /> : i === idx && p.running ? <Loader2 size={12} className="animate-spin" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
          {label}
        </div>
      ))}
    </div>
  )
}

function Overview({ p, events }: { p: Project; events: TraceEvent[] }) {
  const v = p.verdict
  const review = p.stats?.review
  const latest = events.filter((e) => ['info', 'guard', 'spawn', 'done'].includes(e.kind)).slice(-6).reverse()
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <div className="space-y-6">
        {!v && (
          <Card className="p-6">
            <SectionTitle>Progress</SectionTitle>
            <Stepper p={p} />
            {p.status === 'error' && <p className="mt-4 text-sm text-stop">{p.error}</p>}
            <div className="mt-5 space-y-2">
              {latest.map((e) => (
                <div key={e.id} className="animate-rise text-sm"><span className="text-muted">{e.agent} · </span>{e.title}</div>
              ))}
            </div>
          </Card>
        )}
        {v && (
          <Card className="p-6">
            <SectionTitle right={<Badge tone={v.light === 'green' ? 'go' : v.light === 'amber' ? 'wait' : 'stop'}>{LIGHT[v.light].call}</Badge>}>Why this verdict</SectionTitle>
            <ul className="space-y-2 text-[15px]">{v.reasons.map((r, i) => <li key={i} className="flex gap-2"><span className="text-muted">{i + 1}.</span><Markdown text={r} className="[&_p]:m-0" /></li>)}</ul>
            {v.guardrails.length > 0 && (
              <div className="mt-5 rounded-xl border border-wait/30 bg-wait-soft/40 p-4 text-sm">
                <div className="mb-1 font-semibold text-wait">Guardrail applied: the Speaker said {v.speaker_light.toUpperCase()}, evidence rules made it {v.light.toUpperCase()}</div>
                {v.guardrails.map((g, i) => <Markdown key={i} text={g.why} className="[&_p]:m-0" />)}
                <div className="mt-2 text-xs text-muted">Speaker's original call: “{v.speaker_headline}”</div>
              </div>
            )}
          </Card>
        )}
        {v && (
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="p-6"><SectionTitle>How to make it novel</SectionTitle><ul className="list-disc space-y-1.5 pl-4 text-sm">{v.differentiation.map((d, i) => <li key={i}><Markdown text={d} className="[&_p]:m-0" /></li>)}</ul></Card>
            <Card className="p-6"><SectionTitle>Next steps</SectionTitle><ul className="list-disc space-y-1.5 pl-4 text-sm">{v.next_steps.map((d, i) => <li key={i}><Markdown text={d} className="[&_p]:m-0" /></li>)}</ul></Card>
          </div>
        )}
        {review && (
          <Card className="p-6">
            <SectionTitle right={<span className="text-xs text-muted">{review.rounds} round(s) · {review.scouts} scouts · confidence {review.confidence}</span>}>Literature review</SectionTitle>
            <Markdown text={review.synthesis} />
            {review.coverage.length > 0 && (
              <div className="mt-4 space-y-2">
                {review.coverage.map((c) => {
                  const comp = p.plan?.components.find((x) => x.id === c.component)
                  return (
                    <div key={c.component} className="flex items-start gap-3 text-sm">
                      <Badge tone={c.status === 'open' ? 'go' : c.status === 'partially' ? 'wait' : 'stop'}>{c.status}</Badge>
                      <div><span className="font-mono text-xs text-muted">{c.component}</span> {comp?.text} {c.papers.length > 0 && <Markdown text={`[${c.papers.join(', ')}]`} className="inline [&_p]:inline" />}</div>
                    </div>
                  )
                })}
              </div>
            )}
          </Card>
        )}
      </div>
      <div className="space-y-6">
        {p.novelty && (
          <Card className="p-6">
            <SectionTitle>Novelty score</SectionTitle>
            <div className="font-display text-6xl">{p.novelty.score ?? '–'}<span className="text-2xl text-muted">/100</span></div>
            <p className="mt-2 text-xs text-muted">Share of the idea's components (core weighted ×2) not covered by prior work, counting only overlaps backed by a verified quote.</p>
            {p.novelty.already_done_by.length > 0 && <div className="mt-3 text-sm text-stop">Covers every core component: <Markdown className="inline [&_p]:inline" text={`[${p.novelty.already_done_by.map((d) => d.paper_id).join(', ')}]`} /></div>}
          </Card>
        )}
        {p.plan && (
          <Card className="p-6">
            <SectionTitle>Idea components tested</SectionTitle>
            <div className="space-y-2 text-sm">{p.plan.components.map((c) => <div key={c.id}><span className="font-mono text-xs text-muted">{c.id}{c.core ? '*' : ''}</span> {c.text}</div>)}</div>
          </Card>
        )}
        <Card className="p-6">
          <SectionTitle>Run</SectionTitle>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Stat k="Papers" v={p.papers.length} /><Stat k="Agents" v={p.totals.agents} />
            <Stat k="LLM calls" v={p.totals.llm_calls} /><Stat k="Tool calls" v={p.totals.tool_calls} />
            <Stat k="Compressions" v={p.totals.compressions} /><Stat k="Cost" v={`$${p.totals.cost_usd.toFixed(3)}`} />
          </div>
          {p.totals.by_model.length > 0 && (
            <div className="mt-4 space-y-1 text-xs text-muted">
              {p.totals.by_model.map((m) => <div key={m.model} className="flex justify-between gap-2"><span className="truncate">{m.model}</span><span>{m.calls} calls · ${m.cost.toFixed(4)}</span></div>)}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

function Stat({ k, v }: { k: string; v: string | number }) {
  return <div className="rounded-xl bg-sunken px-3 py-2"><div className="text-[11px] text-muted">{k}</div><div className="font-semibold">{v}</div></div>
}

function NotebookView({ p }: { p: Project }) {
  if (!p.notes.length) return <p className="text-muted">Agents write findings here as they work.</p>
  return (
    <div className="space-y-2">
      {p.notes.map((n) => (
        <Card key={n.id} className="flex items-start gap-3 p-4 text-sm">
          <Badge tone={n.kind === 'gap' ? 'go' : n.kind === 'finding' ? 'info' : 'neutral'}>{n.kind}</Badge>
          <div className="flex-1"><Markdown text={n.text + (n.refs.length ? ` [${n.refs.join(', ')}]` : '')} className="[&_p]:m-0" /></div>
          <span className="whitespace-nowrap text-xs text-muted">{n.agent}</span>
        </Card>
      ))}
    </div>
  )
}

export default function Workspace({ id, tab }: { id: string; tab: string }) {
  const [p, setP] = useState<Project | null>(null)
  const [events, setEvents] = useState<TraceEvent[]>([])
  const [err, setErr] = useState('')
  const [drawer, setDrawer] = useState<string | null>(null)
  const [chatBusy, setChatBusy] = useState(false)
  const cursor = useRef(0)

  const load = useCallback(async () => {
    try {
      const [proj, tr] = await Promise.all([api.project(id), api.trace(id, cursor.current)])
      setP(proj)
      if (tr.events.length) {
        cursor.current = tr.events[tr.events.length - 1].id
        setEvents((ev) => {
          const seen = new Set(ev.map((e) => e.id))
          return [...ev, ...tr.events.filter((e) => !seen.has(e.id))].slice(-3000)
        })
      }
    } catch (e) { setErr((e as Error).message) }
  }, [id])

  const live = !!p && (p.running || p.status === 'queued' || chatBusy)
  useEffect(() => {
    load()
    const t = setInterval(load, live ? 1500 : 6000)
    return () => clearInterval(t)
  }, [load, live])

  const known = useMemo(() => new Set(p?.papers.map((x) => x.id) ?? []), [p?.papers])
  const ctx = useMemo(() => ({ open: setDrawer, known }), [known])

  if (err && !p) return <div className="p-10 text-stop">{err}</div>
  if (!p) return <div className="grid h-screen place-items-center text-muted"><Loader2 className="animate-spin" /></div>
  const v = p.verdict
  const paper = drawer ? p.papers.find((x) => x.id === drawer) : null

  return (
    <PaperCtx.Provider value={ctx}>
      <div className="min-h-screen">
        <nav className="flex items-center justify-between border-b border-line px-6 py-3">
          <Logo />
          <div className="flex items-center gap-2">
            {p.running && <Badge tone="info"><Activity size={11} className="animate-glow" /> agents working</Badge>}
            {p.running && <Button variant="ghost" onClick={async () => { await api.stop(id).catch(() => {}); load() }}><Square size={13} /> Stop</Button>}
            {!p.running && p.status !== 'draft' && <Button variant="ghost" onClick={async () => { await api.rerun(id); cursor.current = 0; setEvents([]); load() }}><RotateCcw size={14} /> Re-run</Button>}
          </div>
        </nav>
        <header className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-8 px-6 pt-8">
          <TrafficLight verdict={v?.light ?? null} analyzing={p.running || p.status === 'queued'} size={150} />
          <div className="min-w-0 flex-1">
            <div className="eyebrow mb-2">{p.brief?.field || 'Research idea'}</div>
            <h1 className="font-display text-4xl leading-tight">{p.title || p.brief?.title || p.idea_text.slice(0, 80)}</h1>
            {v ? (
              <div className={cx('mt-3 max-w-3xl text-lg', LIGHT[v.light].text)}><Markdown text={v.headline} className="[&_p]:m-0" /></div>
            ) : (
              <p className="mt-3 text-muted">{p.status === 'error' ? `Failed: ${p.error}` : p.running ? 'The agents are researching. Watch them in Agents (live).' : 'Not started.'}</p>
            )}
            {v && <div className="mt-2 text-sm text-muted">Speaker confidence {Math.round((v.confidence ?? 0) * 100)}% · {p.papers.length} papers · novelty {p.novelty?.score ?? '–'}/100</div>}
          </div>
        </header>
        <div className="sticky top-0 z-20 mt-6 border-b border-line bg-bg/90 backdrop-blur">
          <div className="scroll-thin mx-auto flex max-w-[1500px] gap-1 overflow-x-auto px-6">
            {TABS.map((t) => (
              <a key={t.id} href={`#/p/${id}/${t.id}`}
                className={cx('flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-3 text-sm transition',
                  tab === t.id ? 'border-go text-ink' : 'border-transparent text-muted hover:text-ink')}>
                <t.icon size={14} /> {t.label}
                {t.id === 'papers' && <span className="text-xs text-muted">{p.papers.length}</span>}
              </a>
            ))}
          </div>
        </div>
        <main className="mx-auto max-w-[1500px] px-6 py-8">
          {tab === 'overview' && <Overview p={p} events={events} />}
          {tab === 'agents' && <AgentsView p={p} events={events} />}
          {tab === 'galaxy' && (
            <div>
              <Suspense fallback={<div className="h-[72vh]" />}>
                <PaperGalaxy papers={p.papers} closest={p.stats?.review?.closest ?? []} light={v?.light ?? null} onOpen={setDrawer}
                  className="h-[72vh] min-h-[520px] overflow-hidden rounded-3xl border border-line bg-[radial-gradient(ellipse_at_center,#0d1712_0%,#050806_70%)]" />
              </Suspense>
              <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-muted">
                <span>Orbit = closeness to your idea (inner: same idea → very close → related → background → unranked)</span>
                <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-go" />credibility ≥72</span>
                <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-info" />55–71</span>
                <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-wait" />38–54</span>
                <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-stop" />&lt;38 / retracted</span>
                <span>size = citations · drag to orbit · scroll to zoom · click a paper</span>
              </div>
            </div>
          )}
          {tab === 'graph' && <GraphView p={p} onOpen={setDrawer} />}
          {tab === 'papers' && <PapersView p={p} onOpen={setDrawer} />}
          {tab === 'novelty' && <NoveltyView p={p} />}
          {tab === 'chamber' && <ChamberView p={p} />}
          {tab === 'report' && <ReportView p={p} />}
          {tab === 'chat' && <ChatView p={p} events={events} onBusy={setChatBusy} />}
          {tab === 'notebook' && <NotebookView p={p} />}
        </main>
        {paper && <PaperDrawer paper={paper} projectId={id} onClose={() => setDrawer(null)} onUpdate={load} />}
      </div>
    </PaperCtx.Provider>
  )
}
