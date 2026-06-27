"""Replay fixtures — hand-authored captures used to exercise the policy.

These are scaffolding, NOT recorded runs. A real capture (per `01_build_handoff`
§4: screenshot + UIA/DOM snapshot + ground-truth action + next screenshot)
replaces a fixture behind the same `CaptureStep` shape. Clearly fake by design;
never presented as a real run.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..estimator import Signals
from ..types import IntendedAction, Observation


@dataclass(frozen=True)
class CaptureStep:
    """One recorded (or hand-authored) step: the observation the backend
    replays, the signals the scripted estimator returns for it, and the action
    intended at this step (drives the stakes door)."""

    observation: Observation
    signals: Signals
    intended_action: IntendedAction | None = None
    ground_truth_action: IntendedAction | None = None  # for live A/B later
