#!/usr/bin/env python3
"""Capture runner — drive a live computer-use session and write a replayable JSON capture.

Usage (cmd.exe on the VM):
    set PYTHONPATH=src
    python run_capture.py "open Notepad and type hello"
    python run_capture.py --task "open Notepad and type hello" --out captures/my-run.json
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from cua.capture import save_run
from cua.live import run_live_session
from cua.win_executor import WinExecutor


def _slug(text: str, maxlen: int = 40) -> str:
    """Turn a task string into a filesystem-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:maxlen].rstrip("-")


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a live CUA session and save a replayable JSON capture."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "task_pos", nargs="?", metavar="TASK", help="Task description (positional)"
    )
    group.add_argument(
        "--task", dest="task_flag", metavar="TASK", help="Task description (flag)"
    )
    parser.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Output JSON path (default: captures/<slug>-<UTC-timestamp>.json)",
    )
    args = parser.parse_args()

    task = args.task_flag or args.task_pos
    if not task:
        parser.error(
            'Provide a task: python run_capture.py "<task>" or --task "<task>"'
        )

    # 1. Verify API key before touching the network or the display
    api_key = os.environ.get("ANTHROPIC_API_KEY", "") or _key_from_dotenv()
    if not api_key:
        print(
            "ERROR: ANTHROPIC_API_KEY is not set in the environment.",
            file=sys.stderr,
        )
        print(
            "  cmd.exe:    set ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        print(
            "  PowerShell: $env:ANTHROPIC_API_KEY = 'sk-ant-...'",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2. Determine output path
    if args.out:
        out_path = args.out
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        slug = _slug(task)
        out_path = str(Path("captures") / f"{slug}-{stamp}.json")

    # Ensure the output directory exists before we start the session
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    # 3. Construct WinExecutor — Windows-only deps are lazy; fails cleanly elsewhere
    try:
        executor = WinExecutor()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(
            "Run this script on a Windows desktop with a visible display.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Task  : {task}")
    print(f"Output: {out_path}")
    print("Starting live session …", flush=True)

    # 4. Run the live session.
    #    estimate/policy_fn/stakes are not passed so they use the module defaults
    #    (crude_estimator, decide_policy, classify_stakes) — matching live_probe.py.
    result = run_live_session(
        task,
        executor,
        api_key=api_key,
        model="claude-opus-4-8",
        max_steps=24,
    )

    # 5. Save the capture IMMEDIATELY — the live session is the expensive part;
    #    never let a summary error throw away a recorded run.
    save_run(result, out_path)
    print(f"\nCapture saved -> {out_path}")

    # 6. Concise summary (best-effort; capture is already on disk)
    try:
        counts = result.measurement_counts()
        decision_str = "  ".join(
            f"{r.value}={n}" for r, n in counts.items() if n > 0
        ) or "none"
        belief = result.belief
        belief_summary = (
            f"{len(belief.uncertainties)} uncertainties  "
            f"{len(belief.history)} history-events"
        )
        print()
        print(f"Steps      : {len(result.steps)}")
        print(f"Terminated : {result.terminated}")
        print(f"Escalated  : {result.escalated()}")
        print(f"Decisions  : {decision_str}")
        print(f"Belief     : {belief_summary}")
    except Exception as exc:  # summary is cosmetic; capture already saved
        print(f"(summary unavailable: {exc})")


if __name__ == "__main__":
    main()
