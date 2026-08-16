"""Terms this reader cannot be assumed to know. Deterministic, instant, no model call.

Severity is decided per message, from two things the check knows and the caller does not.

**Is the audience known?** If no audience matched the destination, the tool is working from a
baseline rather than from evidence about these readers, so a finding is a guess: it says so and does
not block. Enforcement follows the evidence, which is the only way the zero-setup case is usable —
blocking on a guess spends someone's first day arguing about their own house words.

**Is the complaint small enough to act on?** Not a word count: the signal is what SHARE of the
terms the reader met are unknown. Three unknown out of twenty in a long document is a fixable
oversight. Fifteen out of twenty is the tool having the wrong reader in mind, and insisting then is
worse than saying so. A check that demands wholesale rewriting is usually wrong about the situation.
"""
from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jargon  # noqa: E402

from . import finding  # noqa: E402

if TYPE_CHECKING:
    from .context import Context

NAME = "terms"
MODE = finding.EXACT

# Above this share of the terms the reader met, the finding is reported rather than enforced.
# 1/3 is the 90th percentile of the share seen when a message IS scored against the audience it was
# written for, measured on two real audiences in both directions. Above it, "the audience is wrong"
# explains the finding better than "the message is wrong". See docs/thresholds.md.
MAX_SHARE_TO_BLOCK = 1 / 3
# ...except when there are very few terms in play, where a share is meaningless: one unknown term
# out of one is 100% and still perfectly actionable.
ALWAYS_ACTIONABLE = 2


def _ambiguous(said: dict[str, str], considered: list[str], ctx: Context) -> str:
    """Terms this audience has written out two different ways, or written out differently here.

    An abbreviation is not one term. LF is the Linux Foundation in one corpus and a line feed in another,
    and a count of authors cannot tell those apart — which is why the scan keeps what each term was
    written out as. Two recorded meanings is the audience telling you the abbreviation is overloaded for
    them, and the reader has no way to pick.

    Deterministic and narrow on purpose. Which sense a message means, where it never says, is not
    decidable here and is not guessed at.

    `said` is what the scan already worked out each term was written out as here. Recomputing it cost a
    second pass over the whole document, which cProfile put at 0.180s of a 0.186s term check.
    """
    meanings = getattr(ctx.audience, "meanings", None)
    if meanings is None:
        return ""
    notes = []
    for term in considered:
        known = meanings(term)
        if term in said:
            # The message says which sense it means, so there is nothing for a reader to work out —
            # whether or not the audience uses the abbreviation for other things as well.
            here = " ".join(said[term].split())
            only = min(known, key=lambda k: 0) if len(known) == 1 else None
            if only and here.lower() != only.lower() and here.lower() not in only.lower():
                notes.append(f'{term} is written out here as "{here}", and this audience has it as '
                             f'"{only}". If both are meant, they are two terms')
            continue
        if len(known) > 1:
            spelt = ", ".join(f"{long} ({n})" for long, n in sorted(known.items(),
                                                                    key=lambda kv: -kv[1]))
            notes.append(f"{term} is used here for more than one thing — {spelt} — so say which")
    return ". ".join(notes[:3])


def run(text: str, ctx: Context) -> finding.Finding | None:
    from . import ADVISE, BLOCK, Finding
    bad, considered, said = jargon.examine(text, ctx.audience.is_known)
    # Terms the previous version already used are not terms this text introduces. Rewriting a
    # published commit message to remove a client's name should not require also explaining the
    # original author's shorthand, and demanding it produces a block nobody can clear.
    before = ctx.previous
    if before and bad:
        inherited = [t for t in bad if jargon.uses(before, t)]
        bad = [t for t in bad if t not in inherited]
    if not bad:
        # A check reports one thing, and an overloaded abbreviation is the thing to report only when
        # there is nothing more actionable. Where a term was never explained at all, that is the fix to
        # ask for: it is concrete, it is what holds the message back, and adding "and by the way ADC
        # means two things to these readers" next to it competes with it for the one edit the reader
        # will make. So the note is worked out here, where it is used, rather than worked out for every
        # message and thrown away for most of them.
        ambiguous = _ambiguous(said, considered, ctx)
        return Finding(ADVISE, ambiguous) if ambiguous else None
    fix = ("Explain each where it first appears, by anchoring it to something this reader already "
           "works with")
    listed = ", ".join(bad)
    if not ctx.audience.resolved:
        return Finding(ADVISE, (
            f"Possibly unexplained for this reader: {listed}. {fix}. This is a guess — no audience "
            f"is configured for this destination, so nothing has been measured about who reads it. "
            f"Run /prose-guard:audiences to fix that, or accept the term with "
            f"/prose-guard:audiences accept {bad[0]}"))
    share = len(bad) / max(len(considered), 1)
    if len(bad) > ALWAYS_ACTIONABLE and share > MAX_SHARE_TO_BLOCK:
        return Finding(ADVISE, (
            f"{len(bad)} of the {len(considered)} terms here look unknown to "
            f"{', '.join(ctx.audience.names)}: {listed}. That is most of them, which usually means "
            f"the audience is wrong rather than the message — check who actually reads this before "
            f"explaining all of them"))
    return Finding(BLOCK, f"Terms used without explanation for "
                          f"{', '.join(ctx.audience.names)}: {listed}. {fix}")
