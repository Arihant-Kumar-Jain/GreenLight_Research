"""Persistence (stdlib SQLite): research projects, papers, corpus chunks, blackboard notes, chat, trace, web cache.

One file at GLR_DB_PATH. JSON columns hold agent outputs. Vectors are stored as float16 BLOBs next to their chunk.
"""

import json
import sqlite3
import threading
import time
import uuid
from typing import Any

import numpy as np

from .config import settings

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    title TEXT,
    idea_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft | queued | running | done | error
    stage TEXT,                            -- intake | plan | research | credibility | novelty | chamber | report | done
    brief TEXT, plan TEXT, novelty TEXT, debate TEXT, verdict TEXT, report TEXT, redactions TEXT, stats TEXT,
    chat_memory TEXT,                      -- compressed summary of older chat turns
    error TEXT
);
CREATE TABLE IF NOT EXISTS papers (
    id TEXT NOT NULL,                      -- P1, P2... stable citation handle inside a project
    project_id TEXT NOT NULL,
    key TEXT NOT NULL,                     -- canonical identity: arxiv:2106.09685 | doi:10... | title:<norm>
    added_at REAL NOT NULL,
    data TEXT NOT NULL,                    -- metadata, credibility, audit, relevance
    PRIMARY KEY (project_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS papers_key ON papers(project_id, key);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT NOT NULL,                      -- P3#c2
    project_id TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    kind TEXT NOT NULL,                    -- abstract | fulltext | web
    text TEXT NOT NULL,
    vec BLOB,
    PRIMARY KEY (project_id, id)
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    ts REAL NOT NULL,
    agent TEXT NOT NULL,
    kind TEXT NOT NULL,                    -- finding | gap | question | decision
    text TEXT NOT NULL,
    refs TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    ts REAL NOT NULL,
    phase TEXT NOT NULL,                   -- intake | chat
    role TEXT NOT NULL,                    -- user | assistant
    content TEXT NOT NULL,
    data TEXT
);
CREATE TABLE IF NOT EXISTS trace (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    ts REAL NOT NULL,
    agent TEXT NOT NULL,
    parent TEXT,
    kind TEXT NOT NULL,                    -- llm | tool | info | error | spawn | done | compress | guard | budget
    title TEXT NOT NULL,
    detail TEXT,
    provider TEXT, model TEXT,
    tokens_in INTEGER, tokens_out INTEGER, latency_ms INTEGER, cost_usd REAL
);
CREATE INDEX IF NOT EXISTS trace_project ON trace(project_id, id);
CREATE TABLE IF NOT EXISTS web_cache (key TEXT PRIMARY KEY, ts REAL NOT NULL, value TEXT NOT NULL);
"""

JSON_COLS = ("brief", "plan", "novelty", "debate", "verdict", "report", "redactions", "stats")


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            settings.db_path.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(settings.db_path, check_same_thread=False, isolation_level=None)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
            # A restart kills running analyses; say so instead of showing a spinner forever.
            _conn.execute("UPDATE projects SET status='error', error='Interrupted by a server restart. Press Re-run.' "
                          "WHERE status IN ('queued','running')")
        return _conn


def q(sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return conn().execute(sql, args).fetchall()


def x(sql: str, args: tuple = ()) -> int:
    with _lock:
        cur = conn().execute(sql, args)
        return cur.lastrowid or cur.rowcount


def _loads(v: str | None) -> Any:
    return json.loads(v) if v else None


# ---------------------------------------------------------------- projects

def create_project(idea_text: str, title: str | None = None, redactions: list | None = None) -> str:
    pid = uuid.uuid4().hex[:12]
    now = time.time()
    x("INSERT INTO projects (id, created_at, updated_at, title, idea_text, status, stage, redactions) "
      "VALUES (?,?,?,?,?,'draft','intake',?)", (pid, now, now, title, idea_text, json.dumps(redactions or [])))
    return pid


def project(pid: str) -> dict | None:
    rows = q("SELECT * FROM projects WHERE id=?", (pid,))
    if not rows:
        return None
    d = dict(rows[0])
    for c in JSON_COLS:
        d[c] = _loads(d[c])
    return d


def projects() -> list[dict]:
    rows = q("SELECT id, title, idea_text, status, stage, verdict, created_at, updated_at FROM projects "
             "ORDER BY updated_at DESC")
    out = []
    for r in rows:
        d = dict(r)
        v = _loads(d.pop("verdict"))
        d["light"] = v.get("light") if v else None
        out.append(d)
    return out


def update_project(pid: str, **fields: Any) -> None:
    if not fields:
        return
    sets, args = [], []
    for k, v in fields.items():
        sets.append(f"{k}=?")
        args.append(json.dumps(v, ensure_ascii=False) if k in JSON_COLS and v is not None else v)
    args += [time.time(), pid]
    x(f"UPDATE projects SET {', '.join(sets)}, updated_at=? WHERE id=?", tuple(args))


def delete_project(pid: str) -> None:
    for t in ("papers", "chunks", "notes", "messages", "trace"):
        x(f"DELETE FROM {t} WHERE project_id=?", (pid,))
    x("DELETE FROM projects WHERE id=?", (pid,))


# ---------------------------------------------------------------- papers

def paper_by_key(pid: str, key: str) -> dict | None:
    rows = q("SELECT id, data FROM papers WHERE project_id=? AND key=?", (pid, key))
    return {**json.loads(rows[0]["data"]), "id": rows[0]["id"]} if rows else None


def add_paper(pid: str, key: str, data: dict) -> tuple[str, bool]:
    """Insert a paper (or return the existing one's id). Returns (paper id, created)."""
    with _lock:
        hit = paper_by_key(pid, key)
        if hit:
            return hit["id"], False
        n = q("SELECT COUNT(*) AS n FROM papers WHERE project_id=?", (pid,))[0]["n"]
        paper_id = f"P{n + 1}"
        x("INSERT INTO papers (id, project_id, key, added_at, data) VALUES (?,?,?,?,?)",
          (paper_id, pid, key, time.time(), json.dumps({**data, "id": paper_id, "key": key}, ensure_ascii=False)))
        return paper_id, True


def update_paper(pid: str, paper_id: str, **fields: Any) -> dict:
    with _lock:
        cur = paper(pid, paper_id) or {}
        cur.update(fields)
        x("UPDATE papers SET data=? WHERE project_id=? AND id=?", (json.dumps(cur, ensure_ascii=False), pid, paper_id))
        return cur


def paper(pid: str, paper_id: str) -> dict | None:
    rows = q("SELECT data FROM papers WHERE project_id=? AND id=?", (pid, paper_id.strip().upper()))
    return json.loads(rows[0]["data"]) if rows else None


def papers(pid: str) -> list[dict]:
    rows = q("SELECT data FROM papers WHERE project_id=? ORDER BY added_at", (pid,))
    return [json.loads(r["data"]) for r in rows]


# ---------------------------------------------------------------- corpus chunks

def add_chunks(pid: str, rows: list[tuple[str, str, str, str, np.ndarray | None]]) -> None:
    with _lock:
        for cid, paper_id, kind, text, vec in rows:
            blob = vec.astype(np.float16).tobytes() if vec is not None else None
            x("INSERT OR REPLACE INTO chunks (id, project_id, paper_id, kind, text, vec) VALUES (?,?,?,?,?,?)",
              (cid, pid, paper_id, kind, text, blob))


def chunks(pid: str) -> list[dict]:
    rows = q("SELECT id, paper_id, kind, text, vec FROM chunks WHERE project_id=?", (pid,))
    return [{"id": r["id"], "paper_id": r["paper_id"], "kind": r["kind"], "text": r["text"],
             "vec": np.frombuffer(r["vec"], dtype=np.float16).astype(np.float32) if r["vec"] else None} for r in rows]


def chunk_ids_for(pid: str, paper_id: str) -> set[str]:
    return {r["id"] for r in q("SELECT id FROM chunks WHERE project_id=? AND paper_id=?", (pid, paper_id))}


# ---------------------------------------------------------------- blackboard notes

def add_note(pid: str, agent: str, kind: str, text: str, refs: list[str] | None = None) -> int:
    return x("INSERT INTO notes (project_id, ts, agent, kind, text, refs) VALUES (?,?,?,?,?,?)",
             (pid, time.time(), agent, kind, text, json.dumps(refs or [])))


def notes(pid: str, kind: str | None = None) -> list[dict]:
    sql = "SELECT * FROM notes WHERE project_id=?" + (" AND kind=?" if kind else "") + " ORDER BY id"
    rows = q(sql, (pid, kind) if kind else (pid,))
    return [{**dict(r), "refs": json.loads(r["refs"])} for r in rows]


# ---------------------------------------------------------------- chat messages

def add_message(pid: str, phase: str, role: str, content: str, data: dict | None = None) -> int:
    return x("INSERT INTO messages (project_id, ts, phase, role, content, data) VALUES (?,?,?,?,?,?)",
             (pid, time.time(), phase, role, content, json.dumps(data, ensure_ascii=False) if data else None))


def messages(pid: str, phase: str | None = None) -> list[dict]:
    sql = "SELECT * FROM messages WHERE project_id=?" + (" AND phase=?" if phase else "") + " ORDER BY id"
    rows = q(sql, (pid, phase) if phase else (pid,))
    return [{**dict(r), "data": _loads(r["data"])} for r in rows]


# ---------------------------------------------------------------- trace

def add_trace(**f: Any) -> None:
    x("INSERT INTO trace (project_id, ts, agent, parent, kind, title, detail, provider, model, tokens_in, tokens_out, "
      "latency_ms, cost_usd) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
      (f.get("project_id"), time.time(), f["agent"], f.get("parent"), f["kind"], f["title"], f.get("detail"),
       f.get("provider"), f.get("model"), f.get("tokens_in"), f.get("tokens_out"), f.get("latency_ms"),
       f.get("cost_usd")))


def trace(pid: str, after: int = 0, limit: int = 500) -> list[dict]:
    return [dict(r) for r in q("SELECT * FROM trace WHERE project_id=? AND id>? ORDER BY id LIMIT ?",
                               (pid, after, limit))]


def trace_totals(pid: str) -> dict:
    r = q("SELECT COUNT(*) AS calls, COALESCE(SUM(tokens_in),0) AS tin, COALESCE(SUM(tokens_out),0) AS tout, "
          "COALESCE(SUM(cost_usd),0) AS cost FROM trace WHERE project_id=? AND kind='llm'", (pid,))[0]
    by_model = q("SELECT model, COUNT(*) AS calls, COALESCE(SUM(tokens_in),0)+COALESCE(SUM(tokens_out),0) AS tokens, "
                 "COALESCE(SUM(cost_usd),0) AS cost FROM trace WHERE project_id=? AND kind='llm' GROUP BY model",
                 (pid,))
    tools = q("SELECT COUNT(*) AS n FROM trace WHERE project_id=? AND kind='tool'", (pid,))[0]["n"]
    agents = q("SELECT COUNT(DISTINCT agent) AS n FROM trace WHERE project_id=?", (pid,))[0]["n"]
    compress = q("SELECT COUNT(*) AS n FROM trace WHERE project_id=? AND kind='compress'", (pid,))[0]["n"]
    return {"llm_calls": r["calls"], "tokens_in": r["tin"], "tokens_out": r["tout"], "cost_usd": round(r["cost"], 5),
            "tool_calls": tools, "agents": agents, "compressions": compress,
            "by_model": [dict(m) for m in by_model]}


# ---------------------------------------------------------------- cache

def cache_get(key: str, max_age_s: float | None = None) -> Any:
    rows = q("SELECT ts, value FROM web_cache WHERE key=?", (key,))
    if not rows or (max_age_s and time.time() - rows[0]["ts"] > max_age_s):
        return None
    return json.loads(rows[0]["value"])


def cache_put(key: str, value: Any) -> None:
    x("INSERT OR REPLACE INTO web_cache (key, ts, value) VALUES (?,?,?)", (key, time.time(), json.dumps(value)))
