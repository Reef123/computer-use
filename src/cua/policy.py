"""Policy [BUILD] — the uncertainty-reduction engine (consolidated spec §4).

A pure function: (observation, belief) -> (measurement, belief'). It computes no
signals; it combines them. Each step: identify the uncertainty that most blocks
a confident commit, emit the cheapest measurement that reduces it. Acting is the
highest-cost measurement, taken only when no cheaper one would change the
decision. When no estimate is trustworthy, escalate.

The full-look baseline (`forced_probe=True`) is the SAME entry with one flag: it
never takes the cheap skip. It is the A/B's other arm, not a second codebase.
"""
from __future__ import annotations

from .estimator import Signals, crude_estimator
from .types import (
    ActionType,
    Belief,
    IntendedAction,
    Measurement,
    Observation,
    REDUCER_FOR_KIND,
    Reducer,
    Stakes,
    StateEstimate,
    Uncertainty,
    UpdateEvent,
)

# --- thresholds (consolidated spec §4.4 graduation) ---
TRUST_FLOOR = 0.1   # all entries below this -> out of support -> escalate
TRUST_QUANT = 0.7   # at/above -> read magnitude quantitatively (else ordinal)

# How low P(wrong) must be before committing, scaled by stakes (§4.6).
# High stakes -> strict bar; its false-negative rate on destructive actions
# must be near zero, so it forces more measurement before any commit.
_ACT_BAR = {Stakes.LOW: 0.5, Stakes.HIGH: 0.05}


def classify_stakes(action: IntendedAction | None) -> Stakes:
    """Separate conservative door (§4.6): classification on action TYPE, erring
    high. Not a float, not from the estimator."""
    if action is None:
        return Stakes.LOW
    if action.type in {ActionType.SUBMIT, ActionType.CONFIRM, ActionType.DELETE}:
        return Stakes.HIGH
    return Stakes.LOW


def update_belief(belief: Belief, observation: Observation, signals: Signals) -> Belief:
    """Uncertainty-reduction accounting (§4.5): write fresh magnitude/trust into
    the triples, debit what dropped, credit what rose, log every move. An
    isolated, named step so the belief stays inspectable."""
    old = {u.kind: u for u in belief.uncertainties}
    new_us: list[Uncertainty] = []
    events: list[UpdateEvent] = []
    for kind, (mag, trust) in signals.items():
        new_us.append(Uncertainty(kind, mag, trust, REDUCER_FOR_KIND[kind]))
        prev = old.get(kind)
        if prev is None:
            events.append(UpdateEvent(kind, None, mag, "introduced"))
        elif mag < prev.magnitude:
            events.append(UpdateEvent(kind, prev.magnitude, mag, "debit"))
        elif mag > prev.magnitude:
            events.append(UpdateEvent(kind, prev.magnitude, mag, "credit"))
        else:
            events.append(UpdateEvent(kind, prev.magnitude, mag, "unchanged"))
    return Belief(
        uncertainties=tuple(new_us),
        state=_update_state_estimate(belief.state, observation),
        history=belief.history + tuple(events),
    )


def _update_state_estimate(state: StateEstimate, observation: Observation) -> StateEstimate:
    # Thin: just enough to specify actions. v0 records the frame ref last seen.
    return StateEstimate(screen=observation.vision.image_ref, note=state.note)


def decide(belief: Belief, stakes: Stakes) -> Measurement:
    """The pure decision (§4.3). Pick the most-blocking uncertainty's reducer;
    escalate when no estimate is trustworthy; act only when nothing blocks."""
    us = belief.uncertainties
    if not us:
        return Measurement(Reducer.ACT, reason="no active uncertainty; commit")

    # Support collapse: every estimate is below the trust floor. No screen
    # measurement can strengthen second-order uncertainty -> escalate.
    if all(u.trust < TRUST_FLOOR for u in us):
        return Measurement(
            Reducer.ESCALATE,
            reason="out of support: no uncertainty estimate is trustworthy",
        )

    # The biggest blocker. Ranked ordinally by magnitude; `trust` only governs
    # whether we would read that number quantitatively (§4.4) — same data.
    blocker = max(us, key=lambda u: u.magnitude)
    bar = _ACT_BAR[stakes]

    # Nothing blocks enough to outweigh acting -> commit. Acting is the
    # highest-cost measurement, taken only when no cheaper one changes this.
    if blocker.magnitude < bar:
        return Measurement(Reducer.ACT, reason=f"all uncertainty below act bar ({bar}); commit")

    mode = "quant" if blocker.trust >= TRUST_QUANT else "ordinal"
    return Measurement(
        blocker.reducer,
        reason=(
            f"{blocker.kind.value} blocks commit "
            f"(mag={blocker.magnitude:.2f}, trust={blocker.trust:.2f}, {mode}); "
            f"reduce via {blocker.reducer.value}"
        ),
    )


def _forced_decision(observation: Observation, belief: Belief) -> Measurement:
    """The full-look baseline arm (consolidated spec §2/§8): never take the cheap
    skip. Spend a perception measurement each step, and escalate on the same
    out-of-support condition the blended policy uses. Same policy entry, one flag."""
    us = belief.uncertainties
    if us and all(u.trust < TRUST_FLOOR for u in us):
        return Measurement(Reducer.ESCALATE, reason="full-look baseline: out of support")
    if isinstance(observation.structure, tuple) and observation.structure:
        return Measurement(Reducer.PROBE, reason="full-look baseline: probe every step")
    return Measurement(Reducer.LOOK, reason="full-look baseline: look every step")


def policy(
    observation: Observation,
    belief: Belief,
    intended_action: IntendedAction | None = None,
    *,
    estimate=crude_estimator,
    stakes=classify_stakes,
    forced_probe: bool = False,
) -> tuple[Measurement, Belief]:
    """(observation, belief) -> (measurement, belief').

    Pure given pure `estimate` and `stakes`. The estimator (which computes the
    signals) and the stakes door are injected and swappable; the policy itself
    computes nothing — it combines. `forced_probe=True` selects the full-look
    baseline arm for the A/B: one flag, one code path.
    """
    signals = estimate(observation, belief, intended_action)
    belief2 = update_belief(belief, observation, signals)
    if forced_probe:
        measurement = _forced_decision(observation, belief2)
    else:
        measurement = decide(belief2, stakes(intended_action))
    return measurement, belief2
