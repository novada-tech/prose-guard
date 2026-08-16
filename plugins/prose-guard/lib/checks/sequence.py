"""The separate concerns `high` runs, one per prompt file in phases/, in filename order.

They differ only in their prompt, so they are prompt files rather than near-identical modules. Adding a
concern is a file, which is why nothing here counts them: the count was written into eight places and
was wrong in all of them once a fifth was added.

Order is editorial — outermost decision first — so no later phase creates work for an earlier one.
Unlike the single judgement call these DO block, which is the trade `high` exists to make: a named
concern with a quoted span is actionable in a way a combined verdict is not, at several times the calls.
"""
from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import telling  # noqa: E402

from . import model
from .finding import ADVISE, BLOCK, POOLED, Finding

if TYPE_CHECKING:
    from .context import Context

# A phase whose filename ends in this advises rather than blocks.
ADVISORY = ".advise"

PHASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phases")


class Phase:
    MODE = POOLED

    def __init__(self, path: str) -> None:
        # `4-reference.md` is the reference check and blocks. `6-promise.advise.md` is the promise
        # check and only advises. The severity is in the filename because a check that has not earned
        # the right to hold a message back should say so where somebody adding one will see it, and
        # because putting it inside the prompt would send it to the model as if it were an instruction.
        stem = os.path.basename(path)[:-3]
        self.advises = stem.endswith(ADVISORY)
        if self.advises:
            stem = stem[:-len(ADVISORY)]
        self.NAME = stem.split("-", 1)[-1]
        self._path = path

    def run(self, text: str, ctx: Context | None) -> Finding | None:
        # A phase BLOCKS by default, and that is the whole difference between one of these and the
        # combined verdict: one named concern with a quoted span can be acted on, so it is worth
        # holding a message for. A phase that has not been measured to that standard advises instead —
        # see CONTRIBUTING.md for the scores a check has to reach before the suffix comes off.
        ok, why = model.verdict(self.NAME, self._path, text, ctx)
        return None if ok else Finding(ADVISE if self.advises else BLOCK, why)


def phases() -> list[Phase]:
    try:
        names = sorted(f for f in os.listdir(PHASE_DIR) if f.endswith(".md"))
    except OSError:
        # An unreadable phases directory turned `high` into `low`, charged nothing and said nothing —
        # the worst shape a failure can take in a tool somebody is trusting to check their writing.
        telling.could_not_run(f"no checks could be read from {PHASE_DIR}, so this level ran "
                              f"only the deterministic checks")
        return []
    if not names:
        telling.could_not_run(f"there are no checks in {PHASE_DIR}, so this level ran only the "
                              f"deterministic checks")
    return [Phase(os.path.join(PHASE_DIR, f)) for f in names]
