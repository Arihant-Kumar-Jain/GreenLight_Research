"""Run budgets: hard ceilings on USD, LLM calls, tool calls and wall-clock time for one research run or chat turn.

Every traced LLM/tool call charges the budget in the current context (trace.current_budget). Agents check
`exhausted()` between steps and wrap up with what they have instead of overrunning. Sub-agents get child budgets
that also charge their parent, so a swarm can never spend more than the run allows.
"""

import time
from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    usd: float = 1.0
    llm_calls: int = 400
    tool_calls: int = 400
    seconds: float = 1800
    parent: "Budget | None" = None
    spent_usd: float = 0.0
    used_llm: int = 0
    used_tools: int = 0
    started: float = field(default_factory=time.time)

    def charge(self, *, usd: float = 0.0, llm: int = 0, tools: int = 0) -> None:
        self.spent_usd += usd
        self.used_llm += llm
        self.used_tools += tools
        if self.parent:
            self.parent.charge(usd=usd, llm=llm, tools=tools)

    def reason(self) -> str | None:
        """Why the budget is exhausted, or None while there is room (parents included)."""
        if self.spent_usd >= self.usd:
            return f"cost ceiling ${self.usd:.2f} reached"
        if self.used_llm >= self.llm_calls:
            return f"{self.llm_calls} LLM calls used"
        if self.used_tools >= self.tool_calls:
            return f"{self.tool_calls} tool calls used"
        if time.time() - self.started >= self.seconds:
            return f"time limit {int(self.seconds)}s reached"
        return self.parent.reason() if self.parent else None

    def exhausted(self) -> bool:
        return self.reason() is not None

    def child(self, *, usd: float | None = None, llm_calls: int | None = None, tool_calls: int | None = None,
              seconds: float | None = None) -> "Budget":
        return Budget(usd=usd if usd is not None else self.usd - self.spent_usd,
                      llm_calls=llm_calls or self.llm_calls, tool_calls=tool_calls or self.tool_calls,
                      seconds=seconds or self.seconds, parent=self)

    def snapshot(self) -> dict:
        return {"usd": round(self.spent_usd, 5), "usd_cap": self.usd, "llm_calls": self.used_llm,
                "tool_calls": self.used_tools, "elapsed_s": round(time.time() - self.started, 1)}
