"""GreenLight Research HTTP API (FastAPI). Run: uv run uvicorn glr.api:app --reload --port 8100"""

import asyncio
import datetime as dt

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, db, evals, graph, llm, papers, pipeline, privacy, providers, rerank, web
from .agents import chat, intake
from .config import REPO_DIR, missing_keys, settings
from .privacy import scrub_secrets

app = FastAPI(title="GreenLight Research API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"],
                   allow_headers=["*"])

User = dict
CurrentUser = Depends(auth.require_user)
MaybeUser = Depends(auth.optional_user)

_chat_tasks: dict[str, asyncio.Task] = {}
_intake_tasks: dict[str, asyncio.Task] = {}


# ---------------------------------------------------------------- spend caps

def _daily_guard(run: bool = False) -> None:
    """GLR_MAX_USD_PER_DAY / GLR_MAX_RUNS_PER_DAY (UTC days). A run in flight may finish past the USD cap."""
    today = dt.datetime.now(dt.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    if settings.max_usd_per_day and db.spend_since(today.timestamp()) >= settings.max_usd_per_day:
        raise HTTPException(429, f"Today's budget (${settings.max_usd_per_day:.2f}) is used up. Try again tomorrow (UTC).")
    if run and settings.max_runs_per_day:
        key = f"runs:{today.date()}"
        n = db.cache_get(key) or 0
        if n >= settings.max_runs_per_day:
            raise HTTPException(429, f"Today's limit of {settings.max_runs_per_day} research runs is reached. "
                                     "Try again tomorrow (UTC).")
        db.cache_put(key, n + 1)


def _project_or_404(pid: str, user: User) -> dict:
    """The project if this user owns it. Other users' projects look like 404s."""
    p = db.project(pid)
    if not p or not auth.owns(user, p):
        raise HTTPException(404, "No such project")
    return p


# ---------------------------------------------------------------- status

@app.get("/api/health")
async def health():
    out = {"missing_keys": missing_keys(), "llm_provider": llm.provider_label(),
           "rerankers": {"chain": rerank.chain(), "calibrated": {k: v.get("threshold") for k, v in rerank.calibration().items()},
                         "local_model": rerank.default_local_model() if "local" in rerank.available() else None}, "query_expansion": settings.query_expansion,
           "tavily_key": bool(settings.tavily_api_key), "s2_key": bool(settings.s2_api_key),
           "openalex_polite": bool(settings.openalex_mailto),
           "budget_usd_per_run": settings.max_usd_per_run, "research_rounds": settings.max_research_rounds,
           "max_scouts": settings.max_scouts, "auth": auth.mode()}
    if settings.tavily_api_key:
        out["tavily_credits"] = await web.usage()
    if providers.active():
        try:
            out["models"] = await llm.model_info()
        except Exception as e:
            out["models_error"] = scrub_secrets(str(e))
    return out


# ---------------------------------------------------------------- auth

class GoogleLogin(BaseModel):
    credential: str


@app.get("/api/auth/me")
async def auth_me(user: User | None = MaybeUser):
    return auth.public_config(user)


@app.post("/api/auth/google")
async def auth_google(body: GoogleLogin, response: Response):
    return auth.public_config(await auth.login_with_google(body.credential, response))


@app.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response):
    auth.logout(request, response)
    return {"ok": True}


@app.post("/api/redact")
async def redact_preview(body: dict):
    r = privacy.redact(str(body.get("text", "")))
    return {"text": r.text, "found": r.summary()}


# ---------------------------------------------------------------- projects + intake chat

class Text(BaseModel):
    text: str


def _intake_view(pid: str, user: User) -> dict:
    p = _project_or_404(pid, user)
    return {"project": _summary(p), "messages": db.messages(pid, "intake"),
            "busy": pid in _intake_tasks and not _intake_tasks[pid].done()}


def _summary(p: dict) -> dict:
    return {k: p.get(k) for k in ("id", "title", "idea_text", "status", "stage", "brief", "error", "created_at",
                                  "updated_at")} | {"light": (p.get("verdict") or {}).get("light")}


async def _intake_turn(pid: str) -> None:
    try:
        t = await intake.turn(pid)
        db.add_message(pid, "intake", "assistant", t.reply,
                       {"questions": [q.model_dump() for q in t.questions], "ready": t.ready, "missing": t.missing})
    except Exception as e:
        db.add_message(pid, "intake", "assistant", f"Sorry, that turn failed: {scrub_secrets(str(e))[:300]}",
                       {"error": True})


@app.get("/api/projects")
async def list_projects(user: User | None = MaybeUser):
    return db.projects(user["id"]) if user else []


@app.post("/api/projects")
async def new_project(body: Text, user: User = CurrentUser):
    if missing := missing_keys():
        raise HTTPException(400, f"Add {', '.join(missing)} to GreenLight_Research/.env")
    r = privacy.redact(body.text.strip())
    if len(r.text) < 10:
        raise HTTPException(400, "Describe the idea in a sentence or two")
    _daily_guard()
    pid = db.create_project(r.text, redactions=r.summary(), user_id=user["id"])
    db.add_message(pid, "intake", "user", r.text, {"redactions": r.summary()} if r.count else None)
    _intake_tasks[pid] = asyncio.create_task(_intake_turn(pid))
    return _intake_view(pid, user)


@app.get("/api/projects/{pid}/intake")
async def get_intake(pid: str, user: User = CurrentUser):
    return _intake_view(pid, user)


@app.post("/api/projects/{pid}/intake")
async def intake_message(pid: str, body: Text, user: User = CurrentUser):
    _project_or_404(pid, user)
    if pid in _intake_tasks and not _intake_tasks[pid].done():
        raise HTTPException(409, "Still answering the previous message")
    _daily_guard()
    r = privacy.redact(body.text.strip())
    db.add_message(pid, "intake", "user", r.text, {"redactions": r.summary()} if r.count else None)
    _intake_tasks[pid] = asyncio.create_task(_intake_turn(pid))
    return _intake_view(pid, user)


@app.post("/api/projects/{pid}/start")
async def start(pid: str, user: User = CurrentUser):
    p = _project_or_404(pid, user)
    if not p.get("brief"):
        raise HTTPException(400, "The intake has not produced a brief yet")
    if missing := missing_keys():
        raise HTTPException(400, f"Add {', '.join(missing)} to GreenLight_Research/.env")
    if not pipeline.is_running(pid):
        _daily_guard(run=True)
        pipeline.start(pid)
    return _summary(db.project(pid))


@app.post("/api/projects/{pid}/stop")
async def stop(pid: str, user: User = CurrentUser):
    _project_or_404(pid, user)
    if not pipeline.cancel(pid):
        raise HTTPException(409, "Not running")
    return {"stopped": True}


@app.post("/api/projects/{pid}/rerun")
async def rerun(pid: str, user: User = CurrentUser):
    _project_or_404(pid, user)
    if pipeline.is_running(pid):
        raise HTTPException(409, "Already running")
    _daily_guard(run=True)
    for t in ("papers", "chunks", "notes", "trace"):
        db.x(f"DELETE FROM {t} WHERE project_id=?", (pid,))
    db.update_project(pid, plan=None, novelty=None, debate=None, verdict=None, report=None, stats=None)
    pipeline.start(pid)
    return _summary(db.project(pid))


@app.delete("/api/projects/{pid}")
async def delete(pid: str, user: User = CurrentUser):
    _project_or_404(pid, user)
    if pipeline.is_running(pid):
        raise HTTPException(409, "Stop the run first")
    db.delete_project(pid)
    return {"ok": True}


# ---------------------------------------------------------------- workspace

def _paper_row(p: dict) -> dict:
    c = p.get("credibility") or {}
    return {"id": p["id"], "title": p.get("title"), "year": p.get("year"), "url": p.get("url"),
            "pdf_url": p.get("pdf_url"), "arxiv_id": p.get("arxiv_id"), "doi": p.get("doi"),
            "authors": [a.get("name") for a in p.get("authors", [])[:8]], "n_authors": len(p.get("authors", [])),
            "venue": (p.get("venue") or {}).get("name"), "citations": p.get("citations"),
            "retracted": bool(p.get("is_retracted")), "found_by": p.get("found_by", []), "sources": p.get("sources", []),
            "credibility": c or None, "audit": p.get("audit"), "hf": p.get("hf"),
            "read": bool(p.get("fulltext")), "abstract": (p.get("abstract") or "")[:1200],
            "relevance": p.get("relevance"), "relevance_by": p.get("relevance_by")}


@app.get("/api/projects/{pid}")
async def get_project(pid: str, user: User = CurrentUser):
    p = _project_or_404(pid, user)
    return {**p, "chat_memory": None, "running": pipeline.is_running(pid),
            "papers": [_paper_row(x) for x in db.papers(pid)], "notes": db.notes(pid),
            "totals": db.trace_totals(pid)}


@app.get("/api/projects/{pid}/papers/{paper_id}")
async def get_paper(pid: str, paper_id: str, user: User = CurrentUser):
    _project_or_404(pid, user)
    p = db.paper(pid, paper_id)
    if not p:
        raise HTTPException(404, "No such paper")
    return p


@app.post("/api/projects/{pid}/papers/{paper_id}/score")
async def score_paper(pid: str, paper_id: str, user: User = CurrentUser):
    _project_or_404(pid, user)
    if not db.paper(pid, paper_id):
        raise HTTPException(404, "No such paper")
    _daily_guard()
    await papers.enrich(pid, [paper_id.upper()])
    return _paper_row(db.paper(pid, paper_id))


@app.get("/api/projects/{pid}/trace")
async def get_trace(pid: str, after: int = 0, user: User = CurrentUser):
    _project_or_404(pid, user)
    return {"events": db.trace(pid, after), "totals": db.trace_totals(pid)}


# ---------------------------------------------------------------- paper relationship graph

_graph_locks: dict[str, asyncio.Lock] = {}


@app.get("/api/projects/{pid}/graph")
async def get_graph(pid: str, refresh: bool = False, user: User = CurrentUser):
    _project_or_404(pid, user)
    key = f"graph:{pid}:{len(db.papers(pid))}"
    async with _graph_locks.setdefault(pid, asyncio.Lock()):
        if not refresh and (hit := db.cache_get(key)) is not None:
            return hit
        g = await graph.build(pid)
        db.cache_put(key, g)
        return g


class Pair(BaseModel):
    a: str
    b: str
    facts: str = ""


@app.post("/api/projects/{pid}/graph/explain")
async def explain_pair(pid: str, body: Pair, user: User = CurrentUser):
    _project_or_404(pid, user)
    _daily_guard()
    return {"text": await graph.explain(pid, body.a.upper(), body.b.upper(), body.facts[:600])}


# ---------------------------------------------------------------- proof: retrieval eval

_eval_task: asyncio.Task | None = None


@app.get("/api/evals")
async def get_evals():
    return {**evals.results(), "running": bool(_eval_task and not _eval_task.done())}


@app.post("/api/evals/retrieval/{pid}")
async def run_retrieval_eval(pid: str, rebuild: bool = False, user: User = CurrentUser):
    global _eval_task
    _project_or_404(pid, user)
    _daily_guard()
    if _eval_task and not _eval_task.done():
        raise HTTPException(409, "An eval is already running")
    _eval_task = asyncio.create_task(evals.run(pid, rebuild=rebuild))
    return {"started": True}


# ---------------------------------------------------------------- research chat (to-and-fro)

@app.get("/api/projects/{pid}/chat")
async def get_chat(pid: str, user: User = CurrentUser):
    _project_or_404(pid, user)
    msgs = db.messages(pid, "chat")
    for m in msgs:  # episodic-memory vectors stay server-side
        if m.get("data"):
            m["data"].pop("vec", None)
    return {"messages": msgs, "busy": pid in _chat_tasks and not _chat_tasks[pid].done(),
            "memory": (intake.load_memory(pid, "facts").get("items") or [])}


@app.post("/api/projects/{pid}/chat")
async def post_chat(pid: str, body: Text, user: User = CurrentUser):
    _project_or_404(pid, user)
    if pid in _chat_tasks and not _chat_tasks[pid].done():
        raise HTTPException(409, "Still answering the previous message")
    if not body.text.strip():
        raise HTTPException(400, "Empty message")
    _daily_guard()

    async def go():
        try:
            await chat.reply(pid, body.text.strip())
        except Exception as e:
            db.add_message(pid, "chat", "assistant", f"Sorry, that failed: {scrub_secrets(str(e))[:300]}",
                           {"error": True})
    _chat_tasks[pid] = asyncio.create_task(go())
    await asyncio.sleep(0.05)
    return await get_chat(pid, user)


# ---------------------------------------------------------------- static UI (make serve)

DIST = REPO_DIR / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
