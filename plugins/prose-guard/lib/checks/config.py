"""How much checking was asked for, and where that choice is kept.

    disabled  nothing runs. The default, and what you get before you choose.
    low       the two deterministic checks only. No model call.
    medium    plus one advisory judgement call over the remaining concerns.
    high      one gating check per concern instead of that one, each re-verified after any edit.

Precedence: the environment, then plugin config, then the file, then disabled.

What each level costs and which to pick is measured in [docs/design-notes.md](../../../../docs/design-notes.md),
which is the only copy with the unguarded control it was measured against. Two results there are worth
knowing before reading anything here: `low` is not the cheap option, because a held turn costs more of
the session's own context than the small call `medium` adds; and `high` is not known to produce better
prose than `medium`, because the measurement could not tell them apart.

This file kept its own copy of that table and both results, and both had drifted — it said `high` runs
four gating checks when it runs five, and that the comparison scored four concerns when it scored five.
A reader here is looking for where the setting is stored, not choosing a level.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402
import settings  # noqa: E402

LEVELS = settings.LEVELS


# One rule for reading a level, used by both `effort` and `complaints`. They disagreed: this one strips
# and that one did not, so `PROSE_GUARD_EFFORT="low "` was ignored — falling through to whatever the
# file said, or to disabled — while the thing whose job is to say a level is wrong stayed quiet, because
# by its rule the value was fine. A trailing space is what a person leaves in a free-text box.
_LEVEL = settings.one_of(*LEVELS)


def _sources() -> tuple[tuple[str, str | None], ...]:
    """Where a level may be set, nearest first, each with a name for saying which one is wrong."""
    # A third source used to sit between these two: `CLAUDE_PLUGIN_OPTION_EFFORT`, which Claude Code
    # set from a `userConfig` field in plugin.json. Declaring that field made Claude Code ask for a
    # level in a dialog at install — a free-text box, because `userConfig`'s types are string, number,
    # boolean, directory and file with no enumerated type among them, so there was no picker and no way
    # to mark the answer the measurements support. Asking somebody to type a level before they have
    # been told what one costs is a worse first minute than asking nothing at all, and it left the same
    # choice recorded in two places that could disagree. The field is gone and so is the source.
    return (("PROSE_GUARD_EFFORT", os.environ.get("PROSE_GUARD_EFFORT")),
            ("config.json", paths.config().get("effort")))


def chosen() -> str | None:
    """The level a source actually names, or None when no source names one.

    `effort()` cannot answer this. It says `disabled` both for somebody who turned the guard off and
    for somebody who has never been asked, and those two deserve opposite treatment: one has decided
    and must never be nagged, the other is running an install that checks nothing and looks installed.
    `hooks/scripts/session_start.py` is the only caller that needs to tell them apart, and it is the
    one place a person is told their install is doing nothing.
    """
    for _, value in _sources():
        level, _ = _LEVEL(value)
        if level:
            return level
    return None


def effort() -> str:
    return chosen() or "disabled"


def complaints() -> list[str]:
    """Everything wrong with how this level was set, in sentences, or [] when nothing is.

    The environment is checked here and the file is checked by its declaration in settings.py, because
    an environment variable has no file to be declared in. `medim` anywhere means disabled with nothing
    said unless somebody looks, and a level is typed by hand in all three places that can hold one.
    """
    out: list[str] = []
    for name, value in _sources()[:1]:            # the file's own complaint comes from its declaration
        if (value or "").strip():
            _, complaint = _LEVEL(value)
            if complaint:
                out.append(f"{name} {complaint}")
    return out + paths.config_complaints()


def capped(level: str, ceiling: str | None) -> str:
    """The lower of what was asked for and what this destination is worth.

    Here rather than beside the ladder because it needs the levels in order, and this module is where
    the levels are. It kept its own copy of the tuple, and a copy is one addition away from being
    wrong: `capped` returns the level unchanged when either value is not in its list, so a level added
    to `settings.LEVELS` and not to that copy would leave every `max_effort` naming it silently
    uncapped — a destination configured to be checked cheaply, checked at full price, with nothing
    said.
    """
    if not ceiling or ceiling not in LEVELS or level not in LEVELS:
        return level
    return level if LEVELS.index(level) <= LEVELS.index(ceiling) else ceiling


def save(level: str) -> str:
    """Write the choice. Raises rather than failing quietly, so a setup step can report it."""
    if level not in LEVELS:
        raise ValueError(f"{level!r} is not one of {', '.join(LEVELS)}")
    return paths.update_config(effort=level)


if __name__ == "__main__":
    print(f"effort: {effort()}")
    print(f"config: {paths.at('config.json')}")
