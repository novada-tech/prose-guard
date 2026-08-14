"""One model call over what a term check cannot see: relevance, structure, sentences, reference.

The prompt is prose in judgement_prompt.md so it can be read and edited as prose rather than as a
string literal. It only ever advises: measured against a provenance-based label on real messages it
agrees 50-70% of the time, and unstably — the same condition scored 5/10 then 7/10 on the same ten
texts. Useful as a prompt to look again; not something to gate on.
"""
import os

from . import ask as _ask

NAME = "judgement"
COSTS_A_CALL = True
# Running this repeatedly buys nothing, and that is measured rather than assumed: three runs cost three
# calls and 16 seconds against one call and 4, and found the same single item both times.
#
# The reason is what this check IS. Pooling pays where a check picks one item from many candidates of one
# narrow concern, because two runs then pick differently and the difference is coverage. This is one
# combined verdict over every concern at once, so it has nothing to pick between — repeated runs restate
# the same broad objection. `high` is the level that separates the concerns, and pooling is what makes
# that separation worth its calls.
POOLS = False

PROMPT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "judgement_prompt.md")


def run(text, ctx):
    from . import ADVISE, Finding
    ok, why = _ask.ask(NAME, _ask.read_prompt(PROMPT_FILE), text, ctx)
    return None if ok else Finding(ADVISE, "Consider: " + why)
