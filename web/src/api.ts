export type Light = 'green' | 'amber' | 'red'

export type Brief = {
  title: string; research_question: string; hypothesis: string; method: string; contributions: string[]; field: string
  datasets_benchmarks: string[]; baselines: string[]; known_related_work: string[]; constraints: string; keywords: string[]
  open_points: string[]
}

export type Question = { question: string; why: string; options: string[] }
export type Message = {
  id: number; ts: number; phase: string; role: 'user' | 'assistant'; content: string
  data: { questions?: Question[]; ready?: boolean; missing?: string[]; papers?: string[]; steps?: number; tool_calls?: number
    stopped_because?: string; budget?: { usd: number; llm_calls: number; tool_calls: number; elapsed_s: number }
    context?: { compressions: number; elided: number; folded_groups: number; peak_tokens: number }
    redactions?: { type: string; label: string; count: number }[]; error?: boolean
    citations?: { supported: number; partial: number; unsupported: number; revised_from?: number | null } | null; recalled?: number } | null
}

export type ProjectSummary = {
  id: string; title: string | null; idea_text: string; status: string; stage: string | null; light: Light | null
  brief?: Brief | null; error?: string | null; created_at: number; updated_at: number
}

export type CredComponent = { name: string; score: number; weight: number; detail: string }
export type Credibility = {
  score: number; tier: 'strong' | 'solid' | 'mixed' | 'weak' | 'retracted'; confidence: 'high' | 'medium' | 'low'
  retracted: boolean; components: CredComponent[]; notes: string[]
  flags: { type: string; quote: string; why: string; verified: boolean }[]
}
export type Audit = {
  shows: string; key_results: { claim: string; quote: string; verified: boolean }[]
  flags: { type: string; quote: string; why: string; verified: boolean }[]; dropped: number
}
export type Paper = {
  id: string; title: string; year: number | null; url: string | null; pdf_url: string | null; arxiv_id: string | null
  doi: string | null; authors: string[]; n_authors: number; venue: string | null; citations: number | null
  retracted: boolean; found_by: string[]; sources: string[]; credibility: Credibility | null; audit: Audit | null
  hf: { upvotes?: number; models?: number; datasets?: number; spaces?: number; github?: string; url?: string } | null
  read: boolean; abstract: string; relevance: number | null; relevance_by: string | null
}

export type Relation = { id: string; relation: 'same idea' | 'very close' | 'related' | 'background'; why: string }
export type Review = {
  synthesis: string; closest: Relation[]; gaps: string[]; confidence: string; rounds: number; scouts: number
  coverage: { component: string; status: 'covered' | 'partially' | 'open'; papers: string[]; note: string }[]
}
export type Cell = { component: string; overlap: 'none' | 'partial' | 'full' | 'unverified'; quote: string; note: string; verified?: boolean; claimed?: string; strict?: { verdict: string; why: string } }
export type Novelty = {
  score: number | null; unverified_claims: number; strict_downgrades?: number
  components: { id: string; text: string; core: boolean; best: string; covered_by: { paper_id: string; overlap: string }[] }[]
  papers: { paper_id: string; relation: string; difference: string; cells: Cell[] }[]
  already_done_by: { paper_id: string; credibility: number | null }[]
}
export type Argument = { claim: string; reasoning: string; evidence: string[]; struck: boolean; weak?: boolean }
export type Side = {
  opening?: { framing: string; arguments: Argument[]; point_of_information: string }
  rebuttal?: { poi_answer: string; responses: { target: string; response: string; evidence: string[] }[]; concession: string; closing: string }
}
export type Verdict = {
  light: Light; headline: string; confidence: number; reasons: string[]; differentiation: string[]; next_steps: string[]
  clashes: { issue: string; winner: string; why: string }[]; deciding_factor: string
  speaker_light: Light; speaker_headline: string; guardrails: { from: Light; to: Light; why: string }[]; votes?: Light[]
}
export type Debate = {
  motion: string; status: string; proponent: Side; skeptic: Side; struck?: number; weak?: number
  evidence: Record<string, { label: string; url?: string | null; credibility?: number | null }>
}
export type ClaimCheck = { text: string; refs: string[]; label: 'supported' | 'partial' | 'unsupported' | 'unchecked'; why: string }
export type Report = {
  title: string; tldr: string; markdown: string
  citations: { claims: ClaimCheck[]; supported: number; partial: number; unsupported: number; ratio: number | null }
}
export type Totals = {
  llm_calls: number; tokens_in: number; tokens_out: number; cost_usd: number; tool_calls: number; agents: number
  compressions: number; by_model: { model: string; calls: number; tokens: number; cost: number }[]
}
export type Note = { id: number; ts: number; agent: string; kind: string; text: string; refs: string[] }
export type Project = ProjectSummary & {
  plan: { summary: string; components: { id: string; text: string; core: boolean }[]; angles: { title: string; instructions: string; seed_queries: string[] }[] } | null
  novelty: Novelty | null; debate: Debate | null; verdict: Verdict | null; report: Report | null
  stats: { review?: Review; budget?: { usd: number; usd_cap: number; llm_calls: number; tool_calls: number; elapsed_s: number }; totals?: Totals } | null
  running: boolean; papers: Paper[]; notes: Note[]; totals: Totals
}
export type TraceEvent = {
  id: number; ts: number; agent: string; parent: string | null; kind: string; title: string; detail: string | null
  provider: string | null; model: string | null; tokens_in: number | null; tokens_out: number | null
  latency_ms: number | null; cost_usd: number | null
}
export type Health = {
  missing_keys: string[]; llm_provider: string; tavily_key: boolean; s2_key: boolean
  budget_usd_per_run: number; research_rounds: number; max_scouts: number
  models?: Record<string, { id: string; name: string } | string>; models_error?: string; auth?: AuthInfo['mode']
  rerankers?: { chain: string[]; local_model: string | null }
}

export type User = { id: string; email: string; name: string | null; picture: string | null }
export type AuthInfo = { mode: 'google' | 'dev' | 'off'; google_client_id: string | null; user: User | null }

export type GraphNode = {
  id: string; title: string; year: number | null; citations: number | null; credibility: number | null
  cluster: number; relation: string | null; refs_via: string | null; n_refs: number
}
export type GraphEdge = {
  source: string; target: string; type: 'cites' | 'similar' | 'idea'; weight?: number; via?: string | null
  evidence?: string; relation?: string
}
export type GraphData = {
  nodes: GraphNode[]; edges: GraphEdge[]; clusters: { id: number; label: string; size: number }[]
  idea: { title: string }; stats: { cites: number; similar: number; refs_via: Record<string, number> }
}

export type Gate = { threshold: number | null; balanced_accuracy: number; auroc: number | null; pass_rate_answerable: number | null; reject_rate_offtopic: number | null }
export type EvalRow = {
  config: string; reranker: string | null; 'recall@1': number; 'recall@5': number; 'recall@10': number; 'mrr@10': number
  'ndcg@10': number; 'paper_hit@5': number; latency_ms: number; p95_ms: number; concurrency?: number; gate?: Gate
}
export type EvalSet = {
  style: string; n_pos: number; n_neg: number; synthetic: boolean; embed_model: string; expansion_model: string
  rerankers: Record<string, string>; rows: EvalRow[]; examples: string[]
}
export type Evals = {
  running: boolean
  retrieval: { project: string; date: string; sets: Record<string, EvalSet> } | null
  calibration: Record<string, Gate & { measured_on: string; model: string; date: string; n_pos: number; n_neg: number; set?: string }>
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!r.ok) {
    let msg = `${r.status}`
    try { msg = (await r.json()).detail ?? msg } catch { /* not json */ }
    throw new Error(msg)
  }
  return r.json() as Promise<T>
}

const post = <T,>(path: string, body?: unknown) => req<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined })

export type IntakeView = { project: ProjectSummary; messages: Message[]; busy: boolean }

export const api = {
  health: () => req<Health>('/api/health'),
  me: () => req<AuthInfo>('/api/auth/me'),
  googleLogin: (credential: string) => post<AuthInfo>('/api/auth/google', { credential }),
  logout: () => post<{ ok: boolean }>('/api/auth/logout'),
  projects: () => req<ProjectSummary[]>('/api/projects'),
  newProject: (text: string) => post<IntakeView>('/api/projects', { text }),
  intake: (id: string) => req<IntakeView>(`/api/projects/${id}/intake`),
  intakeSend: (id: string, text: string) => post<IntakeView>(`/api/projects/${id}/intake`, { text }),
  start: (id: string) => post<ProjectSummary>(`/api/projects/${id}/start`),
  stop: (id: string) => post<{ stopped: boolean }>(`/api/projects/${id}/stop`),
  rerun: (id: string) => post<ProjectSummary>(`/api/projects/${id}/rerun`),
  remove: (id: string) => req<{ ok: boolean }>(`/api/projects/${id}`, { method: 'DELETE' }),
  project: (id: string) => req<Project>(`/api/projects/${id}`),
  trace: (id: string, after: number) => req<{ events: TraceEvent[]; totals: Totals }>(`/api/projects/${id}/trace?after=${after}`),
  chat: (id: string) => req<{ messages: Message[]; busy: boolean; memory?: { kind: string; text: string }[] }>(`/api/projects/${id}/chat`),
  chatSend: (id: string, text: string) => post<{ messages: Message[]; busy: boolean }>(`/api/projects/${id}/chat`, { text }),
  scorePaper: (id: string, pid: string) => post<Paper>(`/api/projects/${id}/papers/${pid}/score`),
  graph: (id: string, refresh = false) => req<GraphData>(`/api/projects/${id}/graph${refresh ? '?refresh=1' : ''}`),
  explain: (id: string, a: string, b: string, facts: string) => post<{ text: string }>(`/api/projects/${id}/graph/explain`, { a, b, facts }),
  evals: () => req<Evals>('/api/evals'),
  runEval: (pid: string, rebuild = false) => post<{ started: boolean }>(`/api/evals/retrieval/${pid}${rebuild ? '?rebuild=1' : ''}`),
  redact: (text: string) => post<{ text: string; found: { type: string; label: string; count: number }[] }>('/api/redact', { text }),
}
