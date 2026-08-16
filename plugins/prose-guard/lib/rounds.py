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
from __future__ import annotations

import argparse
import glob
import json
import os
import time
from typing import Any

import paths

# One bound, across every session on the machine, because that is the number somebody can reason about
# — 40 a session times however many sessions is not a bound anybody can hold in their head. The oldest
# go as new ones arrive. A hundred arguments is more than a week of a busy install and about 600KB at
# the cap below.
MOST_KEPT = 100
# A draft longer than this is truncated rather than dropped: what a reader wants is the difference
# between two versions, and the difference is usually near the part somebody objected to.
LONGEST = 6000


def _dir() -> str:
    return paths.at("rounds")


def _path(session: str) -> str:
    return os.path.join(_dir(), f"{session}.json")


def _read(path: str) -> dict[str, Any]:
    try:
        with open(path) as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except Exception:
        return {}


def _write(path: str, data: dict[str, Any]) -> None:
    try:
        os.makedirs(_dir(), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(data, fh, indent=1)
    except OSError:
        pass                                 # remembering is a convenience, never a reason to fail


def _clip(text: Any) -> str:
    text = str(text or "")
    return text if len(text) <= LONGEST else text[:LONGEST] + "\n[...truncated]"


def held(session: str, envelope: dict[str, Any], text: str, check: str, said: str) -> None:
    """Record a draft that was refused, and why. The first call opens an argument.

    `envelope` is everything the checks were told before they read a word — see `envelope()` in the
    hook. It is kept because "why did it say that" is almost never answered by the finding: it is
    answered by which audience applied, what the destination said the moment was, and which level
    actually ran after the destination capped it.
    """
    path = _path(session)
    data = _read(path)
    if not data.get("open"):
        data["open"] = {"started": time.time(), "drafts": [], **envelope}
    data["open"]["drafts"].append({"text": _clip(text), "held_by": check, "said": said})
    _write(path, data)


def went_out(session: str, text: str, spent: int | None = None) -> int | None:
    """Close the open argument with the text that finally went out. No argument, nothing written."""
    path = _path(session)
    data = _read(path)
    argument = data.pop("open", None)
    if not argument:
        return None                          # nothing was held back, so there is nothing to look at
    if spent is not None:
        argument["model_calls"] = spent
    argument["sent"] = _clip(text)
    argument["ended"] = time.time()
    data.setdefault("arguments", []).append(argument)
    _write(path, data)
    _prune()
    return len(argument["drafts"])


def _prune() -> None:
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


def everything() -> list[dict[str, Any]]:
    """Every closed argument on this machine, newest first."""
    out: list[dict[str, Any]] = []
    for path in glob.glob(os.path.join(_dir(), "*.json")):
        data = _read(path)
        for argument in data.get("arguments") or []:
            out.append(dict(argument, session=os.path.basename(path)[:-5]))
    return sorted(out, key=lambda a: a.get("ended") or 0, reverse=True)


def forget() -> int:
    gone = 0
    for path in glob.glob(os.path.join(_dir(), "*.json")):
        try:
            os.remove(path)
            gone += 1
        except OSError:
            pass
    return gone


def _when(stamp: float | None) -> str:
    return time.strftime("%d %b %H:%M", time.localtime(stamp)) if stamp else "?"


def _differs(before: str, after: str) -> str:
    """The first line that is not in both, which is nearly always the one somebody was asked to fix."""
    old = set(before.split("\n"))
    for line in after.split("\n"):
        if line.strip() and line not in old:
            return line.strip()
    return ""


def _envelope_lines(argument: dict[str, Any]) -> list[tuple[str, Any]]:
    """The envelope as label/value pairs, in the order somebody debugging reads them."""
    out = [("effort", argument.get("level", "?"))]
    if argument.get("asked_for") and argument["asked_for"] != argument.get("level"):
        out.append(("capped from", f"{argument['asked_for']} — this destination is worth less"))
    out.append(("judged for", argument.get("audience") or "?"))
    if argument.get("guessing"):
        out.append(("", "no audience matched, so nothing could be held back on terms"))
    for key, value in (argument.get("situation") or {}).items():
        out.append((key, value))
    out.append(("checks that ran", ", ".join(argument.get("checks") or []) or "?"))
    if argument.get("model_calls") is not None:
        out.append(("model calls", argument["model_calls"]))
    if argument.get("edit_of"):
        out.append(("this call wrote", f"{argument['edit_of']} sentence(s) of a longer document"))
    return out


def _cli() -> None:
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
        print(f"{argument.get('destination', '?')}, {_when(argument.get('started'))}, "
              f"{len(argument['drafts'])} rewrite(s)\n")
        # The envelope first, because "why did it say that" is nearly always answered here rather than
        # in the finding: a level the destination capped, an audience that never matched, a situation
        # line that told the checks something the reader would not recognise.
        print("--- what the checks were told " + "-" * 40)
        for label, value in _envelope_lines(argument):
            print(f"  {label:22s} {value}")
        print()
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
