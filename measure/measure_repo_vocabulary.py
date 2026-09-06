#!/usr/bin/env python3
"""Would a repository's own words release the terms it should, and what would they silence?

    python3 measure/measure_repo_vocabulary.py --repo ~/code/some-repo --term ANTLR --term MWE2
    python3 measure/measure_repo_vocabulary.py --repo ~/code/some-repo --corpus messages.jsonl

Deterministic and free: no model is asked. It reads the repository on disk and its `git log`.

The question it answers. An audience's vocabulary is measured by author breadth — four distinct people
must have written a term before the audience is assumed to know it — and that is the right model for a
chat channel and the wrong one for a repository's documentation, where one person writes the README a
hundred people read. `learn.py scan --text` yields one author per file, so a term in a README can never
reach the cut through it. This asks the other question: if the terms in a repository's OWN documents were
taken as shared context for a message going TO that repository, without any author count —

  * would the terms that were wrongly held be released? (`--term`, one per term you know was wrongly held)
  * what else would go quiet? (`--corpus`, messages written for this repository's readers)

Both directions, per SCOPE — because a repository contains every acronym anybody ever wrote into it,
including in vendored code, licence headers, dependency names and a `pom.xml`, and the scopes are what
decide how much of that is taken as known:

    newcomer   README, CLAUDE.md, AGENTS.md, CONTRIBUTING.md at the root — what a newcomer is told to read
    docs       newcomer, plus every prose file under docs/ and website/
    prose      every tracked .md .mdx .rst .adoc .txt file anywhere
    log        git log, subjects and bodies
    build      pom.xml, build.gradle*, package.json, *.mwe2, Makefile, *.toml, .github/**
    all        every tracked text file, code included

The corpus, when given, is lines of {"text": ...} (an `author` field is ignored: breadth is the thing
this harness deliberately does not use). Score it against the shipped `engineers` baseline alone, then
against baseline + each scope, and print what each scope silences. Read that list before believing a
scope: a term it silences is only a false alarm if this repository's readers really do have it, and the
harness cannot know that. With no corpus, the repository's own commit messages are scored — held out
from every scope except `log`, which is the same data and is marked as such.

The one part that asks a model, and only when you say so:

    python3 measure/measure_repo_vocabulary.py --repo ~/code/some-repo --ask shared:ANTLR --ask mention:SPDX --reps 3

A scope cannot tell a term the documentation USES from one it only MENTIONS — quotes as an example, lists
among alternatives, carries in licence boilerplate, or names as something that needs explaining. `--ask`
hands a model every `docs` sentence that carries the term and asks which it is, `--reps` times, and scores
the answer against the label you gave: `shared` (the docs establish it, releasing it is right), `mention`
(they do not, holding it is right) or `unsure` (report the answer, score nothing). It prints what the run
cost. This is the measurement that decides whether a model belongs between a repository's documents and
the `terms` check at all, and it is the only thing here that spends tokens.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Iterable

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "plugins", "prose-guard", "lib"))

import audiences  # noqa: E402
import jargon  # noqa: E402

PROSE_EXT = (".md", ".mdx", ".markdown", ".rst", ".adoc", ".txt", ".org")
NEWCOMER = ("README", "README.md", "README.rst", "README.txt", "CLAUDE.md", "AGENTS.md",
            "CONTRIBUTING.md")
BUILD = ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "package.json",
         "Makefile", "*.mwe2", "*.toml", ".github/*", ".github/**/*")
DOC_DIRS = ("docs", "doc", "website")
# Above this a tracked file is a bundle, a fixture or a generated artefact, not something anybody reads.
LARGEST = 512 * 1024

# --ask. Sentence boundaries good enough for documentation: end punctuation, a blank line, or the start of
# a list item, heading or table row. A sentence is cut at SENTENCE characters and a term gets at most
# SENTENCES of them, so one term that a README uses fifty times costs what one that it uses six times
# costs.
SPLIT = re.compile(r"(?<=[.!?])\s+|\n\s*\n|\n(?=[-*#|])")
SENTENCE = 300
SENTENCES = 6
LABELS = ("shared", "mention", "unsure")
# What the model is asked. PASS is read as "the documentation establishes the term", FAIL as "it only
# mentions it", because `checks.ask` reads one verdict shape and this is the one it reads.
ASK = ("Every sentence below comes from one repository's own documentation, and every one of them uses "
       "the abbreviation {term}. Decide whether that documentation ESTABLISHES {term} as a working term "
       "for somebody who reads this repository's pull requests — a thing the repository is built on, "
       "produces or exists to serve, used as a term the reader is expected to carry — or only MENTIONS "
       "it: as an example of a term, a quotation, licence or governance boilerplate, or a term the "
       "documentation itself says needs explaining.\n\n"
       "Answer PASS if the documentation establishes {term}. Answer FAIL: followed by one line saying "
       "why, if it only mentions it.")


def tracked(repo: str) -> list[str]:
    out = subprocess.run(["git", "-C", repo, "ls-files", "-z"], capture_output=True, text=True,
                         timeout=120).stdout
    return [p for p in out.split("\0") if p]


def read(repo: str, rel: str) -> str:
    path = os.path.join(repo, rel)
    try:
        if os.path.getsize(path) > LARGEST:
            return ""
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return ""
    if b"\0" in raw[:4096]:
        return ""                                  # binary
    return raw.decode("utf-8", errors="ignore")


def commit_messages(repo: str) -> list[str]:
    out = subprocess.run(["git", "-C", repo, "log", "--no-merges", "--format=%B%x01"],
                         capture_output=True, text=True, timeout=600).stdout
    return [m.strip() for m in out.split("\x01") if m.strip()]


def terms_in(texts: Iterable[str]) -> set[str]:
    found: set[str] = set()
    for text in texts:
        body = jargon.prose(text)
        found |= {t for t in set(jargon.ACRONYM.findall(body)) if jargon.is_acronym(t)}
    return found


def scopes(repo: str, files: list[str]) -> dict[str, list[str]]:
    """Which tracked files each scope reads. `log` is not a file and is handled by the caller."""
    newcomer = [f for f in files if f in NEWCOMER]
    docs = newcomer + [f for f in files if f.split("/")[0] in DOC_DIRS and f.endswith(PROSE_EXT)]
    prose = [f for f in files if f.endswith(PROSE_EXT)]
    build = [f for f in files if any(fnmatch.fnmatch(f, pat) or fnmatch.fnmatch(os.path.basename(f), pat)
                                     for pat in BUILD)]
    return {"newcomer": newcomer, "docs": docs, "prose": prose, "build": build, "all": files}


def harvest(repo: str) -> dict[str, tuple[set[str], int, float]]:
    """scope -> (terms, documents read, seconds)."""
    files = tracked(repo)
    out: dict[str, tuple[set[str], int, float]] = {}
    for name, chosen in scopes(repo, files).items():
        t0 = time.perf_counter()
        found = terms_in(read(repo, f) for f in chosen)
        out[name] = (found, len(chosen), time.perf_counter() - t0)
    t0 = time.perf_counter()
    log = commit_messages(repo)
    out["log"] = (terms_in(log), len(log), time.perf_counter() - t0)
    return out


def load_corpus(path: str) -> list[str]:
    rows = []
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            text = str(row.get("text") or "")
            if text.strip():
                rows.append(text)
    return rows


def score(corpus: list[str], known: set[str]) -> tuple[int, int, dict[str, int]]:
    """(messages with a finding, terms flagged, {term: messages it was flagged in})."""
    hit_messages = 0
    flagged: dict[str, int] = {}
    for text in corpus:
        bad, _ = jargon.scan(text, lambda t: t.upper() in known)
        if bad:
            hit_messages += 1
        for t in bad:
            flagged[t] = flagged.get(t, 0) + 1
    return hit_messages, sum(flagged.values()), flagged


def sentences_with(term: str, texts: Iterable[str]) -> list[str]:
    """The distinct sentences that use `term`, in document order, capped."""
    pat = re.compile(rf"\b{re.escape(term)}\b")
    out: list[str] = []
    for text in texts:
        for s in SPLIT.split(text):
            s = " ".join(s.split())
            hit = pat.search(s)
            if not hit:
                continue
            # Cut around the term, not from the front: cut from the front first, a survey sentence that
            # names BLUF in its 400th character had no sentence at all.
            start = max(0, min(hit.start() - SENTENCE // 2, len(s) - SENTENCE))
            s = s[start:start + SENTENCE]
            if s not in out:
                out.append(s)
            if len(out) >= SENTENCES:
                return out
    return out


def ask_model(jobs: list[tuple[str, str, list[str], int]], workers: int) -> dict[tuple[str, int], bool]:
    """(term, rep) -> True when the model says the documentation establishes the term. Spends tokens."""
    from checks import ask as _ask

    def one(job: tuple[str, str, list[str], int]) -> tuple[tuple[str, int], bool]:
        term, label, sents, rep = job
        ok, _ = _ask.ask("repo-vocabulary", ASK.format(term=term), "\n".join(f"- {s}" for s in sents))
        return (term, rep), ok

    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(one, jobs))


def cost(log_path: str) -> tuple[int, int, int, float]:
    """(calls, input tokens, output tokens, seconds) from the checker's own usage log."""
    calls = tokens_in = tokens_out = 0
    seconds = 0.0
    try:
        with open(log_path) as fh:
            for line in fh:
                row = json.loads(line)
                calls += 1
                tokens_in += (row.get("input_tokens") or 0) + (row.get("cache_read_input_tokens") or 0) \
                    + (row.get("cache_creation_input_tokens") or 0)
                tokens_out += row.get("output_tokens") or 0
                seconds += row.get("seconds") or 0.0
    except (OSError, ValueError):
        pass
    return calls, tokens_in, tokens_out, seconds


def use_or_mention(repo: str, asks: list[str], reps: int, workers: int) -> None:
    labelled: list[tuple[str, str]] = []
    for item in asks:
        label, _, term = item.partition(":")
        if label not in LABELS or not term:
            raise SystemExit(f"--ask wants LABEL:TERM with LABEL one of {', '.join(LABELS)}, not {item!r}")
        labelled.append((label, term.upper()))
    texts = [read(repo, f) for f in scopes(repo, tracked(repo))["docs"]]
    jobs = []
    empty = []
    for label, term in labelled:
        sents = sentences_with(term, texts)
        if not sents:
            empty.append(term)
            continue
        for rep in range(reps):
            jobs.append((term, label, sents, rep))
    if empty:
        print(f"\nnot in any `docs` sentence, so nothing to ask about: {', '.join(empty)}")
    if not jobs:
        return

    log_path = os.environ.get("CHECKER_COST_LOG")
    if not log_path:
        fd, log_path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.environ["CHECKER_COST_LOG"] = log_path
    t0 = time.time()
    answers = ask_model(jobs, workers)
    wall = time.time() - t0
    calls, tokens_in, tokens_out, seconds = cost(log_path)
    if calls and not tokens_out:
        # `checks.ask` passes whenever it cannot get an answer — a rate limit, a wrong flag, a CLI that
        # is not logged in — and passes silently, because that is right for a hook and wrong for a
        # harness. Here every "PASS" would read as "the documentation establishes it", and one run of
        # this printed exactly that table on 24 calls that had all been refused with a 429.
        raise SystemExit(f"\n{calls} calls and no model answered any of them (0 output tokens in "
                         f"{log_path}): every verdict is the fallback pass, not a measurement. Run "
                         f"`{_cli()} -p PASS --output-format json` and read `result` for why.")

    print(f"\nAsking whether the `docs` scope USES or only MENTIONS each term, {reps} rep(s) each. "
          f"S = the model says the documentation establishes it, M = it only mentions it.\n")
    print(f"{'term':8s} {'label':8s} {'answers':{max(reps, 7)}s}  stable  agrees  sentences")
    stable_right = {"shared": 0, "mention": 0}
    counted = {"shared": 0, "mention": 0}
    drifted = 0
    for label, term in labelled:
        if term in empty:
            continue
        got = [answers[(term, r)] for r in range(reps)]
        letters = "".join("S" if g else "M" for g in got)
        stable = len(set(got)) == 1
        drifted += not stable
        agrees = "-"
        if label in counted:
            counted[label] += 1
            want = label == "shared"
            right = stable and got[0] == want
            stable_right[label] += right
            agrees = "yes" if right else "no"
        n = len(next(s for t, _, s, _ in jobs if t == term))
        print(f"{term:8s} {label:8s} {letters:{max(reps, 7)}s}  {'yes' if stable else 'NO':6s}  {agrees:6s}  {n}")
    print(f"\nshared terms released, stably: {stable_right['shared']}/{counted['shared']}; "
          f"mentioned terms kept, stably: {stable_right['mention']}/{counted['mention']}; "
          f"terms the model changed its answer on: {drifted}/{len(labelled) - len(empty)}.")
    print(f"cost: {calls} calls, {tokens_in:,} input tokens (cache reads included), {tokens_out:,} output "
          f"tokens, {seconds:.0f}s of model time in {wall:.0f}s wall.")


def _cli() -> str:
    import host
    return host.CLI


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, help="a local checkout")
    ap.add_argument("--term", action="append", default=[], metavar="TERM",
                    help="a term you know was wrongly held for this repository's readers; repeatable")
    ap.add_argument("--corpus", metavar="FILE.jsonl",
                    help='lines of {"text": ...} written for this repository\'s readers. Default: its '
                         'own commit messages')
    ap.add_argument("--show", type=int, default=25, help="how many silenced terms to list per scope")
    ap.add_argument("--ask", action="append", default=[], metavar="LABEL:TERM",
                    help="ask a model whether the docs USE this term or only MENTION it, and score the "
                         "answer against LABEL: shared, mention or unsure. Repeatable. Spends tokens")
    ap.add_argument("--reps", type=int, default=1, help="ask each --ask question N times; 3 shows drift")
    ap.add_argument("--workers", type=int, default=8, help="model calls in flight at once")
    a = ap.parse_args()
    repo = os.path.abspath(os.path.expanduser(a.repo))
    if a.ask:
        use_or_mention(repo, a.ask, a.reps, a.workers)
        return

    baseline = audiences.BASELINES.get("engineers", set())
    got = harvest(repo)
    order = ("newcomer", "docs", "prose", "log", "build", "all")

    print(f"{repo}\n")
    print(f"{'scope':9s} {'documents':>9s} {'seconds':>8s} {'terms':>6s} {'beyond baseline':>16s}  "
          + "  ".join(f"{t:>6s}" for t in a.term))
    for name in order:
        found, docs, secs = got[name]
        extra = found - baseline
        hits = "  ".join(f"{('yes' if t.upper() in found else 'no'):>6s}" for t in a.term)
        print(f"{name:9s} {docs:9d} {secs:8.3f} {len(found):6d} {len(extra):16d}  {hits}")

    corpus = load_corpus(a.corpus) if a.corpus else commit_messages(repo)
    what = a.corpus or "its own commit messages"
    if not corpus:
        print(f"\nno corpus to score: {what} is empty")
        return
    base_msgs, base_terms, base_flagged = score(corpus, baseline)
    print(f"\nScoring {len(corpus)} messages from {what} against the engineers baseline: "
          f"{base_msgs} messages hold a finding ({100 * base_msgs / len(corpus):.1f}%), "
          f"{base_terms} term flags, {len(base_flagged)} distinct terms.\n")
    print(f"{'scope':9s} {'messages held':>13s} {'term flags':>10s} {'silenced terms':>14s}  what goes quiet")
    for name in order:
        found, _, _ = got[name]
        msgs, flags, flagged = score(corpus, baseline | found)
        silenced = {t: n for t, n in base_flagged.items() if t not in flagged}
        listed = ", ".join(f"{t}({n})" for t, n in sorted(silenced.items(), key=lambda kv: -kv[1])[:a.show])
        note = "  [not held out: the corpus IS the log]" if name == "log" and not a.corpus else ""
        print(f"{name:9s} {msgs:13d} {flags:10d} {len(silenced):14d}  {listed}{note}")

    # Where the widest scope's extra terms actually live. A term known only from code, a licence header or
    # a build file is one the reader may never have seen written in a sentence.
    all_terms = got["all"][0]
    in_prose = got["prose"][0] | got["log"][0]
    code_only = (all_terms - baseline) - in_prose
    print(f"\n`all` knows {len(all_terms - baseline)} terms beyond the baseline; "
          f"{len(code_only)} of them appear in no prose file and no commit message.")
    print("  " + ", ".join(sorted(code_only)[:a.show]) + (" …" if len(code_only) > a.show else ""))


if __name__ == "__main__":
    main()
