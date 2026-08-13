"""One model call over what a term check cannot see: relevance, structure, sentences, reference.

The prompt is in judgement_prompt.md rather than in this file, so it can be read and edited as
prose. It is advisory and never denies: measured against a provenance-based label on real
messages it agrees 50-70% of the time, and the same condition scored 5/10 then 7/10 on the same
ten texts.

This is the omnibus arm. checks/sequence.py is the alternative, one concern at a time.
"""
import os

from . import ask as _ask

NAME = "judgement"
CAN_DENY = False
COSTS_A_CALL = True

PROMPT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "judgement_prompt.md")


def run(text, envelope=None):
    ok, why = _ask.ask(NAME, _ask.read_prompt(PROMPT_FILE), text, envelope)
    return ok, ("" if ok else "Consider: " + why)
