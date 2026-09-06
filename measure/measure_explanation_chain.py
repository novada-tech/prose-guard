#!/usr/bin/env python3
"""How often is one unexplained term the writer's attempt to explain another?

    python3 measure/measure_explanation_chain.py --repo /path/to/your/repo --min-authors 4

Free and deterministic: it reads git history already on the machine and runs the `terms` check, which
makes no model call. Point it at repositories whose commit messages you can read; with no `--repo` it
scores this one, which is small enough that the answer will be mostly noise.

The vocabulary is held out. It is learned from the OLDEST fifth of each repository's history and the
newer messages are the ones scored, because scoring a corpus against a vocabulary learned from the
same corpus says only that the corpus agrees with itself.

Then, among findings that list two or more unknown terms, it counts three readings of "one of these
was the attempt to explain the other", loosest last. What it found on 5,113 documents, and why the
first row cannot move, is in docs/design-notes.md.
"""
from __future__ import annotations

import argparse
import collections
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "plugins", "prose-guard", "lib"))

import jargon  # noqa: E402

# How far past a term's first mention an appositive is still plausibly explaining it. Deliberately
# generous: the loosest of the three readings exists to put an upper bound on the frequency, so it
# should over-count rather than under-count.
APPOSITIVE = 120
SENTENCE_END = re.compile(r"[.!?]\s")
# The oldest share of each history, kept back to learn a vocabulary from and never scored.
TEACH_SHARE = 0.2


def commits(path: str) -> list[tuple[str, str]]:
    """(author, message) for one repository, newest first. Empty when the path is not a checkout."""
    if not os.path.exists(os.path.join(path, ".git")):
        return []
    out = subprocess.run(["git", "-C", path, "log", "--no-merges", "--format=%an%x01%B%x00"],
                         capture_output=True, text=True, errors="replace").stdout
    rows = []
    for chunk in out.split("\0"):
        if "\x01" not in chunk:
            continue
        who, _, text = chunk.strip().partition("\x01")
        if text.strip():
            rows.append((who.strip(), text.strip()))
    return rows


def vocabulary(teach: list[tuple[str, str]], min_authors: int) -> set[str]:
    """Terms enough separate people wrote for the audience to count as knowing them.

    The same author cut audiences.py applies, for the same reason: one person's habit is not a shared
    vocabulary. Its evidence is in docs/thresholds.md.
    """
    authors: dict[str, set[str]] = collections.defaultdict(set)
    for who, text in teach:
        body = jargon.prose(text)
        for term in set(t for t in jargon.ACRONYM.findall(body) if jargon.is_acronym(t)):
            authors[term.upper()].add(who)
    return {term for term, people in authors.items() if len(people) >= min_authors}


def inside_expansion(body: str, bad: list[str], said: dict[str, str]) -> list[tuple[str, str]]:
    """One flagged term inside the written-out form of another. The reducing version of the feature:
    it needs nothing this check does not already compute."""
    return [(term, other) for term in bad for other in bad
            if term != other and term in said and _uses(said[term], other)]


def inside_bracket(body: str, bad: list[str], said: dict[str, str]) -> list[tuple[str, str]]:
    """One flagged term inside a bracket whose preceding word is another flagged term — the shape of
    `ANTLR (the parser generator MWE2 drives)`, where Schwartz-Hearst found no pair so nothing was
    recorded and both terms are still unexplained."""
    out = []
    for match in jargon.INSIDE.finditer(body):
        head = body[max(0, match.start() - 40):match.start()].split()
        term = head[-1].strip(",;:") if head else ""
        if term in bad:
            out += [(term, other) for other in bad
                    if other != term and _uses(match.group(1), other)]
    return out


def in_apposition(body: str, bad: list[str], said: dict[str, str]) -> list[tuple[str, str]]:
    """One flagged term shortly after another, in the same sentence. An explanation written without a
    bracket looks like this, and so does any two terms a writer happened to put side by side — which
    is what makes this an upper bound rather than a detection."""
    out = []
    for term in bad:
        at = re.search(r"\b" + re.escape(term) + r"\b", body)
        if not at:
            continue
        window = body[at.end():at.end() + APPOSITIVE]
        stop = SENTENCE_END.search(window)
        window = window[:stop.start()] if stop else window
        out += [(term, other) for other in bad if other != term and _uses(window, other)]
    return out


def _uses(fragment: str, term: str) -> bool:
    return re.search(r"\b" + re.escape(term) + r"\b", fragment) is not None


READINGS = (("inside the written-out form of the other", inside_expansion),
            ("inside a bracket after the other", inside_bracket),
            (f"within {APPOSITIVE} characters, same sentence", in_apposition))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", action="append", metavar="PATH",
                    help="a git checkout whose commit messages to score. Repeatable. "
                         "Defaults to this repository.")
    ap.add_argument("--min-authors", type=int, default=4, metavar="N",
                    help="how many separate people must write a term for the audience to know it "
                         "(default: 4, the cut audiences.py uses)")
    ap.add_argument("--examples", type=int, default=8, metavar="N",
                    help="how many matching documents to print, so every hit can be judged by hand "
                         "rather than counted (default: 8)")
    args = ap.parse_args()

    rows: list[tuple[str, str]] = []
    for path in args.repo or [REPO]:
        got = commits(os.path.expanduser(path))
        print(f"{len(got):6d} commit messages from {path}")
        rows += got
    if not rows:
        sys.exit("no commit messages found — is --repo a git checkout?")

    cut = int(len(rows) * (1 - TEACH_SHARE))
    score, teach = rows[:cut], rows[cut:]      # git log is newest first, so the tail is the oldest
    known = vocabulary(teach, args.min_authors)
    print(f"       held out {len(teach)} oldest to learn {len(known)} terms past "
          f"{args.min_authors} authors, scoring {len(score)} newer")

    # This repository's own prose costs nothing and is on every machine, so it is always scored too.
    docs = [t for _, t in score]
    for path in sorted(glob.glob(os.path.join(REPO, "**", "*.md"), recursive=True)):
        docs.append(open(path, encoding="utf-8", errors="replace").read())
    for path in sorted(glob.glob(os.path.join(REPO, "measure", "fixtures", "**", "*"),
                                 recursive=True)):
        if os.path.isfile(path) and not path.endswith(".md"):
            docs.append(open(path, encoding="utf-8", errors="replace").read())

    import audiences
    from checks import terms
    from checks.context import Context

    everything = known | audiences.BASELINES.get("engineers", set())

    class Audience:
        resolved = True
        names = ["these committers"]

        def is_known(self, term: str) -> bool:
            return term.upper() in everything

        def meanings(self, term: str) -> dict:
            return {}

    ctx = Context(Audience())
    counts: collections.Counter = collections.Counter()
    shown: dict[str, list] = collections.defaultdict(list)
    for text in docs:
        if not terms.run(text, ctx):
            continue
        counts["findings"] += 1
        bad, _, said = jargon.examine(text, ctx.audience.is_known)
        if len(bad) < 2:
            continue
        counts["two or more unknown"] += 1
        body = jargon.prose(text)
        for label, reading in READINGS:
            got = reading(body, bad, said)
            if got:
                counts[label] += 1
                if len(shown[label]) < args.examples:
                    shown[label].append((got[:8], " ".join(text.split())[:150]))

    print(f"\n{len(docs)} documents, {counts['findings']} with a terms finding, "
          f"{counts['two or more unknown']} listing two or more unknown terms. Of those:")
    for label, _ in READINGS:
        print(f"  {counts[label]:6d}  one term {label}")
    print("\nEvery hit, to be judged by hand — a count is not a true positive:")
    for label, _ in READINGS:
        for pairs, head in shown[label]:
            print(f"  [{label}] {pairs}\n     {head}")


if __name__ == "__main__":
    main()
