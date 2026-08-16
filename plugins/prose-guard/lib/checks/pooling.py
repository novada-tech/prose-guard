"""Running a check until its runs stop surfacing anything new, and what one run of it costs.

The two callers keep a budget in model calls, so what a check costs has to be knowable before it runs:
`mode_of` reads the mode a check declares, `costs_a_call` turns that into money, and `ceiling_for` says
how many times the same check may be asked about this text.

Imports `finding` for the modes and `placing` for what makes two findings the same item, and nothing
else — in particular not its own package, so a check can use any of it without the circular import that
put `finding.py` where it is.
"""
from __future__ import annotations

import typing
from typing import TYPE_CHECKING

from .finding import EXACT, MODES, VERDICT
from .placing import identity

if TYPE_CHECKING:
    from .context import Context
    from .finding import Check, Finding


class Pooled(typing.NamedTuple):
    """What `pooled` returns. Named because `findings` and `firm` are the same type and the second is a
    subset of the first, so a caller that took them in the wrong order would block on everything."""

    findings: list[Finding]
    firm: list[Finding]
    runs: int


def mode_of(check: Check) -> str:
    """Which of the three modes this check runs in, or an error naming the check that did not say.

    An error rather than a default. `POOLS` used to be read with `getattr(check, "POOLS", True)`, so
    the cost of a check that never declared it was decided by which default happened to be written
    here — up to `ceiling_for(text)` model calls for a check whose author expected one.
    """
    mode = getattr(check, "MODE", None)
    if mode not in MODES:
        raise ValueError(f"check {getattr(check, 'NAME', check)!r} declares no MODE "
                         f"(one of {', '.join(MODES)})")
    return mode


def costs_a_call(check: Check) -> bool:
    """Whether one run of this check spends a model call. The budget is kept in calls."""
    return mode_of(check) != EXACT


# How many times a check may run, and when to stop. A fixed number was wrong in both directions: it
# stopped a document with ten real defects after the same number of runs as a clean one, and it capped a
# 2,000-word document at the same effort as a 400-word one.
#
# So the count is not fixed. A check keeps running while its runs keep surfacing something new, and stops
# when a run adds nothing — "the well is dry" rather than "N runs are up". A clean check costs one call. A
# document with many defects keeps paying until it stops yielding.
#
# The ceiling is linear in length, because a longer document has more places to be wrong and deserves the
# care. It exists only so that one pathological file cannot spend a session.
WORDS_PER_RUN = 100
# The floor on the CEILING, not on the runs. A 44-word message capped at two runs can never be observed to
# run dry, so length decided everything and quality decided nothing — which was the whole complaint. Six
# gives the stop rule room to work on a short message that keeps yielding findings.
BASE_CEILING = 6
MOST_RUNS = 25           # a bound, not a target: 2,500 words reaches it
DRY_RUNS = 1             # consecutive runs adding nothing that are tolerated before stopping


def ceiling_for(text: str) -> int:
    """The most times a check may run on this text.

    Linear in words above the base, so a 2,000-word document gets more care than a 400-word one. This is a
    ceiling and not a quota: what a check actually spends is decided by whether its runs keep finding
    something, so a clean document costs one call a check whatever its length.
    """
    return max(BASE_CEILING, min(MOST_RUNS, 1 + len(text.split()) // WORDS_PER_RUN))


def pooled(check: Check, text: str, ctx: Context | None, passes: int | None = None,
           dry_runs: int = DRY_RUNS) -> Pooled:
    """Run a check until its runs stop surfacing anything new, and pool what they found.

    One mechanism where there used to be two, because they were the same mechanism. Running a check twice
    to see whether it says the same thing is this with a ceiling of two. The hook and a deliberate run call
    it the same way, so one effort level means one bar however the text is going out.

    Cheap when there is nothing to say: a check that passes on its first run costs one call. Expensive
    exactly where that is warranted — a document that keeps yielding new findings keeps being asked, up to
    a ceiling that grows with its length.

    `runs` is how many calls this cost, because the caller is keeping a budget and one call per check
    stopped being true the moment a check could run twenty times.

    `firm` is the subset more than one run pointed at. An item only one run raised
    is that run sampling from what is above the bar: on a document with real defects that is a different
    real defect, and on a polished one it is a near-tie. Which of those it is cannot be told from the item,
    so the count travels with it and the caller decides.
    """
    mode = mode_of(check)
    # What one run costs, decided before anything runs. This used to be counted after the pass test, so a
    # check that spends no model call was billed one when it passed and none when it fired.
    cost = 0 if mode == EXACT else 1
    first = check.run(text, ctx)
    if first is None:
        return Pooled([], [], cost)
    if mode == EXACT:
        return Pooled([first], [first], 0)            # deterministic: it says the same thing every time
    if mode == VERDICT:
        # One combined verdict has nothing to pick between, so asking again restates it. See
        # checks/judgement.py for the measurement.
        return Pooled([first], [first], 1)
    ceiling = passes or ceiling_for(text)
    seen = {identity(text, first): [1, first]}
    order = list(seen)
    runs, dry = 1, 0
    while runs < ceiling and dry <= dry_runs:
        again = check.run(text, ctx)
        runs += 1
        if again is None:
            dry += 1
            continue
        # By identity, not by place. A finding that quotes nothing findable used to key on the
        # not-found sentinel, so two runs objecting to different things counted as one run repeating
        # itself — and an item more than one run "agreed" on is the one subset that may be blocked on.
        which = identity(text, again)
        if which in seen:
            seen[which][0] += 1
            dry += 1                          # nothing new, however emphatic
            continue
        seen[which] = [1, again]
        order.append(which)
        dry = 0                               # still yielding, so keep going
    findings: list[Finding] = []
    firm: list[Finding] = []
    for which in order:
        times, finding = seen[which]
        marked = finding._replace(message=f"[{times} of {runs} runs] " + finding.message)
        findings.append(marked)
        if times > 1:
            firm.append(marked)
    return Pooled(findings, firm, runs)
