"""Executors [INTERFACE] — perform computer actions on the target.

The live loop is generic over this seam. `StubExecutor` (canned, no machine
needed) lets the real Computer Use API loop be verified end to end now; a real
executor (screenshot capture + UIA probe + actuation) lands on the Windows VM.
The loop never knows which it drives.

Atomicity contract: `screenshot()` and `screenshot_b64()` must refer to the SAME
frame — capture once, cache the bytes. A real executor that re-captures between
the two would hand the policy one frame and the model another.
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
        """Capture the screen and return it as an Observation. Caches the frame's
        bytes so screenshot_b64() returns the SAME frame."""
        ...

    def screenshot_b64(self) -> str:
        """The last captured frame as a base64 PNG (atomic with screenshot())."""
        ...

    def actuate(self, action: dict) -> str:
        """Perform a commit action (click/type/key); return a short result note."""
        ...

    def probe(self, action: dict):
        """Read the structure (UIA) near a target — the cheap measurement."""
        ...


class StubExecutor:
    """Canned executor: a blank screen, no structure, actions are no-ops. Stands
    in for the Windows VM so the live API loop can be verified with no machine.
    `actuated` records executed actions for tests."""

    def __init__(self, label: str = "stub") -> None:
        self._n = 0
        self._label = label
        self._last_b64 = _BLANK_PNG_B64
        self.actuated: list[str] = []

    def screenshot(self) -> Observation:
        self._n += 1
        self._last_b64 = _BLANK_PNG_B64  # in a real executor: the bytes of THIS frame
        return Observation(
            vision=Vision(f"{self._label}/frame-{self._n}.png", (1024, 768)),
            structure=EMPTY,
        )

    def screenshot_b64(self) -> str:
        return self._last_b64

    def actuate(self, action: dict) -> str:
        self.actuated.append(action.get("action"))
        return f"(stub) executed {action.get('action')}"

    def probe(self, action: dict):
        return EMPTY
