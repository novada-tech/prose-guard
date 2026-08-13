#!/usr/bin/env python3
"""PreToolUse orchestrator: check prose on its way OUT, not on every turn.

Four jobs, everything else delegated:

    is text leaving, and what carries it     lib/destinations.py
    who will read it                         lib/audiences.py
    what is wrong with it                    lib/checks/
    what to do about that                    here

A check returns a Finding with its own severity, because only the check knows whether it is being
exact or guessing. This file turns a Finding into a decision and keeps the argument bounded.

Placement is a cost decision, measured rather than guessed: see lib/checks/config.py. Running these
after every assistant turn instead multiplied the cost by every turn in the session.

It denies rather than rewrites. The agent does the editing, which keeps the deterministic part
honest — it names the exact terms — and leaves judgement with the model.

Every failure path allows the call. A broken writing check must never block outbound work.
"""
import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "lib")))

import audiences  # noqa: E402
import destinations  # noqa: E402
from checks import BLOCK, IN_ORDER as CHECKS  # noqa: E402

MAX_PER_CHECK = 2      # one complaint, then one more if the fix did not land
MAX_DENIALS = 6        # a ceiling across all of them, so one message cannot eat a session
MAX_CALLS = 12         # and a ceiling on calls, since a re-verified check can be asked again


class Context:
    """What the checks are told. Assembled once, read-only, and never inferred from the prose."""

    def __init__(self, dest, tool, tool_input, cwd):
        self.destination = dest
        ids = destinations.identifiers(dest, tool, tool_input, cwd)
        self.audience = audiences.resolve(ids, unresolved_default=default_audience())
        self.situation = destinations.situation(dest, tool, tool_input)
        # A destination can say the readers are better informed than the audience assumes, e.g. a
        # direct message inside a channel-wide audience. Never the other way round.
        override = self.situation.pop("_shared_context", None)
        if override:
            self.audience.shared_context = override


def default_audience():
    try:
        with open(os.path.join(audiences.config_dir(), "config.json")) as fh:
            return json.load(fh).get("unresolved_audience") or "engineers"
    except Exception:
        return "engineers"


def state_dir():
    """Per-session bookkeeping. Never inside a checkout: an earlier design fell back to the plugin
    directory and put one machine's denial count under version control."""
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
    state = {"passed": {}, "denials": {}, "total_denials": 0, "calls": 0, "advised": []}
    try:
        with open(path) as fh:
            state.update(json.load(fh))
    except Exception:
        pass
    return path, state


def save_state(path, state):
    try:
        os.makedirs(state_dir(), exist_ok=True)
        state["advised"] = state["advised"][-50:]
        with open(path, "w") as fh:
            json.dump(state, fh)
    except OSError:
        pass


def emit(decision, message):
    out = {"hookEventName": "PreToolUse"}
    if decision == BLOCK:
        out["permissionDecision"] = "deny"
        out["permissionDecisionReason"] = "Hold this message. " + message + ", then send again."
    else:
        out["additionalContext"] = message
    print(json.dumps({"hookSpecificOutput": out}))


def main():
    if not CHECKS:
        allow()                              # disabled, or nothing configured
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd")

    dest = destinations.match(tool, tool_input)
    if not dest:
        # Passive discovery: note the shape of anything carrying long prose that nothing claims, so
        # setup can offer to add it later. Records no message text and makes no model call.
        destinations.record_candidate(tool, tool_input)
        allow()
    text = destinations.extract(dest, tool, tool_input)
    if not text:
        allow()

    session = str(payload.get("session_id") or "no-session")
    digest = hashlib.sha1(text.encode()).hexdigest()[:16]
    path, state = load_state(session)
    ctx = Context(dest, tool, tool_input, cwd)

    # Walk the checks in order, skipping the ones this exact text already satisfied. A pass belongs
    # to the text that earned it, so an edit made for a later check puts the earlier ones back in
    # play — the only thing that can catch "make this sentence simpler" dropping a fact the reader
    # needed. A message nobody objected to is still walked once, because nothing changed under it.
    #
    # Order is editorial, outermost decision first, so no later check creates work for an earlier
    # one. Bounded three ways so two checks that genuinely disagree make a message expensive and
    # then let it go, rather than hanging the turn.
    advice = []
    for check in CHECKS:
        if state["passed"].get(check.NAME) == digest:
            continue
        if check.COSTS_A_CALL and state["calls"] >= MAX_CALLS:
            state["passed"][check.NAME] = digest
            continue
        if check.COSTS_A_CALL:
            state["calls"] += 1
        try:
            finding = check.run(text, ctx)
        except Exception:
            finding = None                   # a broken check is a silent check, never a blocker
        state["passed"][check.NAME] = digest
        save_state(path, state)
        if finding is None:
            continue
        if finding.severity == BLOCK:
            used = state["denials"].get(check.NAME, 0)
            if used < MAX_PER_CHECK and state["total_denials"] < MAX_DENIALS:
                state["denials"][check.NAME] = used + 1
                state["total_denials"] += 1
                state["passed"].pop(check.NAME, None)   # it has to pass on the NEXT text, not this
                save_state(path, state)
                emit(BLOCK, finding.message)
                return
        # Advice, or a block that has run out of budget. Say it once per text and move on: giving up
        # on one check must not skip the rest.
        key = check.NAME + ":" + digest
        if key not in state["advised"]:
            state["advised"].append(key)
            advice.append(finding.message.rstrip(".") + ".")

    # The message is going out, so the argument is over: reset for the next one. The session ledger
    # deliberately survives, so a fresh draft cannot buy a fresh allowance forever.
    state["passed"] = {}
    state["denials"] = {}
    state["calls"] = 0
    save_state(path, state)

    if not advice:
        allow()
    emit("advise", " ".join(advice) + " Advice from a noisy check, not a blocker.")


if __name__ == "__main__":
    main()
