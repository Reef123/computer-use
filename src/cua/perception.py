"""Perception interface [INTERFACE] — the spine (consolidated spec §3).

The agent asks for an observation; a backend satisfies it. Live and replay are
backends, not rewrites: the runner calls `observe()` each step and never knows
which it faces. v0 ships the replay backend; the live backend (Computer Use API)
drops in behind the same interface in Phase 2.
"""
from __future__ import annotations

from typing import Protocol

from .types import Observation


class PerceptionBackend(Protocol):
    def observe(self) -> Observation | None:
        """Return the next observation, or None when the source is exhausted."""
        ...


class ReplayBackend:
    """Replays recorded observations in order, one per `observe()` call.

    v0 source is a hand-authored fixture; a real captured run (screenshots +
    UIA/DOM snapshots) drops in unchanged. Returns None once exhausted.
    """

    def __init__(self, observations: list[Observation]) -> None:
        self._it = iter(observations)

    def observe(self) -> Observation | None:
        return next(self._it, None)
