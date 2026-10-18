import { FlaskConical, Loader2, Play } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type Evals, type ProjectSummary } from './api'
import { Logo } from './Home'
import { Badge, Button, Card, cx, SectionTitle } from './ui'

function Bar({ v, best }: { v: number; best: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-sunken"><div className={cx('h-full rounded-full', best ? 'bg-go' : 'bg-info/70')} style={{ width: `${v * 100}%` }} /></div>
      <span className={cx('tabular-nums', best && 'font-semibold text-go')}>{v.toFixed(3)}</span>
    </div>
  )
}

export default function ProofPage() {
  const [ev, setEv] = useState<Evals | null>(null)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [pid, setPid] = useState('')
  const [err, setErr] = useState('')
  const [style, setStyle] = useState('hard')
  useEffect(() => {
    const load = () => api.evals().then(setEv).catch((e) => setErr(e.message))
    load()
    api.projects().then((ps) => { const done = ps.filter((p) => p.status === 'done'); setProjects(done); if (done[0]) setPid(done[0].id) })
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [])
  const sets = ev?.retrieval?.sets ?? {}
  const r = sets[style] ?? Object.values(sets)[0]
  const best = (key: 'recall@5' | 'mrr@10' | 'ndcg@10' | 'recall@1') => Math.max(...(r?.rows.map((x) => x[key]) ?? [0]))

  return (
    <div className="min-h-screen">
      <nav className="flex items-center justify-between border-b border-line px-6 py-3"><Logo /><span className="eyebrow">Proof · measured, not claimed</span></nav>
      <main className="mx-auto max-w-6xl px-6 py-10">
        <h1 className="font-display text-5xl">Retrieval, measured</h1>
        <p className="mt-3 max-w-3xl text-muted">
          Every stage of the retrieval pipeline is switched on one at a time and measured on questions written from the
          project's own passages (paraphrased, so keyword overlap alone can't pass) plus off-topic questions the corpus can't
          answer. The off-topic set calibrates each reranker's "not enough evidence" threshold used by the agents.
        </p>
        <Card className="mt-6 flex flex-wrap items-center gap-3 p-4">
          <FlaskConical size={16} className="text-go" />
          <select value={pid} onChange={(e) => setPid(e.target.value)} className="rounded-lg border border-line bg-surface px-3 py-2 text-sm">
            {projects.map((p) => <option key={p.id} value={p.id}>{p.title || p.id}</option>)}
          </select>
          <Button disabled={!pid || ev?.running} onClick={() => api.runEval(pid).then(() => api.evals().then(setEv)).catch((e) => setErr(e.message))}>
            {ev?.running ? <><Loader2 size={14} className="animate-spin" /> Running…</> : <><Play size={14} /> Run retrieval eval</>}
          </Button>
          <span className="text-xs text-muted">Takes a few minutes; uses Nemotron Nano for questions and query expansion.</span>
          {err && <span className="text-sm text-stop">{err}</span>}
        </Card>

        {!r ? <p className="mt-10 text-muted">No eval has been run yet. Nothing is shown until one is.</p> : (
          <>
            <div className="mt-8 flex gap-2">
              {Object.keys(sets).map((k) => (
                <button key={k} onClick={() => setStyle(k)} className={cx('rounded-full border px-3 py-1 text-sm', r.style === k ? 'border-go text-go' : 'border-line text-muted')}>
                  {k === 'hard' ? 'Hard: no shared vocabulary' : 'Paraphrased questions'}
                </button>
              ))}
            </div>
            <p className="mt-3 max-w-3xl text-sm text-muted">{r.style === 'hard'
              ? 'Questions written by someone who has not read the passage, avoiding its technical terms: the realistic case where keyword search fails and semantic search, expansion and reranking have to earn their keep.'
              : 'Paraphrased questions that still share much of the passage vocabulary: easy for keyword search.'}</p>
            <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted">
              <Badge tone="info">{r.n_pos} answerable + {r.n_neg} off-topic questions</Badge>
              <Badge>synthetic, from project {ev?.retrieval?.project}</Badge><Badge>embeddings: {r.embed_model}</Badge>
              <Badge>expansion: {r.expansion_model}</Badge><Badge>{new Date(ev!.retrieval!.date).toLocaleString()}</Badge>
            </div>
            <Card className="mt-4 overflow-x-auto p-6">
              <table className="w-full min-w-[900px] text-sm">
                <thead><tr className="text-left text-xs text-muted">
                  <th className="pb-3">Pipeline</th><th>Reranker</th><th>Recall@1</th><th>Recall@5</th><th>MRR@10</th><th>nDCG@10</th><th>Paper hit@5</th><th className="text-right">Latency</th>
                </tr></thead>
                <tbody>
                  {r.rows.map((x, i) => (
                    <tr key={i} className="border-t border-line">
                      <td className="py-2.5 font-medium">{x.config}</td>
                      <td>{x.reranker ? <Badge tone="info">{x.reranker.replace(/^local:.*\//, 'local: ')}</Badge> : <span className="text-muted">–</span>}</td>
                      <td><Bar v={x['recall@1']} best={x['recall@1'] === best('recall@1')} /></td>
                      <td><Bar v={x['recall@5']} best={x['recall@5'] === best('recall@5')} /></td>
                      <td><Bar v={x['mrr@10']} best={x['mrr@10'] === best('mrr@10')} /></td>
                      <td><Bar v={x['ndcg@10']} best={x['ndcg@10'] === best('ndcg@10')} /></td>
                      <td className="tabular-nums">{x['paper_hit@5'].toFixed(3)}</td>
                      <td className="text-right tabular-nums text-muted">{x.latency_ms.toLocaleString()} ms{x.concurrency && x.concurrency > 1 ? ` (×${x.concurrency} parallel)` : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-4 text-xs text-muted">Gold = the exact passage the question was written from (chunk-level, strict). Latency includes query expansion and embedding calls over the network.</p>
            </Card>
          </>
        )}

        {ev && Object.keys(ev.calibration).length > 0 && (
          <>
            <SectionTitle><span className="mt-10 block">Evidence gate calibration</span></SectionTitle>
            <div className="grid gap-4 md:grid-cols-2">
              {Object.entries(ev.calibration).map(([k, c]) => (
                <Card key={k} className="p-5">
                  <div className="flex items-center justify-between"><Badge tone="info">{k.replace(/^local:.*\//, 'local: ')}</Badge><span className="text-xs text-muted">{c.model}{c.set ? ` · ${c.set} set` : ''}</span></div>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                    <div><div className="text-xs text-muted">Threshold</div><div className="font-semibold tabular-nums">{c.threshold?.toFixed(4)}</div></div>
                    <div><div className="text-xs text-muted">AUROC (answerable vs off-topic)</div><div className="font-semibold">{c.auroc}</div></div>
                    <div><div className="text-xs text-muted">Answerable passed</div><div className="font-semibold">{c.pass_rate_answerable != null ? `${Math.round(c.pass_rate_answerable * 100)}%` : '–'}</div></div>
                    <div><div className="text-xs text-muted">Off-topic rejected</div><div className="font-semibold">{c.reject_rate_offtopic != null ? `${Math.round(c.reject_rate_offtopic * 100)}%` : '–'}</div></div>
                  </div>
                  <p className="mt-3 text-xs text-muted">{c.n_pos} + {c.n_neg} questions, {c.date}. Agents get <code>sufficient_evidence: false</code> below this score.</p>
                </Card>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
