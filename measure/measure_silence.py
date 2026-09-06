#!/usr/bin/env python3
"""Of the calls each destination claims, how many does it ever find the words in.

    python3 measure/measure_silence.py
    python3 measure/measure_silence.py --unique --most-files 200

Deterministic and local. No model calls, no tokens, nothing written anywhere.

A destination that matches a call and recovers no text emits exactly what a clean pass emits: silence,
and no state. That is the one failure in this tool that is invisible from outside, so it has to be
counted, and this is what the count is calibrated against — `discover.SILENT_AFTER` is the number of
claimed calls a destination may go through without finding a word before the hook says so, and the
figure it has to sit above is in the `first text after` column below.

Same contract as `discover.py --from-transcripts`, and the same reason for it: what comes out is a
destination name and a count. Never a value, never a line of anybody's message. It reads conversations
to count outcomes, not to build a corpus, and they are private — ask before running it.

One number needs reading with care and the output labels it: `no text found` counts a `--body-file`
whose file has since been deleted. At runtime the file was there and the text WAS checked, so those are
an artifact of scanning afterwards rather than a gap. The `gone from disk` line is how many of them
look like that.

Length is not one of the reasons a call lands there. Whatever a destination recovers is checked, at the
level `checks.worth_paying_for` allows — so every count here is about whether the text could be READ,
which is the only question this harness is calibrated for.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "plugins", "prose-guard", "lib")))

import command  # noqa: E402
import destinations  # noqa: E402
import discover  # noqa: E402
import host  # noqa: E402


def reads_a_file_that_is_gone(dest: dict, cmd: str) -> bool:
    """A file flag naming a path that does not exist now. Weak evidence, deliberately: a relative path
    resolved against the cwd of a session that ended months ago cannot be resolved here at all."""
    wanted = set(dest.get("text_arg") or ())
    for flag, value in command.flag_values(command.command_itself(cmd)):
        if flag not in wanted:
            continue
        if not (flag.endswith("-file") or flag in ("-F", "--file")):
            continue
        if value != command.STDIN and not os.path.exists(os.path.expanduser(value)):
            return True
    return False


def calls(most_files: int, unique: bool):
    """Every Bash command in local transcripts, oldest first, as the ledger would meet them."""
    directory = os.path.join(host.dot_dir(), "projects")
    files = sorted(glob.glob(os.path.join(directory, "**", "*.jsonl"), recursive=True),
                   key=os.path.getmtime)[-most_files:] if most_files else []
    print(f"reading {len(files)} transcript(s) under {directory}", file=sys.stderr)
    seen: set[str] = set()
    for path in files:
        try:
            fh = open(path, errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"Bash"' not in line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                for block in (row.get("message", {}).get("content") or []):
                    if (not isinstance(block, dict) or block.get("type") != "tool_use"
                            or block.get("name") != "Bash"):
                        continue
                    cmd = str((block.get("input") or {}).get("command") or "")
                    if not cmd or (unique and cmd in seen):
                        continue
                    seen.add(cmd)
                    yield cmd


def main() -> None:
    ap = argparse.ArgumentParser(description="Which destinations claim calls and never find the text.")
    ap.add_argument("--most-files", type=int, default=100000, metavar="N",
                    help="how many transcripts to read, newest first")
    ap.add_argument("--unique", action="store_true",
                    help="count each distinct command once instead of every time it was run")
    a = ap.parse_args()

    outcomes: dict[str, Counter] = {}
    claimed = Counter()
    first_text_after: dict[str, int] = {}
    gone = Counter()
    for cmd in calls(a.most_files, a.unique):
        given = {"command": cmd}
        try:
            dest = destinations.match("Bash", given)
        except Exception:
            continue
        if not dest:
            continue
        name = dest["name"]
        claimed[name] += 1
        try:
            got = destinations.recovered(dest, "Bash", given)
        except Exception:
            outcomes.setdefault(name, Counter())["crashed"] += 1
            continue
        outcomes.setdefault(name, Counter())[got.outcome] += 1
        if got.outcome == destinations.CHECKED:
            first_text_after.setdefault(name, claimed[name] - 1)
        elif got.outcome == destinations.NO_TEXT and reads_a_file_that_is_gone(dest, cmd):
            gone[name] += 1

    if not claimed:
        print("no destination claimed anything. Either nothing here sends prose through Bash, or this "
              "machine keeps no transcripts yet.")
        return
    for name in sorted(claimed):
        counts = outcomes.get(name) or Counter()
        print(f"\n{name}: {claimed[name]} claimed")
        for outcome, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {n:7d}  {outcome}")
        if gone[name]:
            print(f"  {gone[name]:7d}    of those, a file flag naming a path that is gone from disk "
                  f"now — a scan artifact, checked at the time")
        print(f"  first text after {first_text_after.get(name, 'NEVER — this is the shape the hook now reports')} "
              f"claimed call(s)")
    print(f"\nThe hook says so after {discover.SILENT_AFTER} claimed calls with no text and none ever "
          f"recovered, so a `first text after` above that number is a working destination this would "
          f"have reported.")


if __name__ == "__main__":
    main()
