"""Capture round-trip: a live run (fake transport) -> JSON -> offline replay
reproduces the same policy decisions. Proves the live->recorded->replay conveyor
deterministically, with no network and no machine.

Runs with plain `python tests/test_capture.py`; also pytest-collectable.
"""
from __future__ import annotations

import json
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


def test_save_run_v2_round_trip():
    """v2: per-step decided/reason and top-level trace survive JSON round-trip.

    Saves a live session result, reads the raw JSON to assert the new fields are
    present and correct, then verifies load_capture + replay still work unchanged
    (the new fields must not affect replay behaviour).
    """
    transport = FakeTransport([
        _msg("tool_use", _tool("t1", {"action": "screenshot"})),
        _msg("tool_use", _tool("t2", {"action": "left_click", "coordinate": [100, 200]})),
        _msg("end_turn", {"type": "text", "text": "done"}),
    ])
    live = run_live_session("x", StubExecutor(), api_key="x", transport=transport, max_steps=8)
    assert len(live.steps) >= 1, "expected at least one gated step"

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "cap.json")
        save_run(live, path)

        with open(path) as f:
            data = json.load(f)

        # version bumped to 2
        assert data["version"] == 2, f"expected version 2, got {data['version']}"

        # per-step decided + reason match the live measurement
        assert len(data["steps"]) == len(live.steps)
        for i, (raw, step) in enumerate(zip(data["steps"], live.steps)):
            assert raw["decided"] == step.measurement.reducer.value, (
                f"step {i}: decided mismatch: {raw['decided']!r} != {step.measurement.reducer.value!r}"
            )
            assert raw["reason"] == step.measurement.reason, (
                f"step {i}: reason mismatch: {raw['reason']!r} != {step.measurement.reason!r}"
            )
            # original fields still present
            assert "observation" in raw
            assert "intended" in raw

        # top-level trace: one row per trace entry (includes screenshot rows)
        assert "trace" in data, "top-level 'trace' key missing"
        assert isinstance(data["trace"], list)
        assert len(data["trace"]) == len(live.trace.rows), (
            f"trace length mismatch: {len(data['trace'])} != {len(live.trace.rows)}"
        )
        for raw_row, tr_row in zip(data["trace"], live.trace.rows):
            assert raw_row["saw"] == tr_row.saw
            assert raw_row["decided"] == tr_row.decided
            assert raw_row["did"] == tr_row.did
            assert raw_row["why"] == tr_row.why

        # backward compat: load_capture returns obs+intended pairs, replay unchanged
        records = load_capture(path)
        assert len(records) == len(live.steps)
        for (obs, ia), step in zip(records, live.steps):
            assert obs.vision.image_ref == step.observation.vision.image_ref
        backend, proposer, estimate = replay_from_capture(records)
        replayed = run_session(backend, proposer, estimate=estimate)
        assert [s.intended.type for s in replayed.steps] == [s.intended.type for s in live.steps]
        assert [s.measurement.reducer for s in replayed.steps] == [s.measurement.reducer for s in live.steps]


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
