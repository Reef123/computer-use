"""A/B convincer: the kill-question instrument. Proves the harness reports a win
(blended cheaper than full-look, no extra confident-wrong) AND an honest loss
(when the estimator is overconfident, the cheap path eats a confident-wrong that
full-look avoids). The harness is not rigged.

Runs with plain `python tests/test_ab.py`; also pytest-collectable.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cua.ab import _forced_policy, compare
from cua.fixtures import replay_session
from cua.fixtures.form_fill import DEFAULT_ORACLE, NAME, build_capture
from cua.runner import run_session
from cua.types import Reducer


def test_blended_beats_full_look_on_cost_no_confident_wrong():
    report = compare(build_capture(), DEFAULT_ORACLE)
    assert report.blended_cost < report.forced_cost      # cheaper
    assert report.cost_saved >= 1
    assert report.blended_confident_wrong == 0
    assert report.forced_confident_wrong == 0
    assert report.passes_kill_question
    return report


def test_harness_reports_loss_when_estimator_overconfident():
    # Trap: the name field is actually wrong-to-commit, but the crude estimator
    # was confident. Blended cheap-commits there; full-look would have caught it.
    trap_oracle = {NAME: True}
    report = compare(build_capture(), trap_oracle)
    assert report.blended_confident_wrong == 1
    assert report.forced_confident_wrong == 0
    assert not report.passes_kill_question   # honest: cost win, safety loss


def test_full_look_arm_never_cheap_commits():
    backend, proposer, estimate = replay_session(build_capture())
    forced = run_session(backend, proposer, estimate=estimate, policy_fn=_forced_policy)
    assert all(s.measurement.reducer is not Reducer.ACT for s in forced.steps)


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    report = None
    for t in tests:
        r = t()
        if t.__name__ == "test_blended_beats_full_look_on_cost_no_confident_wrong":
            report = r
        print(f"PASS  {t.__name__}")
    if report is not None:
        print("\n--- kill question (illustrative fixture) ---")
        print(report.render())
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
