#!/usr/bin/env python3
"""Run the checks against a piece of text on demand, and print what they object to.

Same checks, same order and same prompts as the hook — `checks.for_effort` is the one list both use.
Two differences: this runs when you ask rather than when text is leaving, and it defaults to the most
thorough level whatever the hook is set to, because this is one deliberate run rather than every
message you send.

    python3 lib/check_prose.py draft.md --for platform-team
    cat draft.md | python3 lib/check_prose.py --who "the #dev channel, arriving cold"
    python3 lib/check_prose.py draft.md --effort low        # no model call at all

Name an audience with --for and its measured vocabulary applies, exactly as it would if the text were
being sent there. Without one, nothing is measured about the reader, so terms are reported as a guess.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audiences  # noqa: E402
from checks import BLOCK, config, for_effort  # noqa: E402


class Context:
    def __init__(self, audience, who=None):
        self.audience = audience
        self.situation = {"destination": "a draft being checked before it is sent anywhere"}
        if who:
            self.situation["who the author says reads this"] = who


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="file to check; omit to read stdin")
    ap.add_argument("--for", dest="audience", help="an audience name; see audiences.py list")
    ap.add_argument("--who", help="describe the reader in your own words, if no audience fits")
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
            raise SystemExit(f"no audience called {a.audience!r}. Try: "
                             f"python3 lib/audiences.py list")
        resolved = audiences.Resolved([aud])
    else:
        resolved = audiences.resolve({})

    ctx = Context(resolved, a.who)
    print(f"audience: {', '.join(resolved.names) if resolved.resolved else 'none named, assuming ' + str(resolved.fallback)}")
    problems = 0
    for check in for_effort(a.effort):
        finding = check.run(text, ctx)
        if finding is None:
            print(f"  {check.NAME:10s} ok")
            continue
        problems += 1
        mark = "must fix" if finding.severity == BLOCK else "consider"
        print(f"  {check.NAME:10s} [{mark}] {finding.message}")
    if not problems:
        print("\nNothing to change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
