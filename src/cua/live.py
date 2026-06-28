"""Live computer-use backend [INTERFACE] — drives the real Computer Use API loop.

The model perceives a screenshot and proposes an action; OUR policy gates each
COMMIT (click/type/key) before it executes — inserting a cheaper measurement
(probe via structure) or escalating when out of support. A `screenshot` action
the model requests is perception and executes directly. The `Executor` performs
the action on the target (stub now; real screenshot + UIA + actuation on the VM).

Raw HTTP via urllib keeps the package dependency-free (the stdlib-only ethos).
`transport` is injectable, so the loop is unit-tested with no network. The API
key is read from the environment and never logged.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .estimator import crude_estimator
from .policy import classify_stakes
from .policy import policy as decide_policy
from .runner import SessionResult, StepRecord
from .trace import Trace
from .types import ActionType, Belief, IntendedAction, Reducer, Target

API_URL = "https://api.anthropic.com/v1/messages"
BETA = "computer-use-2025-11-24"
TOOL_TYPE = "computer_20251124"

# Computer-use action -> our intended-action type (conservative).
_COMMIT_TYPES = {
    "left_click": ActionType.CLICK,
    "right_click": ActionType.CLICK,
    "middle_click": ActionType.CLICK,
    "double_click": ActionType.CLICK,
    "triple_click": ActionType.CLICK,
    "left_click_drag": ActionType.DRAG,
    "type": ActionType.TYPE,
    "scroll": ActionType.SCROLL,
    "key": ActionType.KEY,
}
_SUBMIT_KEYS = {"return", "enter", "kp_enter"}


def map_action(action: dict) -> IntendedAction:
    """Map a computer-use action dict to our intended action. A bare Enter/Return
    keypress reads as a submit (the conservative stakes door)."""
    kind = action.get("action", "")
    coord = action.get("coordinate")
    target = (
        Target(region=(coord[0], coord[1], 0, 0))
        if isinstance(coord, list) and len(coord) == 2
        else None
    )
    at = _COMMIT_TYPES.get(kind, ActionType.CLICK)
    if kind == "key" and str(action.get("text", "")).strip().lower() in _SUBMIT_KEYS:
        at = ActionType.SUBMIT
    return IntendedAction(at, target, arg=action.get("text"))


def _post(payload: dict, api_key: str) -> dict:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "anthropic-beta": BETA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return {"type": "error", "error": json.loads(body).get("error", {"message": body})}
        except json.JSONDecodeError:
            return {"type": "error", "error": {"message": body}}


def _image_result(tool_use_id: str, b64: str) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}],
    }


def _text_result(tool_use_id: str, text: str) -> dict:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": text}


def run_live_session(
    task: str,
    executor,
    *,
    api_key: str | None = None,
    model: str = "claude-opus-4-8",
    estimate=crude_estimator,
    policy_fn=decide_policy,
    stakes=classify_stakes,
    trace: Trace | None = None,
    max_steps: int = 8,
    transport=_post,
) -> SessionResult:
    """Drive the real computer-use loop: each model-proposed commit is gated by
    our policy before the executor runs it. Screenshot actions execute directly.
    Terminates on the model finishing, an escalate, or the step budget."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    trace = trace or Trace()
    belief = Belief()
    steps: list[StepRecord] = []
    tools = [{
        "type": TOOL_TYPE, "name": "computer",
        "display_width_px": 1024, "display_height_px": 768, "display_number": 1,
    }]
    messages: list[dict] = [{"role": "user", "content": task}]

    for i in range(1, max_steps + 1):
        resp = transport({"model": model, "max_tokens": 1024, "tools": tools, "messages": messages}, api_key)
        if resp.get("type") == "error":
            raise RuntimeError(f"API error: {resp.get('error')}")
        messages.append({"role": "assistant", "content": resp.get("content", [])})
        tool_uses = [b for b in resp.get("content", []) if b.get("type") == "tool_use"]
        if resp.get("stop_reason") != "tool_use" or not tool_uses:
            break  # the model finished its turn

        results = []
        for tu in tool_uses:
            action = tu.get("input", {}) or {}
            kind = action.get("action", "")

            if kind == "screenshot":  # perception — execute directly, no gate
                obs = executor.screenshot()
                trace.record(i, saw=obs.vision.image_ref, decided="look", did="screenshot",
                             why="model requested perception")
                results.append(_image_result(tu["id"], executor.screenshot_b64()))
                continue

            if kind not in _COMMIT_TYPES:  # non-commit (wait, mouse_move, cursor_position) — direct, no gate
                obs = executor.screenshot()
                trace.record(i, saw=obs.vision.image_ref, decided="(direct)", did=kind, why="")
                results.append(_text_result(tu["id"], executor.actuate(action)))
                continue

            # a commit the model wants to make -> gate it through our policy
            intended = map_action(action)
            obs = executor.screenshot()
            measurement, belief = policy_fn(obs, belief, intended, estimate=estimate, stakes=stakes)
            steps.append(StepRecord(len(steps) + 1, obs, intended, measurement))
            trace.record(
                i, saw=obs.vision.image_ref, decided=measurement.reducer.value, did=kind,
                why=measurement.reason if measurement.reducer in (Reducer.PROBE, Reducer.ESCALATE) else "",
            )
            if measurement.reducer is Reducer.ESCALATE:
                results.append(_text_result(tu["id"], "Action withheld: out of support, escalated to a human."))
                return SessionResult(steps=steps, belief=belief, trace=trace)
            if measurement.reducer is Reducer.ACT:
                results.append(_text_result(tu["id"], executor.actuate(action)))
            else:  # probe / look / wait -> measure first, then let the model proceed
                executor.probe(action)
                results.append(_text_result(tu["id"], f"Verified before acting ({measurement.reducer.value}); proceed."))

        messages.append({"role": "user", "content": results})

    return SessionResult(steps=steps, belief=belief, trace=trace)
