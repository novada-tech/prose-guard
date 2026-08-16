#!/usr/bin/env python3
"""The argument that happened before a message went out, kept so it can be read back.

    python3 lib/rounds.py list      # what was argued about, newest first
    python3 lib/rounds.py show 1    # one argument in full: every draft, and what changed
    python3 lib/rounds.py forget    # delete all of it

A held message is an exchange the person never sees. The guard says what was wrong, the agent rewrites,
and the version that finally goes out is the only one that reaches anybody — so a bad complaint and a
good one look identical afterwards, and there is no way to tell whether the rewrite improved the message
or merely satisfied the tool. This is that exchange, on disk, for whoever wants to check.

**This writes message text, and nothing else in this tool does.** `discover.py` records the shape of a
call and never its content, deliberately. So the rule here is narrow, and it is the reason this file can
exist without contradicting that one:

    nothing is written unless a check actually held a message back

A message that passes leaves no trace. A message nobody objected to leaves no trace. What is kept is
exactly the arguments, which is what there is to inspect, and it is kept in your own config directory
next to everything else this tool remembers — never in a repository, never anywhere it can be pushed.

Bounded at MOST_KEPT arguments and LONGEST characters a draft, so a long session cannot fill a disk. Old
files are removed as new ones arrive, and `forget` empties it now.
"""
import argparse
import glob
import json
import os
import time

import paths

# One bound, across every session on the machine, because that is the number somebody can reason about
# — 40 a session times however many sessions is not a bound anybody can hold in their head. The oldest
# go as new ones arrive. A hundred arguments is more than a week of a busy install and about 600KB at
# the cap below.
MOST_KEPT = 100
# A draft longer than this is truncated rather than dropped: what a reader wants is the difference
# between two versions, and the difference is usually near the part somebody objected to.
LONGEST = 6000


def _dir():
    return paths.at("rounds")


def _path(session):
    return os.path.join(_dir(), f"{session}.json")


def _read(path):
    try:
        with open(path) as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except Exception:
        return {}


def _write(path, data):
    try:
        os.makedirs(_dir(), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(data, fh, indent=1)
    except OSError:
        pass                                 # remembering is a convenience, never a reason to fail


def _clip(text):
    text = str(text or "")
    return text if len(text) <= LONGEST else text[:LONGEST] + "\n[...truncated]"


def held(session, destination, level, text, check, said):
    """Record a draft that was refused, and why. The first call opens an argument."""
    path = _path(session)
    data = _read(path)
    if not data.get("open"):
        data["open"] = {"started": time.time(), "destination": destination, "level": level,
                        "drafts": []}
    data["open"]["drafts"].append({"text": _clip(text), "held_by": check, "said": said})
    _write(path, data)


def went_out(session, text):
    """Close the open argument with the text that finally went out. No argument, nothing written."""
    path = _path(session)
    data = _read(path)
    argument = data.pop("open", None)
    if not argument:
        return None                          # nothing was held back, so there is nothing to look at
    argument["sent"] = _clip(text)
    argument["ended"] = time.time()
    data.setdefault("arguments", []).append(argument)
    _write(path, data)
    _prune()
    return len(argument["drafts"])


def _prune():
    """Keep the newest MOST_KEPT arguments across every session, and drop what falls out.

    Counted across sessions rather than within one, because a per-session cap is not a bound: a machine
    that opens twenty sessions a day keeps twenty times whatever the number says.
    """
    files = sorted(glob.glob(os.path.join(_dir(), "*.json")), key=os.path.getmtime, reverse=True)
    room = MOST_KEPT
    for path in files:
        data = _read(path)
        arguments = data.get("arguments") or []
        if room <= 0:
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        if len(arguments) > room:
            data["arguments"] = arguments[-room:]
            _write(path, data)
        room -= len(data.get("arguments") or [])


def everything():
    """Every closed argument on this machine, newest first."""
    out = []
    for path in glob.glob(os.path.join(_dir(), "*.json")):
        data = _read(path)
        for argument in data.get("arguments") or []:
            out.append(dict(argument, session=os.path.basename(path)[:-5]))
    return sorted(out, key=lambda a: a.get("ended") or 0, reverse=True)


def forget():
    gone = 0
    for path in glob.glob(os.path.join(_dir(), "*.json")):
        try:
            os.remove(path)
            gone += 1
        except OSError:
            pass
    return gone


def _when(stamp):
    return time.strftime("%d %b %H:%M", time.localtime(stamp)) if stamp else "?"


def _differs(before, after):
    """The first line that is not in both, which is nearly always the one somebody was asked to fix."""
    old = set(before.split("\n"))
    for line in after.split("\n"):
        if line.strip() and line not in old:
            return line.strip()
    return ""


def _cli():
    ap = argparse.ArgumentParser(
        description="Read back an argument the guard had with an agent: every draft it held, what it "
                    "said, and what finally went out. Only messages that were actually held back are "
                    "kept, and only in your own config directory.")
    # `list` is a subcommand rather than the bare default, so this reads like its siblings:
    # `audiences.py list`, `destinations.py list`. It also means the documentation check can tell a
    # command that needs a subcommand from one that does not, which it cannot do from a usage line.
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="what was argued about, newest first")
    p = sub.add_parser("show", help="one argument in full, by its number in the list")
    p.add_argument("which", type=int)
    sub.add_parser("forget", help="delete every argument kept on this machine")
    a = ap.parse_args()

    if a.cmd == "forget":
        print(f"deleted {forget()} session file(s) from {_dir()}")
        return

    kept = everything()
    if not kept:
        print("Nothing to show: no message has been held back on this machine.")
        print(f"Arguments are kept in {_dir()} once one is.")
        return

    if a.cmd == "show":
        if not 1 <= a.which <= len(kept):
            raise SystemExit(f"there is no argument {a.which}. There are {len(kept)}.")
        argument = kept[a.which - 1]
        print(f"{argument['destination']}, {_when(argument.get('started'))}, "
              f"effort {argument.get('level', '?')}, {len(argument['drafts'])} rewrite(s)\n")
        for n, draft in enumerate(argument["drafts"], 1):
            print(f"--- draft {n} " + "-" * 58)
            print(draft["text"])
            print(f"\n  HELD by {draft['held_by']}: {draft['said']}\n")
        print("--- sent " + "-" * 61)
        print(argument["sent"])
        changed = _differs(argument["drafts"][-1]["text"], argument["sent"])
        if changed:
            print(f"\n  first line that is new in the sent version: {changed}")
        return

    print(f"{len(kept)} argument(s), newest first. `show N` for one in full.\n")
    for n, argument in enumerate(kept, 1):
        drafts = len(argument["drafts"])
        by = ", ".join(sorted({d["held_by"] for d in argument["drafts"]}))
        print(f"{n:3d}  {_when(argument.get('started')):13s} {argument['destination']:22s} "
              f"{drafts} rewrite(s), held by {by}")
    print(f"\nkept in {_dir()} — `forget` deletes all of it")


if __name__ == "__main__":
    _cli()
