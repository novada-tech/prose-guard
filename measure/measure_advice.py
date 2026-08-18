#!/usr/bin/env python3
"""Does advisory feedback change anything? Two questions, and only one of them costs tokens.

    python3 measure/measure_advice.py --transcripts      free: was advice ever acted on, in the wild
    python3 measure/measure_advice.py --probe FILE.json  costs calls: would an agent act if it could

`medium`'s judgement question only ever advises, and `high` demotes a blocking finding to advice once a
check has already asked twice about a message. So a lot of what this tool says can only work by being
read and acted on voluntarily. That is measurable, and it had never been measured.

**The wild, on one machine's transcripts: 40 messages got advice and went out, and 0 were followed by a
correction.** Not one. `--transcripts` recomputes that on whatever transcripts are present.

**Asked directly, the same notes are usable**: given a held draft and its note, an agent said it would
edit in 4 of 6 cases when told the message had already gone out, and revise in 5 of 6 when told it could
still change the text. That is a leading question — asking "what do you do next" makes the note salient
in a way an ordinary turn does not — so treat it as an upper bound on willingness, not a prediction.

Together those say the mechanism fails rather than the wording: a note delivered after the call has run
is ignored, however actionable it is. An advisory finding reaches the model as `additionalContext` on
PreToolUse and the call then proceeds, so there is no turn in which the message could have changed.

`--probe` takes the JSON that `held_drafts.py` writes: a list of {body, complaint}.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "plugins", "prose-guard", "lib"))

import host  # noqa: E402

# Tools that would correct something already sent. A message that got advice and was then corrected is
# the only observable form of "the advice was acted on".
CORRECTS = ("update_pull_request_review_comment", "update_issue_comment", "update_comment",
            "slack_update", "notion-update-page", "update_pull_request", "issue_write",
            "add_reply_to_pull_request_comment")
# How many calls later a correction still counts as a response to the note.
SOON = 8

AFTER = ("You have just posted this review comment on a pull request. The writing guard returned a note "
         "with the result:\n\n  {note}\n\nAdvice from a check that only ever advises, not a blocker.\n\n"
         "The comment as posted:\n\n{body}\n\nWhat do you do next? Answer in one line, starting with "
         "either NOTHING or EDIT.")
BEFORE = ("You are about to post this review comment on a pull request. The writing guard returned a note "
          "before the call ran, and you may revise the text first:\n\n  {note}\n\nAdvice from a check "
          "that only ever advises, not a blocker.\n\nThe comment you were going to post:\n\n{body}\n\n"
          "What do you do? Answer in one line, starting with either POST-AS-IS or REVISE.")


def in_the_wild() -> tuple[int, int]:
    """How often a message that got advice was followed by a correction. Reads transcripts, counts calls."""
    advised = corrected = 0
    for path in glob.glob(os.path.join(host.dot_dir(), "projects", "*", "*.jsonl")):
        try:
            body = open(path, errors="ignore").read()
        except OSError:
            continue
        if "noisy check" not in body and "only ever advise" not in body:
            continue
        order, issued = [], {}
        for line in body.splitlines():
            if not line.startswith("{"):
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            for block in (row.get("message", {}).get("content") or []):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    issued[block.get("id")] = len(order)
                    order.append({"name": block.get("name") or "", "advised": False})
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in issued:
                    seen = json.dumps(block)
                    if "noisy check" in seen or "only ever advise" in seen:
                        order[issued[block["tool_use_id"]]]["advised"] = True
        for n, call in enumerate(order):
            if not call["advised"]:
                continue
            advised += 1
            if any(k in later["name"] for later in order[n + 1:n + 1 + SOON] for k in CORRECTS):
                corrected += 1
    return advised, corrected


def would_act(drafts: list[dict]) -> None:
    """Ask an agent what it would do, with the note arriving after the send and before it."""
    from checks.ask import EFFORT, MODEL

    def ask(prompt: str) -> str:
        # The invocation the checks use: no project settings, a directory of its own, no tools.
        with tempfile.TemporaryDirectory() as elsewhere:
            r = subprocess.run([host.CLI, "-p", prompt, "--model", MODEL, "--effort", EFFORT,
                                "--system-prompt", "You are an agent deciding what to do next. Be terse.",
                                "--output-format", "json"],
                               capture_output=True, text=True, timeout=180, cwd=elsewhere)
        try:
            return (json.loads(r.stdout).get("result") or "").strip().splitlines()[0][:100]
        except Exception:
            return ""

    for label, template, acted in (("note arrives after the send ", AFTER, "EDIT"),
                                   ("note arrives before the send", BEFORE, "REVISE")):
        hits = 0
        for item in drafts:
            answer = ask(template.format(note=item["complaint"][:220], body=item["body"])).upper()
            if answer.startswith(acted) or acted in answer[:24]:
                hits += 1
        print(f"  {label}: would act on it in {hits}/{len(drafts)}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--transcripts", action="store_true",
                    help="count, from transcripts, how often advice was followed by a correction")
    ap.add_argument("--probe", metavar="FILE",
                    help="ask an agent what it would do with each held draft in FILE. Spends tokens.")
    a = ap.parse_args()
    if a.transcripts:
        advised, corrected = in_the_wild()
        print(f"messages that got advice and went out: {advised}")
        print(f"followed by a correction:              {corrected}")
        if advised and not corrected:
            print("\nNot one. An advisory finding reaches the model after the call has run, so there is\n"
                  "no turn in which the message could have changed.")
        return
    if a.probe:
        with open(a.probe) as fh:
            would_act(json.load(fh))
        return
    ap.error("pick --transcripts (free) or --probe FILE (spends tokens)")


if __name__ == "__main__":
    main()
