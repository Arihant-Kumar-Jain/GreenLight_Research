import { ExternalLink, FileText, Loader2, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { api, type Paper, type Project } from '../api'
import { Badge, Button, Card, CredBadge, credTone, cx, Meter } from '../ui'

const REL_TONE = { 'same idea': 'stop', 'very close': 'wait', related: 'info', background: 'neutral' } as const

export function PaperLinks({ p }: { p: Paper }) {
  const links = [
    p.url && ['Paper', p.url], p.pdf_url && ['PDF', p.pdf_url],
    p.doi && !p.doi.includes('arxiv') && ['DOI', `https://doi.org/${p.doi}`],
    p.hf?.url && ['HF', p.hf.url], p.hf?.github && ['Code', p.hf.github],
  ].filter(Boolean) as [string, string][]
  return (
    <div className="flex flex-wrap gap-2">
      {links.map(([k, u]) => (
        <a key={k} href={u} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-0.5 text-xs text-muted hover:text-ink">
          {k} <ExternalLink size={11} />
        </a>
      ))}
    </div>
  )
}

export function PaperDrawer({ paper: p, projectId, onClose, onUpdate }: { paper: Paper; projectId: string; onClose: () => void; onUpdate: () => void }) {
  const [busy, setBusy] = useState(false)
  const c = p.credibility
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose}>
      <aside onClick={(e) => e.stopPropagation()} className="animate-rise scroll-thin h-full w-full max-w-xl overflow-y-auto border-l border-line bg-surface p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <span className="font-mono text-xs text-info">{p.id}</span>
            <h2 className="mt-1 font-display text-2xl leading-tight">{p.title}</h2>
            <div className="mt-1 text-sm text-muted">{p.authors.slice(0, 6).join(', ')}{p.n_authors > 6 ? ` +${p.n_authors - 6}` : ''} · {p.year ?? 'n.d.'}{p.venue ? ` · ${p.venue}` : ''}</div>
          </div>
          <button onClick={onClose} className="text-muted hover:text-ink"><X /></button>
        </div>
        <PaperLinks p={p} />
        {p.retracted && <div className="mt-4 rounded-xl bg-stop-soft p-3 text-sm font-semibold text-stop">This paper has been retracted.</div>}

        <Card className="mt-5 p-5">
          <div className="flex items-center justify-between">
            <h3 className="eyebrow">Credibility</h3>
            {c && <Badge tone={credTone(c)}>{c.tier} · confidence {c.confidence}</Badge>}
          </div>
          {c ? (
            <>
              <div className="mt-2 font-display text-5xl">{c.score}<span className="text-xl text-muted">/100</span></div>
              <div className="mt-4 space-y-3">
                {c.components.map((x) => (
                  <div key={x.name}>
                    <div className="mb-1 flex justify-between text-xs"><span className="font-semibold capitalize">{x.name} <span className="font-normal text-muted">×{x.weight}</span></span><span>{x.score}</span></div>
                    <Meter value={x.score} tone={x.score >= 70 ? 'go' : x.score >= 40 ? 'wait' : 'stop'} />
                    <div className="mt-1 text-xs text-muted">{x.detail}</div>
                  </div>
                ))}
              </div>
              {c.notes.map((n) => <p key={n} className="mt-3 text-xs text-wait">{n}</p>)}
              <p className="mt-3 text-[11px] text-muted">Deterministic score from OpenAlex / Semantic Scholar / Hugging Face data and verified audit flags. Not a judgement of the authors.</p>
            </>
          ) : (
            <Button className="mt-3" variant="outline" disabled={busy} onClick={async () => { setBusy(true); await api.scorePaper(projectId, p.id).catch(() => {}); onUpdate(); setBusy(false) }}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : null} Score credibility
            </Button>
          )}
        </Card>

        {p.audit && (
          <Card className="mt-5 p-5">
            <h3 className="eyebrow mb-2">Auditor</h3>
            <p className="text-sm">{p.audit.shows}</p>
            {p.audit.key_results.map((r, i) => (
              <div key={i} className="mt-3 text-sm">
                <div>{r.claim} {r.verified ? <Badge tone="go">quote verified</Badge> : <Badge>unverified</Badge>}</div>
                <div className="mt-1 border-l-2 border-line pl-3 text-xs italic text-muted">“{r.quote}”</div>
              </div>
            ))}
            {p.audit.flags.map((f, i) => (
              <div key={i} className={cx('mt-3 rounded-lg p-3 text-sm', f.verified ? 'bg-stop-soft/50' : 'bg-sunken opacity-60')}>
                <div className="font-semibold">{f.type.replace(/_/g, ' ')} {f.verified ? <Badge tone="stop">verified</Badge> : <Badge>dropped: quote not in paper</Badge>}</div>
                <div className="mt-1 text-xs">{f.why}</div>
                <div className="mt-1 text-xs italic text-muted">“{f.quote}”</div>
              </div>
            ))}
          </Card>
        )}

        <h3 className="eyebrow mb-2 mt-6">Abstract</h3>
        <p className="text-sm leading-relaxed text-muted">{p.abstract || 'No abstract available.'}</p>
        <div className="mt-5 flex flex-wrap gap-2 text-xs text-muted">
          {p.read && <Badge tone="info"><FileText size={11} /> full text read</Badge>}
          {p.sources.map((s) => <Badge key={s}>{s}</Badge>)}
          {p.found_by.map((s) => <Badge key={s} tone="neutral">found by {s}</Badge>)}
        </div>
      </aside>
    </div>
  )
}

export default function PapersView({ p, onOpen }: { p: Project; onOpen: (id: string) => void }) {
  const [sort, setSort] = useState<'relevance' | 'credibility' | 'citations' | 'year'>('relevance')
  const [q, setQ] = useState('')
  const rel = useMemo(() => new Map((p.stats?.review?.closest ?? []).map((c, i) => [c.id, { ...c, rank: i }])), [p.stats])
  const rows = useMemo(() => {
    const r = p.papers.filter((x) => !q || `${x.title} ${x.authors.join(' ')}`.toLowerCase().includes(q.toLowerCase()))
    const key = (x: Paper) => sort === 'credibility' ? -(x.credibility?.score ?? -1) : sort === 'citations' ? -(x.citations ?? -1)
      : sort === 'year' ? -(x.year ?? 0) : (rel.get(x.id)?.rank ?? 100) * 1000 - (x.credibility?.score ?? 0)
    return [...r].sort((a, b) => key(a) - key(b))
  }, [p.papers, q, sort, rel])

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter papers…" className="w-64 rounded-xl border border-line bg-surface px-3 py-2 text-sm outline-none" />
        <span className="ml-2 text-xs text-muted">Sort:</span>
        {(['relevance', 'credibility', 'citations', 'year'] as const).map((s) => (
          <button key={s} onClick={() => setSort(s)} className={cx('rounded-full border px-2.5 py-1 text-xs', sort === s ? 'border-go text-go' : 'border-line text-muted')}>{s}</button>
        ))}
        <span className="ml-auto text-xs text-muted">{p.papers.filter((x) => x.credibility).length}/{p.papers.length} scored</span>
      </div>
      <div className="space-y-2">
        {rows.map((x) => {
          const r = rel.get(x.id)
          return (
            <Card key={x.id} className="flex items-start gap-4 p-4 transition hover:border-go/30">
              <div className="w-14 shrink-0 pt-0.5 text-center">
                <CredBadge c={x.credibility} onClick={() => onOpen(x.id)} />
                {x.credibility && <div className="mt-1.5"><Meter value={x.credibility.score} tone={credTone(x.credibility)} /></div>}
              </div>
              <button className="min-w-0 flex-1 text-left" onClick={() => onOpen(x.id)}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-info">{x.id}</span>
                  {r && <Badge tone={REL_TONE[r.relation]}>{r.relation}</Badge>}
                  {x.retracted && <Badge tone="stop">retracted</Badge>}
                  {x.audit?.flags.some((f) => f.verified) && <Badge tone="stop">red flags</Badge>}
                  {x.read && <Badge tone="info">read</Badge>}
                </div>
                <div className="mt-1 font-medium leading-snug">{x.title}</div>
                <div className="mt-0.5 text-xs text-muted">
                  {x.authors.slice(0, 3).join(', ')}{x.n_authors > 3 ? ' et al.' : ''} · {x.year ?? 'n.d.'}{x.venue ? ` · ${x.venue}` : ''}
                  {x.citations != null ? ` · ${x.citations.toLocaleString()} citations` : ''}
                  {x.hf?.models ? ` · ${x.hf.models} HF models` : ''}
                </div>
                {r && <div className="mt-1 text-sm text-muted">{r.why}</div>}
              </button>
              <div className="hidden shrink-0 md:block"><PaperLinks p={x} /></div>
            </Card>
          )
        })}
        {!rows.length && <p className="text-muted">No papers yet.</p>}
      </div>
    </div>
  )
}
