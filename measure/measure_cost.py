#!/usr/bin/env python3
"""What a change costs the person using it. Run this before proposing one.

    python3 measure/measure_cost.py --levels disabled,medium --reps 5

Paired sessions: the same task and the same fixture, once per level, several times each. It reports
what YOUR session spent, which is the part a teammate feels — a held-back message costs an extra agent
turn on your own context, and that is usually more than the checker's own call.

Compare against `disabled` **in the same run**. The unguarded control varies between runs by more than
some levels differ from each other, so a number lifted from someone else's run is not a baseline.

Needs the `claude` CLI on PATH. Each session is a real one, so five reps of two levels is ten sessions:
expect a few minutes and real tokens. That is the point — a cost measurement that costs nothing is
measuring nothing.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import shutil
import statistics as st
import subprocess
import tempfile
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.abspath(os.path.join(HERE, "..", "plugins", "prose-guard"))
GUARD = os.path.join(PLUGIN, "hooks", "scripts", "guard-outgoing-prose.sh")

FIXTURE = """We removed the GOOGLE_OAUTH_ACCESS_TOKEN export from set-java-env.sh. It was written on
every shell start. Nothing on a laptop reads it. Terraform preferred it over the application default
credential and the token expires after an hour, so plans started failing in any shell older than that.
GKE access through gke-gcloud-auth-plugin now uses the application default credential instead. CI sets
the variable itself, so nothing changes there.
"""
PROMPT = ("Read notes.txt in this directory. Write the announcement you would post in the team chat "
          "channel to tell everyone about this change, and save it to announce.md. Then say it is "
          "written.")


def one(args: tuple[str, int, str, str, str]) -> dict[str, Any]:
    level, rep, home_root, model, effort = args
    tag = f"{level}_r{rep}"
    work = os.path.join(home_root, tag)
    os.makedirs(os.path.join(work, ".claude"), exist_ok=True)
    with open(os.path.join(work, "notes.txt"), "w") as fh:
        fh.write(FIXTURE)
    # A git working tree, because the prose-file destination only claims a file that is tracked and
    # not ignored — that is how it tells a document someone will read from a scratch file. Without
    # this the guard never fires and the whole measurement reads zero, which looks like "free"
    # rather than "not measured".
    for cmd in (["git", "init", "-q"],
                ["git", "-c", "user.email=m@e", "-c", "user.name=m", "commit", "-q",
                 "--allow-empty", "-m", "fixture"]):
        subprocess.run(cmd, cwd=work, capture_output=True)
    settings = {}
    if level != "disabled":
        settings["hooks"] = {"PreToolUse": [{"hooks": [{"type": "command", "command": GUARD}]}]}
    with open(os.path.join(work, ".claude", "settings.json"), "w") as fh:
        json.dump(settings, fh)

    env = {**os.environ}
    env["PROSE_GUARD_HOME"] = os.path.join(work, "config")
    env["PROSE_GUARD_STATE"] = os.path.join(work, "state")
    env["CHECKER_COST_LOG"] = os.path.join(work, "checker.jsonl")
    env["PROSE_GUARD_EFFORT"] = level
    env.pop("CLAUDE_PLUGIN_OPTION_EFFORT", None)

    started = time.time()
    run = subprocess.run(
        ["claude", "-p", PROMPT, "--model", model, "--effort", effort,
         "--setting-sources", "project", "--output-format", "json",
         "--allowedTools", "Read", "Write", "Edit"],
        cwd=work, capture_output=True, text=True, env=env, timeout=2400)
    seconds = time.time() - started
    try:
        blob = json.loads(run.stdout)
    except Exception:
        return {"level": level, "rep": rep, "error": (run.stdout or run.stderr)[-300:]}
    usage = blob.get("usage") or {}

    calls = tokens = 0
    log = os.path.join(work, "checker.jsonl")
    if os.path.exists(log):
        for line in open(log):
            calls += 1
            tokens += json.loads(line).get("output_tokens", 0)
    wrote = os.path.join(work, "announce.md")
    if calls == 0 and level != "disabled":
        # Say so rather than reporting zero as a result. A level that spends no call has either
        # nothing to check or a destination that did not match, and those are different.
        print(f"  {tag:16s} WARNING: the guard never ran. Check that announce.md landed inside the "
              f"git tree and that the level is set.", flush=True)
    row = {"level": level, "rep": rep, "seconds": round(seconds, 1),
           "turns": blob.get("num_turns"),
           "your_output_tokens": usage.get("output_tokens", 0),
           "your_cache_read": usage.get("cache_read_input_tokens", 0),
           "cost_usd": blob.get("total_cost_usd"),
           "checker_calls": calls, "checker_output_tokens": tokens,
           "words_written": len(open(wrote).read().split()) if os.path.exists(wrote) else 0}
    print(f"  {tag:16s} {seconds:6.1f}s  turns={row['turns']:<3} "
          f"out={row['your_output_tokens']:<6} checker_calls={calls}", flush=True)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="disabled,medium",
                    help="comma separated; always include disabled as the control")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--effort", default="medium", help="effort for the SESSION, not for the checks")
    ap.add_argument("--out", help="write the raw rows here as JSON")
    a = ap.parse_args()

    levels = [x.strip() for x in a.levels.split(",") if x.strip()]
    if "disabled" not in levels:
        print("warning: no `disabled` control in --levels, so there is nothing to compare against\n")

    with tempfile.TemporaryDirectory(prefix="prose-guard-cost-") as root:
        cells = [(lvl, rep, root, a.model, a.effort)
                 for rep in range(1, a.reps + 1) for lvl in levels]
        rows = []
        with cf.ThreadPoolExecutor(max_workers=a.workers) as pool:
            for row in pool.map(one, cells):
                rows.append(row)
        for row in rows:
            if "error" in row:
                shutil.rmtree(os.path.join(root, f"{row['level']}_r{row['rep']}"),
                              ignore_errors=True)

    ok = [r for r in rows if "error" not in r and r.get("words_written")]
    print(f"\nusable sessions: {len(ok)}/{len(rows)}")
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(rows, fh, indent=1)

    def med(sub: list[dict[str, Any]], key: str) -> float:
        return st.median(r[key] for r in sub)

    control = [r for r in ok if r["level"] == "disabled"]
    print(f"\n{'level':10s} {'n':>3s} {'secs':>7s} {'turns':>6s} {'your out':>9s} "
          f"{'cache read':>11s} {'calls':>6s} {'checker out':>12s} {'$':>7s} {'words':>6s}")
    for level in levels:
        sub = [r for r in ok if r["level"] == level]
        if not sub:
            continue
        print(f"{level:10s} {len(sub):3d} {med(sub, 'seconds'):7.1f} {med(sub, 'turns'):6.1f} "
              f"{med(sub, 'your_output_tokens'):9.0f} {med(sub, 'your_cache_read'):11.0f} "
              f"{med(sub, 'checker_calls'):6.1f} {med(sub, 'checker_output_tokens'):12.0f} "
              f"{st.median(r['cost_usd'] or 0 for r in sub):7.3f} "
              f"{med(sub, 'words_written'):6.0f}")

    if control:
        print("\nAdded per message sent, against the disabled control in this run — quote these:")
        for level in levels:
            sub = [r for r in ok if r["level"] == level and level != "disabled"]
            if not sub:
                continue
            print(f"  {level:10s} +{med(sub, 'seconds') - med(control, 'seconds'):.0f}s, "
                  f"+{med(sub, 'your_output_tokens') - med(control, 'your_output_tokens'):.0f} of "
                  f"your output tokens, "
                  f"+${(st.median(r['cost_usd'] or 0 for r in sub) - st.median(r['cost_usd'] or 0 for r in control)):.3f}, "
                  f"{med(sub, 'checker_calls'):.0f} model call(s)")
    print(f"\nmodel={a.model} effort={a.effort} reps={a.reps} — say so when you report these.")


if __name__ == "__main__":
    main()
