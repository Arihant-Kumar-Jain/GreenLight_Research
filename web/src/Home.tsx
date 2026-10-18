import { ArrowUp, BookOpenCheck, Bot, FlaskConical, GitBranch, Scale, ShieldCheck, Trash2 } from 'lucide-react'
import { lazy, Suspense, useEffect, useState } from 'react'
import { go } from './App'
import { api, type Health, type ProjectSummary } from './api'
import { Badge, Card, cx, LIGHT, timeAgo } from './ui'

const Constellation = lazy(() => import('./three/Constellation'))

export function Logo() {
  return (
    <a href="#/" className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" width="26" height="26"><rect x="9" y="2" width="14" height="28" rx="7" fill="#14201a" stroke="#2a3a31" /><circle cx="16" cy="9" r="3.2" fill="#444" /><circle cx="16" cy="16" r="3.2" fill="#444" /><circle cx="16" cy="23" r="3.6" fill="#3ee07f" /></svg>
      <span className="font-display text-xl tracking-tight">GreenLight <span className="italic text-go">Research</span></span>
    </a>
  )
}

const FEATURES = [
  { icon: Bot, title: 'Agent swarm', text: 'A Lead Researcher dispatches parallel Scouts over arXiv, OpenAlex, Hugging Face, the live web (Tavily) and the citation graph.' },
  { icon: Scale, title: 'Research Chamber', text: 'A Proponent and a Skeptic debate your idea from evidence; Nemotron Ultra rules green / amber / red.' },
  { icon: ShieldCheck, title: 'Credibility per paper', text: 'Citations, author h-index, venue, adoption and audited red flags → a transparent 0–100 score.' },
  { icon: BookOpenCheck, title: 'Verified citations', text: 'Novelty overlaps must quote the paper; every report claim is checked against the cited text.' },
  { icon: GitBranch, title: 'Context engineering', text: 'Tiered compression, a shared notebook, budgets and loop guards keep long agent runs sharp and cheap.' },
  { icon: FlaskConical, title: 'Keep talking', text: 'Chat back and forth with the research agent: it remembers, searches more and re-scores as you go.' },
]

export default function Home() {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    api.projects().then(setProjects).catch(() => {})
    api.health().then(setHealth).catch(() => {})
  }, [])

  async function submit() {
    if (text.trim().length < 10 || busy) return
    setBusy(true)
    setErr('')
    try {
      const v = await api.newProject(text)
      go(`/p/${v.project.id}/intake`)
    } catch (e) {
      setErr((e as Error).message)
      setBusy(false)
    }
  }

  async function remove(id: string) {
    await api.remove(id).catch(() => {})
    setProjects((ps) => ps.filter((p) => p.id !== id))
  }

  const models = health?.models
  const modelName = (r: string) => (models && typeof models[r] === 'object' ? (models[r] as { name: string }).name : null)

  return (
    <div className="relative min-h-screen overflow-x-hidden">
      <Suspense fallback={null}>
        <Constellation className="pointer-events-none absolute inset-x-0 top-0 h-[980px] opacity-90 [mask-image:linear-gradient(to_bottom,black_55%,transparent)]" />
      </Suspense>
      <nav className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <Logo />
        <div className="flex items-center gap-3 text-xs text-muted">
          <a href="#/proof" className="hover:text-ink">Proof</a>
          {health && (health.missing_keys.length
            ? <Badge tone="stop">Missing: {health.missing_keys.join(', ')}</Badge>
            : <Badge tone="go">{health.llm_provider} · Tavily ready</Badge>)}
        </div>
      </nav>

      <main className="relative z-10 mx-auto max-w-6xl px-6">
        <section className="pb-10 pt-[300px] text-center md:pt-[340px]">
          <div className="eyebrow mb-5">Deep research · NVIDIA Nemotron on Nebius</div>
          <h1 className="mx-auto max-w-3xl font-display text-5xl leading-[1.05] tracking-tight md:text-6xl">
            Has your research idea <span className="italic text-go">already been done?</span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-muted">
            Describe it. A swarm of agents reads the literature, scores every paper's credibility, maps your idea against
            the closest work component by component, debates it, and tells you green, amber or red, with sources.
          </p>

          <Card className="mx-auto mt-10 max-w-3xl border-go/20 bg-surface/80 p-2 text-left shadow-[0_0_80px_-30px_var(--go)] backdrop-blur-xl">
            <textarea
              value={text} onChange={(e) => setText(e.target.value)} rows={4}
              onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit() }}
              placeholder="e.g. Route each token to a mixture of LoRA adapters with a learned gate, to fine-tune one LLM for many tasks without interference…"
              className="w-full resize-none bg-transparent px-4 py-3 text-[15px] outline-none placeholder:text-muted/60"
            />
            <div className="flex items-center justify-between px-3 pb-2">
              <span className="text-xs text-muted">Personal data is redacted before anything leaves your machine. ⌘↵ to send</span>
              <button onClick={submit} disabled={busy || text.trim().length < 10}
                className="grid h-9 w-9 place-items-center rounded-xl bg-go text-[#05210f] transition disabled:opacity-30">
                <ArrowUp size={18} />
              </button>
            </div>
          </Card>
          {err && <p className="mt-3 text-sm text-stop">{err}</p>}
          {models && (
            <p className="mt-4 text-xs text-muted">
              Models: {['fast', 'reason', 'judge', 'embed'].map((r) => modelName(r)).filter(Boolean).join(' · ')}
            </p>
          )}
        </section>

        {projects.length > 0 && (
          <section className="pb-14">
            <h3 className="eyebrow mb-4">Your research</h3>
            <div className="grid gap-3 md:grid-cols-2">
              {projects.map((p) => (
                <Card key={p.id} className="group flex items-start gap-3 p-4 transition hover:border-go/40">
                  <span className={cx('mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full', p.light ? LIGHT[p.light].bg : 'bg-line',
                    (p.status === 'running' || p.status === 'queued') && 'animate-glow bg-info')} />
                  <a href={p.status === 'draft' ? `#/p/${p.id}/intake` : `#/p/${p.id}`} className="min-w-0 flex-1">
                    <div className="truncate font-medium">{p.title || p.idea_text.slice(0, 80)}</div>
                    <div className="mt-1 text-xs text-muted">
                      {p.status === 'draft' ? 'Intake in progress' : p.status === 'done' && p.light ? LIGHT[p.light].call : p.status}
                      {' · '}{timeAgo(p.updated_at)}
                    </div>
                  </a>
                  <button onClick={() => remove(p.id)} className="text-muted opacity-0 transition hover:text-stop group-hover:opacity-100" title="Delete">
                    <Trash2 size={15} />
                  </button>
                </Card>
              ))}
            </div>
          </section>
        )}

        <section className="grid gap-4 pb-20 md:grid-cols-3">
          {FEATURES.map((f) => (
            <Card key={f.title} className="bg-surface/70 p-5 backdrop-blur-md">
              <f.icon size={18} className="text-go" />
              <div className="mt-3 font-semibold">{f.title}</div>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{f.text}</p>
            </Card>
          ))}
        </section>
      </main>
    </div>
  )
}
