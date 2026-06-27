"""Phase 1b runner contract: the one session loop, exercised through the replay
spine. Proves the three beats run through the loop (not a hand-rolled iteration),
that escalate ends the session, that the loop is backend-agnostic, and that the
step budget holds.

Runs with plain `python tests/test_runner.py`; also pytest-collectable.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cua.estimator import crude_estimator
from cua.fixtures import replay_session
from cua.fixtures.settings_dialog import build_capture
from cua.runner import run_session
from cua.types import Observation, Reducer, Vision


def test_runner_replays_three_beats():
    backend, proposer, estimate = replay_session(build_capture())
    result = run_session(backend, proposer, estimate=estimate)
    reducers = [s.measurement.reducer for s in result.steps]
    assert reducers == [Reducer.LOOK, Reducer.PROBE, Reducer.ESCALATE], reducers
    assert len(result.trace.rows) == 3
    return result


def test_runner_stops_at_escalate_does_not_consume_more():
    # A 4th step after the escalate must NOT be consumed: escalate ends the run.
    capture = build_capture()
    backend, proposer, estimate = replay_session(capture + [capture[1]])
    result = run_session(backend, proposer, estimate=estimate)
    assert len(result.steps) == 3
    assert result.escalated()


def test_runner_is_backend_agnostic():
    # A non-replay backend (no fixture): the loop neither knows nor cares.
    class FakeLiveBackend:
        def __init__(self):
            self._left = [
                Observation(vision=Vision("live/0.png", (800, 600))),
                Observation(vision=Vision("live/1.png", (800, 600))),
            ]

        def observe(self):
            return self._left.pop(0) if self._left else None

    class NullProposer:
        def propose(self, observation, belief):
            return None

    result = run_session(FakeLiveBackend(), NullProposer(), estimate=crude_estimator)
    assert len(result.steps) == 2
    assert sum(result.measurement_counts().values()) == 2


def test_runner_respects_max_steps():
    obs = Observation(vision=Vision("loop/same.png", (800, 600)))

    class InfiniteBackend:
        def observe(self):
            return obs

    class NullProposer:
        def propose(self, observation, belief):
            return None

    result = run_session(InfiniteBackend(), NullProposer(), estimate=crude_estimator, max_steps=5)
    assert len(result.steps) == 5


def test_measurement_counts_sum_to_steps():
    backend, proposer, estimate = replay_session(build_capture())
    result = run_session(backend, proposer, estimate=estimate)
    assert sum(result.measurement_counts().values()) == len(result.steps)
    assert result.perception_cost() >= 1  # at least the one look


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    demo = None
    for t in tests:
        r = t()
        if t.__name__ == "test_runner_replays_three_beats":
            demo = r
        print(f"PASS  {t.__name__}")
    if demo is not None:
        print("\n--- session trace (saw / decided / did / why) ---")
        print(demo.trace.to_markdown())
        print("counts:", {k.value: v for k, v in demo.measurement_counts().items() if v})
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
