# A computer-use agent, and where the evidence took it

This is a computer-use agent that drives a Windows machine. A harness sits around it. The
harness decides how much to check before each action. It also decides when to slow down
before something it cannot undo.

## The vision

Most agents blindly follow the model.

My idea: use a harness to measure uncertainty before action. Do it as cheaply as
possible. That saves the agent from actions it cannot reverse.

## The ladder

"The least it takes" means like a ladder. Bottom is cheap. Top is expensive.

1. Look again at the screen it already has.
2. Probe one spot. Ask the accessibility tree what is under the cursor.
3. Resample the model. Ask it a few times and see if it agrees with itself. Dear, several model calls.
4. Act.

Take the lowest rung that settles the doubt. Go to the next level only if you must. The
agent never acts until it has to.

## The assumption

The agent has to know when it is unsure. Cheaply. If it cannot tell confident from
uncertain on the spot, there is nothing to gate on.

The API gives no confidence signal. So I read it from the outside. Resample the model on
the same screen. Watch how much its answers move. A lot of movement means it is guessing.
Everything stood on that.

## What I built to test it

Four pieces.

A policy core. It turns a belief about what is unknown into one decision. Pure and
testable.

A live loop against the real Computer Use API. The model proposes. The policy gates each
commit.

An executor on a Windows VM. Screen capture, accessibility probe, actuation.

An A/B. It runs the same task two ways: my policy against looking every step. One
question. Cheaper, without committing wrong more often?

Then I put it on a real machine. It drove Notepad through a multi-step find-and-replace,
end to end.

## The capture

Every run records what it saw, what it did, and why it decided each step. That file is
the run, frozen.

After that the machine is out of it. Replay the recording offline. Re-ask the model what
it would do on those exact screens. Run the A/B. Read step by step why it looked. No VM.
No live screen. Every finding here came from one recorded run, questioned from angles I
had not thought of when I recorded it.

## What the evidence said

The A/B came back. The cheap policy was far cheaper. It also committed the one
consequential action blind. The failure was safety.

So I tested the assumption under everything. Resampling came back flat. Near zero on every
step, including the consequential one. The reason is structural. Resampling measures
whether the model knows what to do. It says nothing about whether the action is safe to
do. The model is as sure clicking "Replace All" as clicking a menu.

## Where it moved

The thing that matters is consequence. Can the action be undone. Uncertainty and
consequence live in different places. Uncertainty is in the model's head. Consequence is
out in the world. The model's confidence tells you nothing about whether an action can be
undone. The most dangerous action is the one it is surest about.

Two tests I performed, both destructive:

- **Find and Replace everything.** It just acted, full confidence. The danger sat in the button. The action type looked harmless. Nothing caught it.
- **"Delete the yellow," with two yellows on screen.** It deleted both. It never asked which. Faced with "which one," it chose "all." Ambiguity made it worse.

The first shows danger hiding in a harmless-looking action. The second shows it getting
more reckless under ambiguity.

The safety problem is not a fumbling model. The model is calm and sure right up to the
irreversible thing. Neither its confidence nor the action type tells you the thing is
irreversible.

## Two reads

The agent had one read: how sure am I? It needed two.

Does it know what to do? Ask it a few times. If the answers jump around, it is guessing.

Can it be undone? The model cannot tell you.

One read the model can do. One it cannot. So I built a router. Easy steps get a small
model. Hard steps get a big one. Safe steps act. Risky steps slow down.

## The open problem

What is a cheap, general signal of consequence, when the model's own confidence is no
help? Reading it off the control before acting is cheap. It breaks on custom UI. Letting
the app reveal it, through a confirm dialog, is reliable but late. I have not solved this.

## Where it's going

Two builds. First the second read: the probe that already finds "green" (from the test)
on a screen can read "Replace all, no undo" the same way. Same loop, same probe, one more
thing to listen for. Then the router around both reads, so the easy steps run cheap and
the rare dangerous ones get the slow, careful path.

## Run

    python tests/test_policy.py     # the policy, on deterministic input
    python ab_demo.py               # the A/B kill question, on a fixture
    python live_probe.py            # a real Computer Use API round-trip (reads .env)

`findings/` holds the results this README summarizes.
