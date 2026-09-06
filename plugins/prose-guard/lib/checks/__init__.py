"""One check per module, and one contract between them and the two callers that run them.

    NAME           what to call it in output
    MODE           exact, verdict or pooled — see checks/finding.py, which is where they are defined
    run(text, ctx) -> Finding or None

A check returns None when it has nothing to say, and otherwise a Finding carrying its own severity.
`ctx` is a checks.Context and carries everything a check is allowed to know about the reader and the
moment; the Finding type and the two severities are in checks/finding.py, which imports nothing.

`for_effort(level)` gives the checks that level runs, in order: cheapest and most exact first, so a
message with a plainly wrong term never reaches a model call. A destination may cap its own level:
what the judgement checks ask — does this reader care, is the ask clear — presupposes a reader and an
ask, and a commit message has neither. So may the text itself: `worth_paying_for` returns the level a
message too short to be worth a model call is capped to, which is `free_level()`.

    low     terms and mechanics only. No model call.
    medium  those, then one advisory call over the remaining concerns.
    high    those, then one gating check per prompt file in phases/.

Adding a check is a file here and a line in for_effort. Both callers pick it up.

Assembling that ladder is all this file does, and that is deliberate rather than tidy: importing the
package imports every check, so anything defined here is out of reach of a check that would import it
back. `finding.py` exists because that circle was real. Everything the ladder is built from lives one
module down and is re-exported below, so a caller writes `from checks import pooled` and a check
writes `from .pooling import pooled`, and both get the same function.

    finding.py    what a check returns, the three modes it can run in, and `Check` — the three
                  lines above, stated as a type so a caller can name what it is being passed
    context.py    what a check is told about the reader and the moment
    placing.py    where in the text a finding points, whether this call wrote it, what a resend of
                  it changed, and the text of the sentences it did
    pooling.py    what one run costs, and running a check until it stops yielding
    config.py     how much checking was asked for, and comparing two levels
    model.py      the one way a model-backed check asks its question
    ask.py        the model call itself, and the two clocks bounding it
    sequence.py   the separate concerns `high` runs, one per prompt file
"""
from __future__ import annotations

from . import config, judgement, mechanics, sequence, terms
from .ask import stop_asking_after
from .config import capped
from .context import Context
from .finding import ADVISE, BLOCK, EXACT, POOLED, VERDICT, Check, Finding
from .placing import just_these, what_changed, written_here, wrote_which
from .pooling import ceiling_for, costs_a_call, mode_of, pooled

__all__ = ["ADVISE", "BLOCK", "EXACT", "POOLED", "VERDICT", "Check", "Context", "Finding", "capped",
           "ceiling_for", "costs_a_call", "for_effort", "free_level", "just_these", "mode_of",
           "pooled", "stop_asking_after", "what_changed", "worth_paying_for", "written_here",
           "wrote_which"]


# Each level is the one below it plus what it adds, so a level cannot lose a check the level below it
# runs. Written out three times before, and a sixth deterministic check added to `low` did not reach
# `high` — the containment was a thing to remember rather than a thing the code did.
# `terms` and `mechanics` cost nothing and are exact, so they run at every level that runs anything.
def _ladder(level: str) -> tuple[Check, ...]:
    low = (terms, mechanics)
    return {"low": low, "medium": low + (judgement,),
            "high": low + tuple(sequence.phases())}.get(level, ())


def for_effort(level: str | None = None) -> tuple[Check, ...]:
    return _ladder(level or config.effort())


# Below this many words, a model call is not worth making. It is a floor on SPENDING and not on
# checking: `terms` and `mechanics` cost nothing, and they are what a short message needs. The number
# and what it was measured against are in docs/thresholds.md.
MIN_WORDS_FOR_A_CALL = 25


def free_level() -> str:
    """The most that can be run without spending a model call.

    Derived from the modes the checks declare rather than named, so a paying check added to a level
    moves this instead of quietly making a short message expensive.
    """
    return [lvl for lvl in config.LEVELS if not any(costs_a_call(c) for c in _ladder(lvl))][-1]


def worth_paying_for(text: str) -> str | None:
    """A ceiling this text puts on the effort, or None when its length puts none.

    A ceiling rather than a filter, so that everything downstream — the line the person sees, the
    envelope a held draft is recorded with — says the level that actually ran. `capped` is what
    applies it, the same function a destination's own `max_effort` goes through.
    """
    return None if len(text.split()) >= MIN_WORDS_FOR_A_CALL else free_level()


EFFORT = config.effort()
IN_ORDER = for_effort(EFFORT)
