# Vision-Primary Computer-Use Agent — Spec v2 (Two Sensors, Two Routers)

**What this is.** The settled architecture restated after the first round of live evidence. `00_consolidated_spec.md` is the v1 destination; it is now the *record*, not the current plan. This file supersedes its **Thesis (§1)** and **Estimator (§5)** and leaves the rest of its module design standing. Buildable from cold, readable in one pass.

**Why a v2.** v1 staked the system on one bet: that a cheap external read of the model's *uncertainty* (sample disagreement) would also flag the *dangerous* steps. We built it, drove a real Windows machine, and tested the bet. It failed in a specific, useful way. The failure is what this spec is built around. Evidence: `findings/2026-06-28-disagreement-flat.md`, `findings/2026-06-28-ab-real-numbers.md`, `findings/2026-06-29-consequence-probes.md`.

**Dual register.** Confident about the reasoning, honest about the unknowns. `[BUILD]` = code can be written against it. `[INTERFACE]` = seam defined, internals deferred. `[PROVISIONAL]` = openly unsolved, the honest floor.

---

## 1. Thesis (v2)

One principle, unchanged from v1: **before each action, measure — and spend the cheapest perception that settles what you are measuring.** Acting is the dearest measurement, because it is the only one that changes the world you cannot un-change.

What changed is *what gets measured*. v1 measured one thing (uncertainty) and treated stakes as a bar on it. The evidence forces two:

> **One loop, two sensors, two routers.** The same measure-before-act loop runs every step. But it listens for two different things, with two different ears, and each ear drives a different decision.

- **Sensor A — "Do I know what to do here?"** This is uncertainty. It lives in the model's head. It is read from the outside by **sample disagreement** (resample the screen, watch how much the proposed action moves). It feeds the **model router**.
- **Sensor B — "Can this be undone?"** This is consequence. It lives in the world, not the head. The model's confidence carries *nothing* about it. It must be read from the world's own cues — the control's label and role, whether an undo exists, whether a confirm dialog appears. It feeds the **caution router**.

The two are **orthogonal**, and proving that is the central result of v1 (§5). The model is exactly as sure clicking "Replace All" as clicking a menu. So a single sensor cannot govern both, and the system that assumes it can will be calm and confident right up to the irreversible mistake.

**Vision is still primary.** The model perceives and plans from pixels. Structure (UIA/DOM) is a probe called for precision, disambiguation, or to read consequence — not an always-on layer. Eyes-then-hands still falls out for free: looking is a cheaper measurement than acting, so the loop looks first whenever a cheaper look would change the commit.

**It is a suite, not a tool.** Because the two sensors drive two routers, the product is a **router over a suite of models and caution levels**, not one fixed agent. That is the shape of the thing.

---

## 2. The two routers

### 2.1 Model router — driven by Sensor A (complexity/uncertainty)
Spend the least intelligence the step needs.

| Signal | Route |
|---|---|
| Determined step (disagreement near zero) | **Haiku** — cheap, fast, sufficient |
| Moderate ambiguity | **Sonnet** |
| Genuine fork / unfamiliar UI (disagreement spikes) | **Opus**, and raise the thinking budget |

Thinking budget is the **fine knob** inside a tier; model tier is the coarse one. This is the rescue of the flat finding: disagreement is *flat on determined GUIs* precisely because those are the steps a small model can do. It only spikes on real forks. That makes it a **good complexity signal and a useless safety signal** — exactly the right input for *this* router and the wrong input for the other one.

### 2.2 Caution router — driven by Sensor B (consequence)
Spend the least risk the step allows.

| Consequence read | Route |
|---|---|
| Reversible (typing, navigation, anything with undo) | **act** |
| Irreversible but the world says so (a "Replace All", a "Delete", a confirm dialog) | **look / confirm first**, then act |
| Irreversible *and* unreadable (no cue, no undo, ambiguous target) | **escalate to a human** |

The escalation rung is the one safety guarantee: when consequence is high and cannot be read, the agent stops and hands off. Sensor B is the part we have **not** built yet (§5.2).

---

## 3. System architecture (carried from v1, unchanged)

Five modules behind one perception interface; each has a single reason to change. The wiring from `00_consolidated_spec.md` §2 stands as-is:

- **Perception interface** `[INTERFACE]` — the spine. Two backends (vision = screenshot; structure = UIA/DOM, may return empty), one interface. **Live and replay are backends, not rewrites** — the agent never knows whether it faces a live target or a recording.
- **Policy** `[BUILD]` — a pure function `(observation, belief) → (typed measurement, belief')`. Computes no signals; combines them. Resolves one blocking uncertainty per step (coarse, legible).
- **Estimator** `[PROVISIONAL]` — fills the signals the policy reads. **This is where v2 reshapes the most** (§5).
- **Actuation** `[INTERFACE]` — pattern-first, pixel fallback, snap-to-target. Vision owns intent; structure sharpens.
- **Trace** `[INTERFACE]` — saw / decided / did / why. Elevated in v2 to a first-class instrument (§6).

The invariant that matters most for v2: the policy is **pure and testable**, it emits typed measurements and calls nothing directly. Adding a second sensor and two routers does not change that contract — the routers are *consumers* of the policy's typed output and of the estimator's signals, not new branches inside the pure function.

---

## 4. Policy layer `[BUILD]` — what carries, what bends

Carries from v1 §4: belief is a model of what is *not* known; the atom is the **triple** (magnitude, trust, reducer); the decision scans triples, picks the most-blocking weighted by trust, emits its reducer; acting is emitted only when no cheaper measurement would change it; **graduation** — use magnitude ordinally under weak trust, quantitatively under strong trust, same code throughout.

Bends in v2:

- **Stakes is promoted from a door to a sensor.** v1 §4.6 made stakes "a conservative read on the action *type*" (delete/submit/confirm = high). The probes showed that is **both leaky and bypassable** (§5.3). v2 keeps a type-based stakes read as the *floor*, but the real consequence signal is Sensor B reading the **target and outcome**, not the action type. Stakes stops being a wall the model routes around and becomes a measurement the caution router acts on.
- **The estimator now fills two signal families,** not one: an uncertainty/complexity magnitude (Sensor A, for the model router) and a consequence magnitude (Sensor B, for the caution router). The triple representation is unchanged; there are simply triples of both kinds.

---

## 5. Estimator `[PROVISIONAL]` — rebuilt around the evidence

This was "the load-bearing unknown" in v1. Half of it is now *known*, and the other half moved.

### 5.1 Sensor A — uncertainty, via sample disagreement. **Tested. Demoted, not discarded.**
The Computer Use API exposes no logprobs (verified live 2026-06-27), so the only cheap external uncertainty signal is sample disagreement: resample the same screen k times, score how much the proposed action moves.

**Result (measured):** on a determined Notepad find-and-replace, disagreement was **flat — 0.000 on 8 of 9 steps, including the consequential "Replace All" commit.** It spiked only on a genuine fork (step 0: open-the-menu vs click-in-doc, 0.169). `findings/2026-06-28-disagreement-flat.md`.

**Read:** disagreement measures whether the model knows *what to do*, not whether the action is *safe to do*. It is structurally incapable of catching a consequential-but-obvious commit. So it is **dead as a safety signal** and **alive as a complexity signal** — it is exactly the input the §2.1 model router wants. Its open validity gate is now narrow: does it predict step *difficulty* (AUROC vs a "needed a bigger model" label), not wrongness.

> Caveat on record: the ambiguity retrial (`findings/2026-06-29-consequence-probes.md`) was inconclusive — context-free resampling returned no action on most samples, and a frame-pull error dropped half the screens. A fair test of disagreement-under-ambiguity needs **in-context resampling** (replay the real conversation to that step) with the model's text kept, not only its action.

### 5.2 Sensor B — consequence. **The new load-bearing unknown.**
There is no working consequence sensor yet. This is the honest floor of v2. The signal must come from the world, cheaply, before acting. Candidate reads, cheapest first:
- **The control's own label and role** off the structure probe ("Replace all", "Delete", a primary/destructive button role). Cheap. Breaks on custom-drawn UI with no tree.
- **Reversibility cues** — is there an undo, is this a form submit, is this a file overwrite.
- **The app's own confirmation** — a confirm dialog is the world stating "this is consequential." Reliable, but it arrives *after* you have started the action, so it gates the second click, not the first.

The open problem, stated plainly: **a cheap, general signal of consequence, when the model's own confidence is no help.** This is the question that decides whether the agent can safely touch a real machine. The same probe that already reads "green" can read "Replace all, no undo" — same loop, same probe, one more thing to listen for.

### 5.3 What the probes proved about the old stakes door
Live probes on Notepad, recorded via capture-v2 trace (`findings/2026-06-29-consequence-probes.md`):
- **Consequence in the verb** (Delete) gets caught by the type-based door — but it is a **wall, not a gate** (state pinned at 0.40 > the high-stakes bar 0.05, never clears), and the model **routes around it** with a low-stakes key (BackSpace). Blocking an action *type* is bypassable, because the destructive outcome is reachable by several types.
- **Consequence in the noun** (a `click` on a "Replace All" button) slips straight through — the action type reads low-stakes.
- **Ambiguity blindness** — "delete the yellow" with two yellows on screen: it deleted **both**, never registered the ambiguity, `Escalated: False` throughout. The crude estimator reports the same fixed numbers regardless of what is on screen.

All three point at the same fix: read consequence off the **target and outcome**, make it a **gate that decides** (not a wall that blocks), and let genuine ambiguity raise the escalate signal.

---

## 6. The capture as instrument `[INTERFACE]` — elevated in v2

Every run records what it saw, what it did, and **why it decided each step** (capture format v2: per-step `decided` + `reason`, top-level `trace` of `saw / decided / did / why`). That file *is* the run, frozen. After recording, the machine is out of it: replay offline, resample the model on those exact screens, run the A/B, read the trace step by step. No VM, no live screen.

This is not just logging. **Every finding in §5 came from interrogating one recorded run from an angle not in mind when it was recorded.** The capture is the lab bench. It is promoted here from "demo legibility surface" (v1 §7) to the primary research instrument of the project.

---

## 7. The kill question (unchanged, now with a number)

> Can this policy beat "full look every step" on cost while matching or improving the confident-wrong rate?

**Measured answer, v1 evidence: NOT YET.** The blended policy was far cheaper and committed the one consequential action **blind** (`findings/2026-06-28-ab-real-numbers.md`). It failed on safety, not cost. v2's whole reason to exist is that the safety failure is a **consequence** failure (Sensor B missing), not an uncertainty failure (Sensor A works as a complexity signal). Closing the kill question = building Sensor B.

---

## 8. Load-bearing unknowns (v2 honest floor)

1. **A cheap, general consequence signal exists** (Sensor B). The new #1. If false, the agent cannot be trusted on irreversible steps and the honest system is "escalate on any type-flagged action" — safe but not autonomous.
2. **Disagreement predicts difficulty** (not wrongness) well enough to drive the model router. Demoted claim, narrow gate, untested.
3. **Reading consequence off structure generalizes** past native controls to custom UI. The probe reads a UIA/DOM label fine; a canvas-drawn "Delete" button has no label to read.
4. **Screens are static between actions** — carried from v1; heavy SPAs are the likeliest violators.

**Operational response, unchanged:** ignorance detection plus measurement before trust. When consequence is high and unreadable, escalate. No analysis removes the gap; the system contains it by detecting the unreadable case and handing off.

---

## 9. Relationship to v1

`00_consolidated_spec.md` is the record of the destination *as planned*. This file is the destination *as the evidence redrew it*. Specifically:
- v1 §1 Thesis (one trigger family, stakes as a bar) → replaced by §1 here (two sensors, two routers).
- v1 §5 + §10.1 Estimator/uncertainty-bet → replaced by §5 here (Sensor A demoted to complexity; Sensor B is the new bet).
- v1 §2–4, §6–9 (architecture, perception interface, policy mechanics, actuation, trace, harness, A/B) → carried, with the two amendments in §4 above.

The derivation record (`perception_policy_spec.md`, `policy_layer_spec.md`, `05_estimator_spec.md`, `v0_demo_slice_spec.md`) stays as the path. This is the new destination.
