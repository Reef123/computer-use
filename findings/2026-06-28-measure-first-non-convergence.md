# Finding: measure-first starves the action (PROBE never converges to ACT)

**Date:** 2026-06-28 — first real live capture, on Power Automate Desktop.
**Capture:** `captures/in-the-power-automate-desktop-settings-d-20260628T213105Z.json`
**Task:** "turn off the Auto-start application checkbox" in PAD Settings (checkbox was, and remained, checked).

## What happened
6 steps, terminated `model-finished`, decisions = **PROBE×6, ACT×0**. The model proposed the
*same* action every step — `{type: click, target.region: [774, 204]}` (the checkbox point) — and
the policy gated every attempt to **PROBE** (measure-first), never converging to **ACT**. After 6
rounds the model ended its turn. The click never fired; ground-truth confirmed the box stayed checked.

## The bug
Measure-first, as currently tuned, can loop on probing the same target without ever committing. The
model wants to act; the policy keeps re-measuring; the task never completes. A measure-first agent
that never crosses to ACT does nothing — *eyes with no hands*.

## Hypothesis (verify with a trace re-run)
The residual *blocking* uncertainty is probably not reducible by PROBE. PROBE reduces LOCATION/STATE;
if the blocker is **OUTCOME** ("will this click achieve the goal?"), pre-action probing can't clear it
— only acting-and-observing can. A policy that requires clearing OUTCOME before the first ACT
deadlocks. Candidate fixes:
1. OUTCOME uncertainty must not gate the *first* ACT (you cannot measure an outcome you haven't caused).
2. Convergence: once a PROBE confirms the target's identity at the click point, permit ACT.
3. Repeat-probe cap: N identical probes of the same target → force ACT or ESCALATE, never loop.

## Capture-format gap
The saved capture stores observations + intended actions but **not** the probe *results* or the belief
evolution — enough to see the decision *sequence*, not enough to see *why* the bar never cleared.
Fix: serialize the trace (belief updates) alongside steps, then this is self-diagnosing.

## Next
Trace re-run → identify the blocking uncertainty → tune convergence → re-run the toggle, expecting
ACT=1 and task complete.
