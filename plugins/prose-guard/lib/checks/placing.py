"""Where in the text a finding points. A leaf module: it imports nothing, not even its own package.

Findings are compared by where they point rather than by how they are worded, and that one decision is
what everything here serves: two runs objecting to the same sentence in different words are one item,
two runs objecting to different sentences are two, however similar the wording. `pooling.py` counts
items that way, and the hook asks the same question to tell a complaint about this edit from a
complaint about the paragraph around it.

A leaf for the reason `finding.py` is one: the package imports every check at module level, so anything
that lives in `__init__.py` is unreachable from a check without a circular import. Nothing here needs
the package, so nothing here has to be reached round the houses.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Under the guard, so the leaf stays a leaf: `from .finding import Finding` at runtime would
    # initialise the package, and the package imports every check. Only a type checker reads this.
    from .finding import Finding

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


def spans(finding: Finding) -> list[str]:
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


def hits(text: str, finding: Finding) -> list[int]:
    """Which sentences of the text this finding quotes, in the order it quotes them.

    Word-anchored, because the floor on a span is three characters: `"a a"` inside `a another` is not
    the sentence the finding is about.
    """
    sentences = SENTENCE_END.split(" ".join(text.split()))
    out = []
    for span in spans(finding):
        for n, sentence in enumerate(sentences):
            if re.search(r"(?<!\w)" + re.escape(span) + r"(?!\w)", sentence):
                out.append(n)
                break
    return out


def points_at(text: str, finding: Finding) -> int | None:
    """Which sentence of the text a finding is about, or None when it quotes nothing that is in it."""
    found = hits(text, finding)
    return found[0] if found else None


def identity(text: str, finding: Finding) -> int | str:
    """What makes two findings the same item: where it points, or failing that its own words.

    This used to be the sentence number or `-1`, and `-1` was used as a dict key. So every finding that
    quoted nothing findable collided on one key: two runs objecting to different things counted as one
    run repeating itself, the second one's text was thrown away, and the item was promoted into `firm`
    — the one subset the hook may block on. Three runs that agreed on nothing reported 3-of-3
    agreement. Unplaceable findings now get an identity of their own, so they can confirm themselves
    and nothing else.
    """
    spot = points_at(text, finding)
    if spot is not None:
        return spot
    return "said: " + " ".join(finding.message.lower().split())


def written_here(text: str, finding: Finding, mine: set[int] | None) -> bool:
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
    found = hits(text, finding)
    return not found or any(n in mine for n in found)


def wrote_which(text: str, fragment: str) -> set[int] | None:
    """Sentence numbers of `text` that `fragment` covers, or None when the whole text is new.

    An edit into the middle of a document must be judged in the document — a list's purpose is stated in
    its first paragraph, and a hunk cannot see that. But a complaint about a sentence the edit never
    touched is not this edit's fault, so the caller needs to know which sentences it wrote.

    The same shape answers "which sentences did this send change", from the fragment `what_changed`
    returns. Two questions, one arithmetic: a hunk is both what an edit wrote and what it changed.
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


def what_changed(before: str, after: str) -> str:
    """The one span of `after` that `before` does not already carry, "" when there is nothing to narrow.

    A common prefix and a common suffix, so two changes at opposite ends of a message give ONE span
    covering both and everything between them. That is wider than the truth and never narrower, which
    is the only direction available here: a span that missed a change would hide a finding about it.

    Empty when `before` is empty — a first send has nothing to compare against — and when the two are
    the same, so the caller scopes nothing rather than scoping to a guess. `wrote_which` turns this
    into sentence numbers and returns None when it cannot find the span at all, which fails the same
    way.

    Word-aligned at both ends. `wrote_which` locates the span by searching for it, so a fragment
    starting mid-word matches wherever those letters next appear, which can be a sentence away from
    the change.
    """
    if not before or before == after:
        return ""
    limit = min(len(before), len(after))
    head = 0
    while head < limit and before[head] == after[head]:
        head += 1
    tail = 0
    while tail < limit - head and before[-1 - tail] == after[-1 - tail]:
        tail += 1
    start = after.rfind(" ", 0, head) + 1
    space = after.find(" ", len(after) - tail)
    return after[start:space if space >= 0 else len(after)]
def just_these(text: str, which: set[int] | None) -> str:
    """The sentences of `text` that `which` names, or the whole of it when `which` is None.

    The other direction from `wrote_which`, and here because it is the same sentence numbering: a
    caller that has been told which sentences a call wrote is the caller that then has to price them.
    None means the whole text, exactly as it does everywhere else `mine` is read, so a message and a
    whole-file write come back unchanged.

    Sentences the call did not write are dropped rather than blanked, so what comes back is shorter
    than the document by however much of it was already there. That is the whole point: it is a
    length, for pricing, and never the text a check is asked to read — the checks read the document,
    because a smaller window lowers a comparative check's bar instead of sharpening it.
    """
    whole = " ".join(text.split())
    if which is None:
        return whole
    return " ".join(s for n, s in enumerate(SENTENCE_END.split(whole)) if n in which)
