#!/usr/bin/env python3
"""Read audiences from a directory your team keeps, as well as your own.

    python3 lib/share_dir.py                       # what is configured now
    python3 lib/share_dir.py --add '$TEAM_REPO/claude/audiences'
    python3 lib/share_dir.py --remove '$TEAM_REPO/claude/audiences'

The receiving half of `audiences.py share`. One person measures an audience and commits it; everyone
else names the directory once and gets it, and every later improvement to it, by pulling.

The same directory can hold a `destinations.json`, and that is the more valuable half. An audience is
measured from one group's writing; a destination is a fact about which tool sends prose and which field
carries it, and that fact is the same for everyone using that tool. Working it out takes a conversation
with an agent about tools only it can see, and nobody should have that conversation twice.

Paths keep their `$VARS` and `~` unexpanded in the file and are expanded when read, so the same line
works on machines that keep their checkouts in different places — which is why a team setup script can
write it for everybody.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402


def listed():
    """The directories as they are written in config.json, `$VARS` and all.

    paths.shared() is the other half: it expands them and drops the ones that are not there, which is
    what a reader of audiences wants. This half has to show a line that is wrong, because that is the
    line somebody is looking at when they run this.
    """
    raw = paths.config().get("shared") or []
    return list(raw if isinstance(raw, list) else [raw])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--add", metavar="DIR")
    ap.add_argument("--remove", metavar="DIR")
    a = ap.parse_args()
    configured = listed()

    if a.add:
        if a.add in configured:
            print(f"already reading {a.add}")
        else:
            configured.append(a.add)
            print(f"added {a.add} -> {paths.update_config(shared=configured)}")
            # A directory that does not exist yet is not an error: a colleague may be adding the line
            # before the checkout lands. It is skipped until it appears, and saying so beats silence.
            if not os.path.isdir(os.path.expanduser(os.path.expandvars(a.add))):
                print("  it does not exist yet, so nothing is read from it until it does")
    elif a.remove:
        if a.remove not in configured:
            raise SystemExit(f"not configured: {a.remove}")
        configured.remove(a.remove)
        print(f"removed {a.remove} -> {paths.update_config(shared=configured)}")
        print("  the audiences it held are gone from this machine. The files are untouched.")

    print()
    if not configured:
        print("no shared directories. Only your own audiences and the built-in baselines are read.")
        return 0
    for entry in configured:
        real = os.path.expanduser(os.path.expandvars(entry))
        if not os.path.isdir(real):
            print(f"  {entry}\n      {real}  —  not present on this machine")
            continue
        # What in a shared directory is an audience and what is the destinations file is
        # paths.Layer's answer, not this file's. It used to be both, and audiences.py did not agree:
        # it globbed every .json and listed a phantom audience called `destinations`.
        layer = paths.Layer("shared", real, real)
        held = [f"{len(layer.audience_files())} audience(s)"]
        try:
            with open(layer.destinations) as fh:
                rows = len(json.load(fh).get("destinations") or [])
        except Exception:
            rows = 0
        if rows:
            held.append(f"{rows} destination(s)")
        print(f"  {entry}\n      {real}  —  {', '.join(held)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
