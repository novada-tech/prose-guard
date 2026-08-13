"""One check per module. Two callers run them: the outgoing-prose hook, and check_prose.py.

Each check exposes the same four names, so a caller never has to know what a check does:

    NAME          what to call it in output
    CAN_DENY      whether this check is exact enough to hold a message back
    COSTS_A_CALL  whether running it spends a model call
    run(text, envelope) -> (ok, message)

`for_effort(level)` returns the checks that level runs, in order. Order is a design decision, not
a detail: the cheapest and most exact check goes first, so a message with a plainly wrong term
never reaches a model call. The term check leads every level for that reason — it is
deterministic, it names the exact token it objects to, and so it converges.

Adding a check is adding a file here and a line in `for_effort`. Both callers pick it up.
"""
from . import config, judgement, sequence, terms


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
