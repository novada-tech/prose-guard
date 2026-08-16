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
ask, and a commit message has neither.

    low     terms and mechanics only. No model call.
    medium  those, then one advisory call over the remaining concerns.
    high    those, then one gating check per prompt file in phases/.

Adding a check is a file here and a line in for_effort. Both callers pick it up.

Assembling that ladder is all this file does, and that is deliberate rather than tidy: importing the
package imports every check, so anything defined here is out of reach of a check that would import it
back. `finding.py` exists because that circle was real. Everything the ladder is built from lives one
module down and is re-exported below, so a caller writes `from checks import pooled` and a check
writes `from .pooling import pooled`, and both get the same function.

    finding.py    what a check returns, and the three modes it can run in
    context.py    what a check is told about the reader and the moment
    placing.py    where in the text a finding points, and whether this call wrote it
    pooling.py    what one run costs, and running a check until it stops yielding
    config.py     how much checking was asked for, and comparing two levels
    model.py      the one way a model-backed check asks its question
    sequence.py   the separate concerns `high` runs, one per prompt file
"""
from . import config, judgement, mechanics, sequence, terms
from .config import capped
from .context import Context
from .finding import ADVISE, BLOCK, EXACT, POOLED, VERDICT, Finding
from .placing import written_here, wrote_which
from .pooling import ceiling_for, costs_a_call, mode_of, pooled

__all__ = ["ADVISE", "BLOCK", "EXACT", "POOLED", "VERDICT", "Context", "Finding", "capped",
           "ceiling_for", "costs_a_call", "for_effort", "mode_of", "pooled", "written_here",
           "wrote_which"]


# Each level is the one below it plus what it adds, so a level cannot lose a check the level below it
# runs. Written out three times before, and a sixth deterministic check added to `low` did not reach
# `high` — the containment was a thing to remember rather than a thing the code did.
# `terms` and `mechanics` cost nothing and are exact, so they run at every level that runs anything.
def _ladder(level):
    low = (terms, mechanics)
    return {"low": low, "medium": low + (judgement,),
            "high": low + tuple(sequence.phases())}.get(level, ())


def for_effort(level=None):
    return _ladder(level or config.effort())


EFFORT = config.effort()
IN_ORDER = for_effort(EFFORT)
