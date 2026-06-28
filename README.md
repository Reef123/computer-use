# Vision-Primary Computer-Use Agent

Per step, the agent takes the **lowest-cost measurement** that brings its
calibrated risk of acting wrong below the bar set by **stakes** and **support**.
Look, probe, wait, and act are one family of measurements; acting is the
highest-cost one because it changes the world. Eyes-then-hands is a consequence,
not a rule: looking is cheaper than acting, so the agent takes the cheapest
measurement that clears the block first.

> Status: v0. The policy core (pure), the session runner, and the A/B convincer
> run, replay-driven. The live computer-use loop runs against the real Computer
> Use API (our policy gates each commit the model proposes); the UIA structure
> probe and actuation land on the Windows VM. The measurement layer is deferred.
> The design and architecture docs are kept in a separate private tree, not in
> this repo.

## The bar

The kill question: can the blended policy beat **full look every step** on cost
without raising **confident-wrong**? The A/B runs both arms (the same policy, one
flag) over the same recorded task and reports cost and confident-wrong for each.

## Layout

    src/cua/
      types.py        contracts: the belief atom, measurement, observation
      policy.py       the uncertainty-reduction engine (pure) + the full-look baseline
      estimator.py    [provisional] fills magnitude + trust: the honest floor
      perception.py   the spine: replay / live backends behind one interface
      runner.py       the session loop: observe, propose, decide, trace
      ab.py           the convincer: blended vs full-look, cost + confident-wrong
      live.py         the real Computer Use API loop; our policy gates each commit
      executor.py     performs actions on the target (stub now; VM screenshot/UIA/act)
      trace.py        saw / decided / did / why
      fixtures/       hand-authored replay captures + replay wiring (scaffolding)
    tests/
      test_policy.py  the policy contract, on deterministic input
      test_runner.py  the session loop, backend-agnostic, through the replay spine
      test_ab.py      the convincer reports a win and a loss honestly
      test_live.py    the live loop (fake transport): mapping, gating, escalate
    demo_replay.py    run the fixture through the runner and print the trace
    ab_demo.py        run the A/B and print the kill-question verdict
    live_probe.py     drive the real Computer Use API loop (needs ANTHROPIC_API_KEY)

## Run

    python tests/test_policy.py
    python tests/test_runner.py
    python tests/test_ab.py
    python tests/test_live.py
    python demo_replay.py
    python ab_demo.py
    python live_probe.py        # real API round-trip; reads .env
