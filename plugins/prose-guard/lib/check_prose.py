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
from checks import BLOCK, _points_at, config, confirms, for_effort  # noqa: E402


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


def pooled(check, text, ctx, passes, unconfirmed):
    """Findings from several runs of one check, pooled into one report.

    A check returns exactly one item however it is asked. Measured on a 295-word document with about ten
    known defects, asking for up to five items produced one item a run in every condition — so the single
    item is what the check does, not a contract that can be widened.

    What can be widened is the number of runs. Each run picks one item from those above its bar, and two
    runs pick differently, which is the instability that made a rewrite loop feel endless. Pooled instead
    of compared, that sampling is a list: N runs, N calls, and ONE round trip, against N passes costing N
    round trips. A turn spent reading a finding and editing is dearer than the check's own call.

    Items seen more than once are marked, because they are the ones a reader can rely on.
    """
    if passes <= 1 or not check.COSTS_A_CALL:
        return check.run(text, ctx)
    seen, order = {}, []
    for _ in range(passes):
        finding = check.run(text, ctx)
        if finding is None:
            continue
        spot = _points_at(text, finding)
        if spot in seen:
            seen[spot] = (seen[spot][0] + 1, seen[spot][1])
            continue
        seen[spot] = (1, finding)
        order.append(spot)
    if not order:
        return None
    lines = []
    for spot in order:
        times, finding = seen[spot]
        lines.append(("[seen in " + str(times) + f" of {passes} runs] " if times > 1
                      else f"[once in {passes} runs] ") + finding.message)
    first = seen[order[0]][1]
    return first._replace(message="\n             ".join(lines))


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
    ap.add_argument("--passes", type=int, default=1, metavar="N",
                    help="run each check N times and pool what they find, marking how often each item "
                         "came up. N calls and one round trip, instead of N passes and N round trips")
    ap.add_argument("--unconfirmed", action="store_true",
                    help="report every finding, including ones the check does not raise twice. "
                         "Costs less and gives you nits to chase")
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
    problems = 0
    unconfirmed = []
    for check in for_effort(a.effort):
        finding = pooled(check, text, ctx, a.passes, unconfirmed)
        if finding is None:
            print(f"  {check.NAME:10s} ok")
            continue
        # Every finding is put to the same check a second time, and kept only if it objects to the same
        # sentence. Ten runs of the model-based checks over one document that had already been through
        # six rounds of editing produced nine findings and no repeats: past the substantive problems,
        # they generate nits, and acting on nits is work with no end. See docs/thresholds.md.
        if a.passes == 1 and not a.unconfirmed and not confirms(check, text, ctx, finding):
            unconfirmed.append((check.NAME, finding.message))
            print(f"  {check.NAME:10s} ok (raised something once and not again — see below)")
            continue
        problems += 1
        mark = "must fix" if finding.severity == BLOCK else "consider"
        print(f"  {check.NAME:10s} [{mark}] {finding.message}")
    if unconfirmed:
        print("\nRaised once and not reproduced, so not worth acting on. Read them, do not chase them:")
        for name, message in unconfirmed:
            print(f"  {name}: {message[:160]}")
    print()
    print(verdict(a.file, problems, a.passes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
