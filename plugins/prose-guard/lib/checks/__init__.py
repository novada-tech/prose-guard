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

    low     terms and mechanics only. No model call.
    medium  those, then one advisory call over the remaining concerns.
    high    those, then four gating checks, one concern each.

Adding a check is a file here and a line in for_effort. Both callers pick it up.
"""
import collections
import re

from . import config, judgement, mechanics, sequence, terms

Finding = collections.namedtuple("Finding", "severity message")
BLOCK = "block"
ADVISE = "advise"


ORDER = ("disabled", "low", "medium", "high")


def capped(level, ceiling):
    """The lower of what was asked for and what this destination is worth."""
    if not ceiling or ceiling not in ORDER or level not in ORDER:
        return level
    return level if ORDER.index(level) <= ORDER.index(ceiling) else ceiling


SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

def _points_at(text, finding):
    """Which sentence of the text a finding is about, by the span it quotes.

    Findings are compared by where they point rather than by how they are worded: two runs objecting to the
    same sentence in different words are one item, and two runs objecting to different sentences are two,
    however similar the wording.
    """
    quoted = re.findall(r'"([^"]{12,})"', finding.message)
    sentences = SENTENCE_END.split(" ".join(text.split()))
    for span in quoted:
        needle = " ".join(span.split())[:40]
        for n, sentence in enumerate(sentences):
            if needle and needle in sentence:
                return n
    return -1                                 # nothing quoted, or quoted nothing in the text


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
    first = check.run(text, ctx)
    if first is None:
        return [], [], 1
    if not check.COSTS_A_CALL:
        return [first], [first], 0            # deterministic: it says the same thing every time
    if not getattr(check, "POOLS", True):
        # A check that returns one combined verdict has nothing to pick between, so asking again restates
        # it. See checks/judgement.py for the measurement.
        return [first], [first], 1
    ceiling = passes or ceiling_for(text)
    seen = {_points_at(text, first): [1, first]}
    order = [_points_at(text, first)]
    runs, dry = 1, 0
    while runs < ceiling and dry <= dry_runs:
        again = check.run(text, ctx)
        runs += 1
        if again is None:
            dry += 1
            continue
        spot = _points_at(text, again)
        if spot in seen:
            seen[spot][0] += 1
            dry += 1                          # nothing new, however emphatic
            continue
        seen[spot] = [1, again]
        order.append(spot)
        dry = 0                               # still yielding, so keep going
    findings, firm = [], []
    for spot in order:
        times, finding = seen[spot]
        marked = finding._replace(message=f"[{times} of {runs} runs] " + finding.message)
        findings.append(marked)
        if times > 1:
            firm.append(marked)
    return findings, firm, runs


def for_effort(level=None):
    level = level or config.effort()
    # mechanics costs nothing and is exact, so it runs at every level that runs anything.
    if level == "low":
        return (terms, mechanics)
    if level == "high":
        return (terms, mechanics) + tuple(sequence.phases())
    if level == "medium":
        return (terms, mechanics, judgement)
    return ()


EFFORT = config.effort()
IN_ORDER = for_effort(EFFORT)
