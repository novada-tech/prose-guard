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
from __future__ import annotations

import glob
import json
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import command  # noqa: E402
import destinations  # noqa: E402
import host  # noqa: E402
import telling  # noqa: E402

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


def mcp_servers() -> list[str]:
    """Every MCP server this machine has configured, from the user's own file and from plugins.

    Plugins were read from `plugin.json` alone, which found none at all on a machine with 24 plugins
    installed — seven of them declare their servers in a sibling `.mcp.json`. A source that finds
    nothing and says nothing is worse than one that is absent, so host.py reads both and `missing()`
    reports a source that could not be read at all.
    """
    names = set(host.declared_servers())
    try:
        with open(host.user_config()) as fh:
            data = json.load(fh)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    names |= set((data.get("mcpServers") or {}).keys())
    for project in (data.get("projects") or {}).values():
        if isinstance(project, dict):
            names |= set((project.get("mcpServers") or {}).keys())
    return sorted(names)


def clis_on_path() -> list[str]:
    import shutil
    return sorted(name for name in OUTBOUND_CLIS if shutil.which(name))


def from_history(limit: int = 40000) -> tuple[dict[str, int], dict[str, int]]:
    """Which outbound tools you actually use. Command names only — never arguments.

    Arguments are the content of your messages, and this file is read to make a suggestion, not to
    build a corpus. Counting `git commit` without reading what was committed is the whole point.
    """
    counts: dict[str, int] = {}
    subcommands: dict[str, int] = {}
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


def from_transcripts(most_files: int = 400, per_file: int = 5000) -> dict[str, int]:
    """Which tools have actually carried prose to a person here, from past conversations.

    Shell history answers this for command-line tools and cannot answer it at all for MCP ones: an MCP
    call never touches a shell. That is where the destinations that matter are — measured across real
    transcripts on one machine, `mcp__slack__post` 114 calls, `mcp__fleet__post` 85,
    `add_comment_to_pending_review` 83, `slack_send_message` 65 — and setup could see none of them. It
    proposed from which MCP SERVERS were configured, which says nothing about which of their tools send
    prose.

    Same contract as `from_history`, and the same reason for it: what comes back is `_shape()`, which is a
    tool name and a field name. Never a value, never a line of anybody's message. This reads
    conversations to count shapes, not to build a corpus, and it is only run when somebody asks for it —
    see `--from-transcripts`.

    Bounded per file rather than in total, because a total budget spent on the newest conversations is
    recency and nothing else: a first pass capped at 4,000 rows reported Edit and Write and missed
    `mcp__slack__post` at 114 calls, which is the kind of destination this exists to find.
    """
    found: dict[str, int] = {}
    directory = os.path.join(host.dot_dir(), "projects")
    try:
        files = sorted(glob.glob(os.path.join(directory, "*", "*.jsonl")),
                       key=os.path.getmtime, reverse=True)
    except OSError:
        return found
    for path in files[:most_files]:
        try:
            fh = open(path, errors="replace")
        except OSError:
            continue
        seen = 0
        with fh:
            for line in fh:
                if '"tool_use"' not in line:
                    continue
                seen += 1
                if seen > per_file:
                    break
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                for block in (row.get("message", {}).get("content") or []):
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    given = block.get("input")
                    if not isinstance(given, dict):
                        continue
                    try:
                        shape = _shape(block.get("name") or "", given)
                    except Exception:
                        shape = None
                    if shape:
                        found[shape] = found.get(shape, 0) + 1
    return found


def unclaimed() -> dict[str, dict[str, Any]]:
    """Shapes seen carrying prose that no destination claims, with what has been decided about each."""
    out: dict[str, dict[str, Any]] = {}
    for key, entry in telling.everything().items():
        if not key.startswith("unclaimed: "):
            continue
        out[key[len("unclaimed: "):]] = {"uses": entry.get("seen", 0),
                                         "mentioned": bool(entry.get("said")),
                                         "declined": bool(entry.get("declined"))}
    return out


def covered() -> list[dict[str, Any]]:
    """Which shipped or configured destinations already exist, so setup does not re-suggest them."""
    out = []
    for dest in destinations.DESTINATIONS:
        out.append({"name": dest.get("name"), "tool": dest.get("tool"),
                    "bash": dest.get("bash"), "file": dest.get("file")})
    return out


def share(directory: str) -> str:
    """Kept as the name /prose-guard:setup uses. destinations.py owns the implementation."""
    return destinations.share(directory)


# Passive discovery. A shape is mentioned AT MOST ONCE, ever, and only once it has been used enough
# times to be worth interrupting for. What "at most once, ever" means is telling.py's job now — this
# had its own counter, its own `mentioned` flag and its own `declined` flag, which is the same ledger
# four other places were also keeping in their own way.
MENTION_AFTER = 3


# Fields that carry long text which is not being sent anywhere. `old_string` is what an edit replaces,
# `prompt` is an instruction to another agent, `pattern` and `command` are code. Long is not the same as
# outgoing, and discovery gets one mention per shape — spending it on these is spending it on nothing.
NOT_OUTGOING = ("old_string", "prompt", "pattern", "command", "query", "regex", "expression",
                "description", "script", "code", "diff", "input")
# Nothing is excluded for writing a file, and that was a mistake worth recording. The reasoning was
# that the prose-file destination already decides which files count — but it only claims a file that
# is TRACKED, and discovery is asked only about calls nothing claimed. So excluding Write silenced the
# one case that needed saying: a blog plan written to ~/novada, which is not a git repository at all,
# was never checked and, with the exclusion in place, was never mentioned either.


def _reads_like_prose(text: str) -> bool:
    """Long text that is prose rather than a pattern, a script or a payload.

    Passive discovery has one mention per shape and had been spending it on `git grep -E`, on the text
    an edit replaces, and on subagent prompts — six mentions in real use, none of them a destination.
    Word count alone cannot tell a paragraph from a regex; sentences and ordinary words can.
    """
    words = text.split()
    if len(words) < destinations.MIN_WORDS:
        return False
    if sum(text.count(c) for c in ".!?") < 2:
        return False                         # a paragraph has sentences; a pattern does not
    alpha = sum(1 for w in words if w.strip(".,;:!?()[]\"'").isalpha())
    return alpha >= 0.7 * len(words)


# This tool's own commands. Checking a check is circular, and the `--who` argument to check_prose.py is
# a sentence describing a reader, so it passes the prose test and was offered as a destination to add.
# Tools whose text has no human reader, so the two questions this tool asks have no answer for them.
# A prompt to a subagent is instructions to a machine that will act on them and report back; nobody is
# being asked to care about it or act on it after one read. Proposing these as destinations asks somebody
# to configure a check against writing that is not for anybody, and they came up on a real install.
NO_HUMAN_READER = ("SendMessage", "Agent", "Task", "Skill", "TodoWrite", "WebFetch", "AskUserQuestion")

OWN_COMMANDS = ("check_prose.py", "learn.py", "audiences.py", "discover.py", "install_rule.py",
                "share_dir.py", "fetch.py", "measure_check.py", "measure_cost.py", "measure_rule.py",
                "measure_thresholds.py", "measure_destinations.py")


def _shape(tool: str, tool_input: dict[str, Any]) -> str | None:
    """The SHAPE of a call carrying outgoing prose, never the text.

    For an MCP tool that is the tool name and the field. For Bash it is the binary, its subcommand and
    the flag that held the long argument, so `git commit -m` becomes discoverable the first time it is
    used rather than only if someone thought to configure it.
    """
    if tool == "Bash":
        cmd = str(tool_input.get("command") or "")
        if any(own in cmd for own in OWN_COMMANDS):
            return None
        cmd = command.command_itself(cmd)
        # The name comes from the command that holds the text, not from the start of the line. A chain
        # is several commands and only one of them is sending anything: `cd X && git commit -m "…"` was
        # recorded as `cd X`, so every checkout path became a permanent entry that could never recur,
        # and `git add . && git commit -m "…"` was recorded as `git add`. Over 16,058 real tool calls,
        # 74% of the shapes were unusable and most of the rest named the wrong command. See
        # `command.carrying` and `command.naming`.
        def named(at: int) -> str:
            return command.naming(command.carrying(cmd, at))

        for m in re.finditer(r"(--?[A-Za-z][-\w]*)[= ]\s*['\"]([^'\"]{80,})['\"]", cmd):
            if _reads_like_prose(m.group(2)):
                head = named(m.start())
                return f"bash: {head} {m.group(1)}" if head else None
        # Prose does not always arrive behind a flag. `echo "<a paragraph>"` and `somecli post "<a
        # paragraph>"` put it in a positional argument, and neither was recorded at all — so the one
        # example asked about would never have surfaced. The prose test is what keeps a grep pattern out.
        for m in re.finditer(r"['\"]([^'\"]{80,})['\"]", cmd):
            if _reads_like_prose(m.group(1)):
                head = named(m.start())
                return f"bash: {head}" if head else None
        return None
    if tool in NO_HUMAN_READER:
        return None
    for field, value in tool_input.items():
        if field in NOT_OUTGOING:
            continue
        if isinstance(value, str) and _reads_like_prose(value):
            return f"tool: {tool} [{field}]"
    return None


def decline(shape: str) -> str:
    """Never mention or count this shape again.

    This is what makes passive discovery safe to have at all. Without it, declining a suggestion and
    then using the tool again would produce the same suggestion a second time, which is the failure
    that makes people turn a tool off.
    """
    return telling.Ledger().decline("unclaimed: " + shape)


# Words in a tool or command name that say something about what it does with the text. A suggestion
# only: never applied without someone confirming it, because a wrong guess here is a destination that
# quietly stops holding anything back.
REVIEWED_FIRST = ("draft", "preview", "unsent", "scratch", "compose", "stage")
# Specific forms, not bare words. "note" on its own matched `glab mr note`, which is a comment on
# a merge request and has an addressee — the exact mistake this suggestion exists to avoid
# making silently.
NO_ADDRESSEE = ("git commit", "git tag", "git notes", "changelog", "release_note",
                "release-note")


def suggest_caps(shape: str) -> dict[str, tuple[str, str]]:
    """What a new destination probably deserves, and why, in words a person can agree or disagree with.

    Discovery used to be a yes-or-no question, so everything it added ran at full effort and blocked.
    That is the wrong default in two specific cases, and they are the two things only a person knows:
    whether anybody sees the text before its audience does, and whether it has an addressee at all. The
    name is weak evidence about both — enough to open with a proposal rather than a blank question.
    """
    lowered = shape.lower()
    out: dict[str, tuple[str, str]] = {}
    if any(word in lowered for word in REVIEWED_FIRST):
        out["max_severity"] = ("advise", "the name says draft, so you would read it before it went "
                                         "anywhere — blocking would argue about text you were about "
                                         "to read")
    if any(word in lowered for word in NO_ADDRESSEE):
        out["max_effort"] = ("low", "this looks like a record rather than a message to somebody, and "
                                    "the checks above `low` ask whether the reader will care and "
                                    "whether the ask is clear")
    return out


def record_candidate(tool: str, tool_input: dict[str, Any]) -> str | None:
    """Count a call nothing claimed, and return a one-line note if now is the moment to say so.

    Returns None almost always: at most one note per shape for the lifetime of the config.
    """
    shape = _shape(tool, tool_input)
    if not shape:
        return None
    ledger = telling.Ledger()
    key = "unclaimed: " + shape
    uses = ledger.seen(key)
    if uses < MENTION_AFTER or not ledger.worth_saying(key, for_good=True):
        return None
    caps = suggest_caps(shape)
    return (f"prose-guard has seen long text go out through `{shape}` {uses} times and "
            f"does not check it. Add it with /prose-guard:setup if that is worth checking"
            + (f" — probably as {', '.join(v[0] for v in caps.values())} rather than a block, "
               f"going by the name" if caps else "")
            + f". This is the only time it will be mentioned.")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="What here could be sending prose to a person.")
    ap.add_argument("--decline", metavar="SHAPE",
                    help="never suggest this shape again. Permanent, and what setup uses when you "
                         "say no.")
    ap.add_argument("--from-transcripts", action="store_true",
                    help="count which tools have carried prose in past conversations on this machine. "
                         "Reads them to count shapes — a tool name and a field name — and never a value "
                         "from anybody's message. Ask before running it: they are private.")
    ap.add_argument("--share", metavar="DIR",
                    help="copy the destinations you have worked out into a directory your team keeps, "
                         "so nobody else has to work them out")
    a = ap.parse_args()
    if a.decline:
        print("declined for good:", decline(a.decline))
        return
    if a.share:
        print(share(a.share))
        return

    if a.from_transcripts:
        counted = from_transcripts()
        claimed = {d.get("name") for d in destinations.DESTINATIONS}
        print("Tools that have carried prose to somebody here, most used first.")
        print("Shapes only — a tool name and a field name, never a value from a message.\n")
        if not counted:
            print("  nothing found. Either nothing here sends prose, or this machine keeps no "
                  "transcripts yet.")
            return
        for shape, uses in sorted(counted.items(), key=lambda kv: -kv[1]):
            print(f"  {uses:5d}  {shape}")
        print(f"\n{len(counted)} shape(s). Ones already covered by a destination need nothing; for the "
              f"rest, /prose-guard:setup writes them.")
        print(f"Destinations configured now: {', '.join(sorted(n for n in claimed if n)) or 'none'}")
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
            for field, (value, why) in suggest_caps(shape).items():
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
