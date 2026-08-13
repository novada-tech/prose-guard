#!/usr/bin/env python3
"""Install the communication rule into ~/.claude/rules/, where it loads every session.

    python3 lib/install_rule.py            # what state it is in
    python3 lib/install_rule.py --install
    python3 lib/install_rule.py --remove

A plugin cannot ship a rule: a rules/ directory inside a plugin does not load. So this copies the
file. It COPIES rather than symlinks on purpose — the plugin's directory is versioned and is replaced
on update, so a link into it breaks the moment you upgrade.

The consequence of copying is that an upgrade does not refresh it, which is why --status compares the
two and says so.

The rule is the cheapest part of this tool and the only part that acts while a message is being
written rather than when it is sent. It also reaches subagents, which an output style does not.
"""
import argparse
import filecmp
import os
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(_HERE, "..", "rule", "engineer-communication.md")
TARGET = os.path.join(os.path.expanduser("~"), ".claude", "rules",
                      "prose-guard-communication.md")


def _rival():
    """Another rule already loading that says much the same thing.

    Installing a second copy is worse than installing none: both load every turn, and longer
    guidance measurably dilutes adherence. It happened — a machine ended up with 501 words of
    near-identical rule across two files that differed only in their closing paragraph.

    Compared on opening words rather than on the whole text, because the copy that matters is a
    variant: a team's own version points at its own skills where this one is generic.
    """
    directory = os.path.dirname(TARGET)
    try:
        mine = set(open(SOURCE).read().split()[:40])
    except OSError:
        return None
    for name in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
        path = os.path.join(directory, name)
        if os.path.abspath(path) == os.path.abspath(TARGET) or not name.endswith(".md"):
            continue
        try:
            theirs = set(open(path).read().split()[:40])
        except OSError:
            continue
        if len(mine & theirs) >= 0.7 * len(mine):
            return path
    return None


def status():
    if not os.path.isfile(SOURCE):
        return "missing", f"the plugin's copy is not where it should be: {SOURCE}"
    rival = _rival()
    if rival and not os.path.exists(TARGET):
        return "duplicate", (
            f"{rival} already loads and says much the same thing. Installing this one would load "
            f"both every turn, and longer guidance measurably dilutes adherence. Keep the one you "
            f"have — if it is your team's own version it points at your own skills, which this "
            f"generic copy cannot. --force installs anyway.")
    if not os.path.exists(TARGET):
        return "absent", f"not installed. --install copies it to {TARGET}"
    if os.path.islink(TARGET):
        return "link", f"{TARGET} is a symlink. Replace it: a link into the plugin breaks on update"
    if filecmp.cmp(SOURCE, TARGET, shallow=False):
        return "current", f"installed and up to date: {TARGET}"
    return "stale", (f"installed but different from the plugin's copy. Either you edited it, which "
                     f"is fine, or the plugin was updated. Compare:\n"
                     f"  diff {TARGET} {SOURCE}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--force", action="store_true", help="overwrite a file you changed")
    a = ap.parse_args()
    state, message = status()

    if a.remove:
        if state in ("absent", "missing"):
            print("nothing to remove")
            return 0
        os.remove(TARGET)
        print("removed", TARGET)
        return 0

    if not a.install:
        print(f"{state}: {message}")
        return 0

    if state == "missing":
        print(message)
        return 1
    if state in ("stale", "link", "duplicate") and not a.force:
        print(f"{state}: {message}\n\nRe-run with --force to replace it.")
        return 1
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    shutil.copyfile(SOURCE, TARGET)
    print(f"installed {TARGET}\nRestart Claude Code: rules load at startup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
