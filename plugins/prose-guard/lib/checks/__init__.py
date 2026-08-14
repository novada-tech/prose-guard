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

# How many times to run a check, from the length of what it is judging. A check returns exactly one item
# however it is asked — measured on a 295-word document with about ten known defects, asking for up to
# five produced one a run — so coverage comes from runs. One item for a 100-word message and one for a
# 1,000-word document holds the long one to a lower bar, and nobody should have to pass a flag to fix
# that. Costing more for a longer document is the right trade.
WORDS_PER_PASS = 100
MOST_PASSES = 5
# Never fewer than two, because one run cannot tell a reliable finding from a near-tie.
FEWEST_PASSES = 2


def passes_for(text):
    """The same answer for the hook and for a deliberate run, so both apply one bar."""
    return max(FEWEST_PASSES, min(MOST_PASSES, 1 + len(text.split()) // WORDS_PER_PASS))


def _points_at(text, finding):
    """Which sentence of the text a finding is about, by the span it quotes.

    Findings are compared by where they point rather than by how they are worded: two runs objecting to
    the same sentence in different words agree, and two runs objecting to different sentences do not,
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


def pooled(check, text, ctx, passes=None):
    """Run a check enough times for the length of the text, and pool what the runs find.

    One mechanism where there used to be two, because they were the same mechanism. Running a check
    twice to see whether it says the same thing is pooling with two runs; running it four times on a long
    document is pooling with four. The hook and a deliberate run now apply one bar: the same number of
    passes for the same text, and the same rule for what counts.

    Cheap when there is nothing to say. A check that passes on its first run costs one call — only a check
    that found something is asked again, which is where the extra calls earn their place.

    Returns (findings, firm) where findings is one entry per distinct sentence complained about, and firm
    is the subset that more than one run pointed at. An item only one run raised is that run sampling from
    what is above the bar: on a document with real defects that is a different real defect, and on a
    polished one it is a near-tie. Which of those it is cannot be told from the item, so the count is
    reported and the caller decides.
    """
    first = check.run(text, ctx)
    if first is None:
        return [], []
    if not check.COSTS_A_CALL:
        return [first], [first]               # deterministic: it says the same thing every time
    passes = passes or passes_for(text)
    seen = {_points_at(text, first): [1, first]}
    order = [_points_at(text, first)]
    for _ in range(max(0, passes - 1)):
        again = check.run(text, ctx)
        if again is None:
            continue
        spot = _points_at(text, again)
        if spot in seen:
            seen[spot][0] += 1
            continue
        seen[spot] = [1, again]
        order.append(spot)
    findings, firm = [], []
    for spot in order:
        times, finding = seen[spot]
        marked = finding._replace(message=f"[{times} of {passes} runs] " + finding.message)
        findings.append(marked)
        if times > 1:
            firm.append(marked)
    return findings, firm


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
