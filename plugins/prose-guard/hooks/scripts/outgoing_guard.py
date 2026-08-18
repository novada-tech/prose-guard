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
from __future__ import annotations

import hashlib
import concurrent.futures
import json
import os
import re
import shlex
import sys
from typing import Any, Callable, NoReturn, TYPE_CHECKING

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "lib")))

import audiences  # noqa: E402
import paths  # noqa: E402
import rounds  # noqa: E402
import destinations  # noqa: E402
import discover  # noqa: E402
import telling  # noqa: E402
import checks as checks_module  # noqa: E402
from checks import (BLOCK, EFFORT, IN_ORDER as CHECKS, Context, ceiling_for,  # noqa: E402
                    costs_a_call, pooled, written_here, wrote_which)

if TYPE_CHECKING:
    from audiences import Resolved
    from checks import Check, Finding
    from destinations import Dest

MAX_PER_CHECK = 2      # one complaint, then one more if the fix did not land
MAX_DENIALS = 6        # a ceiling across all of them, so one message cannot eat a session
# Calls one message may cost, across every check and every run of one. Scaled by length, because a flat
# number is not a budget for a document — it is a budget for a chat message, silently applied to both.
#
# Flat at 20 it bound in every case: 20 divided among six model-backed checks is three runs each, for a
# 200-word message and a 10,000-word document alike, while `ceiling_for` was asking for between six and
# twenty-five. The whole point of scaling runs with length was dead in the hook, and dividing the budget
# between the checks — which was right, and bought five concerns instead of one — made it bind harder.
#
# A clean document is unaffected: pooling stops as soon as runs stop finding things, so one call a check
# is what good prose costs whatever its length. This only ever binds on a document with real defects,
# which is the case that deserves the calls.
MOST_CALLS = 90        # the absolute ceiling, so a runaway cannot happen
MAX_UNREADABLE = 2     # times a session is asked to make its text visible before it is let through


def context_for(dest: Dest, tool: str, tool_input: dict[str, Any], cwd: str | None) -> Context:
    """What the checks are told. Assembled once, read-only, and never inferred from the prose.

    The type is checks.Context, shared with check_prose.py. Two classes of the same name used to set
    different fields — five here and two there — so a rule reading one of them through `getattr` was
    silently inert in the deliberate path, and nothing said so.
    """
    ids = destinations.identifiers(dest, tool, tool_input, cwd)
    situation = destinations.situation(dest, tool, tool_input)
    # Which sentences of the document this call actually wrote. None means all of them — a new file, a
    # message, a commit. A finding outside them is about text that was already there.
    whole, fresh = destinations.resulting(dest, tool, tool_input, cwd)
    ctx = Context(
        audiences.resolve(ids, unresolved_default=default_audience()),
        situation=situation,
        # The version this text replaces, where one exists. A term already in it is not one this
        # message introduces, and holding a message back over words somebody else wrote is a demand
        # nobody can satisfy.
        previous=destinations.previous(dest, tool, tool_input, cwd),
        mine=wrote_which(whole, fresh) if whole else None)
    # A destination can say the readers are better informed than the audience assumes, e.g. a direct
    # message inside a channel-wide audience. Never the other way round.
    override = ctx.situation.pop("_shared_context", None)
    if override:
        ctx.audience.shared_context = override
    return ctx


# One command, not one session. A global off switch is the thing to avoid: someone turns it off for a
# minute and finds out weeks later it was never turned back on, having believed all along that their
# prose was being checked. This cannot outlive the command it is written on, and it appears in the
# transcript beside whatever it let through.
SKIP_VAR = "PROSE_GUARD_SKIP"


def skipped(tool_input: dict[str, Any]) -> str | None:
    """The stated reason for skipping this one command, if there is one.

    Only where the shell would read it: an assignment before the command, at the front of the line or
    just after `;`, `&&` or `||`. It used to be searched for anywhere in the command string, so a
    command that merely CONTAINED the words switched the guard off — a commit message documenting the
    escape hatch, a release note explaining it, a message telling a colleague it exists. Those went out
    unchecked and looked checked, and the ledger recorded a reason their author never claimed. Writing
    about a thing is not doing it.

    A reason is required, and not because it is checked — nothing here can tell a good reason from a bad
    one. It is required because writing one is a sentence someone reads later, which is a different act
    from flipping a switch. `PROSE_GUARD_SKIP=1` does not work.
    """
    for run in re.split(r";|&&|\|\|", str(tool_input.get("command") or "")):
        try:
            words = shlex.split(run)
        except ValueError:
            continue
        # Assignments come before the command and stop at the first word that is not one, which is
        # exactly where the shell stops treating them as assignments.
        for word in words:
            if "=" not in word or word.startswith("-"):
                break
            name, _, value = word.partition("=")
            if name != SKIP_VAR:
                continue
            reason = value.strip()
            if len(reason) < 8 or reason.isdigit():
                return ""                    # present but empty: refuse, and say what is missing
            return reason
    return None


def default_audience() -> str:
    return paths.config().get("unresolved_audience") or "engineers"


def state_dir() -> str:
    """Per-session bookkeeping, beside everything else this tool remembers. Never inside the plugin:
    an earlier design fell back to the plugin directory and put one machine's denial count under
    version control."""
    return os.path.join(os.environ.get("PROSE_GUARD_STATE") or paths.home(), "sessions")


# NoReturn, because callers below say `allow()` on its own line and carry on reading as though the
# function had returned. It never does.
def allow() -> NoReturn:
    sys.exit(0)


def load_state(session: str) -> tuple[str, dict[str, Any]]:
    path = os.path.join(state_dir(), session + ".json")
    # passed and denials describe the message being argued about and reset once it goes out.
    # total_denials is the session ledger and never resets, so the guard cannot keep blocking for a
    # whole session however many fresh drafts arrive.
    # `verdicts` maps a check to what it made of one exact text: {"digest": ..., "message": ...,
    # "severity": ...}, with no message meaning it passed. It used to hold the digest alone, so a
    # denial had to forget it to make the check run again — and an identical resend then re-derived
    # the same answer at the price of a model call. Three identical sends cost three calls.
    state = {"verdicts": {}, "denials": {}, "total_denials": 0, "calls": 0, "advised": []}
    try:
        with open(path) as fh:
            state.update(json.load(fh))
    except Exception:
        pass
    return path, state


def save_state(path: str, state: dict[str, Any]) -> None:
    try:
        os.makedirs(state_dir(), exist_ok=True)
        state["advised"] = state["advised"][-50:]
        with open(path, "w") as fh:
            json.dump(state, fh)
    except OSError:
        pass


def _one_stop(message: str) -> str:
    """A finding ending in exactly one full stop, so a sentence can follow it."""
    return message.rstrip().rstrip(".,;:") + "."


def emit(decision: str, message: str, hint: str = "", for_user: str = "") -> None:
    """`additionalContext` reaches the model and not the person; `systemMessage` reaches the person and
    not the model — verified against the hooks reference. A finding is for whoever is writing, so it goes
    to the model. A decision about what this tool should check in future is the person's, so it goes to
    both: they see it, and the model knows enough to offer to do it."""
    out = {"hookEventName": "PreToolUse"}
    if decision == BLOCK:
        out["permissionDecision"] = "deny"
        # Two sentences, not one clause bolted onto another. A model finding is already a sentence
        # ending in a full stop, so appending ", then send again." produced
        #
        #     …unable to tell what it refers to., then send again.
        #
        # in front of a person. The finding is normalised to end in exactly one stop and the
        # instruction follows as its own sentence, which reads the same whether the finding is a
        # sentence from a model or a phrase from arithmetic.
        out["permissionDecisionReason"] = ("Hold this message. " + _one_stop(message)
                                           + " Then send again." + hint)
    elif message:
        out["additionalContext"] = message
    said = {"hookSpecificOutput": out}
    # `systemMessage` is a SIBLING of hookSpecificOutput, not a field inside it — see the common fields
    # table in the hooks reference. Nested, it is well-formed JSON that Claude Code discards, so every
    # transparency line this tool has ever emitted was silently dropped: the level, the audience, the
    # rewrite count, the checks that could not run. The hook exited 0 and the JSON parsed, which is why
    # nothing looked wrong. Verified by reading the output of a real run rather than the string we put
    # into it — the mistake this repeats otherwise is checking the value we just set.
    if for_user:
        said["systemMessage"] = for_user
    print(json.dumps(said))


# What this tool may add to the conversation about one message, in characters. Everything every check
# found used to be joined and sent, with nothing bounding it: measured at 1,466 tokens for one edit of
# a long document, of which 1,393 were findings about sentences the edit never touched, and a worst
# case of 8,310. That is the tool making an agent read a list of somebody else's sentences while it is
# mid-edit and can act on none of them. One budget for the whole turn rather than one per check,
# because five checks each staying under a limit is not a limit.
MOST_TO_SAY = 3000


def one_message(found: list[Finding], mine: Callable[[Finding], bool],
                budget: int) -> tuple[str, list[Finding]]:
    """Everything worth saying about one check's findings, and which of them actually got said.

    What this call wrote comes first, whatever order the runs found things in: those are the ones the
    agent can act on now, and they are the only ones that can hold the message back. So a budget that
    runs out drops the least actionable findings, not an arbitrary tail.

    The second half of the return exists because a caller that remembers what it has already said must
    remember only what was SHOWN. Marking a finding as said and then dropping it for budget suppresses
    it having never been read once — the mistake `telling.py` names in its own docstring, and the one
    that is easy to make here because the findings this drops are exactly the ones worth remembering.
    """
    ordered = [f for f in found if mine(f)] + [f for f in found if not mine(f)]
    lines: list[str] = []
    shown: list[Finding] = []
    dropped = 0
    for f in ordered:
        line = f.message + ("" if mine(f) else "  (already in the file)")
        # `lines and` is a floor of one, deliberately: a check that found something always gets to say
        # one thing, or a spent budget would silence the last check completely and that is
        # indistinguishable from it passing. So the real ceiling is the budget plus one line per check.
        if lines and sum(len(x) + 1 for x in lines) + len(line) > budget:
            dropped += 1
            continue
        lines.append(line)
        shown.append(f)
    if dropped:
        lines.append(f"({dropped} more, about text this call did not write. "
                     f"`python3 lib/check_prose.py <file>` shows them.)")
    return "\n".join(lines), shown


def repeated(finding: Finding) -> str:
    """What a finding is remembered under, once it has been said about text the call did not write.

    Its own words, not the digest of the document it was found in. Keyed on the digest — which is what
    `advised` uses, and rightly, for a finding about the text being sent — the same complaint about the
    same untouched paragraph came back on every edit, because every edit changes the digest. Five edits
    to one README repeated four such notes five times, at a model call apiece, and none of them was
    something the edit in hand could act on.
    """
    return "already said: " + hashlib.sha1(finding.message.encode()).hexdigest()[:12]


def say(finding: Finding, check: Check, state: dict[str, Any], path: str, digest: str,
        advice: list[str], keep: Callable[[str, str], None] | None = None,
        also: list[str] | None = None) -> bool:
    """Deny on this finding, or add it to the advice. True when the call was denied and we are done.

    Split out because an identical resend re-says what a check already decided, and doing that had to
    mean re-running the check. The decision — deny, or advise — depends on the session's ledger rather
    than on the text, so it is the same code either way.
    """
    if finding.severity == BLOCK:
        used = state["denials"].get(check.NAME, 0)
        if used < MAX_PER_CHECK and state["total_denials"] < MAX_DENIALS:
            state["denials"][check.NAME] = used + 1
            state["total_denials"] += 1
            save_state(path, state)
            # The escape hatch is named only on the last denial this check gets, which is the first
            # moment it is the right answer. Naming it in every denial would teach the cheaper move
            # before the correct one, and the correct one is almost always to edit the text. An agent
            # that has already tried twice is a different situation.
            hint = ("" if used + 1 < MAX_PER_CHECK else
                    "\n\nIf editing cannot fix this — you are reproducing text you did not write, "
                    "or quoting someone — say so and send it anyway: "
                    'PROSE_GUARD_SKIP="<why>" in front of the command excuses that one command. '
                    "If a term is fine for this reader in general, "
                    "`/prose-guard:audiences` is the lasting fix.")
            if keep:
                keep(check.NAME, finding.message)
            # What the other checks found, in the same interruption. Only this one holds the message
            # back; the rest are context, so the rewrite can address everything in one turn instead of
            # being sent back once per concern. That is the whole saving now the checks are asked
            # together: a held message used to cost a round per objecting check, and each round re-ran
            # every check because the text — and so the digest — had changed.
            #
            # Exactly one blocker, still. `docs/design-notes.md` records what two of them did: "explain
            # every term" and "contains nothing they will not act on" each undid the other and the
            # session ended with no message at all, 0 of 5 usable, twice. Listing the others as context
            # is not the same thing, because nothing is being demanded by two checks at once.
            more = (("\n\nAlso worth fixing while you are here, though none of it is holding this "
                     "back: ") + " ".join(also)) if also else ""
            emit(BLOCK, finding.message + more, hint)
            return True
    # Advice, or a block that has run out of budget. Say it once per text and move on: giving up on
    # one check must not skip the rest.
    key = check.NAME + ":" + digest
    if key not in state["advised"]:
        state["advised"].append(key)
        advice.append(finding.message.rstrip(".") + ".")
    save_state(path, state)
    return False


def reader(audience: Resolved | None) -> str:
    """Who the message was judged for, and whether that was measured or assumed.

    Whether the audience matched is not a detail. One that did was measured from what those people have
    actually written, and it can hold a message back. One that did not cannot — findings become advice,
    because blocking on a guess spends somebody's first day arguing about their own house vocabulary.
    Somebody watching a message go out unchallenged deserves to know which of those they are looking at,
    and it used to be invisible.

    Which baseline the guess is against is deliberately not here. It read `no audience for this —
    guessing against engineers`, which is 44 characters of a line that appears on every message a person
    sends, behind a `PreToolUse:<tool> says:` prefix Claude Code adds and nothing here can shorten. The
    fact worth carrying is that the reader is assumed rather than measured; which assumption it was is a
    question somebody asks once, and `/prose-guard:audiences` answers it.
    """
    if audience is not None and audience.resolved and audience.names:
        return " + ".join(audience.names)
    return "no audience"


# How many checks may be asked at the same time. Each is a `claude -p` subprocess, so this is bounded by
# what a laptop should be running at once rather than by anything about the checks.
MOST_AT_ONCE = 6


def all_at_once(checks: list[Check], text: str, ctx: Context | None,
                budget: int) -> dict[str, tuple]:
    """Ask every check that costs a model call at the same time, and return what each said.

    They were asked one after another, and each answer is a `claude -p` subprocess taking about eight
    seconds. Measured on a real pull request review: 39 guarded calls, median 50.3s, and 217.7s for a
    925-word summary comment — 34.5 minutes of a 168-minute session spent waiting here.

    Nothing about the ANSWERS changes. The checks are independent: each reads the same unmodified text
    and none can see another's verdict, which is why asking them together is only a question of when.
    `docs/design-notes.md` records a "parallel checks" failure and it is a different thing — two checks
    that could each HOLD A MESSAGE BACK, each undoing the other's demand. That is about what may block,
    not about what may run, and only one finding blocks here either way.

    The budget is divided up front instead of as they run. A share each is what the sequential version
    was already aiming at, and it is the only division available when nobody goes first.
    """
    if not checks or budget <= 0:
        # Nothing left to spend, so nothing is asked. `max(1, 0 // n)` floors at one and asked anyway,
        # which spent a call for every check after a session had already used its budget — the one thing
        # the budget exists to stop. The walk skips paying checks itself once the budget is gone, so
        # returning nothing here is what makes both agree.
        return {}
    share = max(1, budget // len(checks))
    ceiling = min(ceiling_for(text), share)
    out: dict[str, tuple] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(checks), MOST_AT_ONCE)) as pool:
        asking = {pool.submit(pooled, check, text, ctx, ceiling): check for check in checks}
        for done in concurrent.futures.as_completed(asking):
            check = asking[done]
            try:
                out[check.NAME] = done.result()
            except Exception:
                out[check.NAME] = ([], [], 0)   # a broken check is a silent check, never a blocker
    return out


def other_concerns(running: list[Check], answers: dict[str, tuple], blocking: str,
                   mine: Callable[[Finding], bool], room: int) -> list[str]:
    """What the checks that are NOT holding this message back found, for the same interruption.

    Available only because the checks are asked together: walking them one at a time and stopping at the
    first objection meant the rest had never run, so a held message cost one round per objecting check —
    and every round re-ran every check, because the text had changed and a pass belongs to the text that
    earned it. Handing all of it over at once is what collapses those rounds into one.

    Bounded by `room`, and only about text this call wrote: a concern about a paragraph the edit never
    touched is not something the writer of this edit can act on.
    """
    out: list[str] = []
    for check in running:
        if check.NAME == blocking or check.NAME not in answers:
            continue
        found = [f for f in answers[check.NAME][0] if mine(f)]
        if not found:
            continue
        said, _ = one_message(found, mine, room - sum(len(o) for o in out))
        if said:
            out.append(f"({check.NAME}) {said}")
    return out


def budget_for(text: str, paying: int) -> int:
    """Model calls this message may cost, scaled the way the per-check ceiling is scaled.

    `ceiling_for` is what one check would spend on this text if it kept finding things; times the
    checks that cost anything, that is what the message would spend unbounded. MOST_CALLS is the stop.
    """
    return min(MOST_CALLS, max(1, paying) * ceiling_for(text))



def tally(level: str, rewrites: int, notes: int, calls: int,
          audience: Resolved | None = None) -> str:
    """The one line the person sees when a message has been checked.

    Written as counts rather than a verdict because the useful reading is comparative: three rewrites
    on one message is worth looking at, and so is a level nobody meant to be running, or a reader
    nobody meant to be assumed.

    Fields separated rather than a sentence, and that is about where it lands. Claude Code prints it as
    `PreToolUse:<tool> says: <this>`, and a tool name like
    `mcp__github__add_comment_to_pending_review` has already spent the width before this gets a word in.
    A sentence read after that prefix parses as a second clause of somebody else's sentence; four fields
    in a fixed order read as a status line, which is what it is — the same shape every time, on every
    message, so an unexpected value is the thing the eye catches rather than something to read for.
    """
    said = []
    if rewrites:
        said.append(f"{rewrites} rewrite" + ("s" if rewrites != 1 else ""))
    if notes:
        said.append(f"{notes} note" + ("s" if notes != 1 else ""))
    fields = ["prose-guard", level, reader(audience),
              ", ".join(said) if said else "clean"]
    if calls:
        fields.append(f"{calls} call" + ("s" if calls != 1 else ""))
    # Where to read the argument back, said only when there is one. A rewrite is an exchange that
    # happened out of sight, and somebody judging whether the complaint was fair needs the drafts rather
    # than the count. Nothing is recorded unless a check held something back, so this field and that
    # record appear together or not at all.
    #
    # A skill rather than a script path, because everything else here is asked for in words —
    # /prose-guard:setup, /prose-guard:audiences — and a path to a file inside a plugin directory is
    # not something anybody should have to keep.
    if rewrites:
        fields.append("/prose-guard:feedback")
    return " · ".join(fields)


def say_together(findings: list[Finding], checks: list[Check], state: dict[str, Any], path: str,
                 digest: str, advice: list[str], keep: Callable[[str, str], None]) -> bool:
    """One interruption carrying what every free check found. True when the call was denied.

    Nothing when there is nothing: the caller does not have to check first. The denial is counted
    against each check that objected, because each did, and against the session once, because the
    person was interrupted once — counting it per check there would halve a session's allowance for
    a message that was held back a single time.
    """
    if not findings:
        return False
    joined = findings[0]._replace(message="\n".join(f.message for f in findings))
    before = state["total_denials"]
    for n, check in enumerate(checks):
        # Only the first reaches `say`, so only it can emit; the rest just record that they objected.
        if n:
            state["denials"][check.NAME] = state["denials"].get(check.NAME, 0) + 1
    denied = say(joined, checks[0], state, path, digest, advice, keep)
    if denied and len(checks) > 1:
        state["total_denials"] = before + 1
        save_state(path, state)
    return denied


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    path, state = load_state(str(payload.get("session_id") or "no-session"))
    ledger = telling.Ledger(state)

    # Anything wrong with a file somebody hand-wrote, said once a session because they can fix it and
    # it stops being true when they do. Every one of these used to pass silently and in the same
    # direction: the guard more aggressive than asked, or absent while looking present.
    wrong = (checks_module.config.complaints() + destinations.COMPLAINTS
             + audiences.COMPLAINTS)
    if wrong and ledger.worth_saying("bad settings"):
        save_state(path, state)
        emit("advise", "", for_user="prose-guard: " + "; ".join(wrong[:3]) + ".")
        return
    if not CHECKS:
        allow()                              # disabled, or nothing configured
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
        # It speaks up at most once per shape, ever — see discover.record_candidate.
        note = discover.record_candidate(tool, tool_input)
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
    level = checks_module.capped(EFFORT, dest.get("max_effort"))
    running = checks_module.for_effort(level)
    if not running:
        allow()

    digest = hashlib.sha1(text.encode()).hexdigest()[:16]
    ctx = context_for(dest, tool, tool_input, cwd)

    # A held message is an exchange nobody sees: the guard objects, the agent rewrites, and only the
    # last version reaches anybody — so a bad complaint and a good one look identical afterwards. This
    # keeps the drafts so somebody can read the argument back. It writes message text, which nothing
    # else here does, and the rule that makes that acceptable is that it only ever runs on the path
    # below, where a check has actually held something back. See lib/rounds.py.
    session = str(payload.get("session_id") or "no-session")

    def envelope() -> dict[str, Any]:
        """Everything the checks were told before they read a word.

        Recorded because "why did it say that" is almost never answered by the finding. It is answered
        by which audience applied — and whether one applied at all — by what the destination said the
        moment was, and by which level actually ran once the destination had capped it.
        """
        return {"destination": dest.get("name", "?"),
                "level": level,
                "asked_for": EFFORT,
                "audience": " + ".join(ctx.audience.names) or ctx.audience.fallback or "?",
                "guessing": not ctx.audience.resolved,
                # What the model-backed checks are shown about the moment. Keys beginning with _ are
                # internal and are not shown to them, so they are not shown here either.
                "situation": {k: v for k, v in (ctx.situation or {}).items()
                              if not k.startswith("_")},
                "checks": [c.NAME for c in running],
                "edit_of": len(ctx.mine) if ctx.mine else None}

    def keep(name: str, said: str) -> None:
        rounds.held(session, envelope(), text, name, said)

    # Walk the checks in order, skipping the ones this exact text already satisfied. A pass belongs
    # to the text that earned it, so an edit made for a later check puts the earlier ones back in
    # play — the only thing that can catch "make this sentence simpler" dropping a fact the reader
    # needed. A message nobody objected to is still walked once, because nothing changed under it.
    #
    # Order is editorial, outermost decision first, so no later check creates work for an earlier
    # one. Bounded three ways so two checks that genuinely disagree make a message expensive and
    # then let it go, rather than hanging the turn.
    advice: list[str] = []
    # Findings from the checks that cost nothing, held until all of them have run. Stopping at the
    # first objection is right when the next one costs a model call — and it is what keeps two blocking
    # checks from pulling a message apart, which `docs/design-notes.md` records producing no message at
    # all. Neither reason applies to `terms` and `mechanics`: both are free, both are absolute, and both
    # ask for a one-word fix. Being sent back for a doubled word and then again for an unexplained
    # acronym is one turn wasted, and a held turn is the most expensive thing this tool does.
    free_findings: list[Finding] = []
    free_checks: list[Check] = []
    # What this message may spend, from its own length. See budget_for.
    budget = budget_for(text, sum(1 for c in running if costs_a_call(c)))
    unpaid = [c for c in running if costs_a_call(c)
              and (state["verdicts"].get(c.NAME) or {}).get("digest") != digest]
    # Asked together, before the walk, so the walk spends no time waiting. The walk itself is unchanged:
    # same order, same caching, same one-finding-blocks rule — it just reads answers that already exist.
    answers = all_at_once(unpaid, text, ctx, max(0, budget - state["calls"]))
    for check in running:
        remembered = state["verdicts"].get(check.NAME) or {}
        if remembered.get("digest") == digest:
            if not remembered.get("message"):
                continue                     # it passed on this exact text; nothing has changed
            # It objected to this exact text and the text has not changed, so the answer has not
            # either. Re-say it without paying for it again.
            finding = checks_module.Finding(remembered["severity"], remembered["message"])
            if not costs_a_call(check) and finding.severity == BLOCK:
                free_findings.append(finding)
                free_checks.append(check)
                continue
            if say(finding, check, state, path, digest, advice, keep):
                return
            continue
        if costs_a_call(check) and state["calls"] >= budget:
            state["verdicts"][check.NAME] = {"digest": digest}
            continue
        if check.NAME in answers:
            # Already asked, at the same time as its siblings. See all_at_once: the budget is divided a
            # share each, which is what the sequential version was aiming at — handing each check
            # whatever was left meant the first one took it, and on an edit of one sentence in a
            # 1,960-word file all nineteen calls went to `relevance` while four concerns never ran.
            found, firm, spent = answers[check.NAME]
            state["calls"] += spent
        else:
            try:
                # Costs nothing, so there is nothing to gain by asking it early: the free checks are
                # arithmetic and answer immediately.
                found, firm, spent = pooled(check, text, ctx, ceiling_for(text))
                state["calls"] += spent
            except Exception:
                found, firm = [], []         # a broken check is a silent check, never a blocker
        if not found:
            state["verdicts"][check.NAME] = {"digest": digest}
            save_state(path, state)
            continue
        # One message carrying everything this check found, so a caller pays one turn to fix several
        # things rather than one turn each.
        # Block only on what this call wrote. A complaint about a paragraph the edit never touched is
        # worth saying and is not grounds for refusing the edit.
        def mine(f: Finding) -> bool:
            return written_here(text, f, ctx.mine)
        # Drop what has already been said about text this call did not write. Only those: a finding
        # about the edit in hand is about THIS text and is remembered by its digest, so an unchanged
        # resend re-says it and an edit that did not fix it earns the complaint again. See `repeated`.
        already = set(state.get("said", []))
        found = [f for f in found if mine(f) or repeated(f) not in already]
        if not found:
            state["verdicts"][check.NAME] = {"digest": digest}
            save_state(path, state)
            continue
        blocking = [f for f in firm if f.severity == BLOCK and mine(f)]
        said, shown = one_message(found, mine, MOST_TO_SAY - sum(len(a) for a in advice))
        # Marked here, from what the message actually carried, and never from `found`: the findings a
        # spent budget drops are the not-mine ones, so marking before showing would silence exactly
        # the notes nobody has read yet.
        for f in shown:
            if not mine(f):
                ledger.worth_saying(repeated(f))
        finding = found[0]._replace(message=said, severity=BLOCK if blocking else "advise")
        # A destination can refuse to block at all. Blocking is justified by the text being about to
        # reach a reader unreviewed; where it is not — a draft that lands in your own compose box —
        # the finding is worth saying and not worth a turn spent arguing.
        if finding.severity == BLOCK and dest.get("max_severity") == "advise":
            finding = finding._replace(severity="advise")
        state["verdicts"][check.NAME] = {"digest": digest, "message": finding.message,
                                         "severity": finding.severity}
        if not costs_a_call(check) and finding.severity == BLOCK:
            free_findings.append(finding)
            free_checks.append(check)
            continue
        # Everything the free checks found goes out in one interruption, before anything is paid for.
        if say_together(free_findings, free_checks, state, path, digest, advice, keep):
            return
        free_findings, free_checks = [], []
        if say(finding, check, state, path, digest, advice, keep,
               also=other_concerns(running, answers, check.NAME, mine, MOST_TO_SAY // 2)):
            return

    # A free check objected and nothing after it did, so this is where that is said.
    if say_together(free_findings, free_checks, state, path, digest, advice, keep):
        return

    # The message is going out, so the argument is over: a new message gets a fresh allowance and a
    # fresh budget. The session ledger of total denials deliberately survives, so a fresh draft cannot
    # buy a fresh allowance for ever.
    #
    # What is NOT cleared is what each check made of the text it last saw. That used to be, and it is
    # what made sending the same text three times cost three model calls: the answer to "what does this
    # check make of this exact text" cannot change, and the digest stored beside it already separates
    # one text from the next, so clearing it only bought the same answer again. It holds one entry per
    # check, so it cannot grow.
    # The message is going out, so close the argument with the text that finally went. Returns None
    # when nothing was ever held back, and then nothing has been written at any point.
    rounds.went_out(session, text, state["calls"])

    # Read before they are cleared: this is the whole argument that led to the message going out.
    rewrites = sum(state["denials"].values())
    calls = state["calls"]
    state["denials"] = {}
    state["calls"] = 0
    save_state(path, state)

    # A check that could not run reads exactly like a check that passed. Said to the person, once a
    # session, because it is their install that is not doing what they set it to do — the same bargain
    # a misspelt effort level gets.
    missed = [m for m in telling.never_ran() if ledger.worth_saying("never ran: " + m)]
    if missed:
        save_state(path, state)
    for_user = "prose-guard: " + "; ".join(missed) + "." if missed else ""

    # One line to the person, every time a message is actually checked, whether or not anything was
    # wrong with it. Advice goes to the model and a denial is a permission prompt, so until now the
    # only outcome the person saw was a block — and a check that quietly stopped covering something
    # looked exactly like a check that had nothing to say. Silence here now means one thing: nothing
    # was checked. That is what makes a miss visible without reading a transcript.
    #
    # It costs the agent nothing. `systemMessage` reaches the person and not the model.
    for_user = " ".join(x for x in (for_user, tally(level, rewrites, len(advice), calls, ctx.audience)) if x)

    if not advice and not for_user:
        allow()
    emit("advise", (" ".join(advice) + " Advice from a noisy check, not a blocker.") if advice else "",
         for_user=for_user)


if __name__ == "__main__":
    main()
