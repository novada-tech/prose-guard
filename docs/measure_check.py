#!/usr/bin/env python3
"""Does a check discriminate, or does it just fire? Run this on any check you add or change.

    python3 docs/measure_check.py                       every check
    python3 docs/measure_check.py --check sentence      one of them
    python3 docs/measure_check.py --negatives mine/*.md --reps 2

A check that fails everything carries no information, and neither does one that fails nothing. Both
cost a model call and one of them costs a blocked turn as well. So every check has to be measured in
both directions:

    positives   messages written to carry that check's defect. It must FAIL these.
    negatives   ordinary well-built prose. It must PASS these.

The sentence check once failed 14 of 15 real messages, including messages written with no guidance at
all. It looked like a strict check and was a broken one.

`--reps 2` asks each question twice on the same text and reports how often the answer changes. A check
that disagrees with itself more than it disagrees with your fixtures is not measuring anything, and no
threshold you pick on top of it will help.

Add your own positives to POSITIVES below when you add a check. Three is enough to catch a check that
never fires; it is not enough to claim a rate.
"""
import argparse
import concurrent.futures as cf
import glob
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "plugins", "prose-guard", "lib"))
sys.path.insert(0, LIB)

import audiences  # noqa: E402
from checks import ask as _ask  # noqa: E402
from checks import for_effort  # noqa: E402

PAD = (" This has been in place since the start of the month and nobody has reported anything else "
       "unusual on the affected hosts.")

# Written to carry one specific defect. Keyed by check name.
POSITIVES = {
    "terms": [
        ("bare acronym", "The SFTR path now runs through the new cluster." + PAD),
    ],
    "relevance": [
        ("no reason to care", "The exporter line was deleted from set-java-env.sh in commit 4f21a09 "
                              "and the variable is no longer written at shell start. The change "
                              "touched one file and fourteen lines." + PAD),
        ("proof of testing", "Shells no longer need a daily login. I ran the full suite twice and "
                             "all 340 tests pass, and I checked the plan output by hand three times "
                             "to be sure nothing regressed." + PAD),
        ("nothing to act on", "Your shell will stop asking you to log in every day, because the "
                              "variable that caused it is gone. The fallback happens "
                              "automatically." + PAD),
    ],
    "structure": [
        ("two ideas in one", "Shells no longer need a daily login, and separately the chart version "
                             "moved to 1.14.2 which changes the annotation format for anyone "
                             "templating it by hand, so check your values file." + PAD),
        ("buried lede", "There is a file called set-java-env.sh sourced from bash_aliases.sh. It has "
                        "been there a long time. It exports a token. Shells therefore no longer "
                        "need a daily login, which is the point of this message." + PAD),
        ("forward dependency", "Because of that fallback you will notice no difference on a laptop. "
                               "The fallback is the application default credential, used when the "
                               "variable is absent. The variable is the one the exporter set." + PAD),
    ],
    "sentence": [
        ("the action is buried", "Because the token minted at shell start now expires after an hour "
                                 "and the provider prefers it over the fallback credential, which is "
                                 "why plans started failing mid-afternoon, you will want to run "
                                 "`gcloud auth application-default login` before your next "
                                 "deploy." + PAD),
        ("three stacked claims", "The exporter was removed, the provider now falls back to the "
                                 "application default credential, CI sets the variable itself so "
                                 "nothing changes there, and laptops therefore no longer need the "
                                 "daily login, which also fixes the plan failures." + PAD),
        ("version hidden in a parenthesis",
         "Anyone still on the old chart should upgrade at some point soon (you need 1.14.2 or later, "
         "earlier ones drop the annotation) and then restart their shells." + PAD),
    ],
    "reference": [
        ("coined label", "The silent row is the one worth prioritising, since it is the only case "
                         "where nothing surfaces to the caller. The other two at least raise "
                         "something you can see." + PAD),
        ("distant pronoun", "The exporter wrote a token at shell start. Terraform preferred it over "
                            "the fallback. CI sets its own. Laptops read nothing. It is now gone, so "
                            "the daily prompt stops." + PAD),
        ("invented name", "The startup credential shim is what caused this, so removing it fixes the "
                          "daily login prompt for everyone on a laptop." + PAD),
    ],
}

# the directory holds messages and nothing else, so its own README lives one level up
DEFAULT_NEGATIVES = os.path.join(HERE, "fixtures", "well-built", "*.md")


class Ctx:
    def __init__(self, audience):
        self.audience = audience
        self.situation = {"destination": "a draft being measured, not sent"}


def cell(job):
    check, kind, tag, text, ctx, rep = job
    finding = check.run(text, ctx)
    return {"check": check.NAME, "kind": kind, "tag": tag, "rep": rep,
            "failed": finding is not None,
            "why": (finding.message[:140] if finding else "")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="append", help="check name; repeatable, default all of them")
    ap.add_argument("--negatives", default=DEFAULT_NEGATIVES,
                    help="glob of ordinary well-built prose files it must PASS")
    ap.add_argument("--audience", help="measure against this audience instead of the baseline")
    ap.add_argument("--reps", type=int, default=1, help="ask each question N times; 2 shows drift")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    checks = [c for c in for_effort("high")
              if not a.check or c.NAME in a.check]
    if not checks:
        raise SystemExit(f"no such check. available: "
                         f"{', '.join(c.NAME for c in for_effort('high'))}")

    if a.audience:
        aud = audiences.ALL.get(a.audience)
        if aud is None:
            raise SystemExit(f"no audience called {a.audience!r}")
        ctx = Ctx(audiences.Resolved([aud]))
    else:
        ctx = Ctx(audiences.resolve({}))

    negatives = []
    for path in sorted(glob.glob(a.negatives)):
        text = open(path, errors="replace").read()
        if len(text.split()) >= 25:
            negatives.append((os.path.basename(path), text))
    if not negatives:
        print(f"no negatives matched {a.negatives!r} — a check cannot be validated in one direction "
              f"only, so this run will only tell you whether it fires at all.\n")

    jobs = []
    for check in checks:
        for tag, text in POSITIVES.get(check.NAME, []):
            for rep in range(a.reps):
                jobs.append((check, "positive", tag, text, ctx, rep))
        for tag, text in negatives:
            for rep in range(a.reps):
                jobs.append((check, "negative", tag, text, ctx, rep))
    print(f"{len(jobs)} calls over {len(checks)} check(s), "
          f"{sum(len(POSITIVES.get(c.NAME, [])) for c in checks)} positives, "
          f"{len(negatives)} negatives\n", flush=True)

    rows = []
    with cf.ThreadPoolExecutor(max_workers=a.workers) as pool:
        for row in pool.map(cell, jobs):
            rows.append(row)

    print(f"{'check':12s} {'catches the defect':>19s} {'passes real prose':>19s} "
          f"{'disagrees with itself':>22s}")
    for check in checks:
        mine = [r for r in rows if r["check"] == check.NAME]
        pos = [r for r in mine if r["kind"] == "positive"]
        neg = [r for r in mine if r["kind"] == "negative"]
        drift = []
        for tag in {r["tag"] for r in mine}:
            answers = {r["failed"] for r in mine if r["tag"] == tag}
            if len({r["rep"] for r in mine if r["tag"] == tag}) > 1:
                drift.append(len(answers) > 1)
        print(f"{check.NAME:12s} "
              f"{sum(1 for r in pos if r['failed']):10d}/{len(pos):<8d} "
              f"{sum(1 for r in neg if r['failed'] is False):10d}/{len(neg):<8d} "
              f"{(f'{100 * st.mean(drift):.0f}%' if drift else 'not asked twice'):>22s}")

    misses = [r for r in rows if r["kind"] == "positive" and not r["failed"]]
    alarms = [r for r in rows if r["kind"] == "negative" and r["failed"]]
    if misses:
        print("\nplanted defects it did not see:")
        for r in misses:
            print(f"  {r['check']:12s} {r['tag']}")
    if alarms:
        print("\nfalse alarms on ordinary prose — read these before dismissing them, some are fair:")
        for r in alarms:
            print(f"  {r['check']:12s} {r['tag']:28s} {r['why'][:90]}")
    print(f"\nchecker model: {_ask.MODEL} effort: {_ask.EFFORT} — say so when you report this.")


if __name__ == "__main__":
    main()
