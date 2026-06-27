"""Contracts for the perception-policy core.

The data shapes from `01_build_handoff.md` §3, pinned as code. Types only, no
logic. The estimator fills the magnitude/trust fields; the policy reads them;
the harness routes the measurements.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Reducer(Enum):
    """A measurement: the action that lowers a given uncertainty.

    Look / probe / wait / act are one family with different cost and
    information. Acting is the highest-cost measurement because it changes the
    world. Escalate is a measurement value, not a side path.
    """

    LOOK = "look"
    PROBE = "probe"
    WAIT = "wait"
    ACT = "act"
    ESCALATE = "escalate"


class UncertaintyKind(Enum):
    STATE = "state"          # what screen am I on / did it change
    LOCATION = "location"    # where exactly is the target
    READINESS = "readiness"  # has it settled (async)
    OUTCOME = "outcome"      # what happens if I commit


# The cheapest reducer for each uncertainty kind (consolidated spec §4.2).
# There is no "support" kind: support is the `trust` field on every entry.
REDUCER_FOR_KIND: dict[UncertaintyKind, Reducer] = {
    UncertaintyKind.STATE: Reducer.LOOK,
    UncertaintyKind.LOCATION: Reducer.PROBE,
    UncertaintyKind.READINESS: Reducer.WAIT,
    UncertaintyKind.OUTCOME: Reducer.ACT,
}


@dataclass(frozen=True)
class Uncertainty:
    """The belief atom: a triple (handoff §3.1)."""

    kind: UncertaintyKind
    magnitude: float  # 0..1, P(wrong) about this aspect
    trust: float      # 0..1, confidence in `magnitude` (provenance / support)
    reducer: Reducer  # the measurement that would lower it


@dataclass(frozen=True)
class StateEstimate:
    """Thin background: just enough to specify actions. Not a world-model."""

    screen: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class UpdateEvent:
    """One line of the uncertainty-reduction ledger (handoff §3.2)."""

    kind: UncertaintyKind
    before: float | None  # None = newly introduced
    after: float
    move: str             # "debit" | "credit" | "introduced" | "unchanged"


@dataclass(frozen=True)
class Belief:
    """A model of what is *not* known (foreground) plus a thin state estimate."""

    uncertainties: tuple[Uncertainty, ...] = ()
    state: StateEstimate = StateEstimate()
    history: tuple[UpdateEvent, ...] = ()


@dataclass(frozen=True)
class Target:
    """Region / marker for a probe or act (handoff §3.3)."""

    region: tuple[int, int, int, int] | None = None  # pixel rect (x, y, w, h)
    marker_id: str | None = None                      # structural marker, if snapped


@dataclass(frozen=True)
class Measurement:
    """The policy's only output type (handoff §3.3).

    `escalate` is a reducer value, not a separate branch.
    """

    reducer: Reducer
    target: Target | None = None
    arg: object | None = None
    reason: str = ""


# --- Observation (perception backend -> policy), handoff §3.4 ---


class _Empty:
    """Sentinel: structure was requested but no tree exists (canvas)."""

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "EMPTY"


EMPTY = _Empty()


@dataclass(frozen=True)
class Vision:
    image_ref: str                 # path / id of the screenshot (pixels not loaded in v0)
    coord_space: tuple[int, int]   # scaled-coordinate frame (w, h)


@dataclass(frozen=True)
class Element:
    id: str
    role: str
    name: str
    bounds: tuple[int, int, int, int]
    enabled: bool = True
    offscreen: bool = False
    patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class Observation:
    vision: Vision
    structure: tuple[Element, ...] | _Empty | None = None
    # None  = structure not requested
    # EMPTY = requested but no tree (canvas) -> policy must degrade to pixels


# --- Stakes (separate conservative door, handoff §3.6) ---


class ActionType(Enum):
    CLICK = "click"
    TYPE = "type"
    KEY = "key"
    SCROLL = "scroll"
    DRAG = "drag"
    SUBMIT = "submit"
    CONFIRM = "confirm"
    DELETE = "delete"


class Stakes(Enum):
    LOW = "low"
    HIGH = "high"


@dataclass(frozen=True)
class IntendedAction:
    type: ActionType
    target: Target | None = None
    arg: object | None = None
