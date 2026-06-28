#!/usr/bin/env python3
"""Offline resampling harness — measure sample disagreement over a capture.

Usage:
    PYTHONPATH=src python3 eval_disagreement.py <capture.json> \\
        --task "<task text>" [--k 5]

For each gated step in the capture this script:
  1. Loads the step's screenshot PNG (image_ref, Windows paths normalized).
  2. Base64-encodes it.
  3. Calls the Computer Use API k times with [task text + image], no history.
  4. Extracts the first commit-style action from each response.
  5. Computes disagreement(sampled_actions) and prints per-step results.

⚠  CONTEXT-FREE RESAMPLING (v0 limitation): each API call sees only the
current screenshot + task text — no conversation history, no tool results,
no prior observations. This is a smell test of the signal (does the model
hedge on ambiguous screens?), not the in-context disagreement the live
policy would observe. AUROC against a wrong-commit oracle label is the real
validity gate (05_estimator_spec.md §Validation).

DO NOT RUN: this hits the Anthropic API and incurs token costs. It is built
and tested offline; run it only when a labeled capture exists for validation.
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from cua.capture import load_capture
from cua.disagreement import action_point, action_type, disagreement
from cua.live import BETA, TOOL_TYPE, _post

# Commit action types (mirrors live.py _COMMIT_TYPES keys)
_COMMIT_TYPES: frozenset[str] = frozenset({
    "left_click", "right_click", "middle_click", "double_click", "triple_click",
    "left_click_drag", "type", "scroll", "key",
})

MODEL = "claude-opus-4-8"

_TOOLS = [{
    "type": TOOL_TYPE,
    "name": "computer",
    "display_width_px": 1024,
    "display_height_px": 768,
    "display_number": 1,
}]


# ---------------------------------------------------------------------------
# Key loading (copied from run_capture.py)
# ---------------------------------------------------------------------------

def _key_from_dotenv() -> str:
    """Fallback: read ANTHROPIC_API_KEY from a .env file beside this script."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _normalize_image_ref(image_ref: str, repo_root: Path) -> Path:
    """Resolve a (possibly Windows-style) image_ref to an absolute path.

    Captures recorded on Windows store image_ref with backslashes
    (e.g. 'captures\\win-frame-...png'). Normalise before joining.
    """
    normalized = image_ref.replace("\\", "/")
    return repo_root / normalized


def _load_b64(path: Path) -> str:
    """Read a PNG and return its base64-encoded content."""
    raw = path.read_bytes()
    return base64.b64encode(raw).decode("ascii")


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------

def _sample_action(task: str, b64: str, api_key: str) -> dict | None:
    """Send one context-free call (task + screenshot) and return the first
    commit action dict, or None if the model proposes nothing actionable."""
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": task},
            {"type": "image", "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": b64,
            }},
        ],
    }]
    payload = {
        "model": MODEL,
        "max_tokens": 1024,
        "tools": _TOOLS,
        "messages": messages,
    }
    resp = _post(payload, api_key)
    if resp.get("type") == "error":
        print(f"    [API error] {resp.get('error')}", file=sys.stderr)
        return None
    for block in resp.get("content", []):
        if block.get("type") == "tool_use":
            action = block.get("input", {}) or {}
            if action.get("action") in _COMMIT_TYPES:
                return action
    return None


def _fmt_action(action: dict | None) -> str:
    """Compact one-line representation of an action dict."""
    if action is None:
        return "(none)"
    atype = action_type(action)
    pt = action_point(action)
    if pt:
        return f"{atype}@({pt[0]},{pt[1]})"
    text = action.get("text", "")
    return f"{atype}({text!r})" if text else atype


def _fmt_intended(intended) -> str:
    """Compact representation of an IntendedAction."""
    if intended is None:
        return "(none)"
    t = intended.type.value
    if intended.target and intended.target.region:
        x, y = intended.target.region[0], intended.target.region[1]
        return f"{t}@({x},{y})"
    if intended.arg:
        return f"{t}({intended.arg!r})"
    return t


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("EVAL-DISAGREEMENT  v0 context-free resampling harness")
    print("=" * 70)
    print()
    print("⚠  CONTEXT-FREE RESAMPLING (v0 limitation)")
    print("   Each API call receives only: task text + screenshot.")
    print("   No conversation history, no tool results, no prior steps.")
    print("   This is a smell test of the signal — not the in-context")
    print("   disagreement the live policy observes. AUROC against a")
    print("   wrong-commit oracle label is the real validity gate.")
    print()

    parser = argparse.ArgumentParser(
        description="Offline sample-disagreement eval over a capture file."
    )
    parser.add_argument("capture", help="Path to a capture JSON file.")
    parser.add_argument("--task", required=True, help="Task text (the prompt given to the model).")
    parser.add_argument("--k", type=int, default=5, help="Samples per step (default: 5).")
    args = parser.parse_args()

    # Resolve paths
    repo_root = Path(__file__).resolve().parent
    capture_path = Path(args.capture)
    if not capture_path.is_absolute():
        capture_path = repo_root / capture_path

    if not capture_path.exists():
        print(f"ERROR: capture not found: {capture_path}", file=sys.stderr)
        sys.exit(1)

    # API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "") or _key_from_dotenv()
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in environment or .env", file=sys.stderr)
        sys.exit(1)

    print(f"Capture : {capture_path}")
    print(f"Task    : {args.task}")
    print(f"k       : {args.k}")
    print(f"Model   : {MODEL}")
    print()

    # Load capture
    steps = load_capture(str(capture_path))
    print(f"Steps loaded: {len(steps)}")
    print()

    per_step_scores: list[tuple[int, str, float]] = []

    for idx, (obs, intended) in enumerate(steps):
        img_path = _normalize_image_ref(obs.vision.image_ref, repo_root)
        print(f"--- Step {idx} ---")
        print(f"  image_ref : {obs.vision.image_ref}")
        print(f"  recorded  : {_fmt_intended(intended)}")

        if not img_path.exists():
            print(f"  WARNING   : image not found at {img_path} — skipping step")
            per_step_scores.append((idx, _fmt_intended(intended), float("nan")))
            continue

        b64 = _load_b64(img_path)

        sampled: list[dict] = []
        for s in range(args.k):
            action = _sample_action(args.task, b64, api_key)
            sampled.append(action if action is not None else {})
            print(f"  sample {s+1}/{args.k} : {_fmt_action(action)}")

        # Only score samples that produced a commit action
        valid = [a for a in sampled if a]
        score = disagreement(valid) if valid else float("nan")
        print(f"  disagreement score : {score:.3f}  (from {len(valid)}/{args.k} valid samples)")
        print()
        per_step_scores.append((idx, _fmt_intended(intended), score))

    # Summary table
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Step':>4}  {'Recorded action':<28}  {'Disagreement':>12}")
    print("-" * 50)
    for idx, recorded, score in per_step_scores:
        score_str = f"{score:.3f}" if not (score != score) else "  n/a"  # NaN check
        print(f"{idx:>4}  {recorded:<28}  {score_str:>12}")
    print()
    print("NOTE: High disagreement = model uncertain = candidate for gating.")
    print("AUROC vs. oracle wrong-commit label is the validity gate (spec §05).")


if __name__ == "__main__":
    main()
