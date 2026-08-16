#!/usr/bin/env python3
"""Measure what an audience already knows, from writing they have already done.

    python3 lib/learn.py scan --gh your-org/your-repo --git . --out /tmp/candidates.json
    python3 lib/learn.py create platform /tmp/candidates.json \\
        --who "Infrastructure engineers who run our clusters." \\
        --match-channel C0123 --match-repo your-org/infra --also-known PROD RC

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
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audiences  # noqa: E402
import jargon  # noqa: E402
import paths  # noqa: E402

BOT = re.compile(r"(\[bot\]|-bot$|dependabot|renovate|github-actions)", re.I)
# A credential written into a command rather than passed through a variable. Redacted before a command
# is printed, because the warning naming a failing command is how someone finds out their credential
# was refused — and stderr here is an agent's transcript.
SECRET = re.compile(r"(?i)(bearer|token|key|secret|password)\s*[:= ]\s*\S+")


def short(cmd):
    """A command, cut to one line and with any inline credential taken out.

    Redacted before it is cut, not after: cutting first left the first characters of a token in the
    message, which is enough to identify it and not enough to be useful.
    """
    cmd = SECRET.sub(lambda m: f"{m.group(1)} <redacted>", cmd)
    return cmd if len(cmd) <= 60 else cmd[:57] + "..."


def _row(line):
    """One {"author": ..., "text": ...} line as (author, text, ts), or None if it is not usable.

    One parser, because a source read from a file and the same source piped through a command are the
    same lines and must be filtered the same way — bots dropped by name, an authorless line dropped.
    """
    try:
        row = json.loads(line.strip() or "{}")
    except ValueError:
        return None
    who = str(row.get("author") or "").strip()
    if not who or BOT.search(who):
        return None
    return who, str(row.get("text") or ""), row.get("ts")


def under_home(path):
    """Where a file the scan writes goes. A relative path lands in the config home, not here.

    Both files a scan writes carry every measured person's name — `--out` the member list, `--keep` the
    messages themselves. `candidates.json` relative to the working directory put them in whichever
    repository the scan was run from, which is where an agent runs things, and one `git add -A` away
    from being published. An absolute path is taken as meant.
    """
    return path if os.path.isabs(path) else paths.at(path)


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
                yield author.strip(), body, None


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
                yield who, f"{row.get('title') or ''}\n{row.get('body') or ''}", None
            for c in row.get("comments") or []:
                cw = ((c.get("author") or {}).get("login") or "").strip()
                if cw and not BOT.search(cw):
                    yield cw, c.get("body") or "", None


def from_command(commands):
    """Anything that can emit `{"author": ..., "text": ...}` lines on stdout.

    This exists because `--gh` shells out to the `gh` CLI, so repository text travels disk to disk
    and never passes through an agent's context — and nothing else had that property. Reading a chat
    channel meant an agent reading a page and retyping it into a file: expensive (one page of 100
    messages measured at about 12,000 tokens, much of it stack traces that contribute nothing to an
    acronym count) and, worse, *transcription* rather than piping, which risks introducing errors
    into the corpus being measured.

    So the tool takes a command instead of growing a source per product. A Slack export, a Teams
    dump, a Discord archive, a wiki, an mbox — anything you can pipe. See the recipes in
    docs/sources.md.
    """
    for cmd in commands:
        try:
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
        except Exception as exc:
            print(f"  warning: `{short(cmd)}` could not be run: {exc}", file=sys.stderr)
            continue
        printed = used = 0
        # Read as it arrives rather than waiting for the whole thing. A read against a live service
        # takes tens of minutes, and nothing could be reported — no count, no rate, no way to stop —
        # until it had finished. Someone asked how long theirs would take and there was no answer.
        for line in proc.stdout:
            if not line.strip():
                continue
            printed += 1
            row = _row(line)
            if row:
                used += 1
                yield row
        proc.stdout.close()
        code = proc.wait()
        err = (proc.stderr.read() or "").strip()
        proc.stderr.close()
        if code != 0:
            print(f"  warning: `{short(cmd)}` exited {code}: {err[:160]}", file=sys.stderr)
        # A source that authenticates and then has no data access exits 0 and prints an error object,
        # which looks from here exactly like a channel with nothing in it. Saying what arrived is the
        # difference between finding that out now and measuring an empty corpus.
        if used == 0:
            detail = (f"printed {printed} line(s), none of them "
                      f"{{\"author\": ..., \"text\": ...}}" if printed else "printed nothing")
            print(f"  warning: `{short(cmd)}` {detail}. A rejected credential looks like this.",
                  file=sys.stderr)
        elif used < printed:
            print(f"  note: `{short(cmd)}` gave {used} usable of {printed} line(s)", file=sys.stderr)


def from_jsonl(files):
    """Anything you can export as {"author": ..., "text": ...} per line — chat history, a wiki."""
    for path in files:
        try:
            with open(path, errors="replace") as fh:
                yield from filter(None, (_row(line) for line in fh))
        except OSError:
            continue


def from_text(files):
    """Plain prose with no author available, so it counts as one voice — which stops it reaching the
    shared-knowledge threshold on its own."""
    for path in files:
        try:
            with open(path, errors="replace") as fh:
                yield f"file:{os.path.basename(path)}", fh.read(), None
        except OSError:
            continue


# What a written-out form has to look like to be recorded. Run against the real corpus, the loose version
# produced `PREVIEW]` with nineteen netlify URLs, `E.G.` with three sentence fragments, and `CDM ->
# cdm/pull/653>` — markdown links, code and abbreviations rather than expansions. An ambiguity check fed
# that would fire on noise for ever.
NOT_WORDS = ("/", ">", "<", "http", "@", "#", "|", "`", "*", "=", "{", "}", "[", "]")


def _expansion(short, long):
    """The written-out form, normalised, or "" if this pair is not an expansion at all."""
    if not jargon.ACRONYM.fullmatch(short) or not jargon.is_acronym(short):
        return ""
    spelt = " ".join(long.split())
    if any(bad in spelt for bad in NOT_WORDS):
        return ""
    words = spelt.split()
    if not 1 < len(words) <= 8:
        return ""                             # one word is rarely an expansion; eight is a sentence
    if not all(w.strip("-'").replace("-", "").isalpha() for w in words):
        return ""
    if not _initials_match(short, words):
        return ""
    # Case-folded, so "CodeFresh Container Registry" and "Codefresh container registry" are one meaning
    # rather than two. The first spelling seen is the one shown.
    return spelt


# Words an expansion skips over: "Hong Kong University of Science and Technology" is HKUST.
SKIPPED = ("of", "and", "the", "for", "in", "on", "a", "an", "to", "at", "by", "with")


def _initials_match(short, words):
    """Whether the acronym's letters are the initials of these words, in order.

    Without this, any parenthesis after a couple of words became an expansion: the real corpus gave
    "child model (CDM)", "Xerces validation (XSD)" and "recently released (RC)" — three coincidences that
    would each have been reported as a second meaning for a term that has one.
    """
    letters = [c for c in short.lower() if c.isalnum()]
    initials = [w[0].lower() for w in words if w.lower() not in SKIPPED]
    if len(initials) != len(letters):
        return False
    return all(a == b for a, b in zip(letters, initials))


def tally(sources, cut=None, limit=None, keep=None, report=None, every=3.0):
    """Count as the documents arrive, saying so as it goes.

    `limit` stops the read deliberately. That is safe in one direction and not the other: a term needs
    a fixed number of distinct authors, and authors only accumulate, so the terms found in a prefix are
    always a subset of the terms in the whole. A short read therefore under-measures, and an
    under-measured audience holds back MORE than it should. It cannot let unexplained jargon through.
    Measured on 11,754 real documents: reading half changed 3.5% of verdicts and reading a tenth
    changed 16.5%, every difference in the direction of holding back.

    `keep` is where the usable rows are written as they are read, so a read that dies part way through
    leaves its documents on disk instead of nothing.
    """
    authors = collections.defaultdict(set)
    uses = collections.Counter()
    # What each term was written out as, and by how many people. The scan already finds "Long Form (SF)"
    # pairs and used to discard them. Keeping them is the only way to see that one abbreviation carries
    # two meanings here: LF is Linux Foundation in this corpus and line feed in a kernel one, and a
    # count on its own cannot tell those apart.
    expansions = collections.defaultdict(lambda: collections.defaultdict(set))
    docs = 0
    people = set()
    newest = None
    started = last = time.monotonic()
    handle = open(keep, "w") if keep else None
    try:
        for who, text, when in sources:
            docs += 1
            people.add(who)
            if when is not None and (newest is None or str(when) > str(newest)):
                newest = when
            if handle:
                handle.write(json.dumps({"author": who, "text": text,
                                         **({"ts": when} if when is not None else {})}) + "\n")
            # the same filter the checker uses, so the piles a human reads contain no THE, WAS or WITH
            body = jargon.prose(text)
            for term in set(t for t in jargon.ACRONYM.findall(body) if jargon.is_acronym(t)):
                authors[term.upper()].add(who)
                uses[term.upper()] += 1
            for short, long in jargon.pairs(body).items():
                spelt = _expansion(short, long)
                if spelt:
                    expansions[short.upper()][spelt].add(who)
            now = time.monotonic()
            if report and now - last >= every:
                last = now
                past = sum(1 for w in authors.values() if cut and len(w) >= cut)
                report(f"  {docs} documents, {len(people)} people, {past} terms past the cut "
                       f"({docs / max(0.001, now - started):.0f}/s, "
                       f"{int(now - started)}s elapsed)")
            if limit and docs >= limit:
                if report:
                    report(f"  stopping at {docs} documents, as asked")
                break
    finally:
        if handle:
            handle.close()
    return authors, uses, docs, people, newest, expansions


def cmd_scan(a):
    streams = []
    for repo in (a.git or []):
        streams.append(from_git(repo or "."))
    for slug in (a.gh or []):
        streams.append(from_gh(slug))
    if a.jsonl:
        streams.append(from_jsonl(a.jsonl))
    if a.command:
        streams.append(from_command(a.command))
    if a.text:
        streams.append(from_text(a.text))
    if not streams:
        raise SystemExit("give at least one of --git, --gh, --jsonl, --text or --command")

    def chained():
        for s in streams:
            yield from s

    cut = audiences.MIN_AUTHORS
    out_path = under_home(a.out or "candidates.json")
    keep_path = under_home(a.keep) if a.keep else None
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if keep_path:
        os.makedirs(os.path.dirname(os.path.abspath(keep_path)), exist_ok=True)
    authors, uses, docs, people, newest, expansions = tally(
        chained(), cut=cut, limit=a.max_documents, keep=keep_path,
        report=(None if a.quiet else lambda line: print(line, file=sys.stderr, flush=True)))
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
                     "stopped_early": bool(a.max_documents and docs >= a.max_documents),
                     "newest_read": newest,
                     "what": "authors is how many distinct people wrote the term. That, not how "
                             "often it appears, decides whether the audience shares it."},
           "members": sorted(people),
           # {TERM: {"Long Form": how many people wrote it that way}}. A term with two entries is one
           # this audience uses for two things.
           "expansions": _folded(expansions),
           "known": known, "borderline": borderline, "needs_explaining": rest, "counts": rows}
    if not docs:
        named = ", ".join(f"--{flag} {value}" for flag, values in
                          (("gh", a.gh), ("git", a.git or []), ("command", a.command),
                           ("jsonl", a.jsonl), ("text", a.text))
                          for value in values)
        # Nothing written. A candidates file listing nobody used to be produced anyway, and `create`
        # accepted it — so a mistyped repository slug yielded an audience that knew nothing and
        # therefore held back every term in the house vocabulary. The file was the bridge between a
        # failed read and a working-looking audience, so there is no file.
        #
        # And the old wording sent people to look for warnings that were not there: a source that
        # cannot be reached at all prints one, but `--gh` on a slug that does not exist prints
        # nothing, because nothing failed — the repository simply had no issues to read.
        raise SystemExit(
            "no documents were read, so there is nothing to measure and nothing was written.\n"
            "  Every source was either unreachable or held nothing readable. Check the source names "
            "for a typo, and that the credential in use can see them.\n"
            f"  Sources given: {named or 'none'}")
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    print(f"{docs} documents from {len(people)} people; {len(rows)} terms not already inherited.")
    print(f"  {len(known):4d} reached {cut}+ people — shared knowledge")
    print(f"  {len(borderline):4d} at exactly {cut - 1} — worth a human look: "
          f"{', '.join(borderline[:12])}{' …' if len(borderline) > 12 else ''}")
    print(f"  {len(rest):4d} below that — need explaining")
    if a.max_documents and docs >= a.max_documents:
        # Say what the bound cost, in the units that matter. Not a warning: a short read is a
        # legitimate choice, and it errs towards holding messages back rather than letting them out.
        print(f"\nStopped at {docs} documents, so this under-measures. On 11,754 real documents,"
              f"\nreading half changed 3.5% of verdicts and reading a tenth changed 16.5% — every"
              f"\ndifference in the direction of holding a message back, never letting one through."
              f"\nRe-run without --max-documents, or scan again later and rebuild: more documents can"
              f"\nonly add terms.")
    if newest is not None:
        print(f"\nnewest document read: {newest}")
    if keep_path:
        print(f"documents kept in {keep_path} — pass it as --jsonl to add to them without re-reading")
    print(f"\nwritten to {out_path}")
    print("  it lists every person measured, so it is not in your working tree unless you asked for "
          "that")


def _losses(name, fresh):
    """What a rebuild would take away from an audience that already exists.

    Rebuilding is a normal thing to do — a wider corpus, a second source — and overwriting was silent.
    Two ways that went wrong in practice. A script wrote the routing under a key nothing read, so the
    audience kept applying to its repositories and silently stopped applying to either chat channel,
    while create printed a success line. And a read against a live API died part way through: the
    corpus looked complete, because a document count looks reasonable whatever it is, and the only
    evidence was that fewer terms reached the cut than the run before.

    Both show up as something the previous file had and this one does not.
    """
    old = audiences.ALL.get(name)
    if old is None:
        return [], []
    was = audiences._read(old.path) or {}
    routing, other = [], []

    for key, before in (was.get("matches") or {}).items():
        gone = [v for v in before if v not in (fresh["matches"].get(key) or [])]
        if gone:
            routing.append(f"{key}: {', '.join(gone)}")

    lost_people = sorted(set(was.get("members") or []) - set(fresh["members"]))
    if lost_people:
        other.append(f"{len(lost_people)} of {len(was.get('members') or [])} people are no longer in "
                     f"the corpus: {', '.join(lost_people[:8])}"
                     f"{' …' if len(lost_people) > 8 else ''}")
    lost_terms = sorted(set(was.get("vocabulary") or {}) - set(fresh["vocabulary"]))
    if lost_terms:
        other.append(f"{len(lost_terms)} measured term(s) dropped below the cut: "
                     f"{', '.join(lost_terms[:12])}{' …' if len(lost_terms) > 12 else ''}")
    before_docs = ((was.get("_meta") or {}).get("learned_from") or {}).get("documents")
    now_docs = (fresh["_meta"].get("learned_from") or {}).get("documents")
    if before_docs and now_docs and now_docs < before_docs:
        other.append(f"the corpus shrank, {before_docs} documents to {now_docs} — if a source failed "
                     f"part way through, this is the only sign of it")
    return routing, other


def _folded(expansions):
    """One entry per meaning, case-folded, with the people who wrote each pooled."""
    out = {}
    for term, seen in sorted(expansions.items()):
        merged = {}
        for spelt, who in sorted(seen.items()):
            key = spelt.lower()
            first, people = merged.get(key, (spelt, set()))
            merged[key] = (first, people | who)
        out[term] = {first: len(people) for first, people in
                     sorted(merged.values(), key=lambda pair: -len(pair[1]))}
    return out


def cmd_create(a):
    if not audiences.usable_name(a.name):
        raise SystemExit(f"{a.name!r} cannot be an audience name: it becomes a filename, so it starts "
                         f"with a letter or digit and holds only letters, digits, dot, dash and "
                         f"underscore, up to 64 characters")
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
    if a.match_channel:
        matches["channels"] = a.match_channel
    if a.match_repo:
        matches["repos"] = a.match_repo
    if a.match_owner:
        matches["github_owners"] = a.match_owner
    if a.match_path:
        matches["paths"] = a.match_path
    if not matches:
        raise SystemExit("an audience needs at least one identifier to match on, or it can never "
                         "apply: --match-channel, --match-repo, --match-owner or --match-path")
    # An audience nobody was measured for is not an audience, and the direction it fails in is the
    # expensive one: creating it makes the term check ENFORCE — so it holds back every term in the
    # house vocabulary, having no evidence that anyone knows any of them. A mistyped repository slug
    # used to produce exactly that, and the message said "terms will now be held back" as though the
    # measurement had worked.
    if not vocab and not (cand.get("members") or []):
        raise SystemExit(
            f"{a.name} would know nothing: the candidates file records no terms and no people.\n"
            f"  Creating it would hold back every term in your house vocabulary, because nothing "
            f"shows anyone knows any of them.\n"
            f"  Re-run `scan` against a source that has writing in it, or pass --also-known to name "
            f"the terms yourself.")
    data = {"name": a.name, "who": a.who or "",
            "expansions": cand.get("expansions") or {},
            "matches": matches,
            "inherits": [cand.get("_meta", {}).get("inherits") or "engineers"],
            "members": cand.get("members") or [],
            "vocabulary": vocab,
            "assumptions": {"shared_context": a.shared_context},
            "_meta": {"learned_from": cand.get("_meta", {}),
                      "accepted_by_hand": [t.upper() for t in a.also_known]}}
    routing, other = _losses(a.name, data)
    if routing and not a.force:
        raise SystemExit(
            f"{a.name} already exists, and this would stop it applying to:\n"
            + "".join(f"  {line}\n" for line in routing)
            + "It would keep working everywhere else, so nothing would look broken. Pass the same "
              "identifiers again, or --force if dropping them is deliberate.")
    for line in other:
        print(f"  warning: {line}")
    if routing:
        for line in routing:
            print(f"  warning: no longer applies to {line} (--force)")
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
    s.add_argument("--max-documents", type=int, metavar="N",
                   help="stop after N documents. Safe in one direction only: it under-measures, so "
                        "the audience holds back more than it should rather than less")
    s.add_argument("--keep", metavar="FILE",
                   help="write the usable documents here as they arrive, so a read that dies part "
                        "way through leaves them on disk. Pass it back as --jsonl to add to them. A "
                        "relative path is resolved under your prose-guard config directory")
    s.add_argument("--quiet", action="store_true", help="no progress while it runs")
    s.add_argument("--command", action="append", default=[], metavar="SHELL",
                   help='any command emitting those lines on stdout — a chat export, a wiki dump, '
                        'an mbox. Keeps the text out of an agent\'s context. See docs/sources.md')
    s.add_argument("--text", nargs="+", default=[], metavar="FILE")
    s.add_argument("--inherits", help="baseline to subtract and inherit (default engineers)")
    # Not the working directory. The candidate list holds every measured person's name and every term
    # they used, and a scan is usually run from the repository being worked in.
    s.add_argument("--out", metavar="FILE",
                   help="where the candidate list goes (default: candidates.json in your prose-guard "
                        "config directory). A relative path is resolved there too, because this file "
                        "names every person measured")

    c = sub.add_parser("create", help="write an audience from a candidates file")
    c.add_argument("name")
    c.add_argument("candidates")
    c.add_argument("--who", help="prose describing the people. Read by the checks, never by routing")
    # These decide when the audience APPLIES. They are not sources — the earlier name for the first
    # one was --slack-channel, and someone reached for it expecting it to read that channel.
    c.add_argument("--match-channel", action="append", default=[], metavar="ID",
                   help="a chat channel id this audience READS, not one to learn from")
    c.add_argument("--match-repo", action="append", default=[], metavar="OWNER/REPO",
                   help="a repository this audience reads")
    c.add_argument("--match-owner", action="append", default=[], metavar="OWNER",
                   help="every repository under this owner")
    c.add_argument("--match-path", action="append", default=[], metavar="GLOB",
                   help="file paths this audience reads")
    c.add_argument("--force", action="store_true",
                   help="rebuild even though it drops routing the existing audience had")
    c.add_argument("--also-known", nargs="*", default=[], metavar="TERM",
                   help="terms this audience knows that the count did not reach — the borderline "
                        "pile, and anything a person confirms")
    c.add_argument("--not-known", nargs="*", default=[], metavar="TERM",
                   help="the opposite: a term the count made look shared that a few people happen "
                        "to use in one corner")
    c.add_argument("--shared-context", choices=audiences.CONTEXT_ORDER, default="low",
                   help="how much of the thread these readers already have. `low` assumes they are "
                        "reading it cold, which is the safe default; a destination can raise it per "
                        "call, as a direct message does")

    a = ap.parse_args()
    (cmd_scan if a.cmd == "scan" else cmd_create)(a)


if __name__ == "__main__":
    main()
