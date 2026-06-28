"""Real round-trip: drive the live Computer Use API loop with the stub executor.
Proves the loop against the REAL API with no machine. `python live_probe.py`.

Reads ANTHROPIC_API_KEY from .env (gitignored). Costs a few cents per run.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# load .env (KEY=VALUE lines) without printing anything
_envp = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_envp):
    for _line in open(_envp):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k, _v)

from cua.executor import StubExecutor
from cua.live import run_live_session

if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit("no ANTHROPIC_API_KEY (expected in .env)")

result = run_live_session(
    "Take a screenshot to see the screen, then click whatever you'd click to open settings.",
    StubExecutor(),
    model="claude-opus-4-8",
    max_steps=3,
)
print(result.trace.to_markdown())
print("policy-gated commits:", len(result.steps), "| escalated:", result.escalated())
