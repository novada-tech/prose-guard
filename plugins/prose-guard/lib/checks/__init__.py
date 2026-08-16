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
"""
import re

from . import config, judgement, mechanics, notice, sequence, terms
from .context import Context
from .finding import ADVISE, BLOCK, EXACT, MODES, POOLED, VERDICT, Finding

__all__ = ["ADVISE", "BLOCK", "EXACT", "POOLED", "VERDICT", "Context", "Finding", "capped",
           "ceiling_for", "costs_a_call", "for_effort", "mode_of", "notice", "pooled",
           "written_here", "wrote_which"]

ORDER = ("disabled", "low", "medium", "high")


def mode_of(check):
    """Which of the three modes this check runs in, or an error naming the check that did not say.

    An error rather than a default. `POOLS` used to be read with `getattr(check, "POOLS", True)`, so
    the cost of a check that never declared it was decided by which default happened to be written
    here — up to `ceiling_for(text)` model calls for a check whose author expected one.
    """
    mode = getattr(check, "MODE", None)
    if mode is None and getattr(check, "COSTS_A_CALL", None) is False:
        # terms.py and mechanics.py still declare the older boolean, and both are EXACT. Translated
        # rather than defaulted: a check that declares neither attribute is a mistake, not an EXACT
        # check, and these two lines go when those files name their mode.
        mode = EXACT
    if mode not in MODES:
        raise ValueError(f"check {getattr(check, 'NAME', check)!r} declares no MODE "
                         f"(one of {', '.join(MODES)})")
    return mode


def costs_a_call(check):
    """Whether one run of this check spends a model call. The budget is kept in calls."""
    return mode_of(check) != EXACT


def capped(level, ceiling):
    """The lower of what was asked for and what this destination is worth."""
    if not ceiling or ceiling not in ORDER or level not in ORDER:
        return level
    return level if ORDER.index(level) <= ORDER.index(ceiling) else ceiling


SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# The shortest quoted span that can place a finding. `"a a"` is the shortest thing mechanics quotes, so
# a floor above three characters makes some of its findings unplaceable. The floor exists so that a
# quotation is specific enough to name one sentence rather than any sentence; a short span is held to
# word boundaries below, which is what keeps it specific.
SHORTEST_SPAN = 3
# Every style a check quotes in. Straight double quotes were the whole of it, and twelve characters the
# floor, so `'…'`, a backtick, a curly quote and everything mechanics quotes placed nothing at all.
_QUOTE_PAIRS = ('""', "''", "``", "“”", "‘’")
QUOTED = re.compile("|".join(
    f"{re.escape(open_)}([^{re.escape(close)}]{{{SHORTEST_SPAN},}}){re.escape(close)}"
    for open_, close in _QUOTE_PAIRS))
LONGEST_NEEDLE = 40


def _spans(finding):
    """Every span the finding quotes, in the order it quotes them."""
    out = []
    for match in QUOTED.finditer(finding.message):
        span = " ".join(next(g for g in match.groups() if g is not None).split())
        if len(span) > LONGEST_NEEDLE:
            # Never half a word: the match below is anchored to word boundaries, so a needle cut
            # mid-word would match nothing at all.
            span = span[:LONGEST_NEEDLE].rsplit(" ", 1)[0]
        out.append(span)
    return out


def _hits(text, finding):
    """Which sentences of the text this finding quotes, in the order it quotes them.

    Word-anchored, because the floor on a span is three characters: `"a a"` inside `a another` is not
    the sentence the finding is about.
    """
    sentences = SENTENCE_END.split(" ".join(text.split()))
    out = []
    for span in _spans(finding):
        for n, sentence in enumerate(sentences):
            if re.search(r"(?<!\w)" + re.escape(span) + r"(?!\w)", sentence):
                out.append(n)
                break
    return out


def _points_at(text, finding):
    """Which sentence of the text a finding is about, or None when it quotes nothing that is in it.

    Findings are compared by where they point rather than by how they are worded: two runs objecting to the
    same sentence in different words are one item, and two runs objecting to different sentences are two,
    however similar the wording.
    """
    hits = _hits(text, finding)
    return hits[0] if hits else None


def _identity(text, finding):
    """What makes two findings the same item: where it points, or failing that its own words.

    This used to be the sentence number or `-1`, and `-1` was used as a dict key. So every finding that
    quoted nothing findable collided on one key: two runs objecting to different things counted as one
    run repeating itself, the second one's text was thrown away, and the item was promoted into `firm`
    — the one subset the hook may block on. Three runs that agreed on nothing reported 3-of-3
    agreement. Unplaceable findings now get an identity of their own, so they can confirm themselves
    and nothing else.
    """
    spot = _points_at(text, finding)
    if spot is not None:
        return spot
    return "said: " + " ".join(finding.message.lower().split())


def written_here(text, finding, mine):
    """Whether this finding is about text this call wrote. `mine` is None when all of it is.

    Fails closed. An unplaceable finding used to count as somebody else's, which is what turned every
    `terms` and `mechanics` finding on an edit into advice labelled "(already in the file)" — and
    `terms` has already subtracted every term the version on disk contained, so what it reports is by
    construction what this edit introduced.

    One quoted span landing inside `mine` is enough: a mechanics finding lists up to four typos, and one
    of them being older than the edit does not make the edit's own typo somebody else's.
    """
    if mine is None:
        return True
    hits = _hits(text, finding)
    return not hits or any(n in mine for n in hits)


def wrote_which(text, fragment):
    """Sentence numbers of `text` that `fragment` covers, or None when the whole text is new.

    An edit into the middle of a document must be judged in the document — a list's purpose is stated in
    its first paragraph, and a hunk cannot see that. But a complaint about a sentence the edit never
    touched is not this edit's fault, so the caller needs to know which sentences it wrote.
    """
    if not fragment:
        return None
    whole = " ".join(text.split())
    piece = " ".join(fragment.split())
    at = whole.find(piece)
    if at < 0:
        return None
    ends, mine, spent = SENTENCE_END.split(whole), set(), 0
    for n, sentence in enumerate(ends):
        start, stop = spent, spent + len(sentence)
        if start < at + len(piece) and stop > at:
            mine.add(n)
        spent = stop + 1
    return mine or None


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


def ceiling_for(text):
    """The most times a check may run on this text.

    Linear in words above the base, so a 2,000-word document gets more care than a 400-word one. This is a
    ceiling and not a quota: what a check actually spends is decided by whether its runs keep finding
    something, so a clean document costs one call a check whatever its length.
    """
    return max(BASE_CEILING, min(MOST_RUNS, 1 + len(text.split()) // WORDS_PER_RUN))


def passes_for(text):
    """Kept as the name the measurement harnesses use. The ceiling, not a fixed number of runs."""
    return ceiling_for(text)


def pooled(check, text, ctx, passes=None, dry_runs=DRY_RUNS):
    """Run a check until its runs stop surfacing anything new, and pool what they found.

    One mechanism where there used to be two, because they were the same mechanism. Running a check twice
    to see whether it says the same thing is this with a ceiling of two. The hook and a deliberate run call
    it the same way, so one effort level means one bar however the text is going out.

    Cheap when there is nothing to say: a check that passes on its first run costs one call. Expensive
    exactly where that is warranted — a document that keeps yielding new findings keeps being asked, up to
    a ceiling that grows with its length.

    Returns (findings, firm, runs). `runs` is how many calls this cost, because the caller is keeping a
    budget and one call per check stopped being true the moment a check could run twenty times.

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
        return [], [], cost
    if mode == EXACT:
        return [first], [first], 0            # deterministic: it says the same thing every time
    if mode == VERDICT:
        # One combined verdict has nothing to pick between, so asking again restates it. See
        # checks/judgement.py for the measurement.
        return [first], [first], 1
    ceiling = passes or ceiling_for(text)
    seen = {_identity(text, first): [1, first]}
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
        which = _identity(text, again)
        if which in seen:
            seen[which][0] += 1
            dry += 1                          # nothing new, however emphatic
            continue
        seen[which] = [1, again]
        order.append(which)
        dry = 0                               # still yielding, so keep going
    findings, firm = [], []
    for which in order:
        times, finding = seen[which]
        marked = finding._replace(message=f"[{times} of {runs} runs] " + finding.message)
        findings.append(marked)
        if times > 1:
            firm.append(marked)
    return findings, firm, runs


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
