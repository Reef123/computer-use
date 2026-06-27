"""Replay fixtures — hand-authored captures and the replay wiring used to
exercise the policy and the runner.

These are scaffolding, NOT recorded runs. A real capture (per `01_build_handoff`
§4: screenshot + UIA/DOM snapshot + ground-truth action + next screenshot)
replaces a fixture behind the same `CaptureStep` shape. Clearly fake by design;
never presented as a real run.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..estimator import ScriptedEstimator, Signals
from ..perception import ReplayBackend
from ..types import Belief, IntendedAction, Observation


@dataclass(frozen=True)
class CaptureStep:
    """One recorded (or hand-authored) step: the observation the backend
    replays, the signals the scripted estimator returns for it, and the action
    intended at this step (drives the stakes door)."""

    observation: Observation
    signals: Signals
    intended_action: IntendedAction | None = None
    ground_truth_action: IntendedAction | None = None  # for live A/B later


class ReplayProposer:
    """Returns the recorded intended action for each observation (keyed by frame
    ref). The replay stand-in for a live model proposing the next action."""

    def __init__(self, by_image_ref: dict[str, IntendedAction | None]) -> None:
        self._by = by_image_ref

    def propose(self, observation: Observation, belief: Belief) -> IntendedAction | None:
        return self._by.get(observation.vision.image_ref)


def replay_session(
    capture: list[CaptureStep],
) -> tuple[ReplayBackend, ReplayProposer, ScriptedEstimator]:
    """Wire a captured run into the (backend, proposer, estimator) the runner
    needs. A real capture swaps in for a fixture with no change to the runner."""
    backend = ReplayBackend([s.observation for s in capture])
    proposer = ReplayProposer({s.observation.vision.image_ref: s.intended_action for s in capture})
    estimator = ScriptedEstimator({s.observation.vision.image_ref: s.signals for s in capture})
    return backend, proposer, estimator
