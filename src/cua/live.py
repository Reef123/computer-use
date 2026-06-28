"""Live computer-use backend [INTERFACE] — drives the real Computer Use API loop.

The model perceives a screenshot and proposes an action; OUR policy gates each
COMMIT (click/type/key) before it executes — inserting a cheaper measurement
(probe via structure) or escalating when out of support. `screenshot` and a
whitelist of non-commit actions execute directly; anything unknown is withheld
(fail closed). At most one state-changing action runs per model turn. The
`Executor` performs the action on the target (stub now; real screenshot + UIA +
actuation on the VM).

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

# Commit (state-changing) actions -> our intended-action type. These are gated.
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
# Non-commit actions safe to execute directly (perception / cursor). Anything
# NOT in _COMMIT_TYPES and NOT here is unknown -> withheld (fail closed).
_NONCOMMIT = {"screenshot", "wait", "mouse_move", "cursor_position", "hold_key",
              "left_mouse_down", "left_mouse_up"}

# Conservative high-stakes keys/chords (the stakes door errs high).
_HIGH_KEYS = {"return", "enter", "kp_enter", "delete"}
_HIGH_CHORDS = ("alt+f4", "ctrl+w", "cmd+w", "ctrl+shift+w")


def _is_high_key(text) -> bool:
    t = str(text).strip().lower()
    return t in _HIGH_KEYS or any(c in t for c in _HIGH_CHORDS)


def map_action(action: dict) -> IntendedAction:
    """Map a computer-use commit action to our intended action. Destructive keys
    (Enter/Delete/close chords) read as high stakes (the conservative door).
    Target-by-label semantics — a click on a button named 'Delete' — needs UIA
    and is the executor's job (see 04 brief / probe)."""
    kind = action.get("action", "")
    coord = action.get("coordinate")
    target = (
        Target(region=(coord[0], coord[1], 0, 0))
        if isinstance(coord, list) and len(coord) == 2
        else None
    )
    at = _COMMIT_TYPES.get(kind, ActionType.CLICK)
    if kind == "key" and _is_high_key(action.get("text", "")):
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
        body = e.read().decode("utf-8", "replace")[:2000]
        try:
            return {"type": "error", "error": json.loads(body).get("error", {"message": body})}
        except json.JSONDecodeError:
            return {"type": "error", "error": {"message": f"HTTP {e.code}: {body}"}}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"type": "error", "error": {"message": f"network error: {e}"}}
    except json.JSONDecodeError as e:
        return {"type": "error", "error": {"message": f"non-JSON response: {e}"}}


def _image_result(tool_use_id: str, b64: str) -> dict:
    return {
        "type": "tool_result", "tool_use_id": tool_use_id,
        "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}],
    }


def _text_result(tool_use_id: str, text: str) -> dict:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": text}


def _error_result(tool_use_id: str, text: str) -> dict:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": text, "is_error": True}


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
    """Drive the real computer-use loop. Each model-proposed commit is gated by
    our policy; at most one state-changing action runs per turn; unknown actions
    are withheld (fail closed). Terminates on model-finish, escalate, or budget."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    trace = trace or Trace()
    belief = Belief()
    steps: list[StepRecord] = []
    tools = [{
        "type": TOOL_TYPE, "name": "computer",
        "display_width_px": 1024, "display_height_px": 768, "display_number": 1,
    }]
    messages: list[dict] = [{"role": "user", "content": task}]
    terminated = "budget"

    for i in range(1, max_steps + 1):
        resp = transport({"model": model, "max_tokens": 1024, "tools": tools, "messages": messages}, api_key)
        if resp.get("type") == "error":
            raise RuntimeError(f"API error: {resp.get('error')}")
        messages.append({"role": "assistant", "content": resp.get("content", [])})
        tool_uses = [b for b in resp.get("content", []) if b.get("type") == "tool_use"]
        if resp.get("stop_reason") != "tool_use" or not tool_uses:
            terminated = "model-finished"
            break

        results = []
        acted = False       # at most one state-changing action per model turn
        escalated = False
        for tu in tool_uses:
            action = tu.get("input", {}) or {}
            kind = action.get("action", "")
            tid = tu.get("id")

            if kind == "screenshot":  # perception — execute directly
                obs = executor.screenshot()
                trace.record(i, saw=obs.vision.image_ref, decided="look", did="screenshot",
                             why="model requested perception")
                results.append(_image_result(tid, executor.screenshot_b64()))
                continue
            if kind in _NONCOMMIT:  # known non-commit (wait, mouse_move, …) — direct
                obs = executor.screenshot()
                trace.record(i, saw=obs.vision.image_ref, decided="(direct)", did=kind, why="")
                results.append(_text_result(tid, executor.actuate(action)))
                continue
            if kind not in _COMMIT_TYPES:  # unknown -> fail closed, never execute
                trace.record(i, saw="-", decided="withheld", did=kind, why="unknown action (fail-closed)")
                results.append(_error_result(tid, f"Unknown action '{kind}' withheld; not executed."))
                continue

            # a commit -> gate it, but at most one state-changing action per turn
            if acted or escalated:
                results.append(_text_result(tid, f"Skipped {kind}: one action per turn; re-observe before reissuing."))
                continue

            intended = map_action(action)
            obs = executor.screenshot()
            measurement, belief = policy_fn(obs, belief, intended, estimate=estimate, stakes=stakes)
            steps.append(StepRecord(len(steps) + 1, obs, intended, measurement))
            trace.record(
                i, saw=obs.vision.image_ref, decided=measurement.reducer.value, did=kind,
                why=measurement.reason if measurement.reducer in (Reducer.PROBE, Reducer.ESCALATE) else "",
            )
            if measurement.reducer is Reducer.ESCALATE:
                escalated = True
                results.append(_error_result(tid, f"Action '{kind}' withheld: out of support, escalated to a human; not executed."))
                continue
            if measurement.reducer is Reducer.ACT:
                results.append(_text_result(tid, executor.actuate(action)))
                acted = True
                continue
            # measure-first (probe / look / wait): honest — the commit was NOT executed
            detail = {"probe": "structure read", "look": "re-observed", "wait": "waited"}.get(
                measurement.reducer.value, "measured")
            executor.probe(action)
            results.append(_text_result(
                tid, f"Held {kind} for {measurement.reducer.value} ({detail}); NOT executed. Reissue if still intended."))

        messages.append({"role": "user", "content": results})
        if escalated:
            terminated = "escalate"
            break

    return SessionResult(steps=steps, belief=belief, trace=trace, terminated=terminated)
