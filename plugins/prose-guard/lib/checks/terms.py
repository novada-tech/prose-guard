"""Terms the reader cannot be assumed to know. Deterministic, instant, no model call.

It defers to lib/jargon.py, which is the same code the `jargon.py` command and check_prose.py use.
One implementation, three callers.

CAN_DENY is decided at import time by whether a measured vocabulary exists. Without one the tool
knows what developers in general know and nothing about the people you write to, so a finding is a
guess and it says so instead of blocking. See lib/vocabulary.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NAME = "terms"
COSTS_A_CALL = False

try:
    import jargon
    import vocabulary
    CAN_DENY = vocabulary.HAVE_MEASURED
except Exception:                             # nothing to say if the data is missing
    jargon = None
    vocabulary = None
    CAN_DENY = False


def run(text, envelope=None):
    if jargon is None:
        return True, ""
    bad, _ = jargon.unexplained(text)
    if not bad:
        return True, ""
    fix = ("Explain each where it first appears, by anchoring it to something this reader already "
           "works with")
    if CAN_DENY:
        return False, "Terms used without explanation: " + ", ".join(bad) + ". " + fix
    return False, (
        "Possibly unexplained for this reader: " + ", ".join(bad) + ". " + fix +
        ". This is a guess — nothing has been measured about your audience's vocabulary yet, so "
        "if these are house words, run /prose-guard:learn-vocabulary or add them to "
        + os.path.join(vocabulary.config_dir() if vocabulary else "", "known-terms.txt"))
