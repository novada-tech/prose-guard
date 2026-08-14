"""How much checking was asked for, and where that choice is kept.

    disabled  nothing runs. The default, and what you get before you choose.
    low       the deterministic term check only. No model call.
    medium    plus one advisory judgement call over the remaining concerns.
    high      four gating checks instead of that one, each re-verified after any edit.

Measured against an unguarded control in the same run, five paired sessions per level, medians,
on one fixture and one model — so read the ordering, not the digits:

    low       +12s, +1,500 of the session's own output tokens, 0 model calls
    medium    +19s, +1,600, 1 call
    high      +75s, +2,300, 4-6 calls

low is not the cheap option, which is the counter-intuitive part. It spends no model call, but a
denial costs a whole agent turn on the session's own context, and that is dearer than the small
call medium adds. medium therefore dominates low unless the traffic is already clean.

high is not known to produce better prose than medium. Scored against all four concerns, every
message from both levels satisfied all four — which is a judge at its ceiling rather than a
demonstration that they are equal. high exists because separate checks and re-verification are
what would show up on harder material, and because a deliberate one-off run can afford it.

Precedence: the environment, then plugin config, then the file, then disabled.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

LEVELS = ("disabled", "low", "medium", "high")


def config_dir():
    return paths.home()


CONFIG_PATH = paths.at("config.json")


def _from_file():
    try:
        with open(CONFIG_PATH) as fh:
            return str(json.load(fh).get("effort") or "").lower()
    except Exception:
        return ""


def effort():
    for value in ((os.environ.get("PROSE_GUARD_EFFORT") or "").lower(),
                  # Set by Claude Code from the plugin's userConfig. Verified: it reaches a hook's
                  # environment, though not a skill's shell, which is why it cannot be the only path.
                  (os.environ.get("CLAUDE_PLUGIN_OPTION_EFFORT") or "").lower(),
                  _from_file()):
        if value in LEVELS:
            return value
    return "disabled"


def misspelt():
    """A level that was set to something that is not a level, or "" if every source is clean.

    `userConfig` has no enumerated type — string, number, boolean, directory and file are the whole list
    — so `/plugin configure` offers a free-text box, and "medim" meant disabled with nothing said. This is
    what lets the hook say so where the person can see it.
    """
    for name, value in (("PROSE_GUARD_EFFORT", os.environ.get("PROSE_GUARD_EFFORT")),
                        ("the plugin's effort setting", os.environ.get("CLAUDE_PLUGIN_OPTION_EFFORT")),
                        ("config.json", _from_file())):
        text = (value or "").strip().lower()
        if text and text not in LEVELS:
            return f"{name} is set to {text!r}, which is not one of {', '.join(LEVELS)}"
    return ""


def save(level):
    """Write the choice. Raises rather than failing quietly, so a setup step can report it."""
    if level not in LEVELS:
        raise ValueError(f"{level!r} is not one of {', '.join(LEVELS)}")
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    existing = {}
    try:
        with open(CONFIG_PATH) as fh:
            existing = json.load(fh)
    except Exception:
        pass
    existing["effort"] = level
    with open(CONFIG_PATH, "w") as fh:
        json.dump(existing, fh, indent=1)
        fh.write("\n")
    return CONFIG_PATH


if __name__ == "__main__":
    print(f"effort: {effort()}")
    print(f"config: {CONFIG_PATH}")
