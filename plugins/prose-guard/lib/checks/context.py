"""What a check is told about the reader and the moment. One class, both callers, nothing inferred.

This was an undeclared duck type: the hook set five fields, `check_prose.py` set two, and `terms.py`
read one of them as `getattr(ctx, "previous", "") or ""`. So the rule written for the
commit-scrubbing case — a term the version being replaced already used is not one this text
introduces — was silently inert in the deliberate path and in the rewrite skill, and nothing anywhere
said so. Every field is declared here with the default that means "nothing known", so a caller that
does not set one gets the documented behaviour rather than a disabled rule, and a field added later
reaches both callers or fails loudly in one.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    # A type checker only. `import audiences` at runtime would run its module-level `load()` — every
    # audience file on the machine read — for a class that holds one and looks at none of it.
    from audiences import Resolved


class Context:
    def __init__(self, audience: Resolved, situation: dict[str, Any] | None = None,
                 previous: str = "", mine: set[int] | None = None,
                 resent: set[int] | None = None, subject_line: bool = False) -> None:
        # Whose vocabulary applies, and whether it was measured or guessed.
        self.audience = audience
        # Facts about the moment rather than the reader — a thread reply, an edit, a public repo. Read
        # by the model-backed checks; keys beginning with _ are not shown to them.
        self.situation = dict(situation or {})
        # The version this text replaces, "" where there is none. A term already in it is not one this
        # message introduces, and holding a message back over words somebody else wrote is a demand
        # nobody can satisfy.
        self.previous = previous
        # Which sentences of the text this call actually wrote, or None when all of them are — a new
        # file, a message, a commit. A finding outside them is about text that was already there.
        self.mine = mine
        # Which sentences differ from the draft the guard last held back, or None when it held none.
        #
        # A different question from `mine`, and the difference only shows on a message being sent
        # again after a hold. The writer of a resend wrote every sentence of it and can fix any of
        # them, so this decides nothing about what may hold the message back and nothing about what
        # is somebody else's work — it says only which sentences the writer has already read and
        # chosen to leave, which is what makes a note about one of them not worth repeating. The two
        # coincide on a file edit, where the hunk is both what the call wrote and what it changed.
        self.resent = resent
        # Whether the first line is a subject: a title, on its own line, with the body after it. The
        # destination says so — see `subject_line` in data/destinations.json.
        self.subject_line = subject_line

    def where_an_explanation_fits(self, text: str) -> str:
        """The part of `text` in which a term could be explained where it first appears.

        All of it, unless the first line is a subject. A subject is one line and has no room for a
        gloss, so asking for one there is a demand nobody can satisfy — the same shape as `previous`
        above, and the same answer: take it out of what is scored rather than reporting something the
        writer cannot act on.

        Measured on 3,425 held-out commit messages from four repositories: 95 of 193 terms findings
        were carried by the subject alone. See docs/thresholds.md.

        Only the check that asks for an explanation uses this. `mechanics` reads the whole message,
        because a doubled word in a subject is fixable exactly where it stands.
        """
        return text.partition("\n")[2] if self.subject_line else text
