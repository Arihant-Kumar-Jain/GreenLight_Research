"""Harness tests with a scripted model: parallel tools, loop detection, finish/review, budgets, compression."""

import json
from typing import Annotated

import pytest
from pydantic import BaseModel, Field

from glr import llm, trace
from glr.budget import Budget
from glr.harness import Agent, tool
from glr.llm import ChatResult


class Out(BaseModel):
    answer: str


def call(n, name, **args):
    return {"id": f"c{n}", "name": name, "arguments": json.dumps(args)}


def reply(calls=None, text="", cost=0.0):
    calls = calls or []
    raw = {"role": "assistant", "content": text}
    if calls:
        raw["tool_calls"] = [{"id": c["id"], "type": "function",
                              "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]
    return ChatResult(text=text, model="fake", tool_calls=calls, raw_message=raw, tokens_in=10, tokens_out=10,
                      cost_usd=cost)


def script(steps, seen=None):
    it = iter(steps)

    async def fake(role, messages, tools=None, title=""):
        if seen is not None:
            seen.append(messages)
        _check_pairing(messages)
        try:
            s = next(it)
        except StopIteration:
            return reply(text="done")
        return s(messages, tools) if callable(s) else s
    return fake


def _check_pairing(messages):
    """Every assistant tool_call must be answered by a tool message before the next assistant turn (API rule)."""
    pending = []
    for m in messages:
        if m["role"] == "assistant":
            assert not pending, f"unanswered tool calls {pending}"
            pending = [c["id"] for c in m.get("tool_calls") or []]
        elif m["role"] == "tool":
            assert m["tool_call_id"] in pending, "orphan tool result"
            pending.remove(m["tool_call_id"])
    assert not pending or messages[-1]["role"] == "assistant"


@tool("echo")
async def echo(x: Annotated[str, Field(description="text")]) -> dict:
    return {"echo": x}


@pytest.fixture(autouse=True)
def reset():
    yield
    llm.FAKE = None


async def test_parallel_tools_then_finish():
    llm.FAKE = script([reply([call(1, "echo", x="a"), call(2, "echo", x="b")]),
                       reply([call(3, "finish", answer="ok")])])
    with trace.scope(project_id="t1"):
        r = await Agent("A", "sys", [echo], output=Out).run("task")
    assert r.output == {"answer": "ok"} and r.tool_calls == 2 and r.stopped_because == "finished"


async def test_loop_detection_and_bad_args():
    seen = []
    llm.FAKE = script([reply([call(1, "echo", x="a")]), reply([call(2, "echo", x="a"), call(3, "echo")]),
                       reply([call(4, "finish", answer="ok")])], seen)
    with trace.scope(project_id="t2"):
        r = await Agent("A", "sys", [echo], output=Out).run("task")
    tool_msgs = [m for m in seen[-1] if m["role"] == "tool"]
    assert "repeated_call" in tool_msgs[1]["content"] and "bad_arguments" in tool_msgs[2]["content"]
    assert r.output == {"answer": "ok"}


async def test_review_rejects_once():
    reviews = []

    async def review(out):
        reviews.append(out)
        return "search more" if len(reviews) == 1 else None
    llm.FAKE = script([reply([call(1, "finish", answer="v1")]), reply([call(2, "finish", answer="v2")])])
    with trace.scope(project_id="t3"):
        r = await Agent("A", "sys", [echo], output=Out, review=review).run("task")
    assert r.output == {"answer": "v2"} and len(reviews) == 1  # max_reviews=1: the revision is accepted


async def test_budget_forces_finish():
    calls = iter(range(100))
    tools_offered = []

    def step(messages, tools):
        tools_offered.append([t["function"]["name"] for t in tools or []])
        if tools and len(tools) == 1:
            return reply([call(99, "finish", answer="partial")])
        return reply([call(next(calls), "echo", x=str(next(calls)))], cost=0.4)
    llm.FAKE = script([step] * 10)
    b = Budget(usd=1.0)
    with trace.scope(project_id="t4"):
        r = await Agent("A", "sys", [echo], output=Out, budget=b).run("task")
    assert r.output == {"answer": "partial"} and "cost ceiling" in r.stopped_because
    assert tools_offered[-1] == ["finish"]


async def test_compression_keeps_pairing_and_memory():
    big = "x" * 4000

    @tool("big")
    async def bigtool(k: int) -> dict:
        return {"data": big, "k": k}
    folds = []
    steps = iter(range(100))

    async def fake(role, messages, tools=None, title=""):
        _check_pairing(messages)
        if "compression" in title:
            folds.append(title)
            return reply(text="- searched k=0..n, nothing relevant")
        n = next(steps)
        if n >= 13:
            return reply([call(100, "finish", answer="ok")])
        return reply([call(n, "bigtool", k=n)])
    llm.FAKE = fake
    with trace.scope(project_id="t5"):
        r = await Agent("A", "sys", [bigtool], output=Out, context_tokens=3000, keep_recent=2,
                        max_steps=20).run("task")
    assert r.output == {"answer": "ok"}
    assert r.context["compressions"] > 0 and r.context["elided"] > 0
    assert folds and r.context["folded_groups"] > 0 and r.context["memory"], "tier-2 fold should have run"


async def test_child_budget_charges_parent():
    parent = Budget(usd=1.0)
    child = parent.child(usd=0.5)
    child.charge(usd=0.6, llm=1)
    assert child.exhausted() and parent.spent_usd == pytest.approx(0.6) and not parent.exhausted()
