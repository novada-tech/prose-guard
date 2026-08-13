#!/usr/bin/env python3
"""Every command the docs tell someone to run must exist and accept the flags it is given.

    python3 tests/test_docs_match_code.py

This exists because a skill documented `--audience` for a script that takes `--for`, and the person
who hit it lost time before anything else could go wrong. Prose and argparse drift apart silently:
nothing fails, the command just does not work, and the reader assumes they are holding it wrong.

It reads every markdown file in the repository that contains a command — skills, docs, the README,
the contributing guide — and checks each one against the real interface, including subcommands, whose
flags argparse lists only in their own help.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
PLUGIN = os.path.join(REPO, "plugins", "prose-guard")
# ${CLAUDE_PLUGIN_ROOT} does expand inside a skill body — verified on 2.1.228 — so a skill may use it
# and the real path is the plugin directory. A skill writes it because it runs from anywhere; the docs
# write a relative path because a reader is standing in the checkout. Both name the same file.
ROOT_VAR = "${CLAUDE_PLUGIN_ROOT}"
INVOCATION = re.compile(r'python3\s+"?((?:\$\{CLAUDE_PLUGIN_ROOT\}/|(?:lib|measure)/)[\w/.-]+\.py)"?'
                        r'([^\n`]*)')
FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z-]+)")
# argparse prints its subcommand choices as a positional line of their own: `    {scan,create}`.
# Matching that line, rather than any brace anywhere, is what separates a subcommand list from a
# flag's choices — `--effort {low,medium,high}` made `check_prose.py draft.md` look like a
# subcommand call, and the check reported a command that works perfectly.
SUBCOMMANDS = re.compile(r"^\s{2,}\{([a-z][\w,-]*)\}\s*$", re.M)
FAILS = []
_help = {}


def sources():
    """Every markdown file in the repository that tells a reader to run something.

    Discovered rather than listed. A named list of directories passed while quietly covering fourteen
    fewer commands than the run before it, and a coverage number nobody is looking at is the one that
    shrinks. A new documentation file is now checked the moment it contains a command.
    """
    found = []
    for here, dirs, names in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
        for name in sorted(names):
            if not name.endswith(".md"):
                continue
            path = os.path.join(here, name)
            if INVOCATION.search(open(path, encoding="utf-8", errors="replace").read()):
                found.append(path)
    return sorted(found)


def undocumented():
    """Every command-line entry point that no documented command runs, down to the subcommand.

    Two things hide here. A capability nobody is told to run is a feature that does not exist — a
    subcommand was added, tested and shipped while the only instructions for it lived in a commit
    message. And if the pattern above ever stops matching how a command is written, coverage falls
    silently: the entry points stay the same while the count of parsed commands drops, so this notices.
    """
    ran = set()
    for doc in sources():
        for script_ref, tail in INVOCATION.findall(open(doc).read()):
            script = os.path.realpath(resolve(script_ref))
            words = [w for w in tail.split() if not w.startswith("-")]
            ran.add((script, words[0] if words else None))
            ran.add((script, None))            # the script itself was run, whatever it was given
    out = []
    for directory in (os.path.join(PLUGIN, "lib"), os.path.join(PLUGIN, "lib", "checks"),
                      os.path.join(REPO, "measure")):
        for name in sorted(os.listdir(directory) if os.path.isdir(directory) else []):
            path = os.path.join(directory, name)
            if not name.endswith(".py"):
                continue
            if "argparse" not in open(path, encoding="utf-8", errors="replace").read():
                continue                       # a library, not something anyone runs
            real = os.path.realpath(path)
            rel = os.path.relpath(path, REPO)
            if (real, None) not in ran:
                mentioned = any(name in open(d).read() for d in sources())
                out.append(f"{rel} takes command-line arguments and no documentation runs it"
                           + (" — it is mentioned, but not as a command anyone can copy"
                              if mentioned else ""))
                continue
            subs = set()
            for group in SUBCOMMANDS.findall(helptext(path)):
                subs.update(group.split(","))
            for sub in sorted(subs - {s for p, s in ran if p == real}):
                out.append(f"{rel} has a {sub!r} subcommand that no documentation runs")
    return out


def label(path):
    if path.endswith("SKILL.md"):
        return os.path.basename(os.path.dirname(path))
    return os.path.relpath(path, REPO)


def resolve(script_ref):
    if script_ref.startswith(ROOT_VAR):
        return script_ref.replace(ROOT_VAR, PLUGIN)
    if script_ref.startswith("measure/"):
        return os.path.join(REPO, script_ref)   # measure/ is at the repo root, not inside the plugin
    return os.path.join(PLUGIN, script_ref)


def helptext(*argv):
    if argv not in _help:
        r = subprocess.run([sys.executable, *argv, "--help"], capture_output=True, text=True,
                           timeout=120)
        _help[argv] = r.stdout + r.stderr
    return _help[argv]


def main():
    seen = 0
    for doc in sources():
        name = label(doc)
        for script_ref, tail in INVOCATION.findall(open(doc).read()):
            seen += 1
            script = resolve(script_ref)
            if not os.path.isfile(script):
                FAILS.append(f"{name}: no such script {script_ref}")
                continue

            subs = set()
            for group in SUBCOMMANDS.findall(helptext(script)):
                subs.update(group.split(","))

            # A flag is checked against the level of the command it was written under. `--command`
            # belongs to `learn.py scan` and appears nowhere in `learn.py --help`, so checking every
            # flag against the top level reported working commands as broken.
            words = [w for w in tail.split() if not w.startswith("-")]
            argv, where = [script], os.path.basename(script)
            if subs:
                if not words:
                    FAILS.append(f"{name}: {os.path.basename(script)} needs one of "
                                 f"{{{','.join(sorted(subs))}}} and was given none")
                    continue
                if words[0] not in subs:
                    FAILS.append(f"{name}: {os.path.basename(script)} has no subcommand "
                                 f"{words[0]!r} (it has: {', '.join(sorted(subs))})")
                    continue
                argv, where = [script, words[0]], f"{os.path.basename(script)} {words[0]}"

            usage = helptext(*argv)
            for flag in FLAG.findall(tail):
                if flag not in usage:
                    FAILS.append(f"{name}: {where} does not accept {flag}  (it accepts: "
                                 f"{', '.join(sorted(set(FLAG.findall(usage))))})")

    if seen == 0:
        FAILS.append("found no commands in any documentation — this test would pass vacuously")
    FAILS.extend(undocumented())
    for line in FAILS:
        print("FAIL", line)
    if FAILS:
        print(f"\n{len(FAILS)} failure(s) across {seen} documented command(s)")
        return 1
    print(f"docs match the code: {seen} documented command(s) checked "
          f"across {len(sources())} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
