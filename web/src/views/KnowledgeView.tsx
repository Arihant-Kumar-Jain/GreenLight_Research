import { Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type KG, type Project } from '../api'
import { Badge, Card, Cite, cx, SectionTitle } from '../ui'

const TYPES = [['method', 'Methods'], ['dataset', 'Datasets'], ['task', 'Tasks'], ['metric', 'Metrics']] as const

export default function KnowledgeView({ p }: { p: Project }) {
  const [g, setG] = useState<KG | null>(null)
  const [err, setErr] = useState('')
  const [sel, setSel] = useState<string | null>(null)
  useEffect(() => { if (p.status === 'done') api.knowledge(p.id).then(setG).catch((e) => setErr(e.message)) }, [p.id, p.status])
  if (p.status !== 'done' && !g) return <p className="text-muted">The knowledge graph is built after the research run.</p>
  if (!g) return <div className="grid h-60 place-items-center text-muted">{err ? <span className="text-stop">{err}</span> : <><Loader2 className="animate-spin" /><span className="mt-2 text-sm">Extracting methods, datasets, tasks and metrics…</span></>}</div>
  const ent = sel ? g.entities.find((e) => e.id === sel) : null
  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-sm text-muted">Entities extracted by Nemotron Nano from the {g.papers} most relevant papers. An entity is kept only if its name appears in that paper's own text ({g.dropped} ungrounded or vague names dropped). Click any entity to see the papers using it.</p>
      <div className="grid gap-4 lg:grid-cols-4">
        {TYPES.map(([t, label]) => (
          <Card key={t} className="p-5">
            <SectionTitle>{label}</SectionTitle>
            <div className="flex flex-wrap gap-1.5">
              {g.entities.filter((e) => e.type === t).slice(0, 18).map((e) => (
                <button key={e.id} onClick={() => setSel(sel === e.id ? null : e.id)}
                  className={cx('rounded-full border px-2.5 py-1 text-xs transition', sel === e.id ? 'border-go text-go' : 'border-line hover:border-go/40')}>
                  {e.name} <span className="text-muted">{e.count}</span>
                </button>
              ))}
            </div>
          </Card>
        ))}
      </div>
      {ent && <Card className="animate-rise p-5 text-sm"><Badge tone="info">{ent.type}</Badge> <b>{ent.name}</b> is used by {ent.papers.map((x) => <Cite key={x} id={x} />)}</Card>}
      {g.matrix.length > 0 && g.datasets.length > 0 && (
        <Card className="overflow-x-auto p-6">
          <SectionTitle>Method × dataset coverage</SectionTitle>
          <table className="text-sm">
            <thead><tr><th className="pr-4 text-left text-xs text-muted">Method</th>{g.datasets.map((d) => <th key={d} className="px-3 text-left text-xs">{d}</th>)}</tr></thead>
            <tbody>{g.matrix.map((r) => (
              <tr key={r.method} className="border-t border-line">
                <td className="py-2 pr-4 font-medium">{r.method}</td>
                {g.datasets.map((d) => <td key={d} className="px-3">{r.cells[d]?.length ? r.cells[d].map((x) => <Cite key={x} id={x} />) : <Badge tone="go">gap</Badge>}</td>)}
              </tr>
            ))}</tbody>
          </table>
          <p className="mt-3 text-xs text-muted">"gap" = no collected paper evaluates that method on that dataset (among methods and datasets used by 2+ papers): a candidate experiment, not proof that nobody has done it.</p>
        </Card>
      )}
      {g.results.length > 0 && (
        <Card className="overflow-x-auto p-6">
          <SectionTitle>Reported results (number found in the paper text)</SectionTitle>
          <table className="w-full text-sm"><thead><tr className="text-left text-xs text-muted"><th>Paper</th><th>Method</th><th>Dataset</th><th>Metric</th><th className="text-right">Value</th></tr></thead>
            <tbody>{g.results.map((r, i) => <tr key={i} className="border-t border-line"><td className="py-1.5"><Cite id={r.paper} /></td><td>{r.method}</td><td>{r.dataset}</td><td>{r.metric}</td><td className="text-right tabular-nums">{r.value}</td></tr>)}</tbody></table>
        </Card>
      )}
    </div>
  )
}
