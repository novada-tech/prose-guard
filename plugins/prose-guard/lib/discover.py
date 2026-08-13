#!/usr/bin/env python3
"""What on this machine could be sending prose to a person, so setup can suggest rather than ask.

    python3 lib/discover.py

Four sources, all deterministic and all local. Nothing here decides anything: it hands a list to
`/prose-guard:setup`, which proposes destinations and asks you to confirm. Guessing wrong in either
direction is cheap — a missed destination goes unchecked, an invented one checks something harmless —
but only if a person sees the list, which is why this prints rather than writes.

    mcp        MCP servers configured for Claude Code. Names only; the tools they expose are not
               knowable from disk, so setup asks the agent which of its own tools belong to them.
    cli        outbound command-line tools on PATH. Installed is weak evidence of used.
    history    the same tools as they appear in your shell history, which is strong evidence. Only
               command NAMES are counted; no arguments are read, because arguments carry content.
    unclaimed  tools that already carried long prose past the hook without any destination
               claiming them. The best evidence of all, because it happened.
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import destinations  # noqa: E402

# Command-line tools that post prose to people. Extend freely: an entry here only ever becomes a
# suggestion.
OUTBOUND_CLIS = {
    "gh": "GitHub — pull request and issue comments, PR descriptions, release notes",
    "glab": "GitLab — merge request notes and descriptions",
    "git": "commit messages, annotated tags and notes",
    "jira": "Jira — issue comments and descriptions",
    "az": "Azure DevOps — work item comments",
    "tea": "Gitea — issue and pull request comments",
    "slack": "Slack CLI — messages",
    "teams": "Microsoft Teams CLI — messages",
    "mail": "email",
    "sendmail": "email",
    "curl": "anything, including webhooks that post to chat",
}


def mcp_servers():
    """From ~/.claude.json, at the root and per project, plus any installed plugin that ships one."""
    names = set()
    path = os.path.join(os.path.expanduser("~"), ".claude.json")
    try:
        with open(path) as fh:
            data = json.load(fh)
    except Exception:
        data = {}
    names |= set((data.get("mcpServers") or {}).keys())
    for project in (data.get("projects") or {}).values():
        if isinstance(project, dict):
            names |= set((project.get("mcpServers") or {}).keys())
    for manifest in glob.glob(os.path.join(os.path.expanduser("~"), ".claude", "plugins",
                                           "cache", "*", "*", "*", ".claude-plugin",
                                           "plugin.json")):
        try:
            with open(manifest) as fh:
                d = json.load(fh)
            if d.get("mcpServers"):
                names |= set(d["mcpServers"].keys())
        except Exception:
            continue
    return sorted(names)


def clis_on_path():
    import shutil
    return sorted(name for name in OUTBOUND_CLIS if shutil.which(name))


def from_history(limit=40000):
    """Which outbound tools you actually use. Command names only — never arguments.

    Arguments are the content of your messages, and this file is read to make a suggestion, not to
    build a corpus. Counting `git commit` without reading what was committed is the whole point.
    """
    counts = {}
    subcommands = {}
    for name in ("~/.zsh_history", "~/.bash_history", "~/.local/share/fish/fish_history"):
        path = os.path.expanduser(name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, errors="replace") as fh:
                lines = fh.readlines()[-limit:]
        except OSError:
            continue
        for line in lines:
            # zsh writes ": <ts>:<elapsed>;<command>"
            cmd = line.split(";", 1)[-1].strip() if line.startswith(":") else line.strip()
            words = re.findall(r"[\w.-]+", cmd)[:2]
            if not words:
                continue
            head = words[0]
            if head in OUTBOUND_CLIS:
                counts[head] = counts.get(head, 0) + 1
                if len(words) > 1:
                    key = f"{head} {words[1]}"
                    subcommands[key] = subcommands.get(key, 0) + 1
    return counts, subcommands


def unclaimed():
    """Shapes that carried long prose past the hook with no destination claiming them, and what has
    been decided about each: how many uses, whether it has been mentioned, whether it was declined."""
    try:
        with open(destinations._candidates_path()) as fh:
            return json.load(fh)
    except Exception:
        return {}


def covered():
    """Which shipped or configured destinations already exist, so setup does not re-suggest them."""
    out = []
    for dest in destinations.DESTINATIONS:
        out.append({"name": dest.get("name"), "tool": dest.get("tool"),
                    "bash": dest.get("bash"), "file": dest.get("file")})
    return out


def share(directory):
    """Copy the destinations from this machine into a directory a team keeps.

    Worth more shared than an audience is. An audience describes one group of readers and is measured
    from their writing; a destination records which tool sends prose and which field carries it, and that
    is the same fact for everyone who uses that tool. Working it out means an agent listing the tools it
    can see and a person confirming them, and nobody should do that twice.

    Only what this machine added: the shipped set is already everywhere, and copying it would put a stale
    duplicate in front of the maintained one.
    """
    mine = destinations._read(os.path.join(destinations.config_dir(), "destinations.json"))
    rows = list(mine.get("destinations") or [])
    if not rows:
        return ("Nothing to share: no destinations have been added on this machine. The shipped ones "
                "are already everywhere. Run /prose-guard:setup to work out what is missing.")
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, "destinations.json")
    existing = destinations._read(target)
    have = {json.dumps(x, sort_keys=True) for x in (existing.get("destinations") or [])}
    added = [x for x in rows if json.dumps(x, sort_keys=True) not in have]
    merged = dict(existing)
    merged["destinations"] = list(existing.get("destinations") or []) + added
    merged.setdefault("_meta", {})["what"] = (
        "Destinations this team has worked out. Read after your own file and before the shipped set, so "
        "your own destinations.json still wins locally.")
    with open(target, "w") as fh:
        json.dump(merged, fh, indent=1)
        fh.write("\n")
    names = ", ".join(x.get("name", "?") for x in added) or "nothing new"
    return (f"{len(added)} added to {target}: {names}\n"
            f"Nothing is shared until you commit it. Then anyone whose config lists that directory has "
            f"them, with no setup conversation of their own.")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="What here could be sending prose to a person.")
    ap.add_argument("--decline", metavar="SHAPE",
                    help="never suggest this shape again. Permanent, and what setup uses when you "
                         "say no.")
    ap.add_argument("--share", metavar="DIR",
                    help="copy the destinations you have worked out into a directory your team keeps, "
                         "so nobody else has to work them out")
    a = ap.parse_args()
    if a.decline:
        print("declined for good:", destinations.decline(a.decline))
        return
    if a.share:
        print(share(a.share))
        return

    servers = mcp_servers()
    used, subs = from_history()
    print("MCP servers configured here:")
    print("  " + (", ".join(servers) if servers else "none found"))
    print("\n  Which of their tools send prose is not knowable from disk. /prose-guard:setup asks")
    print("  the agent which tools it can actually see, and you confirm.\n")
    print("  Two questions decide how hard each one is checked, and only you can answer them:")
    print("    Does anybody read it before its audience does? Then findings should advise, not block.")
    print("    Does it have an addressee and an ask? If not, the term check is the part that applies.")
    print("  See max_severity and max_effort in docs/reference.md.\n")

    print("Outbound command-line tools on PATH:")
    for name in clis_on_path():
        seen = used.get(name, 0)
        print(f"  {name:10s} {OUTBOUND_CLIS[name]}"
              + (f"  [used {seen}x in your history]" if seen else "  [not in your history]"))

    if subs:
        print("\nThe forms you actually use:")
        for key, n in sorted(subs.items(), key=lambda kv: -kv[1])[:12]:
            print(f"  {n:5d}x  {key}")

    un = unclaimed()
    pending = {k: v for k, v in un.items() if not v.get("declined")}
    declined = [k for k, v in un.items() if v.get("declined")]
    if pending:
        print("\nAlready carried long prose past the guard, and nothing claimed it:")
        for shape, entry in sorted(pending.items(), key=lambda kv: -kv[1].get("uses", 0)):
            seen = " (already mentioned once)" if entry.get("mentioned") else ""
            print(f"  {entry.get('uses', 0):5d}x  {shape}{seen}")
            for field, (value, why) in destinations.suggest_caps(shape).items():
                print(f"           suggest {field}={value}: {why}")
        print("\n  To rule one out for good, so it is never suggested again:")
        print("    python3 lib/discover.py --decline '<shape>'")
    else:
        print("\nNothing unclaimed. This fills in as you work.")
    if declined:
        print(f"\nDeclined, and never suggested again: {', '.join(declined)}")

    print("\nAlready covered:")
    for d in covered():
        print(f"  {d['name']}")


if __name__ == "__main__":
    main()
