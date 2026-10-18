"""Agent trace: every LLM call, tool call, spawn, compression and guardrail is logged against the current project.

The UI polls this table to draw the live agent graph (agent -> parent edges come from `parent`) and the cost view.
Context vars carry project, agent, parent agent and the run budget through asyncio tasks, so parallel sub-agents
log under their own names without passing anything around.
"""

import contextvars
from contextlib import contextmanager

from . import db
from .budget import Budget
from .privacy import scrub_secrets

current_project: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_project", default=None)
current_agent: contextvars.ContextVar[str] = contextvars.ContextVar("current_agent", default="System")
current_parent: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_parent", default=None)
current_budget: contextvars.ContextVar[Budget | None] = contextvars.ContextVar("current_budget", default=None)


@contextmanager
def scope(project_id: str | None = None, agent: str | None = None, budget: Budget | None = None):
    """Enter an agent's scope. A new agent name makes the enclosing agent its parent (for the agent graph)."""
    tokens = []
    if project_id is not None:
        tokens.append((current_project, current_project.set(project_id)))
    if agent is not None and agent != current_agent.get():
        tokens.append((current_parent, current_parent.set(current_agent.get())))
        tokens.append((current_agent, current_agent.set(agent)))
    if budget is not None:
        tokens.append((current_budget, current_budget.set(budget)))
    try:
        yield
    finally:
        for var, tok in reversed(tokens):
            var.reset(tok)


def log(kind: str, title: str, detail: str | None = None, **extra) -> None:
    b = current_budget.get()
    if b is not None:
        if kind == "llm":
            b.charge(usd=extra.get("cost_usd") or 0.0, llm=1)
        elif kind == "tool":
            b.charge(tools=1)
    db.add_trace(project_id=current_project.get(), agent=current_agent.get(), parent=current_parent.get(), kind=kind,
                 title=scrub_secrets(title)[:500], detail=(scrub_secrets(detail)[:6000] if detail else None), **extra)


def info(title: str, detail: str | None = None) -> None:
    log("info", title, detail)


def tool(title: str, detail: str | None = None, provider: str | None = None, latency_ms: int | None = None) -> None:
    log("tool", title, detail, provider=provider, latency_ms=latency_ms)


def error(title: str, detail: str | None = None) -> None:
    log("error", title, detail)


def source(title: str, detail: str | None = None, provider: str | None = None, latency_ms: int | None = None) -> None:
    """An external API call (Tavily, arXiv, OpenAlex, Hugging Face...). Not charged as an agent tool call."""
    log("source", title, detail, provider=provider, latency_ms=latency_ms)
