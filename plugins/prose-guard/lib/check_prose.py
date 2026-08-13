#!/usr/bin/env python3
"""Run the outgoing-prose checks against a piece of text, and print what they object to.

Same checks, same order and same prompts as the `guard-outgoing-prose` hook — `checks.for_effort`
is the single list both use. Two differences: this runs when you ask it to rather than when text
is leaving, and it defaults to the most thorough level whatever the hook is set to, because you
are paying for one deliberate run rather than for every message you send.

    python3 lib/check_prose.py draft.md
    cat draft.md | python3 lib/check_prose.py
    python3 lib/check_prose.py draft.md --audience "the #dev channel, arriving cold"
    python3 lib/check_prose.py draft.md --effort low    # no model call at all

At `high` this is four model calls of a few seconds each. `low` is the deterministic term check on
its own: instant, free, and the check with the best evidence behind it.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checks import config, for_effort  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="file to check; omit to read stdin")
    ap.add_argument("--audience", help="who reads this, in your own words. The checks read it.")
    ap.add_argument("--effort", choices=[lvl for lvl in config.LEVELS if lvl != "disabled"],
                    default="high", help="how much to run. Default high.")
    a = ap.parse_args()

    text = open(a.file).read() if a.file else sys.stdin.read()
    if not text.strip():
        ap.print_help()
        return 2

    envelope = {"audience": a.audience} if a.audience else {}
    problems = 0
    for check in for_effort(a.effort):
        ok, message = check.run(text, envelope)
        if ok:
            print(f"{check.NAME:10s} ok")
            continue
        problems += 1
        print(f"{check.NAME:10s} {message}")
    if not problems:
        print("\nNothing to change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
