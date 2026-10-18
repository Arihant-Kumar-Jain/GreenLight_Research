import { ArrowUp, Cpu, Wrench } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api, type Message, type Project, type TraceEvent } from '../api'
import { Card, cx, Markdown, Typing } from '../ui'

const STARTERS = [
  'What exactly is the closest paper doing differently from my idea?',
  'Which of these papers should I trust least, and why?',
  'Suggest 3 experiments that would make this clearly novel.',
  'Has anyone tried this on a different modality? Search for it.',
]

export default function ChatView({ p, events, onBusy }: { p: Project; events: TraceEvent[]; onBusy: (b: boolean) => void }) {
  const [msgs, setMsgs] = useState<Message[]>([])
  const [busy, setBusy] = useState(false)
  const [memory, setMemory] = useState<{ kind: string; text: string }[]>([])
  const [text, setText] = useState('')
  const [err, setErr] = useState('')
  const end = useRef<HTMLDivElement>(null)
  const since = useRef(0)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const c = await api.chat(p.id)
        if (!alive) return
        setMsgs(c.messages)
        setMemory(c.memory ?? [])
        setBusy(c.busy)
        onBusy(c.busy)
      } catch (e) { setErr((e as Error).message) }
    }
    tick()
    const t = setInterval(tick, busy ? 1200 : 5000)
    return () => { alive = false; clearInterval(t) }
  }, [p.id, busy, onBusy])

  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs.length, busy])

  async function send(m: string) {
    if (!m.trim() || busy) return
    setText('')
    since.current = events.length ? events[events.length - 1].id : 0
    try {
      const c = await api.chatSend(p.id, m)
      setMsgs(c.messages)
      setBusy(true)
      onBusy(true)
    } catch (e) { setErr((e as Error).message) }
  }

  const live = events.filter((e) => e.id > since.current && e.agent === 'Research Chat' && ['tool', 'compress', 'llm'].includes(e.kind)).slice(-5)

  return (
    <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-[1fr_280px]">
    <div className="flex h-[calc(100vh-330px)] min-h-[520px] flex-col">
      <div className="scroll-thin flex-1 space-y-5 overflow-y-auto pr-2">
        {!msgs.length && (
          <div className="py-10 text-center">
            <h3 className="font-display text-3xl">Talk to your research agent</h3>
            <p className="mx-auto mt-2 max-w-xl text-sm text-muted">It knows the brief, the verdict, every paper and the notebook. It can search further, read papers, re-score credibility and remember the conversation.</p>
            <div className="mx-auto mt-6 grid max-w-2xl gap-2 md:grid-cols-2">
              {STARTERS.map((s) => <button key={s} onClick={() => send(s)} className="rounded-xl border border-line p-3 text-left text-sm text-muted hover:border-go/40 hover:text-ink">{s}</button>)}
            </div>
          </div>
        )}
        {msgs.map((m) => (
          <div key={m.id} className={cx('animate-rise flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div className={cx('max-w-[88%] rounded-2xl px-4 py-3 text-[15px]', m.role === 'user' ? 'bg-go-soft' : 'border border-line bg-surface')}>
              {m.role === 'user' ? <div className="whitespace-pre-wrap">{m.content}</div> : <Markdown text={m.content} />}
              {m.role === 'assistant' && m.data?.steps != null && (
                <div className="mt-3 flex flex-wrap gap-3 border-t border-line pt-2 text-[11px] text-muted">
                  <span className="inline-flex items-center gap-1"><Cpu size={11} />{m.data.steps} step(s)</span>
                  <span className="inline-flex items-center gap-1"><Wrench size={11} />{m.data.tool_calls} tool call(s)</span>
                  {m.data.budget && <span>${m.data.budget.usd.toFixed(4)} · {m.data.budget.elapsed_s}s</span>}
                  {m.data.context && m.data.context.compressions > 0 && <span>context compressed ×{m.data.context.compressions}</span>}
                  {m.data.recalled ? <span>recalled {m.data.recalled} earlier exchange(s)</span> : null}
                  {m.data.citations?.revised_from ? <span className="text-wait">self-corrected: {m.data.citations.revised_from} unsupported → {m.data.citations.unsupported}</span> : null}
                  {m.data.citations && <span>citations checked: {m.data.citations.supported} supported{m.data.citations.partial ? `, ${m.data.citations.partial} partial` : ''}{m.data.citations.unsupported ? `, ${m.data.citations.unsupported} unsupported` : ''}</span>}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <Card className="animate-rise max-w-[88%] p-4">
            <Typing />
            <div className="mt-2 space-y-1 font-mono text-[11px] text-muted">
              {live.map((e) => <div key={e.id} className="truncate">{e.kind === 'tool' ? '→ ' : e.kind === 'compress' ? '⇣ ' : '· '}{e.title}</div>)}
            </div>
          </Card>
        )}
        <div ref={end} />
      </div>
      <div className="mt-4 flex items-end gap-2">
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(text) } }}
          placeholder={p.status === 'done' ? 'Ask a follow-up, challenge the verdict, or change the idea…' : 'You can chat while the research runs…'}
          className="flex-1 resize-none rounded-xl border border-line bg-surface px-4 py-3 text-[15px] outline-none focus:border-go/50" />
        <button onClick={() => send(text)} disabled={!text.trim() || busy} className="grid h-11 w-11 place-items-center rounded-xl bg-go text-on-go disabled:opacity-30"><ArrowUp size={18} /></button>
      </div>
      {err && <p className="mt-2 text-sm text-stop">{err}</p>}
    </div>
    <Card className="scroll-thin hidden h-fit max-h-[calc(100vh-330px)] overflow-y-auto p-4 lg:block">
      <h3 className="eyebrow mb-2">Long-term memory</h3>
      <p className="mb-3 text-[11px] text-muted">Facts the agent extracted from this conversation. Pinned into every answer; older turns are folded into a summary and recalled by similarity.</p>
      {memory.length ? memory.map((f, i) => (
        <div key={i} className="mb-2 text-xs"><span className="font-mono text-[10px] text-info">{f.kind}</span><div><Markdown text={f.text} className="[&_p]:m-0" /></div></div>
      )) : <p className="text-xs text-muted">Nothing yet.</p>}
    </Card>
    </div>
  )
}
