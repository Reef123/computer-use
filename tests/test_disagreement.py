"""Disagreement functions — deterministic unit tests (no network).

Runs with plain `python tests/test_disagreement.py`; also pytest-collectable.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cua.disagreement import (
    action_point,
    action_type,
    disagreement,
    target_dispersion,
    type_disagreement,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _click(x: int, y: int) -> dict:
    return {"action": "left_click", "coordinate": [x, y]}


def _type(text: str) -> dict:
    return {"action": "type", "text": text}


def _key(text: str) -> dict:
    return {"action": "key", "text": text}


def _screenshot() -> dict:
    return {"action": "screenshot"}


# ---------------------------------------------------------------------------
# action_type
# ---------------------------------------------------------------------------

def test_action_type_extracts_field():
    assert action_type({"action": "left_click", "coordinate": [1, 2]}) == "left_click"
    assert action_type({"action": "type", "text": "hi"}) == "type"
    assert action_type({}) == ""


# ---------------------------------------------------------------------------
# action_point
# ---------------------------------------------------------------------------

def test_action_point_returns_tuple_for_valid_coord():
    assert action_point({"action": "left_click", "coordinate": [640, 360]}) == (640, 360)


def test_action_point_returns_none_for_type_action():
    assert action_point({"action": "type", "text": "hello"}) is None


def test_action_point_returns_none_for_empty():
    assert action_point({}) is None


def test_action_point_returns_none_for_bad_coord():
    assert action_point({"action": "left_click", "coordinate": ["x", "y"]}) is None
    assert action_point({"action": "left_click", "coordinate": [1]}) is None


# ---------------------------------------------------------------------------
# type_disagreement
# ---------------------------------------------------------------------------

def test_type_disagreement_identical_clicks_is_zero():
    actions = [_click(100, 200)] * 5
    assert type_disagreement(actions) == 0.0


def test_type_disagreement_empty_is_zero():
    assert type_disagreement([]) == 0.0


def test_type_disagreement_single_is_zero():
    assert type_disagreement([_click(1, 1)]) == 0.0


def test_type_disagreement_all_different():
    # 3 different action types -> 2/3 don't match the modal (each count 1)
    # modal count = 1, disagreements = 2, ratio = 2/3
    actions = [_click(1, 1), _type("hi"), _key("Return")]
    td = type_disagreement(actions)
    assert abs(td - 2 / 3) < 1e-9


def test_type_disagreement_majority_type():
    # 4 clicks, 1 type -> modal = click (4), disagreements = 1, ratio = 1/5
    actions = [_click(1, 1)] * 4 + [_type("x")]
    td = type_disagreement(actions)
    assert abs(td - 0.2) < 1e-9


def test_type_disagreement_half_half():
    actions = [_click(1, 1), _click(2, 2), _type("a"), _type("b")]
    td = type_disagreement(actions)
    assert abs(td - 0.5) == 0.0


# ---------------------------------------------------------------------------
# target_dispersion
# ---------------------------------------------------------------------------

def test_target_dispersion_identical_clicks_is_zero():
    actions = [_click(512, 384)] * 4
    assert target_dispersion(actions) == 0.0


def test_target_dispersion_empty_is_zero():
    assert target_dispersion([]) == 0.0


def test_target_dispersion_single_click_is_zero():
    assert target_dispersion([_click(100, 100)]) == 0.0


def test_target_dispersion_coordinate_less_actions_is_zero():
    # type and key have no coordinates -> no points -> 0.0, no crash
    actions = [_type("hello"), _key("Return"), _screenshot()]
    assert target_dispersion(actions) == 0.0


def test_target_dispersion_opposite_corners_near_one():
    # (0,0) to (1024,768) = full diagonal -> normalized = 1.0
    actions = [_click(0, 0), _click(1024, 768)]
    disp = target_dispersion(actions, display=(1024, 768))
    assert abs(disp - 1.0) < 1e-9


def test_target_dispersion_spread_clicks_high():
    # Spread across most of the screen should produce a high dispersion value
    actions = [
        _click(0, 0),
        _click(1000, 700),
        _click(500, 10),
    ]
    disp = target_dispersion(actions, display=(1024, 768))
    # max pair is (0,0) <-> (1000,700): dist = sqrt(1000^2+700^2) ~ 1220
    # diagonal = sqrt(1024^2+768^2) = 1280; ratio ~ 0.953
    assert disp > 0.9


def test_target_dispersion_small_spread_low():
    # All near the same point — max dist < 20px on a 1280-diagonal display
    actions = [_click(500, 400), _click(505, 402), _click(498, 399)]
    disp = target_dispersion(actions, display=(1024, 768))
    assert disp < 0.02


def test_target_dispersion_mixed_with_type_actions():
    # Only click actions contribute; type actions are ignored silently
    actions = [_click(0, 0), _type("hello"), _click(1024, 768)]
    disp = target_dispersion(actions, display=(1024, 768))
    assert abs(disp - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# disagreement (combined)
# ---------------------------------------------------------------------------

def test_disagreement_identical_clicks_near_zero():
    actions = [_click(640, 360)] * 5
    score = disagreement(actions)
    assert score == 0.0


def test_disagreement_empty_is_zero():
    assert disagreement([]) == 0.0


def test_disagreement_single_is_zero():
    assert disagreement([_click(1, 1)]) == 0.0


def test_disagreement_type_confusion_dominates():
    # All different types, same location doesn't matter — type_disagreement = 2/3
    actions = [_click(500, 500), _type("hi"), _key("Return")]
    score = disagreement(actions)
    assert abs(score - 2 / 3) < 1e-9


def test_disagreement_spread_coordinates_dominates():
    # Same action type (all clicks) but spread across the screen
    diagonal = math.sqrt(1024 ** 2 + 768 ** 2)
    expected_disp = math.sqrt(1024 ** 2 + 768 ** 2) / diagonal  # = 1.0
    actions = [_click(0, 0), _click(1024, 768)]
    score = disagreement(actions, display=(1024, 768))
    # type_disagreement = 0 (both left_click), target_dispersion = 1.0
    assert abs(score - 1.0) < 1e-9


def test_disagreement_coordinate_less_actions_no_crash():
    actions = [_type("hello"), _type("world"), _key("Return")]
    # type_disagreement: type=2, key=1 -> 1/3; target_dispersion: 0 (no coords)
    score = disagreement(actions)
    assert abs(score - 1 / 3) < 1e-9


def test_disagreement_in_range():
    for actions in [
        [],
        [_click(1, 1)],
        [_click(0, 0), _click(512, 384), _type("x")],
        [_screenshot()] * 3,
    ]:
        s = disagreement(actions)
        assert 0.0 <= s <= 1.0, f"out of range for {actions}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
