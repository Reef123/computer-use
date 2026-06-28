"""Runner [INTERFACE] — the one session loop (consolidated spec §8).

Wires the spine and the policy into a single loop: observe -> propose -> the
policy decides the cheapest measurement -> trace. The loop is generic over the
backend, the action proposer, and the estimator, so replay and live are the same
code with different injections; the agent never knows which it faces.

Open-loop by design for v0: one decision per recorded state. A recorded run is a
sequence of committed-action states, so the runner validates the policy's
decision at each state rather than simulating several measurements within one
state. Within-state closed-loop replay is deferred: it needs finer capture
(every perception, not just every action) or a live re-observation, which lands
with the live backend in Phase 2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .perception import PerceptionBackend
from .policy import classify_stakes, policy
from .trace import Trace
from .types import EMPTY, Belief, IntendedAction, Measurement, Observation, Reducer


class Proposer(Protocol):
    """Supplies the action the agent intends to commit at a state. Live: the
    model proposing from the screenshot. Replay: the recorded ground-truth
    action. Drives the stakes door; the policy decides whether to measure first.
    """

    def propose(self, observation: Observation, belief: Belief) -> IntendedAction | None:
        ...


@dataclass(frozen=True)
class StepRecord:
    index: int
    observation: Observation
    intended: IntendedAction | None
    measurement: Measurement


@dataclass
class SessionResult:
    steps: list[StepRecord] = field(default_factory=list)
    belief: Belief = field(default_factory=Belief)
    trace: Trace = field(default_factory=Trace)
    terminated: str = ""  # live runs: "model-finished" | "escalate" | "budget"

    def measurement_counts(self) -> dict[Reducer, int]:
        counts = {r: 0 for r in Reducer}
        for s in self.steps:
            counts[s.measurement.reducer] += 1
        return counts

    def perception_cost(self) -> int:
        """Illustrative cost proxy for the A/B: perception measurements inserted
        (look / probe / wait). Phase 3 refines this with real latency + tokens."""
        cheap = (Reducer.LOOK, Reducer.PROBE, Reducer.WAIT)
        return sum(1 for s in self.steps if s.measurement.reducer in cheap)

    def escalated(self) -> bool:
        return any(s.measurement.reducer is Reducer.ESCALATE for s in self.steps)


def run_session(
    backend: PerceptionBackend,
    proposer: Proposer,
    *,
    estimate,
    policy_fn=policy,
    stakes=classify_stakes,
    trace: Trace | None = None,
    max_steps: int = 64,
) -> SessionResult:
    """Drive a session to termination: backend exhausted, escalate, or budget.

    `policy_fn` is injected so the Phase 3 A/B can pass the same policy with the
    forced-probe baseline arm (`probe_trigger_forced=true`): one code path, one
    flag, no second codebase.
    """
    belief = Belief()
    trace = trace or Trace()
    steps: list[StepRecord] = []
    i = 0
    while i < max_steps:
        observation = backend.observe()
        if observation is None:
            break
        i += 1
        intended = proposer.propose(observation, belief)
        measurement, belief = policy_fn(observation, belief, intended, estimate=estimate, stakes=stakes)
        steps.append(StepRecord(i, observation, intended, measurement))
        trace.record(
            i,
            saw=_saw(observation),
            decided=measurement.reducer.value,
            did=_did(intended, measurement),
            why=measurement.reason if measurement.reducer in (Reducer.PROBE, Reducer.ESCALATE) else "",
        )
        if measurement.reducer is Reducer.ESCALATE:
            break
    return SessionResult(steps=steps, belief=belief, trace=trace)


def _saw(observation: Observation) -> str:
    if observation.structure is None:
        kind = "no-probe"
    elif observation.structure is EMPTY:
        kind = "no-tree"
    else:
        kind = f"{len(observation.structure)} elems"
    return f"{observation.vision.image_ref} ({kind})"


def _did(intended: IntendedAction | None, measurement: Measurement) -> str:
    if measurement.reducer is Reducer.ACT:
        return f"act: {intended.type.value}" if intended else "act"
    if measurement.reducer is Reducer.ESCALATE:
        return "(escalate / handoff)"
    return f"(measure: {measurement.reducer.value})"
