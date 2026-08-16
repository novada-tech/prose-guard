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
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "lib")))

import audiences  # noqa: E402
import paths  # noqa: E402
import destinations  # noqa: E402
import checks as checks_module  # noqa: E402
from checks import (BLOCK, EFFORT, IN_ORDER as CHECKS, ceiling_for, costs_a_call, pooled,
                    written_here, wrote_which)  # noqa: E402

MAX_PER_CHECK = 2      # one complaint, then one more if the fix did not land
MAX_DENIALS = 6        # a ceiling across all of them, so one message cannot eat a session
MAX_CALLS = 20         # calls one message may cost, across every check and every run of one
MAX_UNREADABLE = 2     # times a session is asked to make its text visible before it is let through


class Context:
    """What the checks are told. Assembled once, read-only, and never inferred from the prose."""

    def __init__(self, dest, tool, tool_input, cwd):
        self.destination = dest
        ids = destinations.identifiers(dest, tool, tool_input, cwd)
        self.audience = audiences.resolve(ids, unresolved_default=default_audience())
        self.situation = destinations.situation(dest, tool, tool_input)
        # The version this text replaces, where one exists. A term already in it is not one this
        # message introduces, and holding a message back over words somebody else wrote is a demand
        # nobody can satisfy.
        self.previous = destinations.previous(dest, tool, tool_input, cwd)
        # Which sentences of the document this call actually wrote. None means all of them — a new file, a
        # message, a commit. A finding outside them is about text that was already there.
        whole, fresh = destinations.resulting(dest, tool, tool_input, cwd)
        self.mine = wrote_which(whole, fresh) if whole else None
        # A destination can say the readers are better informed than the audience assumes, e.g. a
        # direct message inside a channel-wide audience. Never the other way round.
        override = self.situation.pop("_shared_context", None)
        if override:
            self.audience.shared_context = override


# One command, not one session. A global off switch is the thing to avoid: someone turns it off for a
# minute and finds out weeks later it was never turned back on, having believed all along that their
# prose was being checked. This cannot outlive the command it is written on, and it appears in the
# transcript beside whatever it let through.
SKIP = re.compile(r"""(?:^|\s|;|&&|\|\|)PROSE_GUARD_SKIP=(?:"([^"]*)"|'([^']*)'|(\S+))\s""")


def skipped(tool_input):
    """The stated reason for skipping this one command, if there is one.

    A reason is required, and not because it is checked — nothing here can tell a good reason from a bad
    one. It is required because writing one is a sentence someone reads later, which is a different act
    from flipping a switch. `PROSE_GUARD_SKIP=1` does not work.
    """
    match = SKIP.search(str(tool_input.get("command") or "") + " ")
    if not match:
        return None
    reason = next((g for g in match.groups() if g), "").strip()
    if len(reason) < 8 or reason.isdigit():
        return ""                            # present but empty: refuse, and say what is missing
    return reason


def default_audience():
    return paths.config().get("unresolved_audience") or "engineers"


def state_dir():
    """Per-session bookkeeping, beside everything else this tool remembers. Never inside the plugin:
    an earlier design fell back to the plugin directory and put one machine's denial count under
    version control."""
    return os.path.join(os.environ.get("PROSE_GUARD_STATE") or paths.home(), "sessions")


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


def emit(decision, message, hint="", for_user=""):
    """`additionalContext` reaches the model and not the person; `systemMessage` reaches the person and
    not the model — verified against the hooks reference. A finding is for whoever is writing, so it goes
    to the model. A decision about what this tool should check in future is the person's, so it goes to
    both: they see it, and the model knows enough to offer to do it."""
    out = {"hookEventName": "PreToolUse"}
    if for_user:
        out["systemMessage"] = for_user
    if decision == BLOCK:
        out["permissionDecision"] = "deny"
        # The hint goes after the instruction, not inside it: "then send again" is what to do, and
        # anything appended before it reads as part of the complaint.
        out["permissionDecisionReason"] = ("Hold this message. " + message + ", then send again."
                                          + hint)
    elif message:
        out["additionalContext"] = message
    print(json.dumps({"hookSpecificOutput": out}))


def main():
    if not CHECKS:
        # A level set to something that is not a level reads exactly like being switched off. Say so once
        # a session, where the person can see it, because the setting is theirs.
        from checks import config as _config
        wrong = _config.misspelt()
        if wrong:
            try:
                payload = json.load(sys.stdin)
            except Exception:
                payload = {}
            path, state = load_state(str(payload.get("session_id") or "no-session"))
            if not state.get("told_misspelt"):
                state["told_misspelt"] = True
                save_state(path, state)
                emit("advise", "", for_user=f"prose-guard is doing nothing: {wrong}.")
                return
        allow()                              # disabled, or nothing configured
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd")

    reason = skipped(tool_input)
    if reason == "":
        emit(BLOCK, ('PROSE_GUARD_SKIP needs a reason someone can read rather than a value — e.g. '
                     'PROSE_GUARD_SKIP="republishing a message I did not write". It applies to this '
                     'one command'))
        return
    if reason:
        path, state = load_state(str(payload.get("session_id") or "no-session"))
        state["skipped"] = state.get("skipped", []) + [reason]
        save_state(path, state)
        count = len(state["skipped"])
        emit("advise", f"Writing check skipped for this command: {reason}"
                       + (f". That is {count} skips this session — if the check is wrong about "
                          f"something in general, /prose-guard:audiences is the fix that lasts"
                          if count >= 3 else ""))
        return

    dest = destinations.match(tool, tool_input)
    if not dest:
        # Passive discovery: count anything carrying long prose that nothing claims, so setup can
        # offer to add it later. Records the shape only, never the text, and makes no model call.
        # It speaks up at most once per shape, ever — see destinations.record_candidate.
        note = destinations.record_candidate(tool, tool_input)
        if note:
            emit("advise", note, for_user=note)
            return
        allow()
    text = destinations.extract(dest, tool, tool_input, cwd)
    if not text:
        # Matched, but the prose is not in the call. Say so once a session: silence here reads exactly
        # like a check that passed, which is how the pull request for this change went out unchecked.
        why = destinations.unreadable(dest, tool, tool_input, cwd)
        if why:
            # Held back rather than mentioned. Advice here is a request the agent is free to skip, and
            # the pull request for this very change went out unchecked while the note said so
            # afterwards. This is the one case where blocking needs no judgement about the prose: text
            # is about to be published and the guard cannot see it, and the remedy is one flag.
            #
            # Bounded like every other denial, so a caller that cannot comply is not stuck: after
            # MAX_UNREADABLE it is said as advice and the call goes through.
            path, state = load_state(str(payload.get("session_id") or "no-session"))
            held = state.get("unreadable", 0)
            state["unreadable"] = held + 1
            save_state(path, state)
            if held < MAX_UNREADABLE:
                emit(BLOCK, why.rstrip("."))
                return
            if held == MAX_UNREADABLE:
                emit("advise", why + " Letting it through: this has come up "
                                     f"{held + 1} times and the check is not worth blocking on.")
                return
        allow()

    # A destination can be worth less than the level you asked for. The gating checks ask whether the
    # reader will care and whether the ask is clear; a commit message has no addressee and no ask, and
    # paying four model calls for one is the wrong trade for something read years later, by someone
    # looking for when a line changed. See data/destinations.json.
    running = checks_module.for_effort(checks_module.capped(EFFORT, dest.get("max_effort")))
    if not running:
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
    unpaid = [c for c in running if costs_a_call(c) and state["passed"].get(c.NAME) != digest]
    for check in running:
        if state["passed"].get(check.NAME) == digest:
            continue
        if costs_a_call(check) and state["calls"] >= MAX_CALLS:
            state["passed"][check.NAME] = digest
            continue
        try:
            # The same pooling a deliberate run uses, so both apply one bar: passes scale with the
            # length of the text, and an item more than one run pointed at is what can be blocked on.
            #
            # The budget is in calls, and it is divided rather than handed over. Giving each check
            # whatever was left meant the first one took it: on an edit of one sentence in a 1,960-word
            # file, all nineteen calls went to `relevance` and four concerns never ran at all. A share
            # each buys five concerns for the same money, which is what `high` is being paid for.
            share = max(1, (MAX_CALLS - state["calls"]) // max(1, len(unpaid)))
            found, firm, spent = pooled(check, text, ctx, min(ceiling_for(text), share))
            state["calls"] += spent
            if costs_a_call(check):
                unpaid = [c for c in unpaid if c.NAME != check.NAME]
        except Exception:
            found, firm = [], []             # a broken check is a silent check, never a blocker
        state["passed"][check.NAME] = digest
        save_state(path, state)
        if not found:
            continue
        # One message carrying everything this check found, so a caller pays one turn to fix several
        # things rather than one turn each.
        # Block only on what this call wrote. A complaint about a paragraph the edit never touched is
        # worth saying and is not grounds for refusing the edit.
        def mine(f):
            return written_here(text, f, ctx.mine)
        blocking = [f for f in firm if f.severity == BLOCK and mine(f)]
        finding = found[0]._replace(
            message="\n".join(f.message + ("" if mine(f) else "  (already in the file)")
                              for f in found),
            severity=BLOCK if blocking else "advise")
        # A destination can refuse to block at all. Blocking is justified by the text being about to
        # reach a reader unreviewed; where it is not — a draft that lands in your own compose box —
        # the finding is worth saying and not worth a turn spent arguing.
        if finding.severity == BLOCK and dest.get("max_severity") == "advise":
            finding = finding._replace(severity="advise")
        if finding.severity == BLOCK:
            used = state["denials"].get(check.NAME, 0)
            if used < MAX_PER_CHECK and state["total_denials"] < MAX_DENIALS:
                state["denials"][check.NAME] = used + 1
                state["total_denials"] += 1
                state["passed"].pop(check.NAME, None)   # it has to pass on the NEXT text, not this
                save_state(path, state)
                # The escape hatch is named only on the last denial this check gets, which is the
                # first moment it is the right answer. Naming it in every denial would teach the
                # cheaper move before the correct one, and the correct one is almost always to edit
                # the text. An agent that has already tried twice is a different situation.
                hint = ("" if used + 1 < MAX_PER_CHECK else
                        "\n\nIf editing cannot fix this — you are reproducing text you did not write, "
                        "or quoting someone — say so and send it anyway: "
                        'PROSE_GUARD_SKIP="<why>" in front of the command excuses that one command. '
                        "If a term is fine for this reader in general, "
                        "`/prose-guard:audiences` is the lasting fix.")
                emit(BLOCK, finding.message, hint)
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
