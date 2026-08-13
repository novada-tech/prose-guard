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


def confirms(check, text, ctx, finding):
    """Whether running the same check again objects to the same sentence.

    Measured on one 370-word document already through six rounds of editing: ten runs of the five
    model-based checks produced one clean result and nine findings, and no finding was raised twice.
    `reference` objected on every run and to a different sentence almost every time. A check that
    cannot reproduce its own complaint is generating nits, and acting on them is unbounded work — this
    is what stops that, at the cost of one extra call for a check that fired.
    """
    if not check.COSTS_A_CALL:
        return True                           # deterministic: it will say the same thing every time
    try:
        again = check.run(text, ctx)
    except Exception:
        return False
    if again is None:
        return False
    where = _points_at(text, finding)
    return where >= 0 and where == _points_at(text, again)


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
