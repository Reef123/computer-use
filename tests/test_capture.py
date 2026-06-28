"""Capture round-trip: a live run (fake transport) -> JSON -> offline replay
reproduces the same policy decisions. Proves the live->recorded->replay conveyor
deterministically, with no network and no machine.

Runs with plain `python tests/test_capture.py`; also pytest-collectable.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cua.capture import load_capture, replay_from_capture, save_run
from cua.executor import StubExecutor
from cua.live import run_live_session
from cua.runner import run_session
from cua.types import ActionType


class FakeTransport:
    def __init__(self, scripted):
        self.scripted = list(scripted)

    def __call__(self, payload, api_key):
        return self.scripted.pop(0) if self.scripted else {"type": "message", "stop_reason": "end_turn", "content": []}


def _msg(stop, *blocks):
    return {"type": "message", "stop_reason": stop, "content": list(blocks)}


def _tool(tid, action):
    return {"type": "tool_use", "id": tid, "name": "computer", "input": action}


def test_live_run_round_trips_through_offline_replay():
    transport = FakeTransport([
        _msg("tool_use", _tool("t1", {"action": "screenshot"})),
        _msg("tool_use", _tool("t2", {"action": "left_click", "coordinate": [100, 200]})),
        _msg("tool_use", _tool("t3", {"action": "type", "text": "hi"})),
        _msg("end_turn", {"type": "text", "text": "done"}),
    ])
    live = run_live_session("x", StubExecutor(), api_key="x", transport=transport, max_steps=8)
    assert len(live.steps) == 2  # the click + the type are the gated commits

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "cap.json")
        save_run(live, path)
        records = load_capture(path)
        assert len(records) == 2
        assert records[0][1].type is ActionType.CLICK and records[1][1].type is ActionType.TYPE
        backend, proposer, estimate = replay_from_capture(records)
        replayed = run_session(backend, proposer, estimate=estimate)

    # offline replay reproduces the live policy decisions exactly
    assert [s.intended.type for s in replayed.steps] == [s.intended.type for s in live.steps]
    assert [s.measurement.reducer for s in replayed.steps] == [s.measurement.reducer for s in live.steps]
    return replayed


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
