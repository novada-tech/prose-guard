#!/usr/bin/env python3
"""Could the one cheap question be a GATE for the six expensive ones, instead of a lesser verdict?

    python3 measure/measure_gate.py --reps 2

`low` costs 0 model calls, `medium` 1, `high` 6 — one per paying check, because pooling stops on the first
empty run. And `medium`'s one call buys nothing that changes an outgoing message: its combined judgement
question only advises, and advice is inert (41 given, 0 acted on — `measure_advice.py`).

So the interesting question is not whether that question is a good VERDICT. It was measured as one and it
is not: 50-70% agreement with a real label, unstable between runs, which is why it never blocks. The
question is whether it is a good ALARM. A gate needs recall and almost no precision: if it says "something
is wrong here", the six specific checks then adjudicate and one of them can hold the message. A false alarm
costs six calls; a miss costs a message going out unchecked.

    recall     of texts the specific checks hold, how many does the gate flag?  MUST be high
    precision  of texts it flags, how many are really faulty?                   cheap to get wrong

If recall is high, a cascade is strictly better than today's ladder: a clean message costs 1 call instead
of 6, and a faulty one costs 7 instead of 6, while keeping the only mechanism shown to change what goes
out. If recall is low, a cascade is a cheaper way to miss things and the ladder should lose `medium`
instead.

Positives come from `held_drafts.py` — real messages the specific checks really held. Negatives are the
well-built fixtures every check must pass.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "plugins", "prose-guard", "lib"))

import audiences  # noqa: E402
import checks  # noqa: E402

AT_ONCE = 6


def gate() -> object:
    """The one combined question, which is what `medium` pays for."""
    return next(c for c in checks.for_effort("medium") if c.NAME == "judgement")


def negatives(extra: list[str] | None = None) -> list[tuple[str, str]]:
    out = []
    for path in (extra or []):
        with open(path) as fh:
            out.append((os.path.basename(path), fh.read()))
    if extra:
        return out
    for where in ("well-built", "well-built-long"):
        for path in sorted(glob.glob(os.path.join(HERE, "fixtures", where, "*.md"))):
            if os.path.basename(path) == "README.md":
                continue
            with open(path) as fh:
                out.append((os.path.basename(path), fh.read()))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--held", metavar="FILE", help="positives: what held_drafts.py wrote")
    ap.add_argument("--reps", type=int, default=2, help="how many times to ask each text")
    ap.add_argument("--negatives", nargs="*", metavar="FILE",
                    help="clean prose it must pass, instead of the built-in fixtures. Eleven fixtures "
                         "cannot carry a false-block rate; real prose that shipped can.")
    a = ap.parse_args()

    check = gate()
    ctx = checks.Context(audiences.Resolved([], "engineers"))
    jobs = []
    if a.held:
        with open(a.held) as fh:
            for n, item in enumerate(json.load(fh), 1):
                if item.get("body"):
                    jobs.append(("positive", f"held {n}", item["body"]))
    for name, text in negatives(a.negatives):
        jobs.append(("negative", name, text))

    def ask(job):
        kind, name, text = job
        fired = sum(1 for _ in range(a.reps) if check.run(text, ctx) is not None)
        return kind, name, fired

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=AT_ONCE) as pool:
        for got in pool.map(ask, jobs):
            rows.append(got)
            print(f"  {got[0]:8s} {got[1]:22s} fired {got[2]}/{a.reps}", flush=True)

    pos = [r for r in rows if r[0] == "positive"]
    neg = [r for r in rows if r[0] == "negative"]
    caught = sum(1 for r in pos if r[2])
    alarms = sum(1 for r in neg if r[2])
    print(f"\n  recall:    {caught}/{len(pos)} of texts the specific checks held were flagged")
    print(f"  precision: {len(neg) - alarms}/{len(neg)} well-built fixtures passed cleanly")
    if pos:
        print(f"\n  a gate at this recall lets {len(pos) - caught} of {len(pos)} faulty messages through "
              f"unchecked.")


if __name__ == "__main__":
    main()
