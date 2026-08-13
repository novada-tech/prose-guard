"""The four separate concerns `high` runs, one per prompt file in phases/, in filename order.

They differ only in their prompt, so they are prompt files rather than four near-identical modules.

Order is editorial — outermost decision first — so no later phase creates work for an earlier one.
Unlike the single judgement call these DO block, which is the trade `high` exists to make: a named
concern with a quoted span is actionable in a way a combined verdict is not, at four times the calls.
"""
import os

from . import ask as _ask

PHASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phases")


class Phase:
    COSTS_A_CALL = True

    def __init__(self, path):
        self.NAME = os.path.basename(path)[:-3].split("-", 1)[-1]
        self._path = path

    def run(self, text, ctx):
        from . import BLOCK, Finding
        ok, why = _ask.ask(self.NAME, _ask.read_prompt(self._path), text, ctx)
        return None if ok else Finding(BLOCK, why)


def phases():
    try:
        names = sorted(f for f in os.listdir(PHASE_DIR) if f.endswith(".md"))
    except OSError:
        return []
    return [Phase(os.path.join(PHASE_DIR, f)) for f in names]
