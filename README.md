# Vision-Primary Computer-Use Agent

Per step, the agent takes the **lowest-cost measurement** that brings its
calibrated risk of acting wrong below the bar set by **stakes** and **support**.
Look, probe, wait, and act are one family of measurements; acting is the
highest-cost one because it changes the world. Eyes-then-hands is a consequence,
not a rule: looking is cheaper than acting, so the agent takes the cheapest
measurement that clears the block first.

> Status: v0. The policy core (pure, replay-driven) runs. The live backends
> (Computer Use API, UIA / CDP structure, actuation) and the A/B convincer
> follow; the measurement layer is deferred. The design and architecture docs
> are kept in a separate private tree, not in this repo.

## Layout

    src/cua/
      types.py        contracts: the belief atom, measurement, observation
      policy.py       the uncertainty-reduction engine (pure)
      estimator.py    [provisional] fills magnitude + trust — the honest floor
      perception.py   the spine: replay / live backends behind one interface
      trace.py        saw / decided / did / why
      fixtures/       hand-authored replay captures (scaffolding, not real runs)
    tests/
      test_policy.py  the policy contract, exercised on deterministic input

## Run

    python tests/test_policy.py
