"""A/B convincer [eval] — the kill-question instrument (consolidated spec §9).

Runs the same recorded task two ways: the blended policy vs the SAME policy with
the full-look baseline forced on (`forced_probe=True`, one flag, one code path).
Reports perception cost and confident-wrong for each arm, so the kill question
reads directly: does the blended policy beat full-look-every-step on cost WITHOUT
raising confident-wrong?

Honest scope: on a hand-authored fixture the confident-wrong oracle is a manual
label, illustrative only. Real numbers need the captured run (Phase 0.5) plus a
labeling pass. The harness reports a loss as readily as a win (see the trap test)
so the result is never rigged.
"""
from __future__ import annotations

from dataclasses import dataclass

from .fixtures import CaptureStep, replay_session
from .policy import policy
from .runner import SessionResult, run_session
from .types import Reducer

# The oracle: per frame ref, would committing here (without more perception) be
# wrong? Manual labels for a fixture; a labeling pass for a real capture.
Oracle = dict[str, bool]


def _forced_policy(*args, **kwargs):
    """The baseline arm: the same policy with the full-look flag on."""
    return policy(*args, forced_probe=True, **kwargs)


def _confident_wrong(result: SessionResult, oracle: Oracle) -> int:
    """A committed action (ACT) at a state the oracle calls wrong-to-commit."""
    return sum(
        1
        for s in result.steps
        if s.measurement.reducer is Reducer.ACT
        and oracle.get(s.observation.vision.image_ref, False)
    )


@dataclass(frozen=True)
class AbReport:
    blended_cost: int
    forced_cost: int
    blended_confident_wrong: int
    forced_confident_wrong: int

    @property
    def cost_saved(self) -> int:
        return self.forced_cost - self.blended_cost

    @property
    def passes_kill_question(self) -> bool:
        # Cheaper than full-look AND no worse on confident-wrong.
        return self.cost_saved > 0 and self.blended_confident_wrong <= self.forced_confident_wrong

    def render(self) -> str:
        verdict = "PASS" if self.passes_kill_question else "NOT YET"
        return (
            f"kill question: {verdict}\n"
            f"  perception cost   blended={self.blended_cost}  full-look={self.forced_cost}"
            f"  (saved {self.cost_saved})\n"
            f"  confident-wrong   blended={self.blended_confident_wrong}"
            f"  full-look={self.forced_confident_wrong}\n"
            f"  note: confident-wrong is an illustrative manual label until the captured run."
        )


def compare(capture: list[CaptureStep], oracle: Oracle, *, max_steps: int = 64) -> AbReport:
    """Run both arms over the same capture and report the kill-question numbers."""
    backend_b, proposer_b, estimate_b = replay_session(capture)
    blended = run_session(backend_b, proposer_b, estimate=estimate_b, max_steps=max_steps)

    backend_f, proposer_f, estimate_f = replay_session(capture)
    forced = run_session(
        backend_f, proposer_f, estimate=estimate_f, policy_fn=_forced_policy, max_steps=max_steps
    )

    return AbReport(
        blended_cost=blended.perception_cost(),
        forced_cost=forced.perception_cost(),
        blended_confident_wrong=_confident_wrong(blended, oracle),
        forced_confident_wrong=_confident_wrong(forced, oracle),
    )
