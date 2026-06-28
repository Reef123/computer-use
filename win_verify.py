"""win_verify.py — Run this on the Windows VM to prove WinExecutor is ready.

Usage:
    PYTHONPATH=src python win_verify.py

Assumes a visible desktop; opens Notepad for UIA probing, then closes it.
Each of the 4 steps prints a clear PASS/FAIL line.

Steps:
  1. screenshot() + screenshot_b64() — valid PNG round-trip.
  2. probe() — open Notepad, focus + maximize it, derive probe point from its
     real BoundingRectangle, probe the edit area, and verify the result is a
     real Notepad control (not a desktop fallthrough).
  3. UIA pin-twice gate — close + reopen Notepad, focus + maximize, probe the
     same kind of point, assert name/role/bounds match across reopen and that
     neither probe is a desktop fallthrough.
  4. actuate() — benign mouse_move, no state change.
"""
from __future__ import annotations

import base64
import struct
import subprocess
import sys
import time

# Assumes PYTHONPATH=src
from cua.win_executor import WinExecutor


# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

# Desktop element names that indicate a probe fell through to the shell
DESKTOP_NAMES: frozenset[str] = frozenset({"Desktop", "Program Manager", "Desktop 1"})

# Logical full-screen bounds in 1024x768 space — matches desktop fallthrough
FULL_LOGICAL_BOUNDS: tuple[int, int, int, int] = (0, 0, 1024, 768)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _is_valid_png(data: bytes) -> bool:
    """Return True if data starts with the PNG magic bytes."""
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def _png_dimensions(data: bytes) -> tuple[int, int]:
    """Extract (width, height) from a PNG's IHDR chunk (bytes 16-24)."""
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def _open_notepad() -> subprocess.Popen:
    return subprocess.Popen(["notepad.exe"])


def _kill(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        pass


def _is_desktop_fallthrough(result: object) -> bool:
    """Return True if the probe result fell through to the Windows desktop.

    Checks the deepest (first) element: if its name is a known desktop shell
    name, or if its bounds span the entire logical screen, the probe did not
    land on a real application control.
    """
    if not result:
        return False
    e = result[0]
    name_is_desktop = (e.name or "") in DESKTOP_NAMES
    try:
        bounds_is_fullscreen = tuple(e.bounds) == FULL_LOGICAL_BOUNDS
    except Exception:
        bounds_is_fullscreen = False
    return name_is_desktop or bounds_is_fullscreen


def _focus_notepad(ex: WinExecutor):  # noqa: ANN201  (returns uiautomation.WindowControl or None)
    """Locate, focus, and maximize the Notepad top-level window.

    Returns the WindowControl on success, or None if Notepad cannot be found
    within 5 seconds (caller must FAIL the step).
    """
    import uiautomation  # Windows-only; imported lazily so macOS AST parse works
    nb = uiautomation.WindowControl(searchDepth=1, RegexName=".*Notepad.*")
    if not nb.Exists(maxSearchSeconds=5):
        print("  ERROR: Notepad window not found within 5 s")
        return None
    nb.SetActive()
    time.sleep(0.3)
    # Maximize so bounds are deterministic and the probe lands in the edit area
    try:
        nb.Maximize()
    except AttributeError:
        nb.ShowWindow(3)  # SW_MAXIMIZE = 3, fallback if Maximize() missing
    time.sleep(0.5)  # let maximize complete and settle
    return nb


def _probe_notepad_center(ex: WinExecutor, nb) -> dict:
    """Return a probe action whose coordinate is the center of Notepad's window.

    Reads nb.BoundingRectangle (real pixels), converts to logical 1024x768
    space using the executor's scale factors so the coordinate lands in the
    text/edit area.
    """
    rect = nb.BoundingRectangle
    real_cx = (rect.left + rect.right) // 2
    real_cy = (rect.top + rect.bottom) // 2
    sx, sy = ex.scale
    lx = round(real_cx / sx)
    ly = round(real_cy / sy)
    return {"action": "probe", "coordinate": [lx, ly]}


# ---------------------------------------------------------------------------
# step 1: screenshot + screenshot_b64
# ---------------------------------------------------------------------------

def step1_screenshot(ex: WinExecutor) -> bool:
    print("\n=== Step 1: screenshot() + screenshot_b64() ===")
    obs = ex.screenshot()
    path = obs.vision.image_ref
    space = obs.vision.coord_space

    b64 = ex.screenshot_b64()
    raw = base64.b64decode(b64)

    ok_path = bool(path)
    ok_png = _is_valid_png(raw)
    ok_dim = space == (1024, 768)
    w, h = _png_dimensions(raw) if ok_png else (0, 0)

    print(f"  saved path  : {path}")
    print(f"  coord_space : {space}")
    print(f"  b64 size    : {len(b64)} chars")
    print(f"  PNG valid   : {ok_png}")
    print(f"  PNG dims    : {w}x{h} (expected 1024x768)")

    ok = ok_path and ok_png and ok_dim and (w, h) == (1024, 768)
    print(f"Step 1: {'PASS' if ok else 'FAIL'}")
    return ok


# ---------------------------------------------------------------------------
# step 2: probe a known control in Notepad
# ---------------------------------------------------------------------------

def step2_probe(ex: WinExecutor, proc: subprocess.Popen) -> tuple[bool, object]:
    print("\n=== Step 2: probe() a labelled control in Notepad ===")
    from cua.types import EMPTY as _EMPTY

    # Focus and maximize Notepad so we hit a real control, not the desktop
    nb = _focus_notepad(ex)
    if nb is None:
        print("Step 2: FAIL (Notepad window not found — cannot probe)")
        return False, None

    action = _probe_notepad_center(ex, nb)
    print(f"  probing logical coordinate {action['coordinate']}"
          f" (derived from Notepad BoundingRectangle)")
    result = ex.probe(action)

    if result is _EMPTY or not result:
        print("  probe returned EMPTY (no UIA tree at this point)")
        print("Step 2: FAIL")
        return False, result

    print(f"  probe returned {len(result)} element(s):")
    for i, el in enumerate(result, 1):
        print(f"    [{i}] id={el.id!r} role={el.role!r} name={el.name!r} "
              f"bounds={el.bounds} enabled={el.enabled} "
              f"patterns={el.patterns}")

    # Guard: fail explicitly if the probe fell through to the desktop shell
    if _is_desktop_fallthrough(result):
        top = result[0]
        print(f"  FAIL: probe landed on desktop "
              f"(name={top.name!r} bounds={top.bounds}) — "
              f"Notepad is not in the foreground")
        print("Step 2: FAIL")
        return False, result

    top = result[0]
    print(f"  deepest element: name={top.name!r} role={top.role!r} bounds={top.bounds}")
    print("Step 2: PASS")
    return True, result


# ---------------------------------------------------------------------------
# step 3: UIA pin-twice gate
# ---------------------------------------------------------------------------

def step3_pin_twice(ex: WinExecutor, first_result: object) -> bool:
    print("\n=== Step 3: UIA pin-twice gate ===")
    from cua.types import EMPTY as _EMPTY, Element

    # If step 2 produced no usable result, skip rather than double-fail
    if first_result is None or first_result is _EMPTY or not first_result:
        print("  first probe was empty — pin-twice gate cannot run")
        print("Step 3: SKIP (PASS trivially — step 2 already failed)")
        return True  # don't double-fail

    # If step 2 was a desktop fallthrough, propagate the failure — do not pass
    if _is_desktop_fallthrough(first_result):
        top = first_result[0]
        print(f"  first probe was a desktop fallthrough "
              f"(name={top.name!r} bounds={top.bounds})")
        print("Step 3: FAIL (desktop fallthrough from step 2 must not trivially pass)")
        return False

    # Kill and reopen Notepad
    print("  killing Notepad…")
    subprocess.run(["taskkill", "/f", "/im", "notepad.exe"],
                   capture_output=True, check=False)
    time.sleep(0.5)

    print("  reopening Notepad…")
    proc2 = _open_notepad()
    time.sleep(1.0)  # let it open

    # Focus + maximize before the second probe so bounds are comparable
    nb2 = _focus_notepad(ex)
    if nb2 is None:
        _kill(proc2)
        print("  ERROR: Notepad did not reopen within 5 s")
        print("Step 3: FAIL")
        return False

    action2 = _probe_notepad_center(ex, nb2)
    print(f"  probing logical coordinate {action2['coordinate']} for second probe")
    second_result = ex.probe(action2)

    _kill(proc2)

    if second_result is _EMPTY or not second_result:
        print("  second probe returned EMPTY")
        print("Step 3: FAIL")
        return False

    # Guard: fail if the second probe fell through to the desktop shell
    if _is_desktop_fallthrough(second_result):
        top = second_result[0]
        print(f"  FAIL: second probe landed on desktop "
              f"(name={top.name!r} bounds={top.bounds})")
        print("Step 3: FAIL")
        return False

    # Compare the deepest element across both probes
    e1: Element = first_result[0]
    e2: Element = second_result[0]

    name_match = e1.name == e2.name
    role_match = e1.role == e2.role
    # Bounds can shift by a pixel or two if DPI rounding differs; allow ±2px slack
    def _close(b1, b2, tol: int = 2) -> bool:
        return all(abs(a - b) <= tol for a, b in zip(b1, b2))
    bounds_match = _close(e1.bounds, e2.bounds)

    print(f"  first  : name={e1.name!r} role={e1.role!r} bounds={e1.bounds}")
    print(f"  second : name={e2.name!r} role={e2.role!r} bounds={e2.bounds}")
    print(f"  name match  : {name_match}")
    print(f"  role match  : {role_match}")
    print(f"  bounds match: {bounds_match}")

    ok = name_match and role_match and bounds_match
    print(f"Step 3: {'PASS' if ok else 'FAIL'}")
    return ok


# ---------------------------------------------------------------------------
# step 4: benign actuate (mouse_move only — no state changes)
# ---------------------------------------------------------------------------

def step4_actuate(ex: WinExecutor) -> bool:
    print("\n=== Step 4: actuate() — benign mouse_move ===")
    action = {"action": "mouse_move", "coordinate": [512, 400]}
    result = ex.actuate(action)
    print(f"  actuate returned: {result!r}")
    ok = isinstance(result, str) and "withheld" not in result.lower()
    print(f"Step 4: {'PASS' if ok else 'FAIL'}")
    return ok


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    print("WinExecutor verification — starting")
    try:
        ex = WinExecutor()
    except RuntimeError as e:
        print(f"FATAL: cannot construct WinExecutor — {e}")
        print("(This script must run on a Windows machine with a visible desktop.)")
        return 1

    print(f"  real resolution : {ex.real_size}")
    print(f"  scale factors   : sx={ex.scale[0]:.4f}  sy={ex.scale[1]:.4f}")

    results: list[bool] = []

    # step 1 — screenshot
    results.append(step1_screenshot(ex))

    # open Notepad for steps 2 + 3
    print("\n  opening Notepad for UIA probe steps…")
    proc = _open_notepad()
    time.sleep(1.0)

    # step 2 — probe
    ok2, probe_result = step2_probe(ex, proc)
    results.append(ok2)

    # step 3 — pin-twice (kills + reopens Notepad internally)
    results.append(step3_pin_twice(ex, probe_result))

    # step 4 — benign actuate
    results.append(step4_actuate(ex))

    # final summary
    print("\n========================================")
    labels = ["screenshot+b64", "probe", "pin-twice gate", "actuate"]
    all_passed = True
    for label, ok in zip(labels, results):
        status = "PASS" if ok else "FAIL"
        print(f"  {label:<20} {status}")
        if not ok:
            all_passed = False

    overall = "ALL PASS" if all_passed else "SOME FAILURES — see above"
    print(f"\nOverall: {overall}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
