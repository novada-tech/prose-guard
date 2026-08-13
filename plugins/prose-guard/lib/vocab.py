#!/usr/bin/env python3
"""Measure which acronyms your audience actually shares, from writing they have already done.

    python3 lib/vocab.py scan --git --gh your-org/your-repo --out candidates.json
    python3 lib/vocab.py scan --text notes/*.md --git
    python3 lib/vocab.py apply candidates.json          # writes vocabulary.json

Two steps on purpose. `scan` counts, which is arithmetic and needs no judgement. `apply` decides,
and the decisions worth a human are only the borderline ones — so scan sorts the candidates into
three piles and `/prose-guard:learn-vocabulary` walks you through the middle one.

Author BREADTH, not frequency. One person's favourite acronym is not shared knowledge however
often they type it: on the corpus this was calibrated against, one acronym occurred 149 times
from a single author. So every source carries an author, and text with no author counts once.

Nothing leaves your machine. `--gh` shells out to the `gh` CLI you are already logged into.
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vocabulary  # noqa: E402

ACRONYM = re.compile(r"\b([A-Z][A-Z0-9]{1,5})\b")
FENCE = re.compile(r"```.*?```", re.S)
INLINE = re.compile(r"`[^`]+`")
QUOTE = re.compile(r"^\s*>.*$", re.M)
BOT = re.compile(r"(\[bot\]|-bot$|dependabot|renovate|github-actions)", re.I)


def prose(text):
    """Code is not vocabulary. A term only counts where someone wrote it as a word."""
    return INLINE.sub(" ", QUOTE.sub(" ", FENCE.sub(" ", text or "")))


def from_git(repo="."):
    """Commit messages, with their authors. Free, local, and present in every repository."""
    try:
        out = subprocess.run(
            ["git", "-C", repo, "log", "--no-merges", "--format=%an%x00%s%n%b%x01"],
            capture_output=True, text=True, timeout=300).stdout
    except Exception:
        return
    for entry in out.split("\x01"):
        if "\x00" not in entry:
            continue
        author, body = entry.split("\x00", 1)
        author = author.strip()
        if author and not BOT.search(author):
            yield author, body


def from_gh(slug, limit=800):
    """Issues, pull requests and review comments, with their authors — the richest source there is,
    because a review comment is written to a colleague and so uses the shared vocabulary."""
    def run(args):
        try:
            return json.loads(subprocess.run(args, capture_output=True, text=True,
                                             timeout=900).stdout or "[]")
        except Exception:
            return []

    for kind in ("issue", "pr"):
        rows = run(["gh", kind, "list", "-R", slug, "--state", "all", "--limit", str(limit),
                    "--json", "author,title,body,comments"])
        for row in rows:
            who = ((row.get("author") or {}).get("login") or "").strip()
            if who and not BOT.search(who):
                yield who, f"{row.get('title') or ''}\n{row.get('body') or ''}"
            for c in row.get("comments") or []:
                cw = ((c.get("author") or {}).get("login") or "").strip()
                if cw and not BOT.search(cw):
                    yield cw, c.get("body") or ""


def from_text(paths):
    """Any prose you have. No author is available, so it counts as a single voice — which keeps it
    from ever alone reaching the shared-knowledge threshold."""
    for path in paths:
        try:
            with open(path, errors="replace") as fh:
                yield f"file:{os.path.basename(path)}", fh.read()
        except OSError:
            continue


def scan(sources):
    authors = collections.defaultdict(set)
    counts = collections.Counter()
    docs = 0
    for who, text in sources:
        docs += 1
        for term in set(ACRONYM.findall(prose(text))):
            authors[term.upper()].add(who)
            counts[term.upper()] += 1
    return authors, counts, docs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="count acronyms and who uses them")
    s.add_argument("--git", nargs="?", const=".", action="append", metavar="REPO",
                   help="commit messages from a git repo (repeatable, default .)")
    s.add_argument("--gh", action="append", default=[], metavar="OWNER/REPO",
                   help="issues, PRs and review comments via the gh CLI (repeatable)")
    s.add_argument("--text", nargs="+", default=[], metavar="FILE",
                   help="any prose files, e.g. exported chat or wiki pages")
    s.add_argument("--out", default="candidates.json")

    a = sub.add_parser("apply", help="turn a candidates file into vocabulary.json")
    a.add_argument("candidates")
    a.add_argument("--also-known", nargs="*", default=[],
                   help="terms to mark known regardless of what the count says")
    a.add_argument("--not-known", nargs="*", default=[],
                   help="terms to keep flagged regardless of what the count says")

    args = ap.parse_args()

    if args.cmd == "scan":
        streams = []
        for repo in (args.git or []):
            streams.append(from_git(repo or "."))
        for slug in args.gh:
            streams.append(from_gh(slug))
        if args.text:
            streams.append(from_text(args.text))
        if not streams:
            ap.error("give at least one of --git, --gh or --text")

        def chained():
            for st in streams:
                yield from st

        authors, counts, docs = scan(chained())
        cut = vocabulary.MIN_AUTHORS
        rows = {t: {"authors": len(w), "uses": counts[t]} for t, w in authors.items()
                if t not in vocabulary.GENERAL}
        known = sorted(t for t, r in rows.items() if r["authors"] >= cut)
        borderline = sorted((t for t, r in rows.items() if r["authors"] == cut - 1),
                            key=lambda t: -rows[t]["uses"])
        explain = sorted(t for t, r in rows.items() if r["authors"] < cut - 1)
        out = {
            "_meta": {
                "documents": docs,
                "distinct_terms": len(rows),
                "author_cut": cut,
                "what": "authors is how many distinct people wrote the term. That, not the number "
                        "of uses, is what decides whether the audience shares it.",
                "next": "python3 lib/vocab.py apply <this file>, or run "
                        "/prose-guard:learn-vocabulary to be walked through the borderline pile.",
            },
            "known": known,
            "borderline": borderline,
            "needs_explaining": explain,
            "counts": rows,
        }
        with open(args.out, "w") as fh:
            json.dump(out, fh, indent=1)
            fh.write("\n")
        print(f"{docs} documents, {len(rows)} terms not already general.")
        print(f"  {len(known):4d} reached {cut}+ authors — shared knowledge")
        print(f"  {len(borderline):4d} at exactly {cut - 1} — worth a human look:"
              f" {', '.join(borderline[:12])}{' …' if len(borderline) > 12 else ''}")
        print(f"  {len(explain):4d} below that — need explaining")
        print(f"\nwritten to {args.out}")
        return 0

    with open(args.candidates) as fh:
        cand = json.load(fh)
    counts = cand.get("counts") or {}
    terms = {t: counts.get(t, {}).get("authors", vocabulary.MIN_AUTHORS)
             for t in cand.get("known") or []}
    for t in args.also_known:
        terms[t.upper()] = vocabulary.MIN_AUTHORS
    for t in args.not_known:
        terms.pop(t.upper(), None)
    d = vocabulary.config_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "vocabulary.json")
    with open(path, "w") as fh:
        json.dump({"_meta": {"from": os.path.basename(args.candidates),
                             "author_cut": vocabulary.MIN_AUTHORS},
                   "terms": terms}, fh, indent=1)
        fh.write("\n")
    print(f"{len(terms)} terms written to {path}")
    print("Unexplained terms will now be held back rather than reported as a guess.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
