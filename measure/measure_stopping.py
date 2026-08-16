#!/usr/bin/env python3
"""How do you know when a text is finished, if every check reports the worst thing it can find?

    python3 measure/measure_stopping.py --reps 3

The comparative checks each report the single worst instance of their concern, so "it complained" cannot
mean "the text is bad" — a check will complain about good prose too, given something to compare. The
question this answers is whether anything separates the two, and the answer turns out to be how often a
complaint reproduces.

Three documents, all real:

    agent-written   the version an agent wrote, before a senior engineer edited it
    human-edited    the same content after that edit, on the same day, for the same readers
    heavily-edited  a long document already taken through six rounds of this tool

Each check runs twice per pass. A finding is CONFIRMED when both runs point at the same sentence, and
LOOSE when only one run raises it. If the design works, the agent-written version carries confirmed
findings and the other two carry loose ones or none.

Real calls: three documents times reps times up to ten calls each.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "plugins", "prose-guard", "lib")
sys.path.insert(0, LIB)

import audiences  # noqa: E402
import checks as checks_module  # noqa: E402
from checks import Context, sequence  # noqa: E402

WHO = "Engineers on this team, reading a message about a change to their own tooling."


def Ctx() -> Context:
    """The shipped Context, so a harness cannot measure a shape nothing runs."""
    return checks_module.Context(audiences.Resolved([], "engineers"),
                                 {"who": WHO, "situation": "a chat message read once"})


def pass_over(text: str, ctx: Context) -> tuple[list[str], list[str]]:
    """One pass of every comparative check, each finding put back to the same check."""
    confirmed, loose = [], []
    for check in sequence.phases():
        try:
            finding = check.run(text, ctx)
        except Exception:
            continue
        if finding is None:
            continue
        if checks_module.confirms(check, text, ctx, finding):
            confirmed.append(check.NAME)
        else:
            loose.append(check.NAME)
    return confirmed, loose


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--gold", default=os.path.join(HERE, "fixtures", "gold"),
                    help="directory holding agent-written.txt and human-edited.txt")
    a = ap.parse_args()
    ctx = Ctx()

    documents = [("agent-written", os.path.join(a.gold, "agent-written.txt")),
                 ("human-edited", os.path.join(a.gold, "human-edited.txt")),
                 ("heavily-edited", os.path.join(HERE, "fixtures", "long-body.md"))]
    for _, path in documents:
        if not os.path.isfile(path):
            raise SystemExit(f"missing {path}")

    print(f"{a.reps} passes per document, every finding put back to the same check\n")
    print(f"{'document':16} {'words':>6} {'confirmed per pass':>20} {'loose per pass':>16}")
    for label, path in documents:
        text = open(path).read().strip()
        firm, weak = [], []
        for _ in range(a.reps):
            confirmed, loose = pass_over(text, ctx)
            firm.append(len(confirmed))
            weak.append(len(loose))
        print(f"{label:16} {len(text.split()):6} "
              f"{sum(firm) / len(firm):>10.1f} {str(firm):>9} "
              f"{sum(weak) / len(weak):>7.1f} {str(weak):>7}")
    print("\nMeasured at three passes: agent-written 2.0 confirmed per pass, human-edited 1.3, heavily")
    print("edited 0.7. The order is right, so the count is a signal of relative quality. But the")
    print("human-edited version never reached zero, so \"nothing confirmed\" is NOT a finished signal:")
    print("the bar is set such that a senior engineer's own writing still draws one or two findings a")
    print("pass. Until that is calibrated, the stopping rule is that the count stops falling, and a")
    print("reader who disagrees with a finding is allowed to be right.")
    print("\nCalibrating it needs more before-and-after pairs than the one in fixtures/gold, from more")
    print("than one author. Tuning five prompts against a single pair would fit the pair, not the bar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
