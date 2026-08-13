#!/usr/bin/env python3
"""Does a change to the rule change what the agent writes? Run this before editing rule/.

    python3 measure/measure_rule.py --rule rule/engineer-communication.md --reps 6
    python3 measure/measure_rule.py --rule a.md --rule b.md --rule none --reps 6

Each `--rule` becomes an arm. `none` is the unguarded control and is always worth including. Every
arm runs the same tasks the same number of times in an isolated directory, with `--setting-sources
project` so nothing on your machine leaks in, and is scored on the behaviours that were shown to
respond to a rule at all:

    unexplained terms   the deterministic check, no model involved
    code block          whether a copy-pasteable command is present, which went 0% without a rule
                        and 100% with one, so it has the most room to regress
    words               to catch a rule being obeyed by writing less rather than by selecting better

The rule is the cheapest part of this tool and the only always-on one, so it is the part where a
change is hardest to notice and easiest to get wrong. Growing one from 156 to 246 words cost nothing
measurable here; a longer draft before that measurably diluted adherence.

**Read the bootstrap intervals, not the means.** At six replicates per arm per task the interval on
the code-block share is about nine points wide, so this rules out a large regression and not a small
one. Two runs of the same arm differ.

This spends real tokens: three arms at six replicates is 54 sessions.
"""
import argparse
import concurrent.futures as cf
import json
import os
import random
import re
import shutil
import statistics as st
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "plugins", "prose-guard", "lib"))
sys.path.insert(0, LIB)

import audiences  # noqa: E402
import jargon  # noqa: E402

# Three tasks, because a rule that helps an announcement can hurt a one-line comment: pitching the
# first version at whole messages made review comments worse than no rule at all.
TASKS = {
    "announce": {
        "file": ("notes.txt", """We removed the GOOGLE_OAUTH_ACCESS_TOKEN export from set-java-env.sh.
It was written on every shell start. Nothing on a laptop reads it. Terraform preferred it over the
application default credential and the token expires after an hour, so plans started failing in any
shell older than that. GKE access through gke-gcloud-auth-plugin now uses the application default
credential instead. CI sets the variable itself, so nothing changes there.
"""),
        "prompt": ("Read notes.txt. Write the message you would post in the team chat channel to "
                   "announce this. Output only the message."),
    },
    "diagnose": {
        "file": ("failure.txt", """A test named test_null_retries_falls_back_to_default fails after a
change to the retry helper. The helper now returns the configured default when the retry count is
null, but the caller checks for null itself before calling, so the default is never reached and the
call goes out with no retry at all. The test asserts three retries and observes one.
"""),
        "prompt": ("Read failure.txt. Report the diagnosis to the engineer who asked. Output only "
                   "your report."),
    },
    "review": {
        "file": ("diff.txt", """--- a/RetryPolicy.java
+++ b/RetryPolicy.java
-    if (count == null) return DEFAULT_RETRIES;
-    return count;
+    return count == null ? config.defaultRetries() : count;
     }
+    // callers already null-check, so this is unreachable
"""),
        "prompt": ("Read diff.txt. Write the review comments you would leave, one per finding, as "
                   "`path:line` plus the comment. Output only the comments."),
    },
}


def run_cell(job):
    arm, rule_path, task_name, rep, root, model, effort = job
    tag = f"{task_name}__{arm}__r{rep}"
    work = os.path.join(root, tag)
    os.makedirs(os.path.join(work, ".claude", "rules"), exist_ok=True)
    if rule_path:
        shutil.copyfile(rule_path, os.path.join(work, ".claude", "rules", "comm.md"))
    task = TASKS[task_name]
    with open(os.path.join(work, task["file"][0]), "w") as fh:
        fh.write(task["file"][1])
    r = subprocess.run(
        ["claude", "-p", task["prompt"], "--model", model, "--effort", effort,
         "--setting-sources", "project", "--allowedTools", "Read"],
        cwd=work, capture_output=True, text=True, timeout=1800)
    text = r.stdout.strip()
    print(f"  {tag:34s} {len(text.split()):4d}w", flush=True)
    return {"arm": arm, "task": task_name, "rep": rep, "text": text}


def score(text, resolved):
    bad, considered = jargon.scan(text, resolved.is_known)
    prose = jargon.FENCE.sub(" ", text)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", prose) if len(s.split()) >= 3]
    return {"unexplained": len(bad), "terms": bad,
            "code_block": 1 if "```" in text else 0,
            "words": len(text.split()),
            "over_30w": (100 * sum(1 for s in sentences if len(s.split()) > 30) / len(sentences)
                         if sentences else 0)}


def interval(values, draws=6000):
    """Bootstrap 90% interval. An earlier round of this work read a three-run swing as a result."""
    values = list(values)
    if len(values) < 2:
        return (float(values[0]), float(values[0])) if values else (0.0, 0.0)
    means = []
    for _ in range(draws):
        means.append(st.mean(random.choice(values) for _ in values))
    means.sort()
    return means[int(0.05 * draws)], means[int(0.95 * draws)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", action="append", required=True,
                    help="path to a rule file, or the word 'none' for an unguarded control")
    ap.add_argument("--reps", type=int, default=6)
    ap.add_argument("--tasks", default=",".join(TASKS))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--audience", help="score against this audience instead of the baseline")
    ap.add_argument("--out")
    a = ap.parse_args()
    random.seed(0)

    aud = audiences.ALL.get(a.audience) if a.audience else None
    if a.audience and aud is None:
        raise SystemExit(f"no audience called {a.audience!r}")
    resolved = audiences.Resolved([aud]) if aud else audiences.resolve({})

    arms = []
    for spec in a.rule:
        if spec == "none":
            arms.append(("none", None))
        elif not os.path.isfile(spec):
            raise SystemExit(f"no such rule file: {spec}")
        else:
            words = len(open(spec).read().split())
            arms.append((f"{os.path.basename(spec)}:{words}w", spec))
    tasks = [t.strip() for t in a.tasks.split(",") if t.strip() in TASKS]

    with tempfile.TemporaryDirectory(prefix="prose-guard-rule-") as root:
        jobs = [(arm, path, task, rep, root, a.model, a.effort)
                for arm, path in arms for task in tasks for rep in range(1, a.reps + 1)]
        print(f"{len(jobs)} sessions: {len(arms)} arm(s) x {len(tasks)} task(s) x {a.reps} reps\n")
        rows = []
        with cf.ThreadPoolExecutor(max_workers=a.workers) as pool:
            for row in pool.map(run_cell, jobs):
                rows.append(row)

    usable = [r for r in rows if len(r["text"].split()) >= 15]
    for r in usable:
        r.update(score(r["text"], resolved))
    if a.out:
        json.dump(rows, open(a.out, "w"), indent=1)

    print(f"\nusable: {len(usable)}/{len(rows)}   "
          f"(a session that produced nothing is a result, not a gap — an earlier design deadlocked "
          f"and scored perfectly on empty files)")
    print(f"\n{'arm':22s} {'n':>3s} {'unexplained':>22s} {'code block':>20s} {'words':>6s} "
          f"{'>30w':>6s}")
    for arm, _ in arms:
        mine = [r for r in usable if r["arm"] == arm]
        if not mine:
            continue
        lo, hi = interval(r["unexplained"] for r in mine)
        clo, chi = interval(r["code_block"] for r in mine)
        print(f"{arm:22s} {len(mine):3d} "
              f"{st.mean(r['unexplained'] for r in mine):6.2f} [{lo:4.2f},{hi:4.2f}]   "
              f"{100 * st.mean(r['code_block'] for r in mine):4.0f}% [{100*clo:3.0f},{100*chi:3.0f}]   "
              f"{st.mean(r['words'] for r in mine):6.0f} "
              f"{st.mean(r['over_30w'] for r in mine):5.1f}%")

    print("\nper task, mean unexplained terms:")
    for task in tasks:
        line = f"  {task:10s}"
        for arm, _ in arms:
            mine = [r for r in usable if r["arm"] == arm and r["task"] == task]
            line += f"  {arm[:14]}: {st.mean(r['unexplained'] for r in mine):.2f}" if mine else ""
        print(line)

    flagged = [(r["arm"], r["task"], r["terms"]) for r in usable if r["terms"]]
    if flagged:
        print("\nunexplained terms, so you can tell a real one from a fixture artefact:")
        for arm, task, terms in flagged:
            print(f"  {arm:22s} {task:10s} {terms}")
    print(f"\nmodel={a.model} effort={a.effort} reps={a.reps} — say so when you report these.")


if __name__ == "__main__":
    main()
