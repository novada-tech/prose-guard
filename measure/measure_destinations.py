#!/usr/bin/env python3
"""What each destination costs at a given level, and how often it complains about good prose.

    python3 measure/measure_destinations.py --effort high --reps 3
    python3 measure/measure_destinations.py --effort high --only "commit message,chat message"

The commit message was capped at `low` after measuring one: about 20 seconds and four model calls,
with findings that changed between runs on the same text. The obvious question is whether that is one
destination or a class of them, and the only honest way to answer it is to measure the rest the same
way.

Every destination is given the SAME text, from `fixtures/well-built/`, so the only thing varying is
which destination it is going to. Those fixtures were judged well built, so a finding on one is
probably noise — that is what makes a false-positive rate meaningful here rather than a guess.

Two numbers per destination:

    cost         wall clock and model calls, which is what a person waits for
    complaints   how many reps raised anything at all, and whether they agreed

A destination that complains in one run of three is worse than one that complains in all three: an
unstable check cannot be acted on, and it teaches people to ignore the output.

This spends real tokens. Eight destinations, three reps, at `high` is 24 sessions of the hook.
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.abspath(os.path.join(HERE, "..", "plugins", "prose-guard"))
GUARD = os.path.join(PLUGIN, "hooks", "scripts", "guard-outgoing-prose.sh")
FIXTURES = os.path.join(HERE, "fixtures", "well-built")


def destinations():
    with open(os.path.join(PLUGIN, "data", "destinations.json")) as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else data["destinations"]


def payload_for(dest, text, repo):
    """A tool call that this destination will claim, built from its own matcher.

    Derived from the destination file rather than hand-written per destination, so a destination added
    later is measured without touching this script.
    """
    if dest.get("bash"):
        # Reconstruct a command the matcher accepts: its pattern names the binary and subcommand.
        pattern = dest["bash"].replace("\\b", "").replace("\\s+", " ")
        head, _, rest = pattern.partition("(")
        first = rest.split(")")[0].split("|")[0]
        after = rest.split(")", 1)[1] if ")" in rest else ""
        second = ""
        if "(" in after:
            second = after.split("(")[1].split(")")[0].split("|")[0]
        flag = next((f for f in dest.get("text_arg") or [] if not f.endswith("file")), "--body")
        command = " ".join(x for x in (head.strip(), first, second) if x)
        return "Bash", {"command": f'{command} {flag} "{text}"'}, None
    if dest.get("file"):
        path = os.path.join(repo, "note.md")
        with open(path, "w") as fh:
            fh.write("placeholder\n")
        subprocess.run(["git", "-C", repo, "add", "note.md"], capture_output=True, timeout=60)
        return "Write", {"file_path": path, "content": text}, None
    tool = (dest.get("tool") or ["unknown"])[0]
    field = (dest.get("text_fields") or ["body"])[0]
    body = {field: text}
    for key, source in (dest.get("identifiers") or {}).items():
        if isinstance(source, str):
            body[source] = "C0123" if key == "channel" else "your-org"
    return f"mcp__probe__{tool}", body, None


def shim_for_counting():
    """A `claude` earlier on PATH that records each invocation and then runs the real one.

    The guard's own call counter cannot be read from outside: when a message goes out clean it resets
    `calls` to zero before it exits, which is right for the tool and made this harness report zero
    calls for a run that plainly took fifteen seconds. Counting the process is what the tool cannot
    hide.
    """
    real = shutil.which("claude")
    if not real:
        return None, None
    directory = tempfile.mkdtemp(prefix="pg-shim-")
    log = os.path.join(directory, "calls.log")
    shim = os.path.join(directory, "claude")
    with open(shim, "w") as fh:
        fh.write(f'#!/bin/sh\necho call >> {log}\nexec {real} "$@"\n')
    os.chmod(shim, 0o755)
    return directory, log


def home_with_audience(effort):
    home = tempfile.mkdtemp(prefix="pg-dest-")
    os.makedirs(os.path.join(home, "audiences"))
    with open(os.path.join(home, "config.json"), "w") as fh:
        json.dump({"effort": effort}, fh)
    # A resolved audience, so severity is the real thing rather than the unresolved-guess path, and
    # matching on everything so one audience covers every destination.
    with open(os.path.join(home, "audiences", "team.json"), "w") as fh:
        json.dump({"name": "team",
                   "who": "Engineers on this team. They read incident threads and reviews cold.",
                   "matches": {"channels": ["C0123"], "repos": ["your-org/infra"],
                               "github_owners": ["your-org"], "paths": ["*"]},
                   "inherits": ["engineers"], "members": ["a", "b", "c", "d"],
                   "vocabulary": {"BSP": 9}, "assumptions": {}}, fh)
    return home


def run_once(dest, text, home, repo, session, shim=None, log=None):
    tool, tool_input, _ = payload_for(dest, text, repo)
    payload = {"tool_name": tool, "session_id": session, "cwd": repo, "tool_input": tool_input}
    env = {**os.environ, "PROSE_GUARD_HOME": home}
    if shim:
        env["PATH"] = shim + os.pathsep + env.get("PATH", "")
    if log and os.path.exists(log):
        os.remove(log)
    started = time.monotonic()
    proc = subprocess.run(["bash", GUARD], input=json.dumps(payload), capture_output=True, text=True,
                          env=env, timeout=900)
    took = time.monotonic() - started
    calls = 0
    if log and os.path.exists(log):
        with open(log) as fh:
            calls = sum(1 for line in fh if line.strip())
    said = ""
    if proc.stdout.strip():
        try:
            out = json.loads(proc.stdout)["hookSpecificOutput"]
            said = out.get("permissionDecisionReason") or out.get("additionalContext") or ""
        except Exception:
            said = proc.stdout.strip()
    return took, calls, said


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--effort", default="high", choices=("low", "medium", "high"))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--fixture", default="incident-update.md")
    ap.add_argument("--only", help="comma-separated destination names")
    a = ap.parse_args()

    if not shutil.which("claude") and a.effort != "low":
        raise SystemExit("the claude CLI is not on PATH, so no model call can be made")
    with open(os.path.join(FIXTURES, a.fixture)) as fh:
        text = fh.read().strip()
    wanted = [n.strip() for n in a.only.split(",")] if a.only else None

    shim, log = shim_for_counting()
    print(f"{a.fixture}: {len(text.split())} words of prose already judged well built")
    print(f"effort {a.effort}, {a.reps} reps per destination\n")
    print(f"{'destination':34} {'capped':7} {'seconds':>8} {'calls':>6} {'complained':>11}  agreed")
    rows = []
    for dest in destinations():
        if wanted and dest["name"] not in wanted:
            continue
        home = home_with_audience(a.effort)
        repo = tempfile.mkdtemp(prefix="pg-repo-")
        for argv in (["init", "-q"], ["config", "user.email", "t@t.t"], ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", repo, *argv], capture_output=True, timeout=60)
        times, calls, saids = [], [], []
        for rep in range(a.reps):
            took, made, said = run_once(dest, text, home, repo, f"d{rep}", shim, log)
            times.append(took)
            calls.append(made)
            saids.append(said)
        complained = sum(1 for s in saids if s)
        # "Agreed" is about the FIRST clause, which is the complaint itself. Two runs objecting to
        # different things is the failure mode worth naming, not two runs wording one thing differently.
        firsts = {s.split(".")[0][:60] for s in saids if s}
        agreed = "-" if complained == 0 else ("yes" if len(firsts) == 1 else "no")
        print(f"{dest['name']:34} {dest.get('max_effort') or '-':7} "
              f"{statistics.median(times):8.1f} {statistics.median(calls):6.0f} "
              f"{complained:>7}/{a.reps} {agreed:>8}")
        rows.append({"destination": dest["name"], "capped": dest.get("max_effort"),
                     "seconds": round(statistics.median(times), 1),
                     "calls": statistics.median(calls), "complained": complained,
                     "reps": a.reps, "agreed": agreed, "said": saids})
    print("\nA complaint about this text is probably wrong: it was judged well built before the run.")
    print("Unstable is worse than frequent — a check that objects once in three cannot be acted on.")
    out = os.path.join(tempfile.gettempdir(), "destination-costs.json")
    with open(out, "w") as fh:
        json.dump(rows, fh, indent=1)
    print(f"\nwritten to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
