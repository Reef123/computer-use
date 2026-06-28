"""Executors [INTERFACE] — perform computer actions on the target.

The live loop is generic over this seam. `StubExecutor` (canned, no machine
needed) lets the real Computer Use API loop be verified end to end now; a real
executor (screenshot capture + UIA probe + actuation) lands on the Windows VM.
The loop never knows which it drives.
"""
from __future__ import annotations

from typing import Protocol

from .types import EMPTY, Observation, Vision

# A 1x1 PNG, base64 — a valid image the API accepts as a screenshot payload.
_BLANK_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


class Executor(Protocol):
    def screenshot(self) -> Observation:
        """The current screen as an Observation (vision + optional structure)."""
        ...

    def screenshot_b64(self) -> str:
        """The screen as a base64 PNG, to return to the model as a tool result."""
        ...

    def actuate(self, action: dict) -> str:
        """Perform a commit action (click/type/key); return a short result note."""
        ...

    def probe(self, action: dict):
        """Read the structure (UIA) near a target — the cheap measurement."""
        ...


class StubExecutor:
    """Canned executor: a blank screen, no structure, actions are no-ops. Stands
    in for the Windows VM so the live API loop can be verified with no machine."""

    def __init__(self, label: str = "stub") -> None:
        self._n = 0
        self._label = label

    def screenshot(self) -> Observation:
        self._n += 1
        return Observation(
            vision=Vision(f"{self._label}/frame-{self._n}.png", (1024, 768)),
            structure=EMPTY,
        )

    def screenshot_b64(self) -> str:
        return _BLANK_PNG_B64

    def actuate(self, action: dict) -> str:
        return f"(stub) executed {action.get('action')}"

    def probe(self, action: dict):
        return EMPTY
