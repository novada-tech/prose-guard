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
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audiences  # noqa: E402
from checks import BLOCK, config, confirms, for_effort  # noqa: E402


class Context:
    def __init__(self, audience, who=None):
        self.audience = audience
        self.situation = {"destination": "a draft being checked before it is sent anywhere"}
        if who:
            self.situation["who the author says reads this"] = who


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="file to check; omit to read stdin")
    ap.add_argument("--for", dest="audience",
                    help="an audience or baseline name — this is what sets the vocabulary. "
                         "See audiences.py list")
    ap.add_argument("--who",
                    help="describe the reader in a sentence, for the model-based checks. It cannot "
                         "change which terms are known; use --for for that")
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
        finding = check.run(text, ctx)
        if finding is None:
            print(f"  {check.NAME:10s} ok")
            continue
        # Every finding is put to the same check a second time, and kept only if it objects to the same
        # sentence. Ten runs of the model-based checks over one document that had already been through
        # six rounds of editing produced nine findings and no repeats: past the substantive problems,
        # they generate nits, and acting on nits is work with no end. See docs/thresholds.md.
        if not a.unconfirmed and not confirms(check, text, ctx, finding):
            unconfirmed.append((check.NAME, finding.message))
            print(f"  {check.NAME:10s} ok (raised something once and not again — see below)")
            continue
        problems += 1
        mark = "must fix" if finding.severity == BLOCK else "consider"
        print(f"  {check.NAME:10s} [{mark}] {finding.message}")
    if not problems:
        print("\nNothing to change.")
    if unconfirmed:
        print("\nRaised once and not reproduced, so not worth acting on. Read them, do not chase them:")
        for name, message in unconfirmed:
            print(f"  {name}: {message[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
