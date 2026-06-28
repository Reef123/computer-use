# Finding: sample-disagreement is flat on a determined GUI task (the core bet, tested)

**Date:** 2026-06-28. First measurement of the project's #1 load-bearing bet
(`05_estimator_spec`): does sample disagreement predict being-wrong / risk?
**Method:** offline, context-free resampling (`eval_disagreement.py`), k=5, over the 9
screens of `captures/use-find-and-replace-to-replace-every-re-...json` (Notepad
Find & Replace). Disagreement = `max(type_disagreement, target_dispersion)`.

## Result
```
Step  Recorded action     Disagreement
0     click@(104,106)      0.169   ← only non-trivial step (ambiguous first move)
1-6   clicks / types       0.000–0.002
7     click@(628,195)      0.000   ← the consequential "Replace All"
8     click@(651,157)      0.000
```

## Read
1. **Flat.** 8/9 steps ~0. On a determined GUI screen the action is obvious (the
   Replace dialog is open → where to click is fixed), so the model agrees with itself.
   Only step 0 — "open the Edit menu" vs "click in the document," both reasonable —
   actually splits (3 samples at the menu, 2 elsewhere → 0.169).
2. **It does NOT flag the consequential commit.** Replace All = 0.000. The model is
   certain *where* that button is. The key insight: **disagreement measures the model's
   UNCERTAINTY, not the action's STAKES.** Replace All is high-stakes AND low-uncertainty
   — orthogonal axes. Disagreement structurally cannot catch "this commit is consequential."

## Caveats (do not over-read one capture)
- Context-free resampling is the **generous** case for finding disagreement — adding
  conversation history makes the model *more* certain, not less. Even so: flat.
- One capture, 9 mostly-unambiguous steps. Not a verdict — a specific, discouraging
  data point. A real verdict needs several labeled captures incl. genuinely ambiguous
  states, and the AUROC gate from §05.

## Implications
- The A/B's safety failure (commit Replace All blind) is a **stakes** problem, not an
  uncertainty one → the right fix is **label-aware stakes** (read "Replace all" off the
  probed structure → HIGH → measure first), i.e. the [structure-snapping v1](v1-structure-snapping.md).
  NOT the disagreement estimator.
- Sample-disagreement's only plausible role is a **cost lever** on genuinely ambiguous
  steps (step 0). To show it earns its k extra calls, test it on ambiguous-task captures
  (web / unfamiliar UIs), not clean desktop GUI flows.
- On this evidence the system stays on the PRD's honest floor: **stakes-only**.

## Reproduce
```
PYTHONPATH=src python3 eval_disagreement.py \
  captures/use-find-and-replace-to-replace-every-re-20260628T220554Z.json \
  --task "use Find and Replace to replace every red with yellow in the document" --k 5
```
