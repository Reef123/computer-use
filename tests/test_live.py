"""Live computer-use loop, exercised with a FAKE transport (no network). Proves
the loop maps the model's actions, gates commits through our policy, escalates
out-of-support, and feeds tool results back — all deterministically. The real
round-trip against the API lives in `live_probe.py`.

Runs with plain `python tests/test_live.py`; also pytest-collectable.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cua.executor import StubExecutor
from cua.live import map_action, run_live_session
from cua.policy import classify_stakes
from cua.types import ActionType, Reducer, Stakes, UncertaintyKind


class FakeTransport:
    """Returns scripted API responses in order; records what it was sent."""

    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.sent = []

    def __call__(self, payload, api_key):
        self.sent.append(payload)
        if self.scripted:
            return self.scripted.pop(0)
        return {"type": "message", "stop_reason": "end_turn", "content": []}


def _msg(stop, *blocks):
    return {"type": "message", "stop_reason": stop, "content": list(blocks)}


def _tool(tid, action):
    return {"type": "tool_use", "id": tid, "name": "computer", "input": action}


def test_loop_screenshot_then_gated_click_then_done():
    transport = FakeTransport([
        _msg("tool_use", {"type": "text", "text": "I'll look first."},
             _tool("t1", {"action": "screenshot"})),
        _msg("tool_use", _tool("t2", {"action": "left_click", "coordinate": [640, 360]})),
        _msg("end_turn", {"type": "text", "text": "Done."}),
    ])
    result = run_live_session("do the thing", StubExecutor(), api_key="x",
                              transport=transport, max_steps=6)
    # exactly one commit (the click) was gated through the policy
    assert len(result.steps) == 1
    assert result.steps[0].intended.type is ActionType.CLICK
    assert result.steps[0].measurement.reducer in set(Reducer)
    # three API turns: initial, after the screenshot result, after the click result
    assert len(transport.sent) == 3
    return result


def test_escalate_withholds_action_and_stops_the_loop():
    def all_low_trust(observation, belief, intended_action=None):
        return {UncertaintyKind.STATE: (0.6, 0.05), UncertaintyKind.LOCATION: (0.8, 0.05)}

    transport = FakeTransport([
        _msg("tool_use", _tool("t1", {"action": "left_click", "coordinate": [10, 10]})),
        _msg("tool_use", _tool("t2", {"action": "type", "text": "should never run"})),
    ])
    result = run_live_session("x", StubExecutor(), api_key="x",
                              estimate=all_low_trust, transport=transport, max_steps=6)
    assert result.escalated() is True
    assert len(transport.sent) == 1  # stopped on the first commit; never looped again


def test_non_commit_actions_are_not_gated():
    # wait / mouse_move are not commits -> they execute directly, no policy step.
    transport = FakeTransport([
        _msg("tool_use", _tool("t1", {"action": "wait", "duration": 1})),
        _msg("tool_use", _tool("t2", {"action": "mouse_move", "coordinate": [5, 5]})),
        _msg("end_turn", {"type": "text", "text": "ok"}),
    ])
    result = run_live_session("x", StubExecutor(), api_key="x", transport=transport, max_steps=6)
    assert len(result.steps) == 0
    assert len(transport.sent) == 3


def test_map_action_submit_key_is_high_stakes():
    assert classify_stakes(map_action({"action": "key", "text": "Return"})) is Stakes.HIGH
    assert classify_stakes(map_action({"action": "left_click", "coordinate": [1, 2]})) is Stakes.LOW
    assert map_action({"action": "type", "text": "hi"}).type is ActionType.TYPE


def test_unknown_action_is_withheld_fail_closed():
    # an action the loop doesn't recognise must NOT be executed
    stub = StubExecutor()
    transport = FakeTransport([
        _msg("tool_use", _tool("t1", {"action": "frobnicate", "x": 1})),
        _msg("end_turn", {"type": "text", "text": "ok"}),
    ])
    result = run_live_session("x", stub, api_key="x", transport=transport, max_steps=4)
    assert len(result.steps) == 0
    assert "frobnicate" not in stub.actuated


def test_one_state_changing_action_per_turn():
    # two commits in one model turn -> only the first runs; the second is skipped
    def confident(observation, belief, intended_action=None):
        return {UncertaintyKind.STATE: (0.05, 0.3), UncertaintyKind.LOCATION: (0.05, 0.3)}

    stub = StubExecutor()
    transport = FakeTransport([
        _msg("tool_use",
             _tool("a", {"action": "left_click", "coordinate": [10, 10]}),
             _tool("b", {"action": "left_click", "coordinate": [20, 20]})),
        _msg("end_turn", {"type": "text", "text": "done"}),
    ])
    result = run_live_session("x", stub, api_key="x", estimate=confident, transport=transport, max_steps=4)
    assert len(result.steps) == 1
    assert result.steps[0].measurement.reducer is Reducer.ACT
    assert stub.actuated.count("left_click") == 1


def test_probe_resolves_and_converges_to_act():
    # S147 regression: on the first real capture the model proposed the SAME
    # checkbox click 6x, the policy PROBEd every time, and the probe result was
    # discarded -> LOCATION stayed 0.6 -> it never crossed to ACT. With the
    # feedback fold, a probe that returns real structure drops LOCATION to 0.3
    # and converges to ACT in one turn — using the DEFAULT crude estimator.
    from cua.types import Element

    class ProbingExecutor(StubExecutor):
        def probe(self, action):
            return (Element(id="chk", role="CheckBox",
                            name="Auto-start application", bounds=(770, 200, 16, 16)),)

    stub = ProbingExecutor()
    transport = FakeTransport([
        _msg("tool_use", _tool("t1", {"action": "left_click", "coordinate": [774, 204]})),
        _msg("end_turn", {"type": "text", "text": "done"}),
    ])
    result = run_live_session("toggle the checkbox", stub, api_key="x",
                              transport=transport, max_steps=6)
    assert result.steps[-1].measurement.reducer is Reducer.ACT
    assert stub.actuated.count("left_click") == 1


def test_type_action_converges_without_a_location_probe():
    # type/key actions have no coordinate -> nothing to probe. The estimator must
    # not raise LOCATION for them, or they loop forever (the second S147 gap). With
    # no LOCATION, only STATE (0.4) remains, which is under the low-stakes bar -> ACT.
    stub = StubExecutor()
    transport = FakeTransport([
        _msg("tool_use", _tool("t1", {"action": "type", "text": "hello world"})),
        _msg("end_turn", {"type": "text", "text": "typed"}),
    ])
    result = run_live_session("type hello", stub, api_key="x",
                              transport=transport, max_steps=4)
    assert result.steps[-1].measurement.reducer is Reducer.ACT
    assert "type" in stub.actuated


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    demo = None
    for t in tests:
        r = t()
        if t.__name__ == "test_loop_screenshot_then_gated_click_then_done":
            demo = r
        print(f"PASS  {t.__name__}")
    if demo is not None:
        print("\n--- live-loop trace (fake transport) ---")
        print(demo.trace.to_markdown())
    print(f"\n{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
