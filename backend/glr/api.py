"""GreenLight Research HTTP API (FastAPI). Run: uv run uvicorn glr.api:app --reload --port 8100"""

import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, graph, llm, papers, pipeline, privacy, providers, web
from .agents import chat, intake
from .config import REPO_DIR, missing_keys, settings
from .privacy import scrub_secrets

app = FastAPI(title="GreenLight Research API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"],
                   allow_headers=["*"])

_chat_tasks: dict[str, asyncio.Task] = {}
_intake_tasks: dict[str, asyncio.Task] = {}


def _project_or_404(pid: str) -> dict:
    p = db.project(pid)
    if not p:
        raise HTTPException(404, "No such project")
    return p


# ---------------------------------------------------------------- status

@app.get("/api/health")
async def health():
    out = {"missing_keys": missing_keys(), "llm_provider": llm.provider_label(),
           "tavily_key": bool(settings.tavily_api_key), "s2_key": bool(settings.s2_api_key),
           "openalex_polite": bool(settings.openalex_mailto),
           "budget_usd_per_run": settings.max_usd_per_run, "research_rounds": settings.max_research_rounds,
           "max_scouts": settings.max_scouts}
    if settings.tavily_api_key:
        out["tavily_credits"] = await web.usage()
    if providers.active():
        try:
            out["models"] = await llm.model_info()
        except Exception as e:
            out["models_error"] = scrub_secrets(str(e))
    return out


@app.post("/api/redact")
async def redact_preview(body: dict):
    r = privacy.redact(str(body.get("text", "")))
    return {"text": r.text, "found": r.summary()}


# ---------------------------------------------------------------- projects + intake chat

class Text(BaseModel):
    text: str


def _intake_view(pid: str) -> dict:
    p = _project_or_404(pid)
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
async def list_projects():
    return db.projects()


@app.post("/api/projects")
async def new_project(body: Text):
    if missing := missing_keys():
        raise HTTPException(400, f"Add {', '.join(missing)} to GreenLight_Research/.env")
    r = privacy.redact(body.text.strip())
    if len(r.text) < 10:
        raise HTTPException(400, "Describe the idea in a sentence or two")
    pid = db.create_project(r.text, redactions=r.summary())
    db.add_message(pid, "intake", "user", r.text, {"redactions": r.summary()} if r.count else None)
    _intake_tasks[pid] = asyncio.create_task(_intake_turn(pid))
    return _intake_view(pid)


@app.get("/api/projects/{pid}/intake")
async def get_intake(pid: str):
    return _intake_view(pid)


@app.post("/api/projects/{pid}/intake")
async def intake_message(pid: str, body: Text):
    _project_or_404(pid)
    if pid in _intake_tasks and not _intake_tasks[pid].done():
        raise HTTPException(409, "Still answering the previous message")
    r = privacy.redact(body.text.strip())
    db.add_message(pid, "intake", "user", r.text, {"redactions": r.summary()} if r.count else None)
    _intake_tasks[pid] = asyncio.create_task(_intake_turn(pid))
    return _intake_view(pid)


@app.post("/api/projects/{pid}/start")
async def start(pid: str):
    p = _project_or_404(pid)
    if not p.get("brief"):
        raise HTTPException(400, "The intake has not produced a brief yet")
    if missing := missing_keys():
        raise HTTPException(400, f"Add {', '.join(missing)} to GreenLight_Research/.env")
    pipeline.start(pid)
    return _summary(db.project(pid))


@app.post("/api/projects/{pid}/rerun")
async def rerun(pid: str):
    _project_or_404(pid)
    if pipeline.is_running(pid):
        raise HTTPException(409, "Already running")
    for t in ("papers", "chunks", "notes", "trace"):
        db.x(f"DELETE FROM {t} WHERE project_id=?", (pid,))
    db.update_project(pid, plan=None, novelty=None, debate=None, verdict=None, report=None, stats=None)
    pipeline.start(pid)
    return _summary(db.project(pid))


@app.delete("/api/projects/{pid}")
async def delete(pid: str):
    _project_or_404(pid)
    if pipeline.is_running(pid):
        raise HTTPException(409, "Stop is not supported while running; wait for it to finish")
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
            "read": bool(p.get("fulltext")), "abstract": (p.get("abstract") or "")[:1200]}


@app.get("/api/projects/{pid}")
async def get_project(pid: str):
    p = _project_or_404(pid)
    return {**p, "chat_memory": None, "running": pipeline.is_running(pid),
            "papers": [_paper_row(x) for x in db.papers(pid)], "notes": db.notes(pid),
            "totals": db.trace_totals(pid)}


@app.get("/api/projects/{pid}/papers/{paper_id}")
async def get_paper(pid: str, paper_id: str):
    _project_or_404(pid)
    p = db.paper(pid, paper_id)
    if not p:
        raise HTTPException(404, "No such paper")
    return p


@app.post("/api/projects/{pid}/papers/{paper_id}/score")
async def score_paper(pid: str, paper_id: str):
    _project_or_404(pid)
    if not db.paper(pid, paper_id):
        raise HTTPException(404, "No such paper")
    await papers.enrich(pid, [paper_id.upper()])
    return _paper_row(db.paper(pid, paper_id))


@app.get("/api/projects/{pid}/trace")
async def get_trace(pid: str, after: int = 0):
    _project_or_404(pid)
    return {"events": db.trace(pid, after), "totals": db.trace_totals(pid)}


# ---------------------------------------------------------------- paper relationship graph

_graph_locks: dict[str, asyncio.Lock] = {}


@app.get("/api/projects/{pid}/graph")
async def get_graph(pid: str, refresh: bool = False):
    _project_or_404(pid)
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
async def explain_pair(pid: str, body: Pair):
    _project_or_404(pid)
    return {"text": await graph.explain(pid, body.a.upper(), body.b.upper(), body.facts[:600])}


# ---------------------------------------------------------------- research chat (to-and-fro)

@app.get("/api/projects/{pid}/chat")
async def get_chat(pid: str):
    _project_or_404(pid)
    return {"messages": db.messages(pid, "chat"), "busy": pid in _chat_tasks and not _chat_tasks[pid].done()}


@app.post("/api/projects/{pid}/chat")
async def post_chat(pid: str, body: Text):
    _project_or_404(pid)
    if pid in _chat_tasks and not _chat_tasks[pid].done():
        raise HTTPException(409, "Still answering the previous message")
    if not body.text.strip():
        raise HTTPException(400, "Empty message")

    async def go():
        try:
            await chat.reply(pid, body.text.strip())
        except Exception as e:
            db.add_message(pid, "chat", "assistant", f"Sorry, that failed: {scrub_secrets(str(e))[:300]}",
                           {"error": True})
    _chat_tasks[pid] = asyncio.create_task(go())
    await asyncio.sleep(0.05)
    return await get_chat(pid)


# ---------------------------------------------------------------- static UI (make serve)

DIST = REPO_DIR / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
