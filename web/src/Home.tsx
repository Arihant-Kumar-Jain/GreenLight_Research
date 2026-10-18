import { ArrowUp, Trash2 } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { go } from './App'
import { api, type Health, type ProjectSummary } from './api'
import { GoogleButton, useAuth, UserMenu } from './auth'
import { Mark } from './Landing'
import { Card, cx, LIGHT, timeAgo } from './ui'

export function Logo() {
  return (
    <a href="#/app" className="flex items-center gap-2.5">
      <Mark />
      <span className="font-display text-[20px] font-medium tracking-tight">GreenLight Research</span>
    </a>
  )
}

/** Shared top bar for the app pages. */
export function AppBar({ children }: { children?: ReactNode }) {
  return (
    <nav className="sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b border-line bg-bg/90 px-5 backdrop-blur-md sm:px-6">
      <Logo />
      <div className="flex items-center gap-3">{children}<UserMenu /></div>
    </nav>
  )
}

const EXAMPLES = [
  'Does early mobilisation after hip fracture surgery reduce delirium in patients over 80?',
  'Detecting paroxysmal atrial fibrillation in primary care from a wearable ECG patch with a small transformer model',
  'Low-dose colchicine to prevent atrial fibrillation after cardiac surgery',
]

export default function Home() {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const { user, needsSignIn } = useAuth()
  const [askSignIn, setAskSignIn] = useState(false)

  useEffect(() => { api.health().then(setHealth).catch(() => {}) }, [])
  useEffect(() => {
    api.projects().then(setProjects).catch(() => setProjects([]))
    if (user) setAskSignIn(false)
  }, [user])

  async function submit() {
    if (text.trim().length < 10 || busy) return
    if (needsSignIn) return setAskSignIn(true)
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
    setProjects((ps) => (ps ?? []).filter((p) => p.id !== id))
  }

  const models = health?.models
  const modelName = (r: string) => (models && typeof models[r] === 'object' ? (models[r] as { name: string }).name : null)
  const status = health && (health.missing_keys.length
    ? <span className="text-sm text-stop">Missing: {health.missing_keys.join(', ')}</span>
    : <span className="hidden items-center gap-2 text-sm text-muted sm:flex"><span className="h-2 w-2 rounded-full bg-go" />{health.llm_provider} connected</span>)

  return (
    <div className="min-h-screen">
      <AppBar>{status}</AppBar>

      <main className="mx-auto max-w-3xl px-5 pb-24 pt-14 sm:px-6">
        <h1 className="font-display text-[clamp(2.2rem,4.6vw,3.2rem)] font-normal leading-[1.08] tracking-[-0.015em]">What do you want to research?</h1>
        <p className="mt-3 max-w-[36rem] text-[17px] text-muted">
          Describe a question or an idea in a sentence or two. A short chat sharpens it, then the agents get to work.
        </p>

        <Card className="mt-8 p-2 shadow-[0_1px_2px_rgba(14,42,33,.06),0_8px_24px_-12px_rgba(14,42,33,.12)] focus-within:border-ink/30">
          <label htmlFor="idea" className="sr-only">Research question or idea</label>
          <textarea
            id="idea" value={text} onChange={(e) => setText(e.target.value)} rows={4}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit() }}
            placeholder="e.g. Does vitamin D supplementation reduce exacerbations in adults with asthma who are deficient?"
            className="w-full resize-none bg-transparent px-4 py-3 text-[16px] outline-none placeholder:text-muted/70"
          />
          <div className="flex items-center justify-between gap-3 px-3 pb-2">
            <span className="text-[13px] text-muted">Personal data is redacted before anything leaves your machine. Ctrl+Enter to send.</span>
            <button onClick={submit} disabled={busy || text.trim().length < 10}
              className="inline-flex h-10 shrink-0 items-center gap-2 rounded-xl bg-go px-4 text-[15px] font-semibold text-on-go transition hover:bg-ink disabled:opacity-35">
              Start <ArrowUp size={16} />
            </button>
          </div>
        </Card>
        {err && <p className="mt-3 text-sm text-stop">{err}</p>}
        {askSignIn && needsSignIn && (
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-[15px]">
            Sign in to start research. Your questions and results stay private to your account.
            <GoogleButton />
          </div>
        )}

        <div className="mt-6">
          <div className="text-[14px] font-semibold text-muted">Try an example</div>
          <div className="mt-2 flex flex-col gap-2">
            {EXAMPLES.map((ex) => (
              <button key={ex} onClick={() => setText(ex)}
                className="rounded-xl border border-line bg-surface px-4 py-2.5 text-left text-[15px] transition hover:border-ink/30">
                {ex}
              </button>
            ))}
          </div>
        </div>

        {models && (
          <p className="mt-6 text-[13px] text-muted">
            Models: {['fast', 'reason', 'judge', 'embed'].map((r) => modelName(r)).filter(Boolean).join(', ')}
          </p>
        )}

        <section className="mt-14">
          <h2 className="font-display text-2xl">Your research</h2>
          {projects === null ? null : projects.length === 0 ? (
            <p className="mt-3 text-[15px] text-muted">
              {needsSignIn ? 'Sign in to see your research.' : 'Nothing yet. Start with a question above; your projects will be listed here.'}
            </p>
          ) : (
            <ul className="mt-4 divide-y divide-line border-y border-line">
              {projects.map((p) => (
                <li key={p.id} className="group flex items-center gap-4 py-3.5">
                  <span className={cx('h-2.5 w-2.5 shrink-0 rounded-full', p.light ? LIGHT[p.light].bg : 'bg-line',
                    (p.status === 'running' || p.status === 'queued') && 'animate-glow bg-info')} />
                  <a href={p.status === 'draft' ? `#/p/${p.id}/intake` : `#/p/${p.id}`} className="min-w-0 flex-1">
                    <div className="truncate font-semibold">{p.title || p.idea_text.slice(0, 90)}</div>
                    <div className="mt-0.5 text-[13.5px] text-muted">
                      {p.status === 'draft' ? 'Intake in progress' : p.status === 'done' && p.light ? LIGHT[p.light].call : p.status}
                      {', '}{timeAgo(p.updated_at)}
                    </div>
                  </a>
                  <button onClick={() => remove(p.id)} aria-label={`Delete ${p.title || 'project'}`}
                    className="rounded-lg p-2 text-muted opacity-60 transition hover:bg-stop-soft hover:text-stop group-hover:opacity-100 focus-visible:opacity-100">
                    <Trash2 size={16} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  )
}
