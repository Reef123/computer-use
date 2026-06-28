"""Estimator [PROVISIONAL] — fills magnitude + trust for the policy.

This is the load-bearing unknown of the whole system (consolidated spec §5):
whether a cheap external signal predicts being-wrong well enough to trigger on
is unproven. DO NOT HARDEN. v0 returns low trust everywhere, which forces the
policy into ordinal mode (sort, pick biggest). v1 replaces this with a real
external signal (logprobs / sample disagreement) behind the same contract; the
policy does not change when it does.
"""
from __future__ import annotations

from .types import EMPTY, Belief, IntendedAction, Observation, UncertaintyKind

# Estimator output: {kind: (magnitude, trust)}.
Signals = dict[UncertaintyKind, "tuple[float, float]"]

_LOW_TRUST = 0.3  # above the escalate floor, below the quantitative threshold -> ordinal


def crude_estimator(
    observation: Observation,
    belief: Belief,
    intended_action: IntendedAction | None = None,
) -> Signals:
    """v0 estimator: low trust everywhere; crude magnitudes from coarse cues.

    The honest floor. These magnitudes are heuristic placeholders, trusted only
    ordinally. Read this as a stub, not a model.
    """
    signals: Signals = {UncertaintyKind.STATE: (0.4, _LOW_TRUST)}
    # LOCATION applies only to actions that target a screen POINT. Coordinate-less
    # actions (type / key) go to the focused control — there is no location to pin,
    # so raising LOCATION here would demand an unanswerable probe (no point to read)
    # and the action could never converge to ACT (S147: type/key non-convergence).
    targets_a_point = intended_action is not None and intended_action.target is not None
    if targets_a_point:
        # Location is harder to pin when structure can't help (canvas / no tree).
        if observation.structure is EMPTY or observation.structure is None:
            signals[UncertaintyKind.LOCATION] = (0.6, _LOW_TRUST)
        else:
            signals[UncertaintyKind.LOCATION] = (0.3, _LOW_TRUST)
    return signals


class ScriptedEstimator:
    """Replay / test estimator: returns the signals recorded with each step.

    Scaffolding, not a real estimator. It lets the policy decision logic run on
    deterministic input (the demo is code that is read, not run live). Keyed by
    the observation's image_ref so a recorded run maps cleanly to its signals.
    """

    def __init__(self, by_image_ref: dict[str, Signals]) -> None:
        self._by_ref = by_image_ref

    def __call__(
        self,
        observation: Observation,
        belief: Belief,
        intended_action: IntendedAction | None = None,
    ) -> Signals:
        return self._by_ref[observation.vision.image_ref]
