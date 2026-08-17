#!/usr/bin/env python3
"""Every draft this machine has actually held back, with what it was held for and where it was going.

    python3 measure/held_drafts.py --out /tmp/held.json

A corpus that costs nothing and is better than any fixture: real messages, written for real readers, with
a real complaint attached and, usually, the rewrite that satisfied it. One machine's transcripts held 95
of them.

Reads transcripts, so it stays on the machine. Unlike `discover.py`, this DOES keep message text — that is
the point of it — so what it writes is as private as the transcripts it came from. Write it somewhere
temporary, and do not commit what comes out.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "plugins", "prose-guard", "lib"))

import host  # noqa: E402

COMPLAINT = re.compile(r"Hold this message\.\s*(?:\[[^\]]+\]\s*)?(.+?)(?:, then send again|\.?\s*Then send)",
                       re.S)


def held(most_files: int | None = None) -> list[dict]:
    """Each held draft: the text, the complaint, and whatever fields located it."""
    out = []
    # Every transcript, not the newest few hundred. A cap of 400 found 12 of the 59 holds on this
    # machine: they are spread across sessions rather than concentrated in recent ones, and the whole
    # point of this corpus is that it is small and hard-won. Reading all of them takes about a second.
    files = sorted(glob.glob(os.path.join(host.dot_dir(), "projects", "*", "*.jsonl")),
                   key=os.path.getmtime, reverse=True)
    for path in (files if most_files is None else files[:most_files]):
        try:
            body = open(path, errors="ignore").read()
        except OSError:
            continue
        if "Hold this message" not in body:
            continue
        issued = {}
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
                    issued[block.get("id")] = (block.get("name") or "", block.get("input") or {})
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in issued:
                    # A denial, not a file that happens to contain the phrase. A hook refusal comes
                    # back as the whole result and begins with it; reading this repository's own notes
                    # produced four phantom "held" Read calls before this line existed.
                    content = block.get("content")
                    if isinstance(content, list):
                        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                    content = str(content or "").lstrip()
                    if not re.match(r"(Error:\s*)?Hold this message", content):
                        continue
                    seen = content
                    tool, given = issued[block["tool_use_id"]]
                    if not isinstance(given, dict):
                        continue
                    text = max((v for v in given.values() if isinstance(v, str)), key=len, default="")
                    found = COMPLAINT.search(seen)
                    out.append({"tool": tool, "body": text,
                                "complaint": (found.group(1) if found else "").replace("\\n", " ")[:400],
                                "path": given.get("path"), "line": given.get("line"),
                                "pullNumber": given.get("pullNumber")})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, metavar="FILE", help="where to write them. Somewhere temporary.")
    a = ap.parse_args()
    drafts = held()
    with open(a.out, "w") as fh:
        json.dump(drafts, fh, indent=1)
    print(f"{len(drafts)} held draft(s) -> {a.out}")
    by_tool: dict[str, int] = {}
    for d in drafts:
        by_tool[d["tool"]] = by_tool.get(d["tool"], 0) + 1
    for tool, n in sorted(by_tool.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {tool}")
    print("\nThis file holds message text. Do not commit it.")


if __name__ == "__main__":
    main()
