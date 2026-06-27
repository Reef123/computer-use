"""A longer form-fill, built for the A/B convincer. It includes a low-uncertainty
field where the blended policy can cheap-commit (and full-look cannot), so the
cost delta is real, plus a high-stakes submit where the blended policy must still
verify. Scaffolding, not a captured run.

`DEFAULT_ORACLE` marks which commits would be wrong (illustrative manual labels).
The A/B trap test flips a label to show the harness reports a loss honestly.
"""
from __future__ import annotations

from . import CaptureStep
from ..types import (
    ActionType,
    Element,
    IntendedAction,
    Observation,
    Target,
    UncertaintyKind,
    Vision,
)

ARRIVED = "form/01-arrived.png"
NAME = "form/02-name.png"
TIMEOUT = "form/03-timeout.png"
SUBMIT = "form/04-submit.png"

# Manual oracle: would committing here, without more perception, be wrong?
# The name field is safe to commit; the submit must be verified (it is high
# stakes, so the blended policy probes there anyway).
DEFAULT_ORACLE = {NAME: False, SUBMIT: True}


def build_capture() -> list[CaptureStep]:
    arrive = CaptureStep(
        observation=Observation(
            vision=Vision(ARRIVED, (1280, 800)),
            structure=(Element("win.dialog", "window", "New connection", (200, 150, 880, 520)),),
        ),
        signals={
            UncertaintyKind.STATE: (0.7, 0.3),     # just arrived -> orient
            UncertaintyKind.LOCATION: (0.2, 0.3),
        },
        intended_action=IntendedAction(ActionType.CLICK, Target(region=(640, 300, 200, 28))),
    )

    # A wide, clearly-labelled field with low uncertainty: the blended policy can
    # commit without paying for a probe; full-look still probes.
    name = CaptureStep(
        observation=Observation(
            vision=Vision(NAME, (1280, 800)),
            structure=(Element("fld.name", "edit", "Connection name", (640, 300, 200, 28), patterns=("setvalue",)),),
        ),
        signals={
            UncertaintyKind.STATE: (0.1, 0.3),
            UncertaintyKind.LOCATION: (0.15, 0.3),  # wide field, easy to hit
        },
        intended_action=IntendedAction(ActionType.TYPE, Target(region=(640, 300, 200, 28)), arg="Acme CRM"),
    )

    # A small adjacent numeric field: location uncertainty high -> earned probe.
    timeout = CaptureStep(
        observation=Observation(
            vision=Vision(TIMEOUT, (1280, 800)),
            structure=(
                Element("fld.timeout", "edit", "Timeout (s)", (640, 360, 56, 24), patterns=("setvalue",)),
                Element("fld.retries", "edit", "Retries", (704, 360, 56, 24), patterns=("setvalue",)),
            ),
        ),
        signals={
            UncertaintyKind.STATE: (0.2, 0.3),
            UncertaintyKind.LOCATION: (0.7, 0.3),
        },
        intended_action=IntendedAction(ActionType.TYPE, Target(region=(640, 360, 56, 24)), arg="30"),
    )

    # The destructive confirm: high stakes forces the blended policy to verify
    # rather than cheap-commit, even though uncertainty is only moderate.
    submit = CaptureStep(
        observation=Observation(
            vision=Vision(SUBMIT, (1280, 800)),
            structure=(Element("btn.create", "button", "Create", (980, 620, 90, 32), patterns=("invoke",)),),
        ),
        signals={
            UncertaintyKind.STATE: (0.2, 0.3),
            UncertaintyKind.LOCATION: (0.3, 0.3),
        },
        intended_action=IntendedAction(ActionType.SUBMIT, Target(region=(980, 620, 90, 32))),
    )

    return [arrive, name, timeout, submit]
