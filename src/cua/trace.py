"""Trace [INTERFACE] — the readable record (consolidated spec §7).

Per step: saw / decided / did, plus "why I reached" on any probe or escalate.
This is the demo's legibility surface; the full harness-grade schema is deferred
with the measurement layer.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TraceRow:
    step: int
    saw: str
    decided: str
    did: str
    why: str = ""


class Trace:
    def __init__(self) -> None:
        self.rows: list[TraceRow] = []

    def record(self, step: int, saw: str, decided: str, did: str, why: str = "") -> None:
        self.rows.append(TraceRow(step, saw, decided, did, why))

    def to_markdown(self) -> str:
        head = "| # | saw | decided | did | why I reached |\n|---|---|---|---|---|\n"
        body = "".join(
            f"| {r.step} | {r.saw} | {r.decided} | {r.did} | {r.why} |\n" for r in self.rows
        )
        return head + body
