"""A settings-dialog form-fill, scripted to drive the three v0 beats:
look (orient on arrival), one earned probe (a small adjacent field), and an
escalate (a custom-drawn region with no trustworthy estimate).

Scaffolding, not a captured run. A real capture replaces it behind the same
`CaptureStep` shape.
"""
from __future__ import annotations

from . import CaptureStep
from ..types import (
    ActionType,
    Element,
    EMPTY,
    IntendedAction,
    Observation,
    Target,
    UncertaintyKind,
    Vision,
)


def build_capture() -> list[CaptureStep]:
    # Step 1 — just arrived at the dialog: STATE uncertainty dominates -> LOOK.
    step1 = CaptureStep(
        observation=Observation(
            vision=Vision(image_ref="settings/01-arrived.png", coord_space=(1280, 800)),
            structure=(Element("win.dialog", "window", "Settings", (200, 150, 880, 520)),),
        ),
        signals={
            UncertaintyKind.STATE: (0.7, 0.3),     # high, ordinal
            UncertaintyKind.LOCATION: (0.2, 0.3),
        },
        intended_action=IntendedAction(ActionType.CLICK, Target(region=(640, 360, 60, 24))),
    )

    # Step 2 — settled, but the target is a small adjacent field: LOCATION
    # uncertainty dominates and structure is present -> one earned PROBE.
    step2 = CaptureStep(
        observation=Observation(
            vision=Vision(image_ref="settings/02-form.png", coord_space=(1280, 800)),
            structure=(
                Element("fld.timeout", "edit", "Timeout (s)", (640, 360, 60, 24), patterns=("setvalue",)),
                Element("fld.retries", "edit", "Retries", (640, 392, 60, 24), patterns=("setvalue",)),
            ),
        ),
        signals={
            UncertaintyKind.STATE: (0.2, 0.3),     # resolved by the look
            UncertaintyKind.LOCATION: (0.7, 0.3),  # small adjacent fields -> high
        },
        intended_action=IntendedAction(ActionType.TYPE, Target(region=(640, 360, 60, 24)), arg="30"),
    )

    # Step 3 — a custom-drawn region: no tree, and no trustworthy estimate.
    # Support collapses (all trust below the floor) -> ESCALATE, not a guess.
    step3 = CaptureStep(
        observation=Observation(
            vision=Vision(image_ref="settings/03-canvas.png", coord_space=(1280, 800)),
            structure=EMPTY,  # requested, no tree -> degrade to pixels
        ),
        signals={
            UncertaintyKind.STATE: (0.6, 0.05),    # below TRUST_FLOOR
            UncertaintyKind.LOCATION: (0.8, 0.05), # below TRUST_FLOOR
        },
        intended_action=IntendedAction(ActionType.CLICK, Target(region=(900, 600, 20, 20))),
    )

    return [step1, step2, step3]
