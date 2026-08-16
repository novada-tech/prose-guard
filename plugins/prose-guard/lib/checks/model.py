"""The one way a model-backed check asks its question, so "the checker never ran" can be said.

`ask.ask` answers `(True, "")` for every failure. That default is right — a writing check that cannot
reach a model must not hold up work — and it is also the same answer as "this prose is fine". Two of
the three ways it happens are visible from here: no prompt file for the check, and no `claude` on
PATH. The third, a timeout or a checker that answers nothing, is inside `ask.ask` and would be
reported from there.

Both callers used to do the read-the-prompt-then-ask pair themselves, which is why neither noticed
that a prompt file it could not read was a pass.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import telling  # noqa: E402

from . import ask as _ask

# The command `ask.py` invokes. Repeated here rather than imported because ask.py builds the name into
# its argument list; one constant there would be the place for it.
BINARY = "claude"


def verdict(name, prompt_path, text, ctx):
    """(ok, why) from the model, and a notice instead of a silent pass where it never got asked."""
    prompt = _ask.read_prompt(prompt_path)
    if not prompt:
        telling.could_not_run(f"the {name} check has no prompt to ask ({prompt_path} could not be "
                              f"read), so it passed everything without looking")
        return True, ""
    if not shutil.which(BINARY):
        telling.could_not_run(f"`{BINARY}` is not on PATH, so no model-backed check ran — at this "
                              f"level that leaves only the deterministic checks")
        return True, ""
    return _ask.ask(name, prompt, text, ctx)
