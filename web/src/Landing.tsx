import { X } from 'lucide-react'
import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import { go } from './App'
import { GoogleButton, useAuth, UserMenu } from './auth'
import { cx } from './ui'

const Specimen = lazy(() => import('./three/Specimen'))

/* Landing page. Copy follows docs/GreenLight_Research_Idea_Scope.pdf and nothing beyond it.
   One particle specimen sits behind the page; each story section tells it what to become (data-stage). */

export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden>
      <rect x="9" y="2" width="14" height="28" rx="7" fill="var(--ink)" />
      <circle cx="16" cy="9" r="3.2" fill="#3c544b" />
      <circle cx="16" cy="16" r="3.2" fill="#3c544b" />
      <circle cx="16" cy="23" r="3.6" fill="#22b36b" />
    </svg>
  )
}

const scrollTo = (id: string) => {
  const el = document.getElementById(id)
  if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 64, behavior: 'smooth' })
}

function Nav() {
  const { info } = useAuth()
  return (
    <header className="fixed inset-x-0 top-0 z-30 border-b border-line/70 bg-bg/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-5 sm:px-8">
        <a href="#/" aria-label="GreenLight Research, back to top" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }) }} className="flex items-center gap-2.5">
          <Mark />
          <span className="hidden font-display text-[21px] font-medium tracking-tight sm:inline">GreenLight Research</span>
        </a>
        <nav className="flex items-center gap-1 text-[15px]">
          {[['How it works', 'how'], ['Sources', 'sources'], ['Compare', 'compare']].map(([label, id]) => (
            <button key={id} onClick={() => scrollTo(id)} className="hidden rounded-lg px-3 py-2 text-muted transition hover:bg-sunken hover:text-ink md:block">
              {label}
            </button>
          ))}
          {info?.user && (
            <a href="#/app" className="ml-1 rounded-lg px-3 py-2 font-semibold text-ink transition hover:bg-sunken">Open app</a>
          )}
          <span className="ml-2"><UserMenu /></span>
        </nav>
      </div>
    </header>
  )
}

/** Start researching: straight to the app when signed in, otherwise a Google sign-in popup first. */
function useStart() {
  const { needsSignIn, user } = useAuth()
  const [asking, setAsking] = useState(false)
  useEffect(() => {
    if (asking && user) {
      setAsking(false)
      go('/app')
    }
  }, [asking, user])
  return { start: () => (needsSignIn ? setAsking(true) : go('/app')), asking, close: () => setAsking(false) }
}

function SignInDialog({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/35 p-4 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="signin-title" onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-md rounded-2xl border border-line bg-surface p-8 text-center shadow-[0_24px_60px_-20px_rgba(14,42,33,.35)]">
        <button onClick={onClose} aria-label="Close" className="absolute right-3 top-3 rounded-lg p-2 text-muted transition hover:bg-sunken hover:text-ink">
          <X size={18} />
        </button>
        <div className="flex justify-center"><Mark size={34} /></div>
        <h2 id="signin-title" className="mt-4 font-display text-[28px] leading-tight">Sign in to start researching</h2>
        <p className="mx-auto mt-2 max-w-[22rem] text-[15.5px] text-muted">
          Your questions, papers and results stay private to your account.
        </p>
        <div className="mt-6 flex justify-center"><GoogleButton /></div>
      </div>
    </div>
  )
}

/** A story section: copy on the left, the specimen shows the matching shape on the right. */
function Chapter({ stage, id, title, children }: { stage: number; id?: string; title: string; children: ReactNode }) {
  return (
    <section id={id} data-stage={stage} className="relative flex min-h-[92vh] items-center py-24">
      <div className="mx-auto w-full max-w-7xl px-5 sm:px-8">
        <div className="max-w-[34rem]">
          <h2 className="font-display text-[clamp(2.1rem,4.2vw,3.2rem)] font-normal leading-[1.08] tracking-[-0.015em]">{title}</h2>
          <div className="mt-6 space-y-5 text-[17px] leading-[1.65] text-muted">{children}</div>
        </div>
      </div>
    </section>
  )
}

/** Capability rows from the scope: name on the left, what the researcher gets on the right. */
function Gets({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="divide-y divide-line border-y border-line text-[15.5px]">
      {rows.map(([k, v]) => (
        <div key={k} className="grid gap-1 py-3.5 sm:grid-cols-[10.5rem_1fr] sm:gap-5">
          <dt className="font-semibold text-ink">{k}</dt>
          <dd className="text-muted">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

const LIGHTS = [
  { name: 'Green', color: 'bg-go', text: 'Open. Little or no prior work covers the core of your idea.' },
  { name: 'Amber', color: 'bg-wait', text: 'Partly done. Some parts exist; the brief shows how to differentiate.' },
  { name: 'Red', color: 'bg-stop', text: 'Done. A credible paper already covers every core part.' },
]

const PIPELINE: [string, string][] = [
  ['Planner', 'Turns your question into components and search angles.'],
  ['Lead researcher', 'Splits the work and sends scouts out in parallel.'],
  ['Scouts', 'Each searches its angle across the healthcare sources and reports back in a compact digest.'],
  ['Critic', 'Rejects thin coverage and forces another round.'],
  ['Reader', 'Reads the closest papers in full.'],
  ['Credibility auditor', 'Scores every paper and checks red flags against the text.'],
  ['Answer writer', 'Drafts the answer from the papers, citing each claim.'],
  ['Evidence checker', 'Marks every claim as supported, partial or unsupported.'],
]

const MECHANICS: [string, string][] = [
  ['Deep research loop', 'The lead splits a question into angles and sends scouts out in parallel; a critic rejects thin coverage and forces another round.'],
  ['Context compression', 'Long searches are folded into short digests and a working memory, and the lead sees only the scouts’ compact reports. Long sessions stay fast and focused.'],
  ['Shared notebook', 'Agents write findings to a common blackboard every agent can read.'],
  ['Live view', 'Watch the agents work in real time: who is searching what, which papers were found, what was rejected.'],
]

const TRUST: [string, string][] = [
  ['Every answer is cited.', 'Each claim links to the paper and passage it came from, and unsupported claims are marked.'],
  ['It says “not enough evidence” instead of guessing.', 'If the papers do not support an answer, it fetches more or says so.'],
  ['Credibility is computed, not guessed.', 'The trust score comes from citation data, author reputation, venue and verified red flags, not from an AI’s opinion.'],
  ['Claims about papers need the paper’s own words.', 'Overlaps and red flags carry a quote checked against the text.'],
  ['The verdict is guardrailed.', 'If a credible paper already covers every core part of the idea, the light is red whatever the debate says. If the search was thin, it is never green.'],
]

const SOURCES: [string, string][] = [
  ['PubMed', 'Peer-reviewed biomedical literature.'],
  ['Europe PMC', 'Abstracts, open full texts and publication counts per year: how crowded a topic is.'],
  ['medRxiv and bioRxiv', 'The newest preprints, clearly marked as not peer-reviewed.'],
  ['ClinicalTrials.gov', 'Is someone already running a trial on this?'],
  ['Cochrane systematic reviews', 'The strongest “already done” signal.'],
  ['WHO, FDA and EMA', 'Guidelines and regulatory context.'],
  ['OpenAlex and Semantic Scholar', 'Citations, author reputation and reference lists for the credibility score and the graph.'],
]

const COMPARE: [string, string, string][] = [
  ['Literature assistants (e.g. Elicit, Consensus)', 'Find and summarise papers that answer a question', 'No trust score per paper; do not judge whether your idea is new'],
  ['Citation tools (e.g. Scite)', 'Show whether citations support or dispute a claim', 'Per-claim view; no research chat or novelty verdict'],
  ['Graph tools (e.g. Connected Papers, ResearchRabbit)', 'Visualise related literature', 'Exploration only; no answers, trust score or decision'],
]

export default function Landing() {
  const [ready, setReady] = useState(false)
  const { start, asking, close } = useStart()
  useEffect(() => {
    const t = setTimeout(() => setReady(true), 60)
    return () => clearTimeout(t)
  }, [])

  return (
    <div className="relative min-h-screen overflow-x-clip">
      <Suspense fallback={null}>
        <Specimen className="pointer-events-none fixed inset-0 z-0" />
      </Suspense>
      {/* Keep copy legible over the specimen: paper wash on the copy side (wide) or behind everything (narrow). */}
      <div className="pointer-events-none fixed inset-0 z-0 bg-[linear-gradient(90deg,var(--bg)_0%,color-mix(in_srgb,var(--bg)_88%,transparent)_34%,transparent_58%)] max-lg:bg-[color-mix(in_srgb,var(--bg)_80%,transparent)]" />

      <Nav />
      {asking && <SignInDialog onClose={close} />}

      <main className="relative z-10">
        {/* 0 · Hero: the question (helix) */}
        <section data-stage="0" className="relative flex min-h-[100svh] items-center">
          <div className="mx-auto w-full max-w-7xl px-5 pb-16 pt-28 sm:px-8">
            <div className={cx('max-w-[44rem] transition-all duration-1000 ease-out motion-reduce:transition-none', ready ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0')}>
              <p className="text-[15px] font-semibold text-go">A research assistant for healthcare papers</p>
              <h1 className="mt-5 font-display text-[clamp(2.6rem,5.2vw,4.5rem)] font-normal leading-[1.03] tracking-[-0.025em]">
                Ask the literature. Get cited answers. Know if your idea is new.
              </h1>
              <p className="mt-6 max-w-[34rem] text-[18px] leading-[1.6] text-muted">
                A team of AI agents finds the relevant healthcare papers, answers your questions from them with citations,
                keeps fetching literature when needed and scores how trustworthy each paper is. Then it tells you whether
                your idea is open, partly done or done, and points to topics worth researching.
              </p>
              <div className="mt-9 flex flex-wrap items-center gap-3">
                <button onClick={start} className="rounded-xl bg-go px-6 py-3.5 text-[16px] font-semibold text-on-go shadow-[0_1px_0_rgba(0,0,0,.08)] transition hover:bg-ink">
                  Start researching
                </button>
                <button onClick={() => scrollTo('discovery')} className="rounded-xl border border-line bg-surface px-6 py-3.5 text-[16px] font-semibold transition hover:border-ink/30">
                  See how it works
                </button>
              </div>
              <p className="mt-8 text-[14.5px] text-muted">
                For PhD students and early researchers, lab heads and grant writers, and R&amp;D teams scanning a field.
              </p>
            </div>
          </div>
        </section>

        {/* The problem (helix stays) */}
        <section data-stage="0" className="relative py-24">
          <div className="mx-auto w-full max-w-7xl px-5 sm:px-8">
            <div className="max-w-[40rem]">
              <h2 className="font-display text-[clamp(2.1rem,4.2vw,3.2rem)] font-normal leading-[1.08] tracking-[-0.015em]">
                Weeks finding papers. Months on ideas that were already done.
              </h2>
              <div className="mt-10 grid gap-x-10 gap-y-8 sm:grid-cols-2">
                {[
                  ['Finding and reading the right papers is slow.', 'You search several databases, open dozens of PDFs and are still not sure the important work was found.'],
                  ['Getting answers out of papers is manual.', '“Which methods were tried for X? On which patients? With what results?” means reading paper after paper and taking notes.'],
                  ['Not every paper deserves trust.', 'Weak baselines, tiny samples, over-claimed results and retracted work exist. Search ranks by relevance, not reliability.'],
                  ['“Has this already been done?” has no quick answer.', 'If a topic is saturated, months of work add little. If it is barely touched, there is a real opening. Today that judgement takes weeks.'],
                ].map(([h, p]) => (
                  <div key={h} className="border-t-2 border-ink pt-4">
                    <h3 className="text-[17px] font-semibold leading-snug">{h}</h3>
                    <p className="mt-2 text-[15.5px] leading-relaxed text-muted">{p}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <Chapter stage={1} id="discovery" title="Find the papers that matter.">
          <p>Ask a research question. Agents search healthcare sources in parallel and return the most relevant papers, preprints and trials, with links.</p>
          <Gets rows={[
            ['Paper discovery', 'Parallel scouts across the healthcare sources, each on its own angle.'],
            ['Fetch more literature', 'When the collected papers cannot answer a question, the agent says so, searches again, then answers.'],
          ]} />
        </Chapter>

        <Chapter stage={2} title="Ask the papers, not the internet.">
          <p>A to-and-fro chat that answers questions <em>from the papers themselves</em>, using their abstracts and full texts. Every claim carries a citation to the paper and passage it came from.</p>
          <Gets rows={[
            ['Ask the papers', 'Answers built from retrieval over abstracts and full texts, cited claim by claim.'],
            ['Evidence check', 'Drafted answers are checked against the source text; unsupported or contradicting claims are flagged.'],
          ]} />
        </Chapter>

        <Chapter stage={3} title="Know which papers to trust.">
          <p>Every paper gets a trust score from 0 to 100, computed from how often and how well it is cited, how reputed its authors are, where it was published, and verified red flags.</p>
          <p className="flex items-start gap-3 rounded-xl border border-stop/25 bg-stop-soft px-4 py-3 text-[15.5px] text-ink">
            <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-stop" />
            Retracted papers score zero.
          </p>
        </Chapter>

        <Chapter stage={4} title="See the whole field at once.">
          <p>An interactive map of papers and researchers: who cites whom, which papers are similar, which clusters exist and where the empty spaces are.</p>
          <Gets rows={[
            ['Research graph', 'Citations, similarity and clusters, so gaps in the literature become visible.'],
            ['Memory', 'The chat remembers the whole session, so you can dig deeper, compare papers and change direction.'],
          ]} />
        </Chapter>

        <Chapter stage={5} id="greenlight" title="GreenLight: is this idea new?">
          <p>On top of the research assistant, GreenLight judges whether your idea has already been done, and where the real openings are.</p>
          <Gets rows={[
            ['Idea intake', 'A short chat turns a rough idea into a clear brief: question, method, population and intended contribution.'],
            ['Novelty matrix', 'Your idea’s components against the closest papers. An overlap only counts if the paper’s own words prove it.'],
            ['For-and-against debate', 'A Proponent and a Skeptic argue the case with evidence; a judge agent rules green, amber or red. Fixed rules can only make the verdict stricter.'],
            ['New topics to research', 'Under-explored angles (a new population, method or outcome), each confirmed with a targeted search, so you leave with concrete directions.'],
          ]} />
          <ul className="space-y-2.5 pt-1">
            {LIGHTS.map((l) => (
              <li key={l.name} className="flex items-start gap-3 text-[15.5px]">
                <span className={cx('mt-1.5 h-3 w-3 shrink-0 rounded-full', l.color)} />
                <span><strong className="font-semibold text-ink">{l.name}.</strong> {l.text}</span>
              </li>
            ))}
          </ul>
        </Chapter>

        {/* Reference sections: the specimen fades out from here. */}
        <div data-specimen-end className="relative bg-bg">
          <section id="how" className="border-t border-line py-24">
            <div className="mx-auto max-w-7xl px-5 sm:px-8">
              <h2 className="max-w-[40rem] font-display text-[clamp(2.1rem,4.2vw,3.2rem)] font-normal leading-[1.08] tracking-[-0.015em]">
                A team of agents, each with one job.
              </h2>
              <div className="mt-12 grid gap-14 lg:grid-cols-[1.1fr_1fr]">
                <ol className="relative space-y-0">
                  {PIPELINE.map(([name, text], i) => (
                    <li key={name} className="grid grid-cols-[2.5rem_1fr] gap-4">
                      <div className="flex flex-col items-center">
                        <span className="grid h-8 w-8 place-items-center rounded-full border border-ink/25 bg-surface font-mono text-[13px] tabular-nums">{i + 1}</span>
                        {i < PIPELINE.length - 1 && <span className="w-px flex-1 bg-line" />}
                      </div>
                      <div className="pb-6 pt-1">
                        <div className="font-semibold">{name}</div>
                        <p className="mt-0.5 text-[15.5px] text-muted">{text}</p>
                      </div>
                    </li>
                  ))}
                  <li className="ml-14 rounded-xl border border-go/25 bg-go-soft px-4 py-3 text-[15.5px]">
                    <span className="font-semibold">For GreenLight:</span> a novelty mapper, a proponent, a skeptic and a judge.
                  </li>
                </ol>
                <div className="space-y-8">
                  {MECHANICS.map(([h, p]) => (
                    <div key={h}>
                      <h3 className="text-[17px] font-semibold">{h}</h3>
                      <p className="mt-1.5 text-[15.5px] leading-relaxed text-muted">{p}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="border-t border-line bg-surface py-24">
            <div className="mx-auto max-w-7xl px-5 sm:px-8">
              <h2 className="max-w-[40rem] font-display text-[clamp(2.1rem,4.2vw,3.2rem)] font-normal leading-[1.08] tracking-[-0.015em]">
                Why researchers can trust it.
              </h2>
              <ul className="mt-12 grid gap-x-12 gap-y-9 md:grid-cols-2 lg:grid-cols-3">
                {TRUST.map(([h, p]) => (
                  <li key={h} className="border-l-2 border-go pl-5">
                    <h3 className="text-[17px] font-semibold leading-snug">{h}</h3>
                    <p className="mt-2 text-[15.5px] leading-relaxed text-muted">{p}</p>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section id="sources" className="border-t border-line py-24">
            <div className="mx-auto grid max-w-7xl gap-12 px-5 sm:px-8 lg:grid-cols-[1fr_1.4fr]">
              <div>
                <h2 className="font-display text-[clamp(2.1rem,4.2vw,3.2rem)] font-normal leading-[1.08] tracking-[-0.015em]">Healthcare sources we follow.</h2>
                <p className="mt-5 max-w-[26rem] text-[17px] leading-relaxed text-muted">
                  Built for healthcare and life sciences first: peer-reviewed literature, preprints, trials, systematic reviews and regulators.
                </p>
              </div>
              <dl className="divide-y divide-line border-y border-line">
                {SOURCES.map(([k, v]) => (
                  <div key={k} className="grid gap-1 py-4 sm:grid-cols-[14rem_1fr] sm:gap-6">
                    <dt className="font-semibold">{k}</dt>
                    <dd className="text-[15.5px] text-muted">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </section>

          <section id="compare" className="border-t border-line bg-surface py-24">
            <div className="mx-auto max-w-7xl px-5 sm:px-8">
              <h2 className="max-w-[40rem] font-display text-[clamp(2.1rem,4.2vw,3.2rem)] font-normal leading-[1.08] tracking-[-0.015em]">
                How it differs from the tools you use.
              </h2>
              <div className="mt-10 overflow-x-auto">
                <table className="w-full min-w-[640px] border-collapse text-left text-[15.5px]">
                  <thead>
                    <tr className="border-b-2 border-ink">
                      <th className="py-3 pr-6 font-semibold">Tool type</th>
                      <th className="py-3 pr-6 font-semibold">What they do well</th>
                      <th className="py-3 font-semibold">Gap</th>
                    </tr>
                  </thead>
                  <tbody>
                    {COMPARE.map(([a, b, c]) => (
                      <tr key={a} className="border-b border-line align-top">
                        <td className="py-4 pr-6 font-semibold">{a}</td>
                        <td className="py-4 pr-6 text-muted">{b}</td>
                        <td className="py-4 text-muted">{c}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-8 max-w-[52rem] text-[17px] leading-relaxed">
                <strong className="font-semibold">Our difference:</strong> one place to find papers, ask them questions with citations,
                know which ones to trust, and decide whether an idea is worth pursuing, with new directions when it is not.
                Built for healthcare first.
              </p>
              <p className="mt-3 text-[13.5px] text-muted">Comparison from general public knowledge, not an in-depth review.</p>
            </div>
          </section>

          <section className="border-t border-line py-28">
            <div className="mx-auto max-w-7xl px-5 sm:px-8">
              <p className="max-w-[46rem] font-display text-[clamp(1.7rem,3.2vw,2.5rem)] leading-[1.25] tracking-[-0.01em]">
                Researchers lose weeks finding papers, reading them for answers and wondering which ones to trust, and months
                on ideas that are already done. GreenLight Research finds the papers, answers from them with citations, scores
                their credibility, and tells you whether the idea is new and where the real openings are.
              </p>
              <button onClick={start} className="mt-10 inline-block rounded-xl bg-go px-6 py-3.5 text-[16px] font-semibold text-on-go transition hover:bg-ink">
                Start researching
              </button>
            </div>
          </section>

          <footer className="border-t border-line py-10">
            <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 text-[14px] text-muted sm:px-8">
              <span className="flex items-center gap-2"><Mark size={18} /> GreenLight Research, built at Nebius Build Week, Berlin, 2026.</span>
              <span>Open models: NVIDIA Nemotron on Nebius Token Factory, Qwen embeddings, Tavily search.</span>
            </div>
          </footer>
        </div>
      </main>
    </div>
  )
}
