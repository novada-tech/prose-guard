#!/usr/bin/env python3
"""Every command the skills tell someone to run must exist and accept the flags it is given.

    python3 tests/test_docs_match_code.py

This exists because a skill documented `--audience` for a script that takes `--for`, and the person
who hit it lost time before anything else could go wrong. Prose and argparse drift apart silently:
nothing fails, the command just does not work, and the reader assumes they are holding it wrong.

It reads every SKILL.md, finds the commands, and checks each one against the real interface.
"""
import glob
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.abspath(os.path.join(HERE, "..", "plugins", "prose-guard"))
# ${CLAUDE_PLUGIN_ROOT} does expand inside a skill body — verified on 2.1.228 — so a skill may use it
# and the real path is the plugin directory.
ROOT_VAR = "${CLAUDE_PLUGIN_ROOT}"
INVOCATION = re.compile(r'python3\s+"?(\$\{CLAUDE_PLUGIN_ROOT\}/[\w/.-]+\.py)"?([^\n`]*)')
FLAG = re.compile(r"(?<![\w-])(--[a-z][a-z-]+)")
FAILS = []


def helptext(path):
    r = subprocess.run([sys.executable, path, "--help"], capture_output=True, text=True, timeout=120)
    return r.stdout + r.stderr


def main():
    seen = 0
    helps = {}
    for skill in sorted(glob.glob(os.path.join(PLUGIN, "skills", "*", "SKILL.md"))):
        body = open(skill).read()
        name = os.path.basename(os.path.dirname(skill))
        for script_ref, tail in INVOCATION.findall(body):
            seen += 1
            script = script_ref.replace(ROOT_VAR, PLUGIN)
            if not os.path.isfile(script):
                FAILS.append(f"{name}: no such script {script_ref}")
                continue
            if script not in helps:
                helps[script] = helptext(script)
            for flag in FLAG.findall(tail):
                if flag not in helps[script]:
                    FAILS.append(f"{name}: {os.path.basename(script)} does not accept {flag}"
                                 f"  (it accepts: "
                                 f"{', '.join(sorted(set(FLAG.findall(helps[script]))))})")
    # a subcommand-style script is checked the same way, via its own --help
    for skill in sorted(glob.glob(os.path.join(PLUGIN, "skills", "*", "SKILL.md"))):
        body = open(skill).read()
        name = os.path.basename(os.path.dirname(skill))
        for script_ref, sub in re.findall(
                r'python3\s+"?(\$\{CLAUDE_PLUGIN_ROOT\}/[\w/.-]+\.py)"?\s+(\w+)', body):
            script = script_ref.replace(ROOT_VAR, PLUGIN)
            if not os.path.isfile(script):
                continue
            if script not in helps:
                helps[script] = helptext(script)
            if "{" in helps[script] and sub not in helps[script]:
                FAILS.append(f"{name}: {os.path.basename(script)} has no subcommand {sub!r}")

    if seen == 0:
        FAILS.append("found no commands in any SKILL.md — this test would pass vacuously")
    for line in FAILS:
        print("FAIL", line)
    if FAILS:
        print(f"\n{len(FAILS)} failure(s) across {seen} documented command(s)")
        return 1
    print(f"skills match the code: {seen} documented command(s) checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
