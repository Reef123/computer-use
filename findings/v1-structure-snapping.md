# v1 idea: structure-snapping (cue-driven target refinement)

**Raised:** 2026-06-28 (Shareef), during the Notepad demo runs.

## The idea
Today the model picks a click *coordinate* from vision, and our probe reads the UIA
element at exactly that pixel — used only to *gate* (is something there?). v1 should
use the structure to *refine the target*: take the model's coarse vision pick, look at
the named controls in the UIA neighborhood (the "cues" — "Edit", "Replace all", a
checkbox), and **snap the action to the matching named element** before acting. Act on
that element's bounds/center, not the raw pixel.

## Why
- Robust to pixel drift, window moves, DPI scaling, theme changes — a 10px-off guess
  still lands on the right control.
- Self-correcting: the named controls are cues the agent already perceives via probe.
- Raises the LOCATION trust honestly (we *know* we hit the named control), which the
  real v1 estimator can use.
- The `Target.marker_id` field already exists for exactly this ("snapped to marker X"
  vs raw region).

## The discipline (don't drift the thesis)
Keep it **vision-primary**. Vision drives intent + coarse target; structure *refines*.
Do NOT flip to enumerate-the-whole-tree-and-navigate-by-name — that's accessibility-
primary automation (what PAD itself is), a different product. Cues sharpen the aim;
they don't replace the eyes.

## Sketch
- After the probe folds back (live.py), if structure is non-empty, find the element
  whose name/role best matches the intended action and snap `Target` to its center +
  set `marker_id`. Fall back to the raw pixel if no good match.
- Feed "snapped to a named control" into the estimator as higher LOCATION trust.
