import { ArrowUp, Rocket, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { go } from './App'
import { api, type Brief, type IntakeView } from './api'
import { UserMenu } from './auth'
import { Logo } from './Home'
import { Badge, Button, Card, cx, Markdown, Typing } from './ui'

function BriefCard({ brief }: { brief: Brief | null | undefined }) {
  if (!brief) return <p className="text-sm text-muted">The brief builds up here as you talk.</p>
  const rows: [string, string | string[]][] = [
    ['Research question', brief.research_question], ['Hypothesis', brief.hypothesis], ['Method', brief.method],
    ['Contributions to test', brief.contributions], ['Field', brief.field], ['Datasets / benchmarks', brief.datasets_benchmarks],
    ['Baselines', brief.baselines], ['Known related work', brief.known_related_work], ['Search keywords', brief.keywords],
    ['Assumptions', brief.open_points],
  ]
  return (
    <div className="space-y-3">
      {brief.title && <div className="font-display text-2xl leading-tight">{brief.title}</div>}
      {rows.filter(([, v]) => (Array.isArray(v) ? v.length : v)).map(([k, v]) => (
        <div key={k}>
          <div className="eyebrow !text-[10px]">{k}</div>
          {Array.isArray(v)
            ? (k === 'Search keywords'
              ? <div className="mt-1 flex flex-wrap gap-1">{v.map((x) => <Badge key={x}>{x}</Badge>)}</div>
              : <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm">{v.map((x) => <li key={x}>{x}</li>)}</ul>)
            : <div className="mt-0.5 text-sm">{v}</div>}
        </div>
      ))}
    </div>
  )
}

export default function Intake({ id }: { id: string }) {
  const [view, setView] = useState<IntakeView | null>(null)
  const [text, setText] = useState('')
  const [err, setErr] = useState('')
  const [starting, setStarting] = useState(false)
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const v = await api.intake(id)
        if (!alive) return
        setView(v)
        if (v.project.status !== 'draft') go(`/p/${id}`)
      } catch (e) { setErr((e as Error).message) }
    }
    tick()
    const t = setInterval(tick, 1300)
    return () => { alive = false; clearInterval(t) }
  }, [id])

  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [view?.messages.length, view?.busy])

  async function send(msg: string) {
    if (!msg.trim() || view?.busy) return
    setText('')
    try { setView(await api.intakeSend(id, msg)) } catch (e) { setErr((e as Error).message) }
  }

  async function start() {
    setStarting(true)
    try { await api.start(id); go(`/p/${id}/agents`) } catch (e) { setErr((e as Error).message); setStarting(false) }
  }

  const msgs = view?.messages ?? []
  const last = [...msgs].reverse().find((m) => m.role === 'assistant')
  const ready = !!last?.data?.ready

  return (
    <div className="flex h-screen flex-col">
      <nav className="flex items-center justify-between border-b border-line px-6 py-3">
        <Logo />
        <div className="flex items-center gap-3">
          <span className="eyebrow">Intake · sharpen the idea</span>
          <UserMenu />
        </div>
      </nav>
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_380px]">
        <div className="flex min-h-0 flex-col">
          <div className="scroll-thin flex-1 overflow-y-auto px-6 py-6">
            <div className="mx-auto max-w-3xl space-y-5">
              {msgs.map((m) => (
                <div key={m.id} className={cx('animate-rise flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
                  <div className={cx('max-w-[85%] rounded-2xl px-4 py-3 text-[15px]', m.role === 'user' ? 'bg-go-soft' : 'border border-line bg-surface')}>
                    {m.role === 'user' ? <div className="whitespace-pre-wrap">{m.content}</div> : <Markdown text={m.content} />}
                    {m.data?.redactions?.length ? (
                      <div className="mt-2 flex items-center gap-1 text-[11px] text-muted"><ShieldCheck size={12} /> redacted before sending: {m.data.redactions.map((r) => `${r.count} ${r.label}`).join(', ')}</div>
                    ) : null}
                    {m.data?.questions?.length ? (
                      <div className="mt-3 space-y-3 border-t border-line pt-3">
                        {m.data.questions.map((q, i) => (
                          <div key={i}>
                            <div className="text-sm font-medium">{i + 1}. {q.question}</div>
                            {q.why && <div className="text-xs text-muted">{q.why}</div>}
                            {m.id === last?.id && q.options.length > 0 && (
                              <div className="mt-1.5 flex flex-wrap gap-1.5">
                                {q.options.map((o) => (
                                  <button key={o} onClick={() => send(`${q.question} → ${o}`)} disabled={view?.busy}
                                    className="rounded-full border border-line px-2.5 py-1 text-xs hover:border-go hover:text-go">{o}</button>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
              {view?.busy && <div className="flex"><div className="rounded-2xl border border-line bg-surface px-4 py-3"><Typing /></div></div>}
              <div ref={end} />
            </div>
          </div>
          <div className="border-t border-line px-6 py-4">
            <div className="mx-auto flex max-w-3xl items-end gap-2">
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(text) } }}
                placeholder="Answer, add detail, or say “just start”…"
                className="flex-1 resize-none rounded-xl border border-line bg-surface px-4 py-3 text-[15px] outline-none focus:border-go/50" />
              <button onClick={() => send(text)} disabled={!text.trim() || view?.busy}
                className="grid h-11 w-11 place-items-center rounded-xl bg-go text-on-go disabled:opacity-30"><ArrowUp size={18} /></button>
            </div>
            {err && <p className="mx-auto mt-2 max-w-3xl text-sm text-stop">{err}</p>}
          </div>
        </div>
        <aside className="scroll-thin hidden min-h-0 overflow-y-auto border-l border-line bg-sunken/40 p-6 lg:block">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="eyebrow">Research brief</h3>
            {ready ? <Badge tone="go">ready</Badge> : <Badge>drafting</Badge>}
          </div>
          <Card className="p-4"><BriefCard brief={view?.project.brief} /></Card>
          <Button onClick={start} disabled={!view?.project.brief || starting || view?.busy}
            className={cx('mt-4 w-full py-3', ready && 'ring-4 ring-go-soft')}>
            <Rocket size={16} /> {starting ? 'Launching agents…' : 'Start deep research'}
          </Button>
          {!ready && view?.project.brief && <p className="mt-2 text-center text-xs text-muted">You can start now; the agent will note its assumptions.</p>}
        </aside>
      </div>
    </div>
  )
}
