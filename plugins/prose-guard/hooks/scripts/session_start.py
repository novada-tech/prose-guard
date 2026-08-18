#!/usr/bin/env python3
"""Say, at the start of a session, that this install is checking nothing — while that is still true.

An install where nobody has chosen a level runs no checks, and a tool that runs no checks looks exactly
like a tool with nothing to object to. That is the failure this repository cares about most (CLAUDE.md),
and three things decide whether anybody hears about it.

**When.** At the start of a session, not on the first guarded tool call. A notice that arrives mid-work
lands on whoever happens to be editing, and one that waits for a message never reaches somebody who does
not send one that day.

**On what test.** Whether a level was ever CHOSEN, never whether `config.json` exists. `share_dir.py`
and `audiences.py` both create that file with no `effort` key, so the file is not evidence of a choice.

**How often.** Every session until a level exists. `disabled` is a level, so anybody who wants this
quiet has a one-word way to get it, and the message says so — which is what makes repeating the lesser
failure. A notice that goes quiet by itself leaves an install that is off and looks on.

Nothing here can fail loudly. A SessionStart hook cannot block a session, and this one prints nothing it
is not certain of.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "lib")))

from checks import config  # noqa: E402

# One fact, two readers. The person decides, so they get the sentence with the command in it; the
# model is told the same thing plus what it is expected to do with it, because a person who reads
# "run /prose-guard:setup" usually replies "yes, do that" rather than typing it.
FOR_USER = ("prose-guard is installed but no level is chosen, so it is checking nothing. "
            "Run /prose-guard:setup — a few minutes, and it recommends one. "
            "Choosing `disabled` also stops this notice.")

FOR_MODEL = ("prose-guard is installed but no effort level is chosen, so its checks do not run. If "
             "the user asks about it, or asks why their messages are not being checked, offer to run "
             "the /prose-guard:setup skill. Do not run it unprompted.")


def main() -> None:
    try:
        if config.chosen():
            return
    except Exception:
        return                               # cannot tell, so say nothing
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": FOR_MODEL},
                      # A sibling of hookSpecificOutput, never a field inside it. Nested it is
                      # well-formed JSON that Claude Code discards — see CLAUDE.md, which records
                      # every transparency line this tool ever emitted going out that way.
                      "systemMessage": FOR_USER}))


if __name__ == "__main__":
    main()
