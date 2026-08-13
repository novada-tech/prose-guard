"""The sequenced arm: one concern at a time, each able to hold the message back.

One check object per prompt file in phases/, in filename order. They differ only in their
prompt, so they are prompt files rather than four near-identical modules.

Order is editorial - outermost decision first - so no later phase can create work for an earlier
one. That is what makes freezing a passed phase safe, and freezing is what stops the deadlock:
with re-litigation, phase 1 says cut this, phase 3's fix puts it back, and the turn ends with no
message at all. The orchestrator walks from the first unpassed phase and never returns.

Unlike the omnibus check these DO deny, which is the trade this arm exists to measure: better
output against more calls, more blocked turns, and five chances to hold back a message that was
fine.
"""
import os

from . import ask as _ask

_HERE = os.path.dirname(os.path.abspath(__file__))
PHASE_DIR = os.path.join(_HERE, "phases")


class Phase:
    CAN_DENY = True
    COSTS_A_CALL = True

    def __init__(self, path):
        self.NAME = os.path.basename(path)[:-3].split("-", 1)[-1]
        self._path = path

    def run(self, text, envelope=None):
        ok, why = _ask.ask(self.NAME, _ask.read_prompt(self._path), text, envelope)
        return ok, ("" if ok else why)


def phases():
    try:
        names = sorted(f for f in os.listdir(PHASE_DIR) if f.endswith(".md"))
    except OSError:
        return []
    return [Phase(os.path.join(PHASE_DIR, f)) for f in names]
