#!/usr/bin/env python3
"""Does a check find more, and argue with itself less, when it is given one paragraph at a time?

    python3 measure/measure_splitting.py --reps 3

A fragment with no main verb got through a 370-word document while the same checks found it three times
in three when asked about that sentence alone. That looks like dilution: a check told to find the worst
sentence in twenty picks a different one each run. If so, splitting is worth its extra calls.

Splitting is not one decision for all checks, and the prompts say why:

    local   `sentence`, `mechanics`   about one sentence. A paragraph alone is enough context.
    prefix  `reference`               asks whether a pronoun's subject is "several sentences away" and
                                      whether a name appears "anywhere else". Needs what came BEFORE,
                                      so an isolated middle paragraph makes every pronoun look
                                      unanchored.
    whole   `relevance`, `structure`, `address`
                                      about the document: what is missing, what order it is in, who is
                                      addressed. A paragraph cannot answer any of them.

So this measures two things: whether splitting helps the local check, and whether splitting the prefix
check the same way produces the false positives that taxonomy predicts.

Real calls, so real tokens: two documents, two conditions, plus the prefix probe.
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "plugins", "prose-guard", "lib")
sys.path.insert(0, LIB)

import audiences  # noqa: E402
from checks import Check, Context, sequence  # noqa: E402

WHO = ("Engineers on this team reading a pull request description for a plugin they use but did not "
       "write. They know git and the shell.")
# The sentence that got through, and the same paragraph written properly.
BROKEN = ("Every command-line destination gets this. Both the part that extracts the text and the part "
          "that complains when it cannot read the destination's own list of text-carrying flags, rather "
          "than a list kept in the code.")
WHOLE = ("Every command-line destination gets this. Extraction and the complaint both read the "
         "destination's own list of text-carrying flags, rather than a list hard-coded in one place.")


def Ctx(who: str) -> Context:
    """The shipped Context, so a harness cannot measure a shape nothing runs."""
    return Context(audiences.Resolved([], "engineers"),
                   {"who": who, "situation": "a pull request description"})


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.split()) > 12]


def phase(name: str) -> sequence.Phase:
    return next(p for p in sequence.phases() if p.NAME == name)


def ask(check: Check, text: str, ctx: Context) -> str | None:
    try:
        finding = check.run(text, ctx)
    except Exception:
        return None
    return finding.message if finding else None


def points_at_fragment(message: str | None) -> bool:
    return bool(message) and ("Both the part that extracts" in message
                              or "rather than a list kept in the code" in message)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--document", default=os.path.join(HERE, "fixtures", "long-body.md"),
                    help="a document long enough to dilute a defect")
    a = ap.parse_args()
    ctx = Ctx(WHO)
    clean = open(a.document).read().strip()
    # The fixture is line-wrapped, so the paragraph is found on normalised whitespace and replaced
    # paragraph-wise. Matching the exact string failed silently once and cost an hour.
    # Paragraphs are normalised to one line each, so a wrapped sentence can be found and replaced.
    # Matching the exact wrapped string failed silently, which is why this asserts instead.
    clean = "\n\n".join(" ".join(p.split()) for p in re.split(r"\n\s*\n", clean) if p.strip())
    target = " ".join(WHOLE.split())
    if target not in clean:
        raise SystemExit(f"{a.document} must contain this sentence pair:\n{WHOLE}")
    defective = clean.replace(target, " ".join(BROKEN.split()))

    sentence = phase("sentence")
    print(f"{len(clean.split())} words, {len(paragraphs(clean))} paragraphs, {a.reps} reps\n")
    print(f"{'condition':34} {'found the fragment':>19} {'complained about clean prose':>29}")
    for label, splitter in (("whole document", lambda t: [t]),
                            ("one paragraph at a time", paragraphs)):
        caught = calls = noise = 0
        for _ in range(a.reps):
            for piece in splitter(defective):
                calls += 1
                if points_at_fragment(ask(sentence, piece, ctx)):
                    caught += 1
            for piece in splitter(clean):
                calls += 1
                if ask(sentence, piece, ctx):
                    noise += 1
        print(f"{label:34} {caught}/{a.reps:<17} {noise} finding(s) over "
              f"{a.reps * len(splitter(clean))} run(s)")
        print(f"{'':34} {calls} model calls")

    # The prediction that would make naive splitting wrong.
    print("\nreference, which needs what came before:")
    middle = paragraphs(clean)[len(paragraphs(clean)) // 2]
    reference = phase("reference")
    for label, text in (("that paragraph alone", middle),
                        ("with everything before it", clean[:clean.index(middle) + len(middle)])):
        raised = sum(1 for _ in range(a.reps) if ask(reference, text, ctx))
        print(f"  {label:30} complained in {raised}/{a.reps} runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
