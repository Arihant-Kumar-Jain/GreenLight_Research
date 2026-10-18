"""Context engine: owns an agent's message array and keeps it inside a token budget without breaking it.

The provider is stateless, so the whole array is re-sent every step. Three compression tiers, cheapest first:
  1. Elide   - old tool results are replaced by their tool's digest ("12 papers: P3, P7…"). Messages stay, so no
               tool_call is orphaned (the API rejects an assistant tool_call without its tool message).
  2. Fold    - the oldest complete turn groups (assistant + all its tool results) are summarised by Nemotron Nano
               into a running "working memory" and removed together, so pairing still holds.
  3. Pin     - the task, the working memory and the shared notebook live in the system prompt, rebuilt every
               step; findings written with `note` therefore survive any amount of compression.
Each compression is traced with before/after token counts (kind "compress").
"""

import copy
import json
from typing import Any, Callable

from .. import llm, trace

CHARS_PER_TOKEN = 3.6

FOLD_SYSTEM = """You compress an AI research agent's working history so it can keep working with a small context.
Write a dense memory of what was done and learned: searches run (so they are not repeated), papers found with their
ids (P#) and why they matter, key facts with their paper ids, dead ends, and open questions. Keep every paper id and
number exactly. Bullet points, no preamble, at most 350 words. Merge with the existing memory if one is given."""


def tokens(x: Any) -> int:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    return int(len(s) / CHARS_PER_TOKEN) + 4


class Context:
    def __init__(self, system: str, task: str, *, budget_tokens: int = 24000, keep_recent: int = 3,
                 pinned: Callable[[], str] | None = None, digests: dict[str, Callable[[Any], str]] | None = None):
        self.system = system
        self.task = task
        self.budget = budget_tokens
        self.keep_recent = keep_recent          # newest turn groups never compressed
        self.pinned = pinned                    # live text pinned into the system prompt (e.g. the notebook)
        self.digests = digests or {}
        self.memory = ""                        # tier-2 working memory
        self.groups: list[list[dict]] = []      # each group: one assistant turn + its tool results, or one user turn
        self.stats = {"elided": 0, "folded_groups": 0, "compressions": 0, "peak_tokens": 0}

    # ---------------------------------------------------------------- building

    def add_user(self, content: Any) -> None:
        self.groups.append([{"role": "user", "content": content}])

    def add_assistant(self, message: dict) -> None:
        self.groups.append([message])

    def add_tool_result(self, call_id: str, name: str, result: Any, *, native: bool = True) -> None:
        content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        if len(content) > 14000:
            content = content[:14000] + " …[truncated]"
        if native:
            msg = {"role": "tool", "tool_call_id": call_id, "content": content, "_name": name}
        else:  # inline tool protocol: results go back as a user turn
            msg = {"role": "user", "content": f"[{name} result]\n{content}", "_name": name}
        self.groups[-1].append(msg)

    def system_text(self) -> str:
        parts = [self.system]
        if self.memory:
            parts.append("## Working memory (compressed earlier steps)\n" + self.memory)
        if self.pinned:
            pin = self.pinned()
            if pin:
                parts.append(pin)
        return "\n\n".join(parts)

    def messages(self) -> list[dict]:
        out = [{"role": "system", "content": self.system_text()}, {"role": "user", "content": self.task}]
        for g in self.groups:
            for m in g:
                out.append({k: v for k, v in m.items() if not k.startswith("_")})
        return copy.deepcopy(out)

    def size(self) -> int:
        n = tokens(self.system_text()) + tokens(self.task)
        for g in self.groups:
            for m in g:
                n += tokens(m.get("content") or "") + tokens(m.get("tool_calls") or "")
        self.stats["peak_tokens"] = max(self.stats["peak_tokens"], n)
        return n

    # ---------------------------------------------------------------- compression

    def _elide(self, msg: dict) -> bool:
        if msg.get("_elided") or msg["role"] not in ("tool", "user") or "_name" not in msg:
            return False
        raw = msg["content"]
        try:
            data = json.loads(raw.split("\n", 1)[1] if msg["role"] == "user" else raw)
        except (ValueError, IndexError):
            data = raw
        fn = self.digests.get(msg["_name"])
        try:
            digest = fn(data) if fn else None
        except Exception:
            digest = None
        digest = digest or (raw[:180] + "…")
        msg["content"] = f"[earlier {msg['_name']} result, compressed: {digest}. Already done; don't repeat it.]"
        msg["_elided"] = True
        return True

    async def compress(self) -> None:
        before = self.size()
        if before <= self.budget:
            return
        old = self.groups[:-self.keep_recent] if len(self.groups) > self.keep_recent else []
        elided = sum(self._elide(m) for g in old for m in g)
        self.stats["elided"] += elided
        mid = self.size()
        folded = 0
        if mid > self.budget and old:
            # fold the oldest half of the compressible groups into working memory
            n = max(1, len(old) // 2 + 1)
            n = min(n, len(old))
            chunk = self.groups[:n]
            text = "\n".join(f"{m['role']}: {m.get('content') or ''} "
                             f"{json.dumps(m.get('tool_calls'), default=str)[:600] if m.get('tool_calls') else ''}"
                             for g in chunk for m in g)[:30000]
            user = (f"Existing memory:\n{self.memory or '(none)'}\n\nTask:\n{self.task[:1500]}\n\n"
                    f"History to fold in:\n{text}")
            try:
                res = await llm.chat("fast", [{"role": "system", "content": FOLD_SYSTEM},
                                              {"role": "user", "content": user}],
                                     title="Context compression · fold history", max_tokens=1200, temperature=0.1)
                summary = res.text.strip()
            except Exception as e:  # never lose the run over compression; fall back to a mechanical summary
                trace.error("Context fold failed, using mechanical summary", str(e))
                summary = text[:1500]
            self.memory = summary[:4000]
            self.groups = self.groups[n:]
            folded = n
            self.stats["folded_groups"] += n
        after = self.size()
        self.stats["compressions"] += 1
        trace.log("compress", f"Context compressed {before:,} → {after:,} tokens",
                  f"tier 1 elided {elided} old tool result(s); tier 2 folded {folded} turn group(s) into working "
                  f"memory; budget {self.budget:,} tokens", tokens_in=before, tokens_out=after)
