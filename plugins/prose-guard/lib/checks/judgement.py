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

PROMPT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "judgement_prompt.md")


def run(text, ctx):
    from . import ADVISE, Finding
    ok, why = _ask.ask(NAME, _ask.read_prompt(PROMPT_FILE), text, ctx)
    return None if ok else Finding(ADVISE, "Consider: " + why)
