"""Today-line: drive the hand-authored capture through the policy and assert the
three beats (look, earned probe, escalate). Also covers the contract exits:
structure == EMPTY degrades, commit-when-clear, high-stakes holds.

Runs with plain `python tests/test_policy.py` (no pytest needed); also
pytest-collectable.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cua.estimator import ScriptedEstimator
from cua.fixtures.settings_dialog import build_capture
from cua.policy import classify_stakes, decide, policy
from cua.trace import Trace
from cua.types import (
    ActionType,
    Belief,
    EMPTY,
    IntendedAction,
    Observation,
    Reducer,
    Stakes,
    Uncertainty,
    UncertaintyKind,
    Vision,
)


def test_three_beats_look_probe_escalate():
    capture = build_capture()
    scripted = ScriptedEstimator({s.observation.vision.image_ref: s.signals for s in capture})
    trace = Trace()
    belief = Belief()
    reducers = []
    for i, step in enumerate(capture, 1):
        m, belief = policy(step.observation, belief, step.intended_action, estimate=scripted)
        reducers.append(m.reducer)
        trace.record(
            i,
            saw=f"{step.observation.vision.image_ref} "
            f"({'no-tree' if step.observation.structure is EMPTY else 'tree'})",
            decided=m.reducer.value,
            did="(replay)",
            why=m.reason if m.reducer in (Reducer.PROBE, Reducer.ESCALATE) else "",
        )
    assert reducers == [Reducer.LOOK, Reducer.PROBE, Reducer.ESCALATE], reducers
    return trace


def test_structure_empty_degrades_not_crashes():
    obs = Observation(vision=Vision("x.png", (100, 100)), structure=EMPTY)
    m, _ = policy(obs, Belief())  # crude estimator must handle EMPTY, no crash
    assert m.reducer in set(Reducer)


def test_escalate_when_all_trust_below_floor():
    b = Belief(
        uncertainties=(
            Uncertainty(UncertaintyKind.STATE, 0.6, 0.05, Reducer.LOOK),
            Uncertainty(UncertaintyKind.LOCATION, 0.8, 0.05, Reducer.PROBE),
        )
    )
    assert decide(b, Stakes.LOW).reducer is Reducer.ESCALATE


def test_commit_when_all_uncertainty_below_bar():
    b = Belief(
        uncertainties=(
            Uncertainty(UncertaintyKind.STATE, 0.1, 0.3, Reducer.LOOK),
            Uncertainty(UncertaintyKind.LOCATION, 0.2, 0.3, Reducer.PROBE),
        )
    )
    assert decide(b, Stakes.LOW).reducer is Reducer.ACT


def test_high_stakes_holds_where_low_stakes_commits():
    # magnitude 0.2: below the LOW bar (0.5) -> ACT, but above the HIGH bar
    # (0.05) -> the destructive path keeps measuring instead of committing.
    b = Belief(uncertainties=(Uncertainty(UncertaintyKind.STATE, 0.2, 0.3, Reducer.LOOK),))
    assert decide(b, Stakes.LOW).reducer is Reducer.ACT
    assert decide(b, Stakes.HIGH).reducer is Reducer.LOOK


def test_stakes_classification_errs_high():
    assert classify_stakes(IntendedAction(ActionType.SUBMIT)) is Stakes.HIGH
    assert classify_stakes(IntendedAction(ActionType.DELETE)) is Stakes.HIGH
    assert classify_stakes(IntendedAction(ActionType.CONFIRM)) is Stakes.HIGH
    assert classify_stakes(IntendedAction(ActionType.CLICK)) is Stakes.LOW


def test_low_trust_selects_ordinally_not_escalate():
    # Low-but-supported trust (0.3 > floor 0.1) still ranks ordinally and picks a
    # reducer. Escalate is reserved for support collapse, not mere low trust.
    b = Belief(
        uncertainties=(
            Uncertainty(UncertaintyKind.STATE, 0.7, 0.3, Reducer.LOOK),
            Uncertainty(UncertaintyKind.LOCATION, 0.4, 0.3, Reducer.PROBE),
        )
    )
    assert decide(b, Stakes.LOW).reducer is Reducer.LOOK


def test_readiness_routes_to_wait_not_act():
    # A high readiness blocker routes to WAIT; acting is withheld while a cheaper
    # measurement can still reduce a blocker (even with OUTCOME present).
    b = Belief(
        uncertainties=(
            Uncertainty(UncertaintyKind.READINESS, 0.8, 0.3, Reducer.WAIT),
            Uncertainty(UncertaintyKind.OUTCOME, 0.3, 0.3, Reducer.ACT),
        )
    )
    assert decide(b, Stakes.LOW).reducer is Reducer.WAIT


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    trace = None
    for t in tests:
        result = t()
        if t.__name__ == "test_three_beats_look_probe_escalate":
            trace = result
        print(f"PASS  {t.__name__}")
    if trace is not None:
        print("\n--- trace (saw / decided / did / why) ---")
        print(trace.to_markdown())
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
