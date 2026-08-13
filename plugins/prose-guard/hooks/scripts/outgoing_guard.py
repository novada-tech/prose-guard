#!/usr/bin/env python3
"""PreToolUse orchestrator: check prose on its way OUT, not on every turn.

This file decides three things and delegates the rest. Whether text is leaving and what carries it
(lib/destinations.py), what the checks are told about the reader (the same), and what to do with a
complaint. The checks live one per file in lib/checks/, in the order lib/checks/for_effort gives.
lib/check_prose.py runs the same list on demand, so a check added there is a check the hook runs.

Placement is a cost decision, measured rather than guessed. The checks fire only when text is
actually leaving - a chat message, a review comment, a documentation page, a document written to
disk - and even then they are not free: see lib/checks/config.py for what each level costs.
Running them after every assistant turn instead multiplied that by every turn in the session.

It denies rather than rewrites. The agent does the editing, which keeps the deterministic part
honest (it names the exact terms) and leaves judgement with the model.

Every failure path allows the call. A broken writing check must never block outbound work.
"""
import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "lib")))

import destinations  # noqa: E402
from checks import IN_ORDER as CHECKS  # noqa: E402

MAX_PER_CHECK = 2      # one complaint, then one more if the fix did not land
MAX_DENIALS = 6        # a ceiling across all of them, so one message cannot eat a session
MAX_CALLS = 12         # and a ceiling on calls, since a re-verified check can be asked again


def state_dir():
    """Per-session bookkeeping. Never inside a checkout: an earlier version of this fell back to
    the plugin directory and put one machine's denial count under version control."""
    return os.path.join(
        os.environ.get("PROSE_GUARD_STATE")
        or os.environ.get("CLAUDE_PLUGIN_DATA")
        or os.path.join(os.path.expanduser("~"), ".cache", "prose-guard"),
        "sessions")


def allow():
    sys.exit(0)


def load_state(session):
    path = os.path.join(state_dir(), session + ".json")
    # passed and denials describe the message being argued about and reset once it goes out.
    # total_denials is the session ledger and never resets, so the guard cannot keep blocking for a
    # whole session however many fresh drafts arrive.
    state = {"passed": {}, "denials": {}, "total_denials": 0, "calls": 0, "judged": []}
    try:
        with open(path) as fh:
            state.update(json.load(fh))
    except Exception:
        pass
    return path, state


def save_state(path, state):
    try:
        os.makedirs(state_dir(), exist_ok=True)
        state["judged"] = state["judged"][-50:]
        with open(path, "w") as fh:
            json.dump(state, fh)
    except OSError:
        pass


def satisfied(state, check, digest):
    """Has this check already approved the text in front of us?

    Approval belongs to the exact text that earned it, so an edit made for a later check puts the
    earlier ones back in play. That re-ask is the only thing that can catch "make this sentence
    simpler" dropping a fact the reader needed. A message nobody objected to is still walked once,
    because nothing changed under it.

    It stays bounded - by the per-check budget, the session ledger and the call ceiling - so two
    checks that genuinely disagree make the message expensive and then let it go, rather than
    hanging the turn. That is what an earlier parallel design did: 0 of 5 sessions produced any
    message at all.
    """
    return state["passed"].get(check.NAME) == digest


def main():
    if not CHECKS:
        allow()                              # disabled, or nothing configured
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    dest = destinations.match(tool, tool_input)
    if not dest:
        allow()
    text = destinations.extract(dest, tool, tool_input)
    if not text:
        allow()

    session = str(payload.get("session_id") or "no-session")
    digest = hashlib.sha1(text.encode()).hexdigest()[:16]
    path, state = load_state(session)
    envelope = destinations.envelope(dest, tool, tool_input)

    # Walk the checks in order, skipping the ones this text has already satisfied. Order is
    # editorial - outermost decision first - so no later check creates work for an earlier one.
    #
    # When a check holds the message back it names one problem rather than a list, because handing
    # back a list is what made an earlier design deadlock. Its budget is per check, so an argument
    # about the opening sentence cannot spend the whole allowance and leave the rest unexamined.
    notes = []
    for check in CHECKS:
        if satisfied(state, check, digest):
            continue
        if check.COSTS_A_CALL and not check.CAN_DENY:
            # Advisory model call: charged once per distinct text, so an identical resend after a
            # network error is not paid for twice.
            if digest in state["judged"]:
                state["passed"][check.NAME] = digest
                continue
            state["judged"].append(digest)
        if check.COSTS_A_CALL:
            if state["calls"] >= MAX_CALLS:
                state["passed"][check.NAME] = digest   # ceiling reached: let it go out
                continue
            state["calls"] += 1
        ok, message = check.run(text, envelope)
        if ok:
            state["passed"][check.NAME] = digest
            save_state(path, state)
            continue
        used = state["denials"].get(check.NAME, 0)
        if (check.CAN_DENY and used < MAX_PER_CHECK
                and state["total_denials"] < MAX_DENIALS):
            state["denials"][check.NAME] = used + 1
            state["total_denials"] += 1
            save_state(path, state)
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Hold this message. " + message + ", then send again.",
                }
            }))
            return
        # Out of budget, or a check that cannot deny: say it and move on. Giving up on one check
        # must not skip the rest, which is what an earlier version did.
        notes.append(message.rstrip(".") + ".")
        state["passed"][check.NAME] = digest
        save_state(path, state)

    # The message is going out, so the walk is over: reset for the next one in this session. The
    # session ledger deliberately survives, so a fresh draft cannot buy a fresh allowance forever.
    state["passed"] = {}
    state["denials"] = {}
    state["calls"] = 0
    save_state(path, state)

    if not notes:
        allow()
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": " ".join(notes) +
                                 " This is advice from a noisy check, not a blocker.",
        }
    }))


if __name__ == "__main__":
    main()
