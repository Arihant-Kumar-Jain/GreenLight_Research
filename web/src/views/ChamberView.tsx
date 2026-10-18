import { lazy, Suspense } from 'react'
import type { Argument, Project, Side } from '../api'
import { Badge, Card, Cite, cx, Markdown, SectionTitle } from '../ui'

const ChamberScene = lazy(() => import('../three/ChamberScene'))

function Ev({ ids }: { ids: string[] }) {
  return <span className="ml-1">{ids.map((i) => (i.startsWith('P') ? <Cite key={i} id={i} /> : <Badge key={i} className="mx-0.5">{i}</Badge>))}</span>
}

function Arg({ a, i }: { a: Argument; i: number }) {
  return (
    <div className={cx('rounded-xl border border-line p-4', a.struck && 'opacity-50')}>
      <div className="flex items-start gap-2">
        <span className="font-mono text-xs text-muted">{i + 1}</span>
        <div className="flex-1">
          <div className={cx('font-medium', a.struck && 'line-through')}>{a.claim}</div>
          <div className="mt-1 text-sm text-muted">{a.reasoning}</div>
          <div className="mt-2 text-xs">
            {a.struck ? <Badge tone="stop">struck: no valid evidence</Badge> : <Ev ids={a.evidence} />}
            {a.weak && <Badge tone="wait" className="ml-1">weak: low-credibility sources</Badge>}
          </div>
        </div>
      </div>
    </div>
  )
}

function Bench({ name, side, tone }: { name: string; side: Side; tone: string }) {
  const o = side.opening
  const r = side.rebuttal
  return (
    <Card className="p-6">
      <SectionTitle><span className={tone}>{name}</span></SectionTitle>
      {!o ? <p className="text-sm text-muted">Preparing…</p> : (
        <div className="space-y-3">
          <p className="font-display text-xl italic">“{o.framing}”</p>
          {o.arguments.map((a, i) => <Arg key={i} a={a} i={i} />)}
          <div className="rounded-xl bg-sunken p-3 text-sm"><span className="eyebrow !text-[10px]">Point of information</span><div className="mt-1">{o.point_of_information}</div></div>
          {r && (
            <div className="mt-4 space-y-2 border-t border-line pt-4 text-sm">
              <div className="eyebrow !text-[10px]">Rebuttal</div>
              <p><span className="text-muted">Answers the POI: </span>{r.poi_answer}</p>
              {r.responses.map((x, i) => <p key={i}><span className="text-muted">On “{x.target}”: </span>{x.response}<Ev ids={x.evidence} /></p>)}
              <p className="text-wait">Concedes: {r.concession}</p>
              <p className="italic">{r.closing}</p>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

export default function ChamberView({ p }: { p: Project }) {
  const d = p.debate
  if (!d) return <p className="text-muted">The Chamber convenes after the novelty analysis.</p>
  const v = p.verdict
  return (
    <div className="space-y-6">
      <Card className="relative overflow-hidden p-0 text-center">
        <Suspense fallback={null}><ChamberScene className="pointer-events-none absolute inset-0 opacity-90" /></Suspense>
        <div className="relative bg-gradient-to-t from-surface via-surface/40 to-transparent px-6 pb-6 pt-56">
        <div className="eyebrow">The motion</div>
        <h2 className="mx-auto mt-2 max-w-3xl font-display text-3xl">{d.motion}</h2>
        <div className="mt-2 text-xs text-muted">{Object.keys(d.evidence).length} evidence items · {d.struck ?? 0} argument(s) struck · {d.weak ?? 0} on weak evidence · status {d.status}</div>
        </div>
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Bench name="Proponent: pursue it" side={d.proponent} tone="text-go" />
        <Bench name="Skeptic: done / not worth it" side={d.skeptic} tone="text-stop" />
      </div>
      {v && (
        <Card className="p-6">
          <SectionTitle right={v.votes?.length ? <span className="flex items-center gap-1.5 text-xs text-muted">panel {v.votes.map((x, i) => <Badge key={i} tone={x === 'green' ? 'go' : x === 'amber' ? 'wait' : 'stop'}>{x}</Badge>)}</span> : undefined}>The Speaker panel rules (3 × Nemotron Ultra, majority)</SectionTitle>
          <div className="space-y-3">
            {v.clashes.map((c, i) => (
              <div key={i} className="flex items-start gap-3 text-sm">
                <Badge tone={c.winner === 'proponent' ? 'go' : c.winner === 'skeptic' ? 'stop' : 'neutral'}>{c.winner}</Badge>
                <div><div className="font-medium">{c.issue}</div><Markdown text={c.why} className="text-muted [&_p]:m-0" /></div>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm"><span className="text-muted">Deciding factor: </span>{v.deciding_factor}</p>
        </Card>
      )}
    </div>
  )
}
