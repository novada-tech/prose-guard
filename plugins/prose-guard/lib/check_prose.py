#!/usr/bin/env python3
"""Run the checks against a piece of text on demand, and print what they object to.

Same checks, same order and same prompts as the hook — `checks.for_effort` is the one list both use.
Two differences: this runs when you ask rather than when text is leaving, and it defaults to the most
thorough level whatever the hook is set to, because this is one deliberate run rather than every
message you send.

    python3 lib/check_prose.py draft.md --for platform-team
    python3 lib/check_prose.py draft.md --for engineers --who "the ops rota, arriving cold"
    python3 lib/check_prose.py draft.md --effort low        # no model call at all

The two flags do different jobs and are not interchangeable.

`--for` picks the vocabulary. Name a measured audience and its terms apply exactly as they would if
the text were being sent there. Name a shipped baseline — `engineers` is the one that ships — and the
term check will hold a message back against that, because you asked for it explicitly rather than the
tool guessing. Without `--for`, nothing is measured about the reader and terms are reported as a guess.

`--who` describes the reader in a sentence, for the model-based checks to read. It cannot change which
terms are known, because a sentence is not a vocabulary. Use both together when no measured audience
fits: `--for engineers` for the terms, `--who` for everything else.
"""
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audiences  # noqa: E402
import paths  # noqa: E402
import telling  # noqa: E402
from checks import (BLOCK, Context, ceiling_for, config, costs_a_call,  # noqa: E402
                    for_effort, pooled)


# What a deliberate run may cost is decided by `ceiling_for` and by how much is wrong, and there is no
# separate budget here on purpose.
#
# A flat cap was tried and reverted, because of what it did rather than what it saved: at 40 calls it
# bound above 800 words, so a 5,000-word document got the same 8 runs a check as an 800-word one, and
# the whole point of scaling runs with length is that a long document deserves more care. This is the
# path somebody chose to run on one document, not something paid on every message.
#
# It was never unbounded — MOST_RUNS caps each check at 25, so the worst case is 25 x the model-backed
# checks, and reaching it needs every single run to surface something new. The real defect the review
# found was a claim: the rewrite skill said "four model calls" and then said to run it again. What
# needed fixing was the sentence, and `worst_case()` below now says the number out loud before
# anything is spent.


def context_for(audience, who=None):
    situation = {"destination": "a draft being checked before it is sent anywhere"}
    if who:
        situation["who the author says reads this"] = who
    return Context(audience, situation)


# There is no absolute bar here, and there was one until a reviewer asked what it rested on.
#
# It rested on a single message that one engineer rewrote in a hurry — 1.3 confirmed findings a pass —
# and the tool reported that number back as "what a person's own writing scores", which is a claim one
# hasty example cannot support. A careful piece may well reach zero, and telling somebody to stop at two
# because of that sample is telling them to stop short.
#
# What survives is the relative signal, which is measured and is the person's own: a count that has
# stopped falling across their own passes. Whether it stopped at two or at zero is theirs to judge.
# Making an absolute bar honest would need before-and-after pairs from several authors, deliberately
# written — see docs/design-notes.md, "When is a text finished: no honest answer yet".


def history(path):
    """Confirmed counts from earlier passes over this same file, oldest first."""
    if not path:
        return [], None
    where = paths.at("passes", hashlib.sha1(os.path.abspath(path).encode()).hexdigest()[:16] + ".json")
    try:
        with open(where) as fh:
            return list(json.load(fh)), where
    except Exception:
        return [], where


def verdict(path, problems, passes=1):
    """What the count means, and whether to keep going.

    The count of confirmed findings is the only signal available, and it is a relative one: it orders a
    badly written text above a well written one but does not reach zero on good prose. So what a reader
    needs is not this pass in isolation but whether it is still falling.
    """
    earlier, where = history(path)
    if passes > 1:
        line = f"{problems} check(s) found something, pooled over {passes} runs each"
    else:
        line = f"{problems} confirmed finding(s) this pass"
    if earlier:
        line += " (was " + ", then ".join(str(n) for n in earlier[-3:]) + ")"
    if where:
        try:
            os.makedirs(os.path.dirname(where), exist_ok=True)
            with open(where, "w") as fh:
                json.dump((earlier + [problems])[-6:], fh)
        except OSError:
            pass
    if problems == 0:
        return line + "\nNothing to change."
    if passes > 1:
        return (line + "\nAn item marked as seen more than once is one a reader can rely on; an item seen"
                "\nonce is this check sampling from what is above its bar, which on a document with real"
                "\ndefects means a different real one each run. Fix what you agree with, in one edit, and"
                "\nrun this again — that is one round trip instead of one per finding.")
    if earlier and problems >= min(earlier[-2:] or [problems]):
        return (line + "\nIt has stopped falling. That is the signal this tool has — a count that keeps "
                "dropping means the edits are landing, and one that has levelled off means they are not. "
                "Whether what is left is worth fixing is yours to judge, and disagreeing with it is "
                "allowed.")
    if not earlier:
        return (line + "\nFix them and run this again. What matters is whether the count falls, not "
                "whether it reaches zero: good prose does not reach zero here.")
    if problems < earlier[-1]:
        return line + "\nStill falling. Fix them and run this again."
    return (line + "\nNo lower than last pass. Either the remaining findings are wrong, or they need a "
            "change you have decided not to make. Stopping here is a defensible answer.")


def main():
    ap = argparse.ArgumentParser(
        description="Check a draft the way the guard checks a message, and say what it would "
                    "say. Spends real model calls above `low` — up to 40 for one run — and "
                    "writes nothing except a record of how many findings each pass confirmed, "
                    "which is what tells you whether the last edit helped.")
    ap.add_argument("file", nargs="?", help="file to check; omit to read stdin")
    ap.add_argument("--for", dest="audience",
                    help="an audience or baseline name — this is what sets the vocabulary. "
                         "See audiences.py list")
    ap.add_argument("--who",
                    help="describe the reader in a sentence, for the model-based checks. It cannot "
                         "change which terms are known; use --for for that")
    ap.add_argument("--effort", choices=[x for x in config.LEVELS if x != "disabled"],
                    default="high",
                    help="how hard to look, and what it costs. `low` is the two arithmetic checks and "
                         "no model call; `medium` adds one combined judgement call; `high` (the "
                         "default here, because this is one deliberate run) asks each concern "
                         "separately and re-asks while the answers keep changing")
    a = ap.parse_args()

    text = open(a.file).read() if a.file else sys.stdin.read()
    if not text.strip():
        ap.print_help()
        return 2

    if a.audience:
        aud = audiences.ALL.get(a.audience)
        if aud is None:
            # Say what IS there, and where it is looked for. An audience can vanish — a config
            # directory gets cleaned up, PROSE_GUARD_HOME differs between two shells — and "no such
            # audience" on its own leaves you guessing which of those happened.
            have = ", ".join(sorted(audiences.ALL)) or "none"
            raise SystemExit(f"No audience called {a.audience!r}.\n"
                             f"  looked in: {audiences.user_dir()}\n"
                             f"  found:     {have}\n"
                             f"Create it with /prose-guard:audiences, or pass --who to describe the "
                             f"reader in your own words instead.")
        resolved = audiences.Resolved([aud])
    else:
        resolved = audiences.resolve({})

    ctx = context_for(resolved, a.who)
    # Say what each half is working from. Reporting only "none named" hid the fact that a --who was
    # passed and used, so a reader could not tell whether their sentence had done anything.
    if resolved.resolved:
        print(f"terms judged against: {', '.join(resolved.names)}"
              f"{' (a shipped baseline, not measured for your readers)' if all(audiences.ALL[n].builtin for n in resolved.names) else ''}")
    else:
        print(f"terms judged against: the '{resolved.fallback}' baseline — nothing is measured for "
              f"your readers, so findings are a guess and nothing is held back.")
        print(f"                      `--for {resolved.fallback}` enforces against it; "
              f"/prose-guard:audiences measures your own.")
    if a.who:
        print(f'reader described as:  "{a.who}"  (read by the model-based checks, not by terms)')
    running = for_effort(a.effort)
    passes = ceiling_for(text)
    paying = sum(1 for c in running if costs_a_call(c))
    print(f"up to {passes} runs of each check, stopping when a run adds nothing "
          f"— at most {passes * paying} model calls, and one per check if nothing is wrong")
    problems, loose, spent = 0, 0, 0
    for check in running:
        found, firm, cost = pooled(check, text, ctx, passes)
        spent += cost
        if not found:
            print(f"  {check.NAME:10s} ok")
            continue
        problems += 1
        loose += len(found) - len(firm)
        mark = "must fix" if firm and found[0].severity == BLOCK else "consider"
        for n, finding in enumerate(found):
            print(f"  {check.NAME:10s} [{mark}] {finding.message}" if n == 0
                  else f"  {'':10s}            {finding.message}")
    print()
    for missed in telling.never_ran():
        # A check that never ran reads exactly like a check that passed, so it is said out loud rather
        # than left to be inferred from a clean report.
        print(f"  NOT CHECKED: {missed}")
    print(f"{spent} model call(s) spent.")
    print(verdict(a.file, problems, passes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
