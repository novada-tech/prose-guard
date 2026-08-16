"""How much checking was asked for, and where that choice is kept.

    disabled  nothing runs. The default, and what you get before you choose.
    low       the deterministic term check only. No model call.
    medium    plus one advisory judgement call over the remaining concerns. Still one call: repeating a
              combined verdict was measured at three calls for the same single finding.
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
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402
import settings  # noqa: E402

LEVELS = settings.LEVELS


def _from_file():
    return str(paths.config().get("effort") or "").lower()


def effort():
    for value in ((os.environ.get("PROSE_GUARD_EFFORT") or "").lower(),
                  # Set by Claude Code from the plugin's userConfig. Verified: it reaches a hook's
                  # environment, though not a skill's shell, which is why it cannot be the only path.
                  (os.environ.get("CLAUDE_PLUGIN_OPTION_EFFORT") or "").lower(),
                  _from_file()):
        if value in LEVELS:
            return value
    return "disabled"


def complaints():
    """Everything wrong with how this level was set, in sentences, or [] when nothing is.

    The environment is checked here and the file is checked by its declaration in settings.py, because
    an environment variable has no file to be declared in. `userConfig` has no enumerated type — string,
    number, boolean, directory and file are the whole list — so `/plugin configure` offers a free-text
    box, and `medim` in it means disabled with nothing said unless somebody looks.
    """
    rule = settings.one_of(*LEVELS)
    out = []
    for name, value in (("PROSE_GUARD_EFFORT", os.environ.get("PROSE_GUARD_EFFORT")),
                        ("the plugin's effort setting", os.environ.get("CLAUDE_PLUGIN_OPTION_EFFORT"))):
        if (value or "").strip():
            _, complaint = rule(value)
            if complaint:
                out.append(f"{name} {complaint}")
    return out + paths.config_complaints()


def save(level):
    """Write the choice. Raises rather than failing quietly, so a setup step can report it."""
    if level not in LEVELS:
        raise ValueError(f"{level!r} is not one of {', '.join(LEVELS)}")
    return paths.update_config(effort=level)


if __name__ == "__main__":
    print(f"effort: {effort()}")
    print(f"config: {paths.at('config.json')}")
