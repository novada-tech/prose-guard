#!/usr/bin/env python3
"""Does one finding per check per pass scale, and does it cost more than reporting several at once?

    python3 measure/measure_batching.py --reps 3

Two objections to the single-finding contract, both of which look right on paper:

    A 100-word document and a 1,000-word one get one finding each, so the long one is held to a much
    lower bar for the same number of passes.

    Each pass costs a round trip - an agent turn to read the finding and edit the text - and a turn on
    the session's own context is dearer than the check's own call. Reporting several at once would pay
    that once instead of N times.

Whether the second follows from the first depends entirely on a fact that has to be measured: are the
extra items real? For a comparative check the second-worst item is by construction nearer the bar than
the worst, so a list could be one real finding followed by padding. This asks each check for up to five,
on a long document known to have many defects, and counts how many items reproduce across runs.

An item counts as reproduced when two runs point at the same sentence. That is the same test the tool
uses to decide whether to report a finding at all.
"""
import argparse
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "plugins", "prose-guard", "lib")
sys.path.insert(0, LIB)

import audiences  # noqa: E402
import checks as checks_module  # noqa: E402
from checks import Finding, sequence  # noqa: E402

ONE = "Reply with exactly one line and no reasoning: PASS, or FAIL: <what to change, quoting the span>."
MANY = ("Reply with PASS, or with one line for each failing span, worst first, up to five:\n"
        "FAIL: <what to change, quoting the span>")


class Ctx:
    def __init__(self):
        self.audience = audiences.Resolved([], "engineers")
        self.situation = {"who": "Engineers on this team reading a pull request description.",
                          "situation": "a pull request description"}


def items(message):
    """Split a reply into findings. One line each, however the check was asked."""
    parts = [p.strip(" :-") for p in re.split(r"(?:^|\n)\s*(?:FAIL:?)", message) if p.strip(" :-")]
    return parts or [message]


def where(text, part):
    return checks_module._points_at(text, Finding("advise", part))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("document", nargs="?",
                    default=os.path.join(HERE, "fixtures", "before-rewrite.md"))
    ap.add_argument("--checks", default="sentence,reference,structure")
    a = ap.parse_args()
    text = open(a.document).read().strip()
    ctx = Ctx()
    wanted = [n.strip() for n in a.checks.split(",")]
    print(f"{len(text.split())} words, {a.reps} runs per condition\n")
    print(f"{'check':11} {'asked for':10} {'items per run':>14} {'sentences reproduced':>21}")

    for name in wanted:
        check = next(p for p in sequence.phases() if p.NAME == name)
        where_prompt = check._path
        prompt = open(where_prompt).read()
        for label, instruction in (("one", ONE), ("five", MANY)):
            open(where_prompt, "w").write(prompt if instruction == ONE
                                          else prompt.replace(ONE, instruction))
            counts, seen = [], collections.Counter()
            for _ in range(a.reps):
                finding = check.run(text, ctx)
                found = items(finding.message) if finding else []
                counts.append(len(found))
                for part in found:
                    spot = where(text, part)
                    if spot >= 0:
                        seen[spot] += 1
            open(where_prompt, "w").write(prompt)          # always restored, even on a bad run
            repeated = sum(1 for n in seen.values() if n > 1)
            print(f"{name:11} {label:10} {sum(counts) / len(counts):>7.1f} {str(counts):>6} "
                  f"{repeated:>10} of {len(seen)} distinct")
    print("\nItems that reproduce are the ones a reader can act on. If asking for five yields five items")
    print("but only one reproduces, the contract is right and the objection about scaling needs a")
    print("different answer than a longer list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
