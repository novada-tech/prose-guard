#!/usr/bin/env python3
"""Install the communication rule into ~/.claude/rules/, where it loads every session.

    python3 lib/install_rule.py --status
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


def status():
    if not os.path.isfile(SOURCE):
        return "missing", f"the plugin's copy is not where it should be: {SOURCE}"
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
    if state in ("stale", "link") and not a.force:
        print(f"{state}: {message}\n\nRe-run with --force to replace it.")
        return 1
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    shutil.copyfile(SOURCE, TARGET)
    print(f"installed {TARGET}\nRestart Claude Code: rules load at startup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
