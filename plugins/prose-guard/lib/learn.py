#!/usr/bin/env python3
"""Measure what an audience already knows, from writing they have already done.

    python3 lib/learn.py scan --gh your-org/your-repo --git . --out /tmp/candidates.json
    python3 lib/learn.py create platform /tmp/candidates.json \\
        --who "Infrastructure engineers who run our clusters." \\
        --slack-channel C0123 --repo your-org/infra --also-known PROD RC

Two steps, because they need different things. `scan` counts, which is arithmetic. `create` decides,
and the only decisions worth a person's time are the borderline ones — so `scan` sorts candidates
into three piles and `/prose-guard:audiences` walks through the middle one.

Author BREADTH, not frequency. One person's favourite acronym is not shared knowledge however often
they type it: on the corpus this was calibrated against, one acronym occurred 149 times from a single
author. So every source carries an author, and text with no author counts as one voice.

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
import audiences  # noqa: E402
import jargon  # noqa: E402

BOT = re.compile(r"(\[bot\]|-bot$|dependabot|renovate|github-actions)", re.I)


def from_git(repo="."):
    """Commit messages with their authors. Free, local, in every repository — but thin: few people
    put acronyms in a commit subject, so this alone under-measures."""
    try:
        out = subprocess.run(["git", "-C", repo, "log", "--no-merges",
                              "--format=%an%x00%s%n%b%x01"],
                             capture_output=True, text=True, timeout=600).stdout
    except Exception:
        return
    for entry in out.split("\x01"):
        if "\x00" in entry:
            author, body = entry.split("\x00", 1)
            if author.strip() and not BOT.search(author):
                yield author.strip(), body


def from_gh(slug, limit=400):
    """Issues, pull requests and their comments. The richest source: a review comment is written to
    a colleague, so it uses exactly the vocabulary they share."""
    def run(args):
        try:
            return json.loads(subprocess.run(args, capture_output=True, text=True,
                                             timeout=1800).stdout or "[]")
        except Exception:
            return []

    for kind in ("issue", "pr"):
        for row in run(["gh", kind, "list", "-R", slug, "--state", "all", "--limit", str(limit),
                        "--json", "author,title,body,comments"]):
            who = ((row.get("author") or {}).get("login") or "").strip()
            if who and not BOT.search(who):
                yield who, f"{row.get('title') or ''}\n{row.get('body') or ''}"
            for c in row.get("comments") or []:
                cw = ((c.get("author") or {}).get("login") or "").strip()
                if cw and not BOT.search(cw):
                    yield cw, c.get("body") or ""


def from_jsonl(paths):
    """Anything you can export as {"author": ..., "text": ...} per line — chat history, a wiki."""
    for path in paths:
        try:
            with open(path, errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    who = str(row.get("author") or "").strip()
                    if who and not BOT.search(who):
                        yield who, str(row.get("text") or "")
        except OSError:
            continue


def from_text(paths):
    """Plain prose with no author available, so it counts as one voice — which stops it reaching the
    shared-knowledge threshold on its own."""
    for path in paths:
        try:
            with open(path, errors="replace") as fh:
                yield f"file:{os.path.basename(path)}", fh.read()
        except OSError:
            continue


def tally(sources):
    authors = collections.defaultdict(set)
    uses = collections.Counter()
    docs = 0
    people = set()
    for who, text in sources:
        docs += 1
        people.add(who)
        # the same filter the checker uses, so the piles a human reads contain no THE, WAS or WITH
        for term in set(t for t in jargon.ACRONYM.findall(jargon.prose(text))
                        if jargon.is_acronym(t)):
            authors[term.upper()].add(who)
            uses[term.upper()] += 1
    return authors, uses, docs, people


def cmd_scan(a):
    streams = []
    for repo in (a.git or []):
        streams.append(from_git(repo or "."))
    for slug in (a.gh or []):
        streams.append(from_gh(slug))
    if a.jsonl:
        streams.append(from_jsonl(a.jsonl))
    if a.text:
        streams.append(from_text(a.text))
    if not streams:
        raise SystemExit("give at least one of --git, --gh, --jsonl or --text")

    def chained():
        for s in streams:
            yield from s

    authors, uses, docs, people = tally(chained())
    cut = audiences.MIN_AUTHORS
    inherited = audiences.BASELINES.get(a.inherits or "engineers", set())
    rows = {t: {"authors": len(w), "uses": uses[t]} for t, w in authors.items()
            if t not in inherited}
    known = sorted(t for t, r in rows.items() if r["authors"] >= cut)
    borderline = sorted((t for t, r in rows.items() if r["authors"] == cut - 1),
                        key=lambda t: -rows[t]["uses"])
    rest = sorted((t for t, r in rows.items() if r["authors"] < cut - 1),
                  key=lambda t: -rows[t]["uses"])
    out = {"_meta": {"documents": docs, "people": len(people), "author_cut": cut,
                     "inherits": a.inherits or "engineers",
                     "what": "authors is how many distinct people wrote the term. That, not how "
                             "often it appears, decides whether the audience shares it."},
           "members": sorted(people),
           "known": known, "borderline": borderline, "needs_explaining": rest, "counts": rows}
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    print(f"{docs} documents from {len(people)} people; {len(rows)} terms not already inherited.")
    print(f"  {len(known):4d} reached {cut}+ people — shared knowledge")
    print(f"  {len(borderline):4d} at exactly {cut - 1} — worth a human look: "
          f"{', '.join(borderline[:12])}{' …' if len(borderline) > 12 else ''}")
    print(f"  {len(rest):4d} below that — need explaining")
    print(f"\nwritten to {a.out}")


def cmd_create(a):
    with open(a.candidates) as fh:
        cand = json.load(fh)
    counts = cand.get("counts") or {}
    cut = audiences.MIN_AUTHORS
    vocab = {t: counts.get(t, {}).get("authors", cut) for t in cand.get("known") or []}
    for t in a.also_known:
        vocab[t.upper()] = cut
    for t in a.not_known:
        vocab.pop(t.upper(), None)
    matches = {}
    if a.slack_channel:
        matches["slack_channels"] = a.slack_channel
    if a.repo:
        matches["repos"] = a.repo
    if a.github_owner:
        matches["github_owners"] = a.github_owner
    if a.path:
        matches["paths"] = a.path
    if not matches:
        raise SystemExit("an audience needs at least one identifier to match on, or it can never "
                         "apply: --slack-channel, --repo, --github-owner or --path")
    data = {"name": a.name, "who": a.who or "",
            "matches": matches,
            "inherits": [cand.get("_meta", {}).get("inherits") or "engineers"],
            "members": cand.get("members") or [],
            "vocabulary": vocab,
            "assumptions": {"shared_context": a.shared_context, "reach": a.reach},
            "_meta": {"learned_from": cand.get("_meta", {}),
                      "accepted_by_hand": [t.upper() for t in a.also_known]}}
    path = audiences.save(a.name, data)
    print(f"{a.name}: {len(vocab)} measured terms, {len(data['members'])} people -> {path}")
    print("Unexplained terms for this audience will now be held back rather than guessed at.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="count acronyms and how many people use them")
    s.add_argument("--git", nargs="?", const=".", action="append", metavar="REPO")
    s.add_argument("--gh", action="append", default=[], metavar="OWNER/REPO")
    s.add_argument("--jsonl", nargs="+", default=[], metavar="FILE",
                   help='lines of {"author": ..., "text": ...}')
    s.add_argument("--text", nargs="+", default=[], metavar="FILE")
    s.add_argument("--inherits", help="baseline to subtract and inherit (default engineers)")
    s.add_argument("--out", default="candidates.json")

    c = sub.add_parser("create", help="write an audience from a candidates file")
    c.add_argument("name")
    c.add_argument("candidates")
    c.add_argument("--who", help="prose describing the people. Read by the checks, never by routing")
    c.add_argument("--slack-channel", action="append", default=[])
    c.add_argument("--repo", action="append", default=[])
    c.add_argument("--github-owner", action="append", default=[])
    c.add_argument("--path", action="append", default=[])
    c.add_argument("--also-known", nargs="*", default=[])
    c.add_argument("--not-known", nargs="*", default=[])
    c.add_argument("--shared-context", choices=audiences.CONTEXT_ORDER, default="low")
    c.add_argument("--reach", choices=audiences.REACH_ORDER, default="internal")

    a = ap.parse_args()
    (cmd_scan if a.cmd == "scan" else cmd_create)(a)


if __name__ == "__main__":
    main()
