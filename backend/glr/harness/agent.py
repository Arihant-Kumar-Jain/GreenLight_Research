"""The agent runtime: one hand-written tool loop that every agent in GreenLight Research runs on. No framework.

Per step: build the context → one Nemotron call with the tool schemas → run the requested tools *in parallel*
(asyncio.gather) → append results → compress if over budget. Guarantees the loop enforces in code:
  - budgets: USD / LLM calls / tool calls / wall clock (shared with parent agents), checked every step
  - loop detection: an identical (tool, args) call gets a synthetic "already done" result instead of re-running
  - guard hooks: `before_tool` can veto a call (e.g. a scout trying to read 40 PDFs)
  - terminal tool: the run ends only when the model calls its finish tool with valid arguments; a `review` hook can
    reject a finish with feedback (self-critique / reflection) a bounded number of times
  - forced finish: at the step cap or when the budget runs out, the model must finish with what it has
  - no tool error ever crashes the run; it is returned to the model as data
Every step is traced under the agent's name; sub-agents trace under theirs, with this agent as parent.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from .. import llm, trace
from ..budget import Budget
from .context import Context
from .tools import Tool, finish_tool, short

REPEAT_NOTICE = ("You already made this exact call and its result is above (or in working memory). Repeating it "
                 "returns nothing new: change the query, use another tool, or finish.")


@dataclass
class AgentResult:
    output: dict | None
    text: str
    steps: int
    stopped_because: str
    tool_calls: int
    context: dict = field(default_factory=dict)


class Agent:
    def __init__(self, name: str, system: str, tools: list[Tool], *, role: str = "reason",
                 output: type[BaseModel] | None = None, finish_description: str = "Call when done, with your result.",
                 max_steps: int = 12, budget: Budget | None = None, context_tokens: int = 24000,
                 keep_recent: int = 3, pinned: Callable[[], str] | None = None, temperature: float = 0.2,
                 before_tool: Callable[[str, dict], str | None] | None = None,
                 review: Callable[[dict], Awaitable[str | None]] | None = None, max_reviews: int = 1,
                 max_tokens: int = 6000):
        self.name = name
        self.role = role
        self.tools = {t.name: t for t in tools}
        self.finish = finish_tool(output, finish_description) if output else None
        if self.finish:
            self.tools[self.finish.name] = self.finish
        self.system = system
        self.max_steps = max_steps
        self.budget = budget
        self.context_tokens = context_tokens
        self.keep_recent = keep_recent
        self.pinned = pinned
        self.temperature = temperature
        self.before_tool = before_tool
        self.review = review
        self.max_reviews = max_reviews
        self.max_tokens = max_tokens

    # ---------------------------------------------------------------- one tool call

    async def _run_tool(self, call: dict, seen: set[str]) -> tuple[dict, Any]:
        name = call["name"]
        try:
            args = json.loads(call.get("arguments") or "{}")
        except json.JSONDecodeError as e:
            return call, {"error": "bad_arguments", "detail": f"arguments were not valid JSON: {e}"}
        if not isinstance(args, dict):
            args = {}
        t = self.tools.get(name)
        if t is None:
            return call, {"error": "unknown_tool", "detail": f"No tool {name!r}. Available: {', '.join(self.tools)}"}
        key = name + json.dumps(args, sort_keys=True, default=str)
        if key in seen:
            trace.log("guard", f"Loop detected: repeated {name}", short(args, 300))
            return call, {"error": "repeated_call", "detail": REPEAT_NOTICE}
        seen.add(key)
        if self.before_tool:
            veto = self.before_tool(name, args)
            if veto:
                trace.log("guard", f"Guard blocked {name}", veto)
                return call, {"error": "blocked_by_guard", "detail": veto}
        t0 = time.perf_counter()
        result = await t.call(args)
        ms = int((time.perf_counter() - t0) * 1000)
        trace.tool(f"{name}({short(args, 140)})",
                   (t.digest(result) if t.digest and not (isinstance(result, dict) and "error" in result)
                    else short(result, 1500)), latency_ms=ms)
        return call, result

    # ---------------------------------------------------------------- the loop

    async def run(self, task: str) -> AgentResult:
        with trace.scope(agent=self.name, budget=self.budget):
            return await self._loop(task)

    async def _loop(self, task: str) -> AgentResult:
        ctx = Context(self.system, task, budget_tokens=self.context_tokens, keep_recent=self.keep_recent,
                      pinned=self.pinned, digests={n: t.digest for n, t in self.tools.items() if t.digest})
        trace.log("spawn", f"{self.name} started", short(task, 1200))
        seen: set[str] = set()
        reviews = nudges = calls = 0
        forced: str | None = None
        last_text = ""
        step = 0
        for step in range(1, self.max_steps + 2):
            budget_reason = self.budget.reason() if self.budget else None
            if not forced and (step > self.max_steps or budget_reason):
                forced = budget_reason or f"step limit ({self.max_steps}) reached"
                trace.log("budget", f"{self.name}: wrapping up ({forced})")
                ctx.add_user(f"STOP: {forced}. Do not call any more research tools. "
                             + (f"Call {self.finish.name} now with your best result from the evidence so far; "
                                "say what is incomplete." if self.finish else "Answer now from what you have."))
            tools = [self.finish] if forced and self.finish else (None if forced else list(self.tools.values()))
            try:
                res = await llm.chat(self.role, ctx.messages(), title=f"{self.name} · step {step}",
                                     tools=[t.schema() for t in tools] if tools else None,
                                     temperature=self.temperature, max_tokens=self.max_tokens)
            except Exception as e:
                trace.error(f"{self.name}: model call failed", str(e))
                if forced or step > self.max_steps:
                    break
                ctx.add_user(f"(The previous model call failed: {short(str(e), 200)}. Continue.)")
                continue
            last_text = res.text or last_text

            if not res.tool_calls:
                if not self.finish:
                    ctx.add_assistant({"role": "assistant", "content": res.text or ""})
                    return self._done(None, res.text, step, forced or "answered", calls, ctx)
                ctx.add_assistant({"role": "assistant", "content": res.text or "(no content)"})
                nudges += 1
                if forced or nudges > 3:
                    break
                ctx.add_user(f"Use your tools. When you are done, call {self.finish.name} with the result.")
                continue

            native = bool(res.raw_message and res.raw_message.get("tool_calls"))
            ctx.add_assistant(res.raw_message if native else {"role": "assistant", "content": res.text or ""})
            finish_call = next((c for c in res.tool_calls if self.finish and c["name"] == self.finish.name), None)
            others = [c for c in res.tool_calls if c is not finish_call]
            if forced:
                for c in others:
                    ctx.add_tool_result(c["id"], c["name"], {"error": "budget", "detail": "No more research tools."},
                                        native=native)
                others = []
            results = await asyncio.gather(*(self._run_tool(c, seen) for c in others))  # parallel tool calls
            calls += len(others)
            for c, r in results:
                ctx.add_tool_result(c["id"], c["name"], r, native=native)

            if finish_call:
                try:
                    out = self.finish.parse(finish_call.get("arguments")).model_dump()
                except Exception as e:
                    ctx.add_tool_result(finish_call["id"], finish_call["name"],
                                        {"error": "invalid_result", "detail": str(e)[:900]}, native=native)
                    continue
                if self.review and reviews < self.max_reviews and not forced:
                    feedback = await self.review(out)
                    if feedback:
                        reviews += 1
                        trace.log("guard", f"{self.name}: finish rejected by reviewer, revising", feedback)
                        ctx.add_tool_result(finish_call["id"], finish_call["name"],
                                            {"error": "revise", "detail": feedback}, native=native)
                        continue
                ctx.add_tool_result(finish_call["id"], finish_call["name"], {"ok": True}, native=native)
                return self._done(out, res.text, step, forced or "finished", calls, ctx)
            await ctx.compress()

        # The model never produced a valid finish: last resort, extract it as JSON from the transcript.
        if self.finish:
            try:
                out = await llm.chat_json(self.role, self.system + "\n\nProduce your final result now.",
                                          _transcript(ctx), self.finish.args, title=f"{self.name} · forced result")
                return self._done(out.model_dump(), "", step, forced or "forced", calls, ctx)
            except Exception as e:
                trace.error(f"{self.name}: no result", str(e))
        return self._done(None, last_text, step, forced or "no_result", calls, ctx)

    def _done(self, out: dict | None, text: str, steps: int, why: str, calls: int, ctx: Context) -> AgentResult:
        trace.log("done", f"{self.name} finished ({why}) after {steps} step(s), {calls} tool call(s)",
                  short(out if out is not None else text, 1500))
        return AgentResult(out, text or "", steps, why, calls, {**ctx.stats, "memory": ctx.memory[:2000]})


def _transcript(ctx: Context) -> str:
    lines = [f"Task: {ctx.task}"]
    if ctx.memory:
        lines.append(f"Memory: {ctx.memory}")
    for g in ctx.groups:
        for m in g:
            lines.append(f"{m['role']}: {str(m.get('content') or '')[:3000]}")
    return "\n".join(lines)[-60000:]


async def swarm(jobs: list[tuple[Agent, str]], *, limit: int = 4) -> list[AgentResult | BaseException]:
    """Run sub-agents concurrently (bounded); one failing sub-agent never sinks the others."""
    sem = asyncio.Semaphore(limit)

    async def one(agent: Agent, task: str):
        async with sem:
            return await agent.run(task)
    return await asyncio.gather(*(one(a, t) for a, t in jobs), return_exceptions=True)
