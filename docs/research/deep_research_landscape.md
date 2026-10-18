# Open-source deep-research landscape → what GreenLight Research should borrow

Researched 2026-10-18 (read-only on code). Stars / licence / last push are from the GitHub API on that day.
Benchmark numbers are the projects' own claims unless noted; "≈" or "(secondary)" = only found in third-party
write-ups, verify before quoting on stage.

**TL;DR.** Almost every open deep-research system writes *reports*; almost none rules on *novelty*, and the one that
does (AI Scientist's novelty check) is known to mislabel established methods as novel. Our moat (deterministic
credibility, quote-verified novelty matrix, strict judge, code guardrails, evidence gate, budgets, trace) is real.
What we lack versus the best systems is (1) **an eval of the verdict itself**, (2) **verdict stability**, and (3) the
**quote-first writing / self-feedback** tricks that make OpenScholar, Ai2 ScholarQA and PaperQA2 citation-accurate.

---

## 1. Projects

### 1a. Overview

| # | Project | Repo | ★ | Licence | Last push | Type |
|---|---|---|---|---|---|---|
| 1 | **NVIDIA AI-Q** (Deep Researcher) | [NVIDIA-AI-Blueprints/aiq](https://github.com/NVIDIA-AI-Blueprints/aiq) | ~0.9k | Apache-2.0 | active | multi-agent, Nemotron, **sponsor** |
| 2 | **PaperQA2** (FutureHouse) | [Future-House/paper-qa](https://github.com/Future-House/paper-qa) | 9.4k | Apache-2.0 | 2026-10 | scientific RAG agent |
| 3 | **OpenScholar** (UW / Ai2) | [AkariAsai/OpenScholar](https://github.com/AkariAsai/OpenScholar) | 1.7k | Apache-2.0 | 2025-08 | scientific RAG + self-feedback |
| 4 | **Ai2 ScholarQA** | [allenai/ai2-scholarqa-lib](https://github.com/allenai/ai2-scholarqa-lib) | 0.3k | Apache-2.0 | 2026-10 | literature synthesis pipeline |
| 5 | **Ai2 Paper Finder (Asta)** | [allenai/asta-paper-finder](https://github.com/allenai/asta-paper-finder) | 0.3k | Apache-2.0 | 2026-03 | paper-finding agent |
| 6 | **STORM / Co-STORM** (Stanford) | [stanford-oval/storm](https://github.com/stanford-oval/storm) | 31.7k | MIT | 2025-09 | perspective-driven article writer |
| 7 | **GPT-Researcher** | [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | 30.2k | Apache-2.0 | 2026-10 | planner + executors, deep tree mode |
| 8 | **LangChain open_deep_research** | [langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research) | 12.7k | MIT | 2026-08 | supervisor + researchers (LangGraph) |
| 9 | **HF smolagents Open Deep Research** | [huggingface/smolagents](https://github.com/huggingface/smolagents) (`examples/open_deep_research`) | 29.9k | Apache-2.0 | 2026-10 | code-acting agent |
| 10 | **dzhng/deep-research** | [dzhng/deep-research](https://github.com/dzhng/deep-research) | 19.8k | MIT | 2026-04 | minimal recursive breadth×depth |
| 11 | **Jina node-DeepResearch** | [jina-ai/node-DeepResearch](https://github.com/jina-ai/node-DeepResearch) | 5.2k | Apache-2.0 | 2026-05 | single-agent loop + gaps queue |
| 12 | **Tongyi DeepResearch** (Alibaba) | [Alibaba-NLP/DeepResearch](https://github.com/Alibaba-NLP/DeepResearch) | 20.1k | Apache-2.0 | 2026-02 | RL-trained 30B-A3B agent model |
| 13 | **ByteDance DeerFlow** 2.0 | [bytedance/deer-flow](https://github.com/bytedance/deer-flow) | 84.1k | MIT | 2026-10 | "super-agent" harness |
| 14 | **local-deep-research** | [LearningCircuit/local-deep-research](https://github.com/LearningCircuit/local-deep-research) | 9.3k | MIT | 2026-10 | local-LLM research, journal-quality filter |
| 15 | **MindSearch** (InternLM) | [InternLM/MindSearch](https://github.com/InternLM/MindSearch) | 6.9k | Apache-2.0 | 2025-07 | planner builds a question DAG |
| 16 | **WebThinker** (RUC) | [RUC-NLPIR/WebThinker](https://github.com/RUC-NLPIR/WebThinker) | 1.5k | MIT | 2025-12 | reasoning model + think-search-draft |
| 17 | **Search-R1** / R1-Searcher / ReCall | [PeterGriffinJin/Search-R1](https://github.com/PeterGriffinJin/Search-R1), [RUCAIBox/R1-Searcher](https://github.com/RUCAIBox/R1-Searcher), [Agent-RL/ReCall](https://github.com/Agent-RL/ReCall) | 5.5k / 0.7k / 1.4k | Apache / MIT / MIT | 2025 | RL training for search |
| 18 | **AI Scientist v1/v2** (Sakana) | [SakanaAI/AI-Scientist](https://github.com/SakanaAI/AI-Scientist), [-v2](https://github.com/SakanaAI/AI-Scientist-v2) | 14.8k / 7.4k | custom (AI Scientist Source Code License) | 2025-12 | idea → experiments → paper |
| 19 | **Agent Laboratory** | [SamuelSchmidgall/AgentLaboratory](https://github.com/SamuelSchmidgall/AgentLaboratory) | 5.9k | MIT | 2025-08 | lit review → experiments → report |
| 20 | **Robin** (FutureHouse) | [Future-House/robin](https://github.com/Future-House/robin) | 0.7k | Apache-2.0 | 2026-04 | hypothesis-generation multi-agent |
| 21 | **Zilliz DeepSearcher** | [zilliztech/deep-searcher](https://github.com/zilliztech/deep-searcher) | 8.3k | Apache-2.0 | 2026-09 | deep research over private data (Milvus) |
| 22 | **Khoj** | [khoj-ai/khoj](https://github.com/khoj-ai/khoj) | 37.7k | AGPL-3.0 | 2026-08 | personal "second brain" + research mode |
| – | Anthropic Research (closed, but best public write-up) | [blog](https://www.anthropic.com/engineering/multi-agent-research-system) | – | – | – | orchestrator-worker reference design |

Also seen, lower priority: [camel-ai/owl](https://github.com/camel-ai/owl) (20k, GAIA workforce),
[SkyworkAI/DeepResearchAgent](https://github.com/SkyworkAI/DeepResearchAgent) (3.6k, hierarchical),
[MiroMindAI/MiroThinker](https://github.com/MiroMindAI/MiroThinker) (8.4k, open research-agent model),
[mshumer/OpenDeepResearcher](https://github.com/mshumer/OpenDeepResearcher) (2.8k, notebook demo). Kimi-Researcher
(Moonshot) is end-to-end RL but its agent is not open source.

### 1b. Architecture, retrieval, memory, verification, evals

| Project | Architecture / loop | Retrieval & citations | Context / memory | Verification | Reported evals | Models | Genuinely novel |
|---|---|---|---|---|---|---|---|
| **AI-Q** | LangGraph state machine on NeMo Agent Toolkit + LangChain Deep Agents. **Intent router** → meta answer / **shallow** researcher (bounded) / **deep** researcher (planning, concurrent researcher workers, dedicated writer) | Tavily (default), Exa, You.com; Google Scholar via Serper/SerpAPI; pluggable RAG (NVIDIA RAG, LlamaIndex/Chroma, OpenSearch) | bounded source-tool batching | **rejects citation-incomplete drafts** instead of publishing | #1 on DeepResearch Bench (≈55.95) and DRB II (≈54.50) (secondary); built-in DRB RACE/FACT + FreshQA harness | Nemotron 3 Ultra for deep roles, Nemotron 3.5 Lightning for routing/shallow, Nemotron Embed | Same model family as us; shallow/deep routing; citation-completeness gate |
| **PaperQA2** | Agent with 3 tools in any order: paper search → gather evidence → generate answer (repeatable, broad + narrow searches) | LLM keyword queries over S2/OpenAlex/Crossref; chunks embedded (hybrid dense + sparse); **RCS**: each retrieved chunk is *summarised in context of the question and scored* by an LLM, top summaries kept (`evidence_k`=10, ≤5 sources) | evidence summaries replace raw chunks | metadata: **retraction check**, journal quality, citation counts (S2, Crossref, Unpaywall, OpenAlex) | LitQA2 (248 MCQ): above PhD/postdoc biologists on precision & accuracy; WikiCrow more accurate than Wikipedia; ContraCrow 2.34 contradictions/paper, 70% validated | GPT-4o default, any LiteLLM | RCS; LitQA2 benchmark; contradiction finding at scale |
| **OpenScholar** | Retrieve → draft → **self-feedback** (LM writes feedback: missing info, unsupported claims) → retrieve more → revise → **post-hoc citation verification** | 45M open-access papers (peS2o), ~237M passages; trained retriever + cross-encoder reranker; + S2 API + web | – | citation verification pass; claims every statement is attributed | **ScholarQABench** (2,967 queries, 208 long-form answers, CS/physics/neuro/biomed): OpenScholar-8B beats GPT-4o by 6.1% and PaperQA2 by 5.5% on correctness (Nature 2026); GPT-4o hallucinated 78-90% of citations; experts preferred OS-GPT-4o answers 70% vs human | OpenScholar-8B (Llama-3.1 fine-tune), also GPT-4o | Self-feedback loop; open 45M-paper datastore; ScholarQABench |
| **Ai2 ScholarQA** | Fixed pipeline: retrieve → **quote extraction** (per paper) → **plan outline + cluster quotes into sections** → write each section only from its assigned quotes (+ prior sections) → **comparison tables** for list-like sections | S2 **snippet search** over 11.7M full texts + keyword abstract search, `mxbai-rerank-large-v1`, aggregated to paper level | sections see only their quotes | quotes are exact text, so every claim has a span | outperforms competitors on ScholarQA-CS (ACL 2025 demo paper) | Claude 3.7 Sonnet default | Quote-first writing; auto literature-review tables (ArxivDIGESTables) |
| **Asta Paper Finder** | Query decomposition → search + **citation following** + per-paper **relevance judgement** → follow-up queries | S2 | – | LLM relevance judgement per paper | PaperFindingBench (AstaBench) adj. F1 ≈0.38 (secondary) | – | Relevance-judged paper finding as its own benchmarked task |
| **STORM / Co-STORM** | Pre-writing: discover **perspectives** from similar articles → simulated writer(perspective)↔expert conversations grounded in search → outline → section-by-section article. Co-STORM: human joins a multi-expert discourse; **Moderator** asks questions from *retrieved-but-unused* info; dynamic **mind map** | web search (You/Bing/…), citations per sentence | mind map organises collected info hierarchically | – | FreshWiki (recent Wikipedia articles, leak-free); WildSeek (Co-STORM); editors rated breadth/organisation above outline-RAG | GPT-4o / any | Perspective-guided questioning; "unused evidence" moderator |
| **GPT-Researcher** | Planner writes research questions → parallel executor agents crawl → planner aggregates + filters → report; deep mode = recursive tree (breadth × depth); newer lead/subagent mode with isolated contexts and todo list | 20+ sources/report, many retrievers, local docs, MCP | subagent contexts isolated | source curation/filtering | DeepResearch Bench entry (lower than ODR) | any | Early, well-engineered planner/executor pattern |
| **open_deep_research** | Scope (clarify + brief) → **supervisor** spawns researcher sub-agents via a tool → each researcher ends with a `compress_research` step → final report writer | Tavily / native search / MCP | **compression at the researcher boundary**; supervisor only sees compressed notes | – | DeepResearch Bench RACE 0.4344 (#6 at submission), 0.4943 with GPT-5 | configurable per role (summarise / research / compress / write) | Clean reference of supervisor + compression; per-role model config |
| **smolagents ODR** | Single **CodeAgent** (actions written as Python) + text-browser sub-agent | text browser (from AutoGen), search | – | – | GAIA val **55.15%** (prior open SOTA ~46%); JSON tool-calling instead of code → 33% | o1 / GPT-4o | Code-as-action beats JSON tool calls by ~20 pts on GAIA |
| **dzhng/deep-research** | ~500 LoC: generate SERP queries → read → extract **learnings + follow-up directions** → recurse with breadth halving per depth level | Firecrawl | learnings list carried down the tree | – | none | any | Tiny, readable breadth×depth recursion |
| **Jina node-DeepResearch** | One loop with actions search / visit / reflect / answer; **gaps queue** of sub-questions; disables an action for a step when it yields nothing new; **token budget → "beast mode"** forced answer | Jina Reader + search, embeddings for dedup | knowledge list + gaps queue | answer evaluator (definitive + has references), failed answers stored and context reset | none official | Gemini Flash / any | Gaps queue; action-disabling when no new info |
| **Tongyi DeepResearch** | Agent *model* (30B-A3B MoE) trained with agentic CPT → SFT → on-policy RL on synthetic data; ReAct mode and **Heavy mode = IterResearch** (each round *rebuilds* a compact workspace instead of appending) with parallel agents + synthesiser | web search, visit, scholar, python | **IterResearch** workspace reconstruction per round | – | HLE 32.9, BrowseComp 43.4 (ReAct); Heavy: HLE 38.3, BrowseComp 58.3 (vs o3 24.9 / 49.7) | Tongyi-DR-30B-A3B (Apache-2.0, on OpenRouter) | Open agent model at o3 level; round-wise context rebuild |
| **DeerFlow 2.0** | Lead agent + sub-agents (capped per run), sandboxes (local/Docker/K8s), skills, MCP; v1 (1.x branch) was coordinator → planner (**human edits the plan**) → researcher/coder → reporter | Tavily, Brave, SearXNG…; fetch via Jina/Firecrawl/Crawl4AI | per-user long-term memory; compaction keeps **artifact handles** (paths/URLs) that survive summarisation | – | none in README | DeepSeek, Kimi, Doubao, Qwen, vLLM… | Artifact handles survive compaction; plan-review HITL (v1) |
| **local-deep-research** | Quick pipeline / LangGraph agent strategies | arXiv, PubMed, S2, Wikipedia, SearXNG, GitHub, Tavily…; encrypted local library | research history | **journal reputation scoring over 212k sources + predatory-journal detection** (OpenAlex + DOAJ + Stop Predatory Journals) | SimpleQA 95.7% (Qwen3.6-27B, n=300), xbench-DeepSearch 77% (n=100) | local LLMs | Journal-quality / predatory filter, cheap and deterministic |
| **MindSearch** | WebPlanner writes **code that builds a DAG** of atomic sub-questions; WebSearcher per node does hierarchical retrieval; graph extended as answers arrive | web search engines | per-node contexts | – | human preference vs Perplexity Pro / ChatGPT-Web (ICLR 2025) | InternLM2.5-7B, GPT-4o | Question DAG as explicit plan state |
| **WebThinker** | Large reasoning model interleaves think → search → **draft report sections while researching**; Deep Web Explorer sub-module navigates links | web search + page navigation | – | – | GPQA, GAIA, WebWalkerQA, HLE gains over RAG baselines (NeurIPS 2025) | QwQ-32B / DeepSeek-R1-distill, RL via iterative online DPO | Write-while-research |
| **Search-R1 / R1-Searcher / ReCall** | Train the model with RL (PPO/GRPO) to emit `<search>` calls; **retrieved tokens are loss-masked**; outcome reward (EM) | local Wikipedia retriever (E5) | – | – | +20-40% over RAG on NQ/HotpotQA/… for Qwen2.5 | Qwen2.5 3-7B | Recipe for training search policies (not hackathon-scale) |
| **AI Scientist v1/v2** | Idea gen → **novelty check** (multi-round S2 search, LLM decides novel/not) → experiments (v2: best-first agentic tree search) → paper → LLM reviewer | Semantic Scholar | – | LLM reviewer | v2: one of 3 papers accepted at an ICLR 2025 workshop. Independent evaluations report the novelty check often labels **established methods as novel** | GPT-4o / Claude / o1 | End-to-end; the novelty check is the weak link (our opening) |
| **Agent Laboratory** | Phases: literature review (arXiv) → plan → experiments (mle-solver) → report (paper-solver); optional human co-pilot each phase | arXiv API | phase handoffs | – | human ratings; large cost cut vs prior autonomous systems | o1 / GPT-4o / DeepSeek | Human checkpoint per phase |
| **Robin** | Literature-search agent (Crow/Falcon on PaperQA) + data-analysis agent → ranked hypotheses via **pairwise LLM tournament** | PaperQA-based | – | – | proposed a drug candidate later validated in lab (paper) | – | Tournament ranking of candidates |
| **Anthropic Research** | Lead (Opus) plans, **saves plan to memory**, spawns 3-5 parallel subagents with explicit objective/output/tools/boundaries; **CitationAgent** runs last | web + workspace tools | plan in external memory; subagents write to storage and pass references | citation agent | +90.2% vs single agent on internal eval; token usage ≈80% of BrowseComp variance; ≈15× chat tokens | Claude | Effort-scaling rules in prompt; 20-query LLM-judge rubric eval |

---

## 2. GreenLight Research vs the field

### What we already do better (say this on stage)

| GreenLight Research | Field |
|---|---|
| **A verdict, not just a report**: novelty matrix per component, Chamber, guardrailed green/amber/red | Only AI Scientist checks novelty, with a single LLM yes/no that over-calls "novel" |
| **Deterministic credibility score** (FWCI, percentile, h-index, venue, HF adoption, verified audit flags, recency handling) | PaperQA2 pulls citation counts/retractions/journal quality as metadata; local-deep-research scores journals. No one scores papers with a transparent formula |
| **Quote verification** for every overlap + strict second judge ("same mechanism, other setting = partial") | ScholarQA extracts quotes; nobody re-judges "full" claims |
| **Code guardrails** that can only make the light more severe | AI-Q rejects citation-incomplete drafts (closest analogue) |
| **Calibrated evidence gate** (AUROC 1.0 answerable vs off-topic) | PaperQA2 has a relevance cutoff; not calibrated |
| Hand-written harness: parallel tools, budgets parent→child, loop detection, 3-tier compression, review gate, forced finish | Most use LangGraph; Jina has budget + beast mode; ODR has compression at sub-agent boundary — we have all of these |
| Relationship graph with the **reference line as proof** per citation edge | Paper Finder follows citations; nobody shows proof per edge |
| Redaction before any query; full trace with cost per model | – |
| Same sponsor stack as NVIDIA's own #1 DeepResearch Bench agent (Nemotron + Tavily) | AI-Q validates our model choice |

### Gaps

1. **No eval of the verdict.** The Proof page measures retrieval only. Every serious project reports a task metric
   (LitQA2, ScholarQABench, DRB, GAIA). Judges will ask "how often is it right?"
2. **Verdict instability** (same idea → AMBER on one run, GREEN on another, README).
3. **Report citation support is low** (3 supported / 9 partial / 3 unsupported of 15 claims on the Nebius run).
   ScholarQA and OpenScholar fix exactly this with quote-first writing and self-feedback.
4. **Cross-domain "same mechanism" misses** depend on the scouts thinking of other fields (LLaVA-MoLE case).

---

## 3. Ideas to adopt, ranked by value / effort (hackathon)

Effort: S ≤ 2 h, M ≈ half a day, L ≥ 1 day.

| Rank | Idea (from) | What to change in GreenLight Research | Value | Effort |
|---|---|---|---|---|
| **1** | **Verdict self-consistency** (Robin tournament, Tongyi Heavy synthesis, standard self-consistency) | `agents/chamber.py`/`verdict.py`: run the Speaker 3× (Ultra cost ≈ $0.008/call), majority vote, show the vote split ("2/3 AMBER") and use disagreement as a signal (split vote → at least AMBER guardrail). Optionally force 2 research rounds when the Critic approves round 1 with < N "very close" papers | Fixes the known AMBER/GREEN flip; visible on stage | S |
| **2** | **"Time-travel" verdict benchmark** (AI Idea Bench 2025, RINoBench, LitQA2 idea of answers that exist once) | New eval in `evals.py`: take ideas whose paper is known, run the pipeline with search capped *before* or *after* that paper's date. "Already done" = idea taken from a real paper, search allowed → must find that paper and rule RED/AMBER. "Novel at the time" = same idea, search capped before its publication → should not be RED. Report hit-rate of the source paper in the top-k and verdict accuracy on the Proof page. See §4 option A | Answers "how often is it right?"; unique (no other system has a novelty-verdict eval) | M |
| **3** | **Quote-first section writing** (Ai2 ScholarQA) + **citation-completeness gate** (AI-Q) | `agents/writer.py`: write the report from the novelty matrix's *verified quotes* grouped per component (each section sees only its quotes), not from summaries; then drop or mark sentences the citation checker rates unsupported before publishing. Add one auto **comparison table** (components × closest papers) — we already have the data | Raises supported-citation rate; table is a judge-friendly artefact | S-M |
| **4** | **Self-feedback loop on the report** (OpenScholar) | After the citation check, Nano lists ≤ 3 gaps ("claim X unsupported", "component C has no closest paper") → `search_corpus` / one scout → revise once, keep only if the check improves (we already do this for chat; reuse) | Higher factuality, small code since chat has it | S |
| **5** | **Perspective-guided scouts** (STORM) | `agents/planner.py`: besides topical angles, always add 2 *perspective* angles: "same mechanism in another modality/field" and "a reviewer arguing this is incremental" (+ "a practitioner who would already use X"). Directly targets the LLaVA-MoLE miss | Catches cross-domain prior art | S |
| **6** | **Effort-scaling + broad-then-narrow prompts** (Anthropic) | Lead prompt: explicit rules (narrow idea → 2 scouts × ~5 calls; multi-component idea → 4-5 scouts), "start with short broad queries, then narrow"; give each scout objective, output format, tool guidance, boundaries (we mostly do the last part) | Fewer wasted calls, more coverage | S |
| **7** | **Contextual evidence summaries (RCS)** (PaperQA2) | Before novelty mapping, for each closest paper × component, Nano writes a 2-sentence component-specific summary with a 0-10 score from retrieved passages; mapper gets these + quotes instead of raw chunks | Better mapping on long full texts, cheaper context | M |
| **8** | **Journal-quality / predatory filter** (local-deep-research) + retraction list | `credibility.py` venue component: DOAJ + predatory list lookup (deterministic, fits invariant 3). We already have OpenAlex `is_retracted`; add Retraction Watch CSV for DOIs OpenAlex misses. See §4 option C | Stronger "credibility is computed" story | S-M |
| **9** | **Shallow / deep routing** (AI-Q) | A "quick check" mode: planner + 1 scout round + Speaker without Chamber (~1-2 min) for live demo; full run stays default | Demo safety (9-min runs) | M |
| **10** | **Gaps queue + action disabling** (Jina) | Scouts: if a search returns 0 new P# ids twice, steer to `citation_hop` / `read_paper` instead of another search (extends our loop detection) | Fewer dead searches | S |
| **11** | **Checkpoint / resume** (Anthropic) | Persist stage outputs in `pipeline.py`; resume after a crash or `--reload` from the last finished stage | Robustness during demo | M |
| 12 | Artifact handles survive compaction (DeerFlow) | `harness/context.py` tier-2 fold: always keep the list of P# ids / URLs touched | Small quality gain | S |
| 13 | LLM-judge rubric over 20 queries (Anthropic) / DeepResearch Bench RACE | Score reports 0-1 on factual accuracy, citation accuracy, completeness, source quality, efficiency | Nice-to-have after #2 | M |
| – | Not worth it now | RL-training a search policy (Search-R1, Tongyi), code-as-action agents (smolagents), experiment execution (AI Scientist, Agent Lab) | – | L |

Optional sponsor-flavoured extra: Tongyi-DeepResearch-30B-A3B is open (Apache-2.0) and on OpenRouter; it could be
benchmarked as a scout model, but stick to Nemotron on Nebius for the pitch.

---

## 4. Knowledge data options

### A. Novelty-verdict benchmark ("GLR-NoveltyBench", recommended)

| | |
|---|---|
| What | 30-60 research ideas with known answers. **Already-done set**: ideas paraphrased from abstracts of papers published after the models' training cutoff (e.g. ICLR/NeurIPS/ACL 2025-26 accepted papers via OpenReview / arXiv); gold = that paper (and its listed closest works). **Novel-at-the-time set**: the *same* ideas evaluated with search capped to before the paper's publication date (time travel), plus a slice of [RINoBench](https://huggingface.co/datasets/TimSchopf/RINoBench) ideas with expert 1-5 novelty scores for calibration |
| Size | 30 ideas × 2 conditions = 60 runs ≈ 6 h wall time, ~$12 on Nebius (at $0.195/run); start with 10 ideas |
| Sources / licence | arXiv metadata (CC0 metadata), OpenReview (public); RINoBench data on HF (check its dataset licence; paper is CC BY 4.0) |
| Build effort | M: an LLM paraphrase script (must not reuse the title or more than 3 consecutive words of the abstract, like our retrieval eval), manual check of 30 items, plus a `before_date` filter in sources: OpenAlex `to_publication_date` filter, arXiv `submittedDate:[… TO …]` query, HF/Tavily results filtered by `published` date in `papers.py` |
| Metrics | source-paper recall@10 among collected papers, "closest paper" hit, verdict accuracy (already-done → RED/AMBER), false-RED rate on the time-capped set, run-to-run verdict agreement (3 runs on 5 ideas) |
| Plugs in | `evals.py` + Proof page, next to retrieval eval. Measures ideas #1, #3, #5 above |

### B. Pre-indexed AI/ML paper corpus with citation graph

| | |
|---|---|
| What | All arXiv cs.AI / cs.CL / cs.CV / cs.LG / stat.ML papers (on the order of 10⁵-10⁶; count it from the dump) with title + abstract, Qwen3-Embedding-8B vectors (1024-d MRL, same as `corpus.py`), plus OpenAlex `referenced_works` citation edges restricted to the set |
| Sources / licence | [arXiv metadata dump](https://www.kaggle.com/datasets/Cornell-University/arxiv) (metadata CC0); [OpenAlex snapshot](https://docs.openalex.org/download-all-data/openalex-snapshot) (CC0, S3, no account); optional [Semantic Scholar Datasets API](https://www.semanticscholar.org/product/api) (needs key; ODC-BY for most sets, has SPECTER2 embeddings + citations) |
| Size | ~1.4 GB float16 vectors per ~700k papers at 1024-d + abstracts ~1 GB; pgvector HNSW in the Postgres we already run in GreenLight |
| Build effort | L for the full set (1 day): embedding ~175M abstract tokens on the RTX PRO 6000 with vLLM, or via Token Factory. M if limited to 2023-2026 papers |
| Plugs in | New `sources/local.py` tool "search the local AI/ML index" (dense + BM25, no rate limits, ~50 ms) used by scouts first; citation hops offline. Fixes vocabulary-mismatch recall and OpenAlex/S2 rate limits, and makes the time-travel benchmark (A) reproducible |

### C. Credibility side-data (cheapest)

| | |
|---|---|
| What | Retraction Watch database (DOI → retraction/correction/expression of concern), DOAJ journal list, a predatory-journal list, optional CORE conference ranks |
| Sources / licence | [Retraction Watch via Crossref](https://gitlab.com/crossref/retraction-watch-data) (CSV, updated daily, opened by Crossref in 2023; check licence file); [DOAJ](https://doaj.org/docs/public-data-dump/) (metadata CC0); [Stop Predatory Journals](https://predatoryjournals.org) list |
| Size | tens of MB |
| Build effort | S (2-4 h): download script + DOI/ISSN lookup tables |
| Plugs in | `credibility.py` integrity (retractions/EoC beyond OpenAlex's flag) and venue (predatory → venue 0, DOAJ-listed OA journal → normal); evidence shown in the UI as today |

**Recommendation:** build **A** first (it is the only one that produces a headline number for judges and directly
tests the verdict), do **C** in the margins (2-4 h, strengthens the credibility story), and leave **B** unless the
team has a free day; A's time-travel filter works against the live APIs without B.

---

## 5. Sources

- AI-Q: [repo](https://github.com/NVIDIA-AI-Blueprints/aiq), [NVIDIA blog](https://developer.nvidia.com/blog/how-to-build-deep-agents-for-enterprise-search-with-nvidia-ai-q-and-langchain), [model card](https://build.nvidia.com/nvidia/aiq/modelcard), [forum: top DRB score](https://forums.developer.nvidia.com/t/nvidia-ai-q-achieves-top-score-for-open-portable-ai-researcher/341232), [HyperAI write-up (scores)](https://hyper.ai/en/stories/8e16035fa566be8864bbf764850fd647)
- PaperQA2: [repo](https://github.com/Future-House/paper-qa), [paper arXiv:2409.13740](https://arxiv.org/abs/2409.13740v2), [FutureHouse post](https://www.futurehouse.org/articles/wikicrow)
- OpenScholar: [repo](https://github.com/AkariAsai/OpenScholar), [arXiv:2411.14199](https://arxiv.org/abs/2411.14199v1), [project](https://openscholar.allen.ai/paper), [Nature summary (infodocket)](https://www.infodocket.com/?p=167650)
- Ai2 ScholarQA: [repo](https://github.com/allenai/ai2-scholarqa-lib), [arXiv:2504.10861](https://arxiv.org/html/2504.10861v1), [blog](https://allenai.org/blog/ai2-scholarqa)
- Asta Paper Finder: [repo](https://github.com/allenai/asta-paper-finder)
- STORM: [repo](https://github.com/stanford-oval/storm), [arXiv:2402.14207](https://www.arxiv-vanity.com/papers/2402.14207)
- GPT-Researcher: [repo](https://github.com/assafelovic/gpt-researcher), [docs](https://docs.gptr.dev/docs/gpt-researcher/getting-started/introduction)
- open_deep_research: [repo](https://github.com/langchain-ai/open_deep_research), [DRB leaderboard commit](https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard/commit/de24ae39455b7a7f81558890c5daf5905fa51841)
- smolagents ODR: [HF blog](https://huggingface.co/blog/open-deep-research)
- dzhng/deep-research: [repo](https://github.com/dzhng/deep-research); Jina: [repo](https://github.com/jina-ai/node-DeepResearch)
- Tongyi DeepResearch: [repo](https://github.com/Alibaba-NLP/DeepResearch), [launch thread](https://threadreaderapp.com/thread/1967988004179546451), [MarkTechPost](https://www.marktechpost.com/2025/09/18/alibaba-releases-tongyi-deepresearch-a-30b-parameter-open-source-agentic-llm-optimized-for-long-horizon-research/)
- DeerFlow: [repo](https://github.com/bytedance/deer-flow); local-deep-research: [repo](https://github.com/LearningCircuit/local-deep-research)
- MindSearch: [arXiv:2407.20183](https://arxiv.org/pdf/2407.20183), [ICLR 2025](https://www.iclr.cc/virtual/2025/poster/27772); WebThinker: [repo](https://github.com/RUC-NLPIR/WebThinker), [arXiv:2504.21776](https://arxiv.org/abs/2504.21776v1)
- Search-R1 / R1-Searcher / ReCall: repos linked in table 1a
- AI Scientist v2: [arXiv:2504.08066](https://arxiv.org/pdf/2504.08066), [ICLR workshop](https://iclr.cc/virtual/2025/37267); Agent Laboratory, Robin, DeepSearcher, Khoj: repos in table 1a
- Anthropic: [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- Novelty benchmarks: [RINoBench arXiv:2603.10303](https://arxiv.org/abs/2603.10303v1), [RINoBench data](https://huggingface.co/datasets/TimSchopf/RINoBench), [AI Idea Bench 2025](https://www.alphaxiv.org/abs/2504.14191v1), [NovGauge](https://arxiv.org/html/2609.11234v1), [Think-Probe-Respond](https://arxiv.org/pdf/2608.25660), [Deep Research survey](https://arxiv.org/pdf/2512.02038)
- Other benchmarks: [DeepScholar-Bench](https://arxiv.org/abs/2508.20033?context=cs), [ResearchRubrics](https://arxiv.org/pdf/2511.07685)
- Data: [Crossref × Retraction Watch](https://crossref.org/documentation/retrieve-metadata/retraction-watch/), [OpenAlex snapshot](https://docs.openalex.org/download-all-data/openalex-snapshot), [arXiv metadata (Kaggle)](https://www.kaggle.com/datasets/Cornell-University/arxiv), [DOAJ data dump](https://doaj.org/docs/public-data-dump/)

Not re-verified from primary sources (from memory / secondary): Search-R1 gain range, WebThinker benchmark list,
MindSearch evaluation details, AI-Q exact DRB scores, Paper Finder F1, Agent Laboratory cost claim.
