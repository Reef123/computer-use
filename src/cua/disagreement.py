"""Sample disagreement functions [PURE] — no network, no I/O.

The central bet: when the model proposes N independent actions on the same
screenshot and they disagree (different type OR scattered coordinates), that
spread is a cheap proxy for "the model is uncertain here." Higher disagreement
→ higher P(wrong) → higher magnitude for the estimator.

All functions return a float in [0, 1]. Empty input, single sample, or
coordinate-less actions are handled gracefully (return 0.0, never crash).
"""
from __future__ import annotations

import math
from collections import Counter


def action_type(action: dict) -> str:
    """Return the raw action type string (the 'action' field)."""
    return action.get("action", "")


def action_point(action: dict) -> tuple[int, int] | None:
    """Return the coordinate pair for click-like actions, or None.

    Validates that 'coordinate' is a two-element sequence of numbers before
    trusting it; returns None for type/key/scroll actions that carry no point.
    """
    coord = action.get("coordinate")
    if isinstance(coord, (list, tuple)) and len(coord) == 2:
        try:
            return (int(coord[0]), int(coord[1]))
        except (TypeError, ValueError):
            return None
    return None


def type_disagreement(actions: list[dict]) -> float:
    """Fraction of samples whose action type differs from the modal type.

    0.0 if all samples agree (or fewer than 2 samples exist).
    Approaches 1.0 as diversity of types increases.

    Args:
        actions: Raw action dicts from the computer-use API (tool_use.input).

    Returns:
        float in [0, 1].
    """
    if len(actions) < 2:
        return 0.0
    types = [action_type(a) for a in actions]
    counts = Counter(types)
    modal_count = counts.most_common(1)[0][1]
    # Number of samples that are NOT the modal type
    disagreements = len(types) - modal_count
    return disagreements / len(types)


def target_dispersion(actions: list[dict], display: tuple[int, int] = (1024, 768)) -> float:
    """Max pairwise distance of proposed click coordinates, normalized by the
    display diagonal, among samples that carry a point.

    0.0 if fewer than 2 samples have a point coordinate.
    Capped at 1.0 (a point in one corner vs. the opposite corner = 1.0).

    Args:
        actions:  Raw action dicts.
        display:  (width, height) in pixels — the normalization frame.

    Returns:
        float in [0, 1].
    """
    points = [action_point(a) for a in actions]
    points = [p for p in points if p is not None]
    if len(points) < 2:
        return 0.0
    diagonal = math.sqrt(display[0] ** 2 + display[1] ** 2)
    if diagonal == 0.0:
        return 0.0
    max_dist = 0.0
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            dx = points[i][0] - points[j][0]
            dy = points[i][1] - points[j][1]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > max_dist:
                max_dist = dist
    return min(max_dist / diagonal, 1.0)


def disagreement(actions: list[dict], display: tuple[int, int] = (1024, 768)) -> float:
    """Combined disagreement score in [0, 1].

    Combination rule: max(type_disagreement, target_dispersion).

    Rationale: the two sub-signals measure independent failure modes — the
    model disagreeing on *what* to do vs. *where* to do it. Taking the max
    means either dimension is sufficient to flag uncertainty; a weighted
    average would dilute a strong coordinate-scatter signal when all actions
    agree on type, or dilute type-confusion when no click coordinates are
    present. max is conservative (errs toward flagging) which is appropriate
    for a safety-gated policy: it is cheaper to resample one extra time than
    to let a confident-wrong action through. It is also monotone in each
    sub-signal and stays in [0, 1] without a tuning weight.

    Known ceiling: this is a v0 CONTEXT-FREE signal. It measures spread on
    the same static screenshot; it does not capture in-context ambiguity from
    prior turns. AUROC against a wrong-commit oracle label (Phase 0.5 capture)
    is the validity gate — do not assume this works until that eval passes.

    Args:
        actions:  Raw action dicts (tool_use.input) from k independent calls.
        display:  (width, height) of the coordinate frame for normalization.

    Returns:
        float in [0, 1]. 0.0 for empty or single-sample input.
    """
    if len(actions) < 2:
        return 0.0
    td = type_disagreement(actions)
    disp = target_dispersion(actions, display)
    return max(td, disp)
