"""Things a person should be told about their own install, each said at most once.

A guard that interrupts is expensive — `checks/config.py` measures a held turn as the dominant cost of
this whole tool — so anything said to a person has to be worth a turn, and saying it twice is worse
than not saying it. Five places had worked that out separately and each remembered its own answer: a
marker file beside the config, two booleans in the session state, a `mentioned` flag per discovered
shape, and a counter. They agreed on the policy and shared no code, so the sixth place to need it would
have invented a seventh way.

What they were all doing is here, and it is three operations:

    worth_saying   is this the first time? says yes once, then no for ever
    seen           count how often a thing has happened, so it can be mentioned only once it matters
    decline        never mention this again, whatever the count reaches

and two scopes for the memory. `for_good` outlives the session, and belongs to facts about the install:
that setup was never run, that a tool nobody configured keeps carrying prose. `this_session` resets,
and belongs to facts the person can act on now and that stop being true when they do — a misspelt
level, a check that could not run. Getting that the wrong way round is the failure to avoid in both
directions: nagging every session about a thing they declined, or telling them once about a thing they
have since broken again.

Nothing here raises. A ledger that cannot be written is a reason to stay quiet, not a reason to fail:
the alternative is a tool that cannot remember what it said and therefore repeats itself for ever.
"""
from __future__ import annotations

import json
import os
from typing import Any

import paths

# Enough shapes to cover what one machine really sends, and a stop so a ledger cannot grow without
# bound on a session that touches a thousand of them.
MOST_REMEMBERED = 200


def _path() -> str:
    return paths.at("told.json")


def _read() -> dict[str, Any]:
    try:
        with open(_path()) as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except Exception:
        return {}


def _write(data: dict[str, Any]) -> None:
    try:
        paths.ensure()
        with open(_path(), "w") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
    except OSError:
        pass                                 # cannot remember, so say nothing rather than repeat


def everything() -> dict[str, Any]:
    """The whole ledger, for a command that shows what has been decided. Read-only."""
    return _read()


class Ledger:
    """What has already been said, and what has been declined.

    `session` is the hook's own per-session state dict, or None for a caller that has none — a
    deliberate run of check_prose.py has no session, so everything it says is `for_good` or is said
    every time by design.
    """

    def __init__(self, session: dict[str, Any] | None = None) -> None:
        self.session = session if isinstance(session, dict) else None

    # ------------------------------------------------------------------ once, and never again
    def worth_saying(self, key: str, for_good: bool = False) -> bool:
        """True the first time, False afterwards. Marks it said in the same breath.

        One call rather than an ask-then-mark pair, because the pair is what goes wrong: every one of
        the five hand-written versions had the mark in a different place, and one of them marked it
        before deciding whether to say it.
        """
        if not for_good:
            if self.session is None:
                return True
            said = self.session.setdefault("said", [])
            if key in said:
                return False
            said.append(key)
            return True
        data = _read()
        entry = data.get(key) or {}
        if entry.get("said") or entry.get("declined"):
            return False
        if key not in data and len(data) >= MOST_REMEMBERED:
            return False                     # stop growing rather than track for ever
        entry["said"] = True
        data[key] = entry
        _write(data)
        return True

    # ------------------------------------------------------------------ count first, say later
    def seen(self, key: str) -> int:
        """Count one occurrence of something not yet worth mentioning, and return the running total.

        Returns 0 for anything already said or declined, so a caller can stop counting: the sequence
        "used, suggested, declined, used again, suggested again" is the thing this prevents.
        """
        data = _read()
        entry = data.get(key) or {}
        if entry.get("said") or entry.get("declined"):
            return 0
        if key not in data and len(data) >= MOST_REMEMBERED:
            return 0
        entry["seen"] = entry.get("seen", 0) + 1
        data[key] = entry
        _write(data)
        return entry["seen"]

    def decline(self, key: str) -> str:
        """Never mention this again. Permanent, and it stops the counting as well as the saying."""
        data = _read()
        data.setdefault(key, {})["declined"] = True
        _write(data)
        return key

    def declined(self, key: str | None = None) -> bool | list[str]:
        data = _read()
        if key is not None:
            return bool((data.get(key) or {}).get("declined"))
        return [k for k, v in data.items() if (v or {}).get("declined")]

    def forget(self, key: str | None = None) -> None:
        """For a test, and for somebody who wants to be asked again."""
        data = _read()
        if key is None:
            data = {}
        else:
            data.pop(key, None)
        _write(data)
        if self.session is not None:
            self.session["said"] = []


# ------------------------------------------------------------------ things that could not run
# A check that cannot run answers exactly what a check that passes answers, so what did not happen is
# recorded as it happens and read out by whoever can reach a person. Process-wide rather than on the
# Ledger because the code that notices is a check, and a check is told nothing about sessions or state.
_MISSING: list[str] = []


def could_not_run(what: str) -> None:
    """Record that something did not happen, so a clean report cannot be mistaken for a clean text."""
    if what and what not in _MISSING:
        _MISSING.append(what)


def never_ran() -> list[str]:
    """Everything recorded since this process started, in the order it happened."""
    return list(_MISSING)


def ran_everything() -> None:
    _MISSING.clear()
