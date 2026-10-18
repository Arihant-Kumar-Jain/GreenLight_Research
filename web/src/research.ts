import type { Paper, Project, TraceEvent } from './api'

/* Research progress in the researcher's terms (papers, passages, findings), derived from the project and its live
   trace. No LLM calls, tokens or dollars here on purpose: those are operator metrics, not research ones. */

const SEARCH = /^(search_arxiv|search_openalex|search_hf_papers|search_web|citation_graph)\(/
const LOOKUP = /^search_corpus\(/
const READ = /^read_fulltext\(/

/** "6 passage(s) from P1, P3" → 6 (the digest search_corpus / read_fulltext write to the trace). */
const passages = (e: TraceEvent) => Number(/^(\d+) passage/.exec(e.detail ?? '')?.[1] ?? 0)

export const RELEVANT = 0.4 // cross-encoder relevance to the idea (same cut as the Papers view's amber badge)

export type ResearchStats = {
  papers: number; relevant: number; read: number; scored: number; strong: number; retracted: number
  searches: number; lookups: number; passages: number; findings: number; gaps: number
}

export function researchStats(p: Project, events: TraceEvent[]): ResearchStats {
  const tools = events.filter((e) => e.kind === 'tool')
  return {
    papers: p.papers.length,
    relevant: p.papers.filter((x) => (x.relevance ?? 0) >= RELEVANT).length,
    read: p.papers.filter((x) => x.read).length,
    scored: p.papers.filter((x) => x.credibility).length,
    strong: p.papers.filter((x) => x.credibility && !x.credibility.retracted && x.credibility.score >= 72).length,
    retracted: p.papers.filter((x) => x.retracted).length,
    searches: tools.filter((e) => SEARCH.test(e.title)).length,
    lookups: tools.filter((e) => LOOKUP.test(e.title)).length,
    passages: tools.filter((e) => LOOKUP.test(e.title) || READ.test(e.title)).reduce((n, e) => n + passages(e), 0),
    findings: p.notes.filter((n) => n.kind === 'finding').length,
    gaps: p.notes.filter((n) => n.kind === 'gap').length,
  }
}

/** Per agent: papers it brought in, literature searches it ran, evidence passages it pulled. */
export function agentStats(name: string, papers: Paper[], events: TraceEvent[]) {
  const mine = events.filter((e) => e.agent === name && e.kind === 'tool')
  return {
    papers: papers.filter((x) => x.found_by.includes(name)).length,
    searches: mine.filter((e) => SEARCH.test(e.title)).length,
    passages: mine.filter((e) => LOOKUP.test(e.title) || READ.test(e.title)).reduce((n, e) => n + passages(e), 0),
  }
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`
