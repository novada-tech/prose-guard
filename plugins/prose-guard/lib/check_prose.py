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
from checks import BLOCK, config, for_effort, passes_for, pooled  # noqa: E402


class Context:
    def __init__(self, audience, who=None):
        self.audience = audience
        self.situation = {"destination": "a draft being checked before it is sent anywhere"}
        if who:
            self.situation["who the author says reads this"] = who


# What a person's own writing scores here, measured on one message a senior engineer rewrote himself:
# 1.3 confirmed findings a pass, and never zero. So zero is not the target and pretending otherwise
# sends someone chasing a bar that good prose does not clear. See docs/reference.md and
# measure/measure_stopping.py.
HUMAN_BASELINE = 2


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
    if problems <= HUMAN_BASELINE and earlier and problems >= min(earlier[-2:] or [problems]):
        return (line + f"\nIt has stopped falling, and {problems} is what a person's own writing scores "
                f"here — one message a senior engineer rewrote himself measured 1.3 a pass, never zero. "
                f"This is done. Disagreeing with what is left is allowed.")
    if not earlier:
        return (line + "\nFix them and run this again. What matters is whether the count falls, not "
                "whether it reaches zero: good prose does not reach zero here.")
    if problems < earlier[-1]:
        return line + "\nStill falling. Fix them and run this again."
    return (line + "\nNo lower than last pass. Either the remaining findings are wrong, or they need a "
            "change you have decided not to make. Stopping here is a defensible answer.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="file to check; omit to read stdin")
    ap.add_argument("--for", dest="audience",
                    help="an audience or baseline name — this is what sets the vocabulary. "
                         "See audiences.py list")
    ap.add_argument("--who",
                    help="describe the reader in a sentence, for the model-based checks. It cannot "
                         "change which terms are known; use --for for that")
    ap.add_argument("--passes", type=int, metavar="N",
                    help="override how many times each check runs. The default scales with the length "
                         "of the text, and is the same number the hook uses on the same text")
    ap.add_argument("--effort", choices=[x for x in config.LEVELS if x != "disabled"],
                    default="high")
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

    ctx = Context(resolved, a.who)
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
    passes = a.passes or passes_for(text)
    print(f"{passes} runs of each check, from the length of the text")
    problems, loose = 0, 0
    for check in for_effort(a.effort):
        found, firm = pooled(check, text, ctx, passes)
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
    print(verdict(a.file, problems, passes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
