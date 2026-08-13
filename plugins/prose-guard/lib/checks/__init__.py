"""One check per module, and one contract between them and the two callers that run them.

    NAME          what to call it in output
    COSTS_A_CALL  whether running it spends a model call
    run(text, ctx) -> Finding or None

A check returns None when it has nothing to say, and otherwise a Finding carrying its own severity.
Severity belongs to the finding rather than the check, because the same check is sometimes exact
enough to hold a message back and sometimes only guessing — the term check knows the difference and
nothing else can.

    block   the complaint is specific, small and evidenced. Hold the message.
    advise  hand it over and let the message go.

`for_effort(level)` gives the checks that level runs, in order: cheapest and most exact first, so a
message with a plainly wrong term never reaches a model call. A destination may cap its own level:
what the judgement checks ask — does this reader care, is the ask clear — presupposes a reader and an
ask, and a commit message has neither.

    low     terms only. No model call.
    medium  terms, then one advisory call over the remaining concerns.
    high    terms, then four gating checks, one concern each.

Adding a check is a file here and a line in for_effort. Both callers pick it up.
"""
import collections

from . import config, judgement, sequence, terms

Finding = collections.namedtuple("Finding", "severity message")
BLOCK = "block"
ADVISE = "advise"


ORDER = ("disabled", "low", "medium", "high")


def capped(level, ceiling):
    """The lower of what was asked for and what this destination is worth."""
    if not ceiling or ceiling not in ORDER or level not in ORDER:
        return level
    return level if ORDER.index(level) <= ORDER.index(ceiling) else ceiling


def for_effort(level=None):
    level = level or config.effort()
    if level == "low":
        return (terms,)
    if level == "high":
        return (terms,) + tuple(sequence.phases())
    if level == "medium":
        return (terms, judgement)
    return ()


EFFORT = config.effort()
IN_ORDER = for_effort(EFFORT)
