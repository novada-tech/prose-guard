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


def read():
    try:
        with open(paths.at("config.json")) as fh:
            config = json.load(fh)
    except Exception:
        config = {}
    listed = config.get("shared") or []
    return config, list(listed if isinstance(listed, list) else [listed])


def write(config, listed):
    config["shared"] = listed
    paths.ensure()
    target = paths.at("config.json")
    with open(target, "w") as fh:
        json.dump(config, fh, indent=1)
        fh.write("\n")
    return target


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--add", metavar="DIR")
    ap.add_argument("--remove", metavar="DIR")
    a = ap.parse_args()
    config, listed = read()

    if a.add:
        if a.add in listed:
            print(f"already reading {a.add}")
        else:
            listed.append(a.add)
            print(f"added {a.add} -> {write(config, listed)}")
            # A directory that does not exist yet is not an error: a colleague may be adding the line
            # before the checkout lands. It is skipped until it appears, and saying so beats silence.
            if not os.path.isdir(os.path.expanduser(os.path.expandvars(a.add))):
                print("  it does not exist yet, so nothing is read from it until it does")
    elif a.remove:
        if a.remove not in listed:
            raise SystemExit(f"not configured: {a.remove}")
        listed.remove(a.remove)
        print(f"removed {a.remove} -> {write(config, listed)}")
        print("  the audiences it held are gone from this machine. The files are untouched.")

    print()
    if not listed:
        print("no shared directories. Only your own audiences and the built-in baselines are read.")
        return 0
    for entry in listed:
        real = os.path.expanduser(os.path.expandvars(entry))
        if not os.path.isdir(real):
            print(f"  {entry}\n      {real}  —  not present on this machine")
            continue
        names = [f for f in os.listdir(real) if f.endswith(".json")]
        audiences = [f for f in names if f != "destinations.json"]
        shared_destinations = 0
        if "destinations.json" in names:
            try:
                with open(os.path.join(real, "destinations.json")) as fh:
                    shared_destinations = len(json.load(fh).get("destinations") or [])
            except Exception:
                shared_destinations = 0
        held = [f"{len(audiences)} audience(s)"]
        if shared_destinations:
            held.append(f"{shared_destinations} destination(s)")
        print(f"  {entry}\n      {real}  —  {', '.join(held)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
