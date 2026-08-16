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
                 previous: str = "", mine: set[int] | None = None) -> None:
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
