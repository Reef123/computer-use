"""Read-me demo: run the hand-authored replay through the session runner and
print the trace. `python demo_replay.py`."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from cua.fixtures import replay_session
from cua.fixtures.settings_dialog import build_capture
from cua.runner import run_session

backend, proposer, estimate = replay_session(build_capture())
result = run_session(backend, proposer, estimate=estimate)

print(result.trace.to_markdown())
print("measurement counts:", {k.value: v for k, v in result.measurement_counts().items() if v})
print("escalated:", result.escalated(), "| perception cost:", result.perception_cost())
