"""Capture / replay round-trip — turn a live run into a replayable fixture.

A live session (`run_live_session`) produces a `SessionResult` whose `StepRecord`s
hold the observation + intended action at each gated decision. `save_run` writes
those to JSON (screenshots live on disk as image_refs); `load_capture` +
`replay_from_capture` reconstruct them so the run replays OFFLINE through
`run_session` with the real estimator (signals are re-derived, not stored). This
closes the loop: live on the VM -> recorded capture -> deterministic offline
replay + A/B, no machine needed.
"""
from __future__ import annotations

import json

from .estimator import crude_estimator
from .fixtures import ReplayProposer
from .perception import ReplayBackend
from .runner import SessionResult
from .types import (
    EMPTY,
    ActionType,
    Element,
    IntendedAction,
    Observation,
    Target,
    Vision,
)


def _struct_to_json(s):
    if s is None:
        return None
    if s is EMPTY:
        return "EMPTY"
    return [
        {"id": e.id, "role": e.role, "name": e.name, "bounds": list(e.bounds),
         "enabled": e.enabled, "offscreen": e.offscreen, "patterns": list(e.patterns)}
        for e in s
    ]


def _struct_from_json(v):
    if v is None:
        return None
    if v == "EMPTY":
        return EMPTY
    return tuple(
        Element(e["id"], e["role"], e["name"], tuple(e["bounds"]),
                e.get("enabled", True), e.get("offscreen", False), tuple(e.get("patterns", [])))
        for e in v
    )


def _obs_to_json(o: Observation):
    return {"image_ref": o.vision.image_ref, "coord_space": list(o.vision.coord_space),
            "structure": _struct_to_json(o.structure)}


def _obs_from_json(d) -> Observation:
    return Observation(vision=Vision(d["image_ref"], tuple(d["coord_space"])),
                       structure=_struct_from_json(d["structure"]))


def _ia_to_json(a: IntendedAction | None):
    if a is None:
        return None
    t = a.target
    arg = a.arg if isinstance(a.arg, (str, int, float, bool, type(None))) else str(a.arg)
    return {
        "type": a.type.value,
        "target": None if t is None else {"region": list(t.region) if t.region else None, "marker_id": t.marker_id},
        "arg": arg,
    }


def _ia_from_json(d) -> IntendedAction | None:
    if d is None:
        return None
    tj = d.get("target")
    target = None if tj is None else Target(
        region=tuple(tj["region"]) if tj.get("region") else None, marker_id=tj.get("marker_id"))
    return IntendedAction(ActionType(d["type"]), target, d.get("arg"))


def save_run(result: SessionResult, path: str) -> None:
    """Write the gated steps of a live run to a replayable JSON capture.

    Version 2 adds per-step decision provenance (``decided``, ``reason``) and a
    top-level ``trace`` that covers *every* perception + commit step — including
    non-gated screenshots — so the full "why it looked / why it acted" log is
    captured alongside the committed actions.  Existing fields are untouched so
    v2 files remain loadable by ``load_capture`` and ``replay_from_capture``.
    """
    steps = [
        {
            "observation": _obs_to_json(s.observation),
            "intended": _ia_to_json(s.intended),
            "decided": s.measurement.reducer.value,
            "reason": s.measurement.reason,
        }
        for s in result.steps
    ]
    trace = [
        {"saw": r.saw, "decided": r.decided, "did": r.did, "why": r.why}
        for r in result.trace.rows
    ]
    with open(path, "w") as f:
        json.dump({"version": 2, "steps": steps, "trace": trace}, f, indent=2)


def load_capture(path: str) -> list[tuple[Observation, IntendedAction | None]]:
    """Load a capture (v1 or v2) and return obs+intended pairs for replay.

    The v2 fields (``decided``, ``reason``, top-level ``trace``) are present in
    the JSON but are intentionally not returned here — ``replay_from_capture``
    and ``ab.compare_capture`` re-derive signals via ``crude_estimator`` and
    must ignore the stored policy decisions so replay stays deterministic.
    Missing v2 keys in a v1 file cause no error.
    """
    with open(path) as f:
        data = json.load(f)
    return [(_obs_from_json(r["observation"]), _ia_from_json(r["intended"])) for r in data["steps"]]


def replay_from_capture(records):
    """Wire a loaded capture into (backend, proposer, estimator) for run_session,
    using the real crude estimator. The same observations + actions re-derive the
    same policy decisions deterministically."""
    backend = ReplayBackend([o for o, _ in records])
    proposer = ReplayProposer({o.vision.image_ref: ia for o, ia in records})
    return backend, proposer, crude_estimator
