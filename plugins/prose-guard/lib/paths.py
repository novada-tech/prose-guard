"""Where everything this tool remembers lives. One answer, in one place.

    PROSE_GUARD_HOME, or $XDG_CONFIG_HOME/prose-guard, or ~/.config/prose-guard

Deliberately NOT CLAUDE_PLUGIN_DATA, though that is the blessed per-plugin directory. It is exported
into a hook's environment but not into a skill's shell, so resolving it first gave a config the setup
skill wrote to one place and the hook read from another: setup looked like it worked and the guard
stayed disabled. Nothing said so.

One location that every caller can reach without help is worth more than one that survives an
uninstall. This one survives updates too, and it can be read, diffed and edited by hand.

`layers()` below is the other half of the same job: which places are read, in which order, and what
each of them holds. That belongs here because the alternative was each mechanism working it out again.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
# The data that ships inside the plugin. Relative to this file, like every other shipped path, so no
# module knows its install location and an update moves all of them together.
SHIPPED = os.path.join(_HERE, "..", "data")


def home() -> str:
    return (os.environ.get("PROSE_GUARD_HOME")
            or os.path.join(os.environ.get("XDG_CONFIG_HOME")
                            or os.path.join(os.path.expanduser("~"), ".config"),
                            "prose-guard"))


def at(*parts: str) -> str:
    return os.path.join(home(), *parts)


def config() -> dict[str, Any]:
    """Your choices: the effort level, the directories a team shares, the audience to assume when
    nothing matches. One file, read one way, so no two callers can disagree about its shape.

    There were four readers of this file and each had its own opinion about a missing file and about a
    payload that is not an object. Three swallowed everything; the fourth, share_dir.py, read the key
    outside its own try and put an AttributeError in front of anyone whose config.json had been
    hand-edited to `[1, 2]`. Anything that is not a JSON object is no configuration at all, and that is
    decided here so a caller cannot be the one that forgot.

    Checked against settings.CONFIG, so `effort: "medim"` is a sentence somebody can act on rather than
    a silent disabling. `complaints()` is the same read, returning what was wrong instead of what was
    right; the two are separate calls because almost every caller wants a value and only the hook is in
    a position to tell anybody.
    """
    return _config()[0]


def config_complaints() -> list[str]:
    """What is wrong with config.json, in sentences. Empty when there is nothing to say."""
    return _config()[1]


def _config() -> tuple[dict[str, Any], list[str]]:
    import settings
    return settings.read(at("config.json"), settings.CONFIG, "config.json")


def update_config(**values: Any) -> str:
    """Merge keys into config.json and leave the rest of it alone. Returns where it was written.

    The one writer, for the same reason there is one reader: `indent=` and the trailing newline are
    what makes the file diffable, and a second writer is where that stops being true.
    """
    ensure()
    data = config()
    data.update(values)
    with open(at("config.json"), "w") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    return at("config.json")


def shared() -> list[str]:
    """Directories a team keeps audiences in, read in addition to your own.

    A checkout, usually — put the directory in a repository your colleagues already clone and they get
    the audience by pulling. Read-only from here: nothing writes to a shared directory except `share`,
    deliberately, and removing one is a commit rather than a command.

    Configured as `"shared": [...]` in config.json. Paths may use ~ and $VARS, so the same config line
    works on machines that keep their checkouts in different places.
    """
    raw = config().get("shared") or []
    out = []
    for entry in raw if isinstance(raw, list) else [raw]:
        expanded = os.path.expanduser(os.path.expandvars(str(entry)))
        if os.path.isdir(expanded):
            out.append(expanded)
    return out


def ensure() -> str:
    os.makedirs(home(), exist_ok=True)
    return home()


class Layer:
    """One place data is read from, and what it holds.

    The three differ in layout, and this is the only thing that knows how. Yours and the shipped set
    keep audiences in an `audiences/` subdirectory; a directory a team keeps is flat, because that is
    what `share` writes and what a colleague has already committed.

    Flat means a shared directory holds audiences and a `destinations.json` in one namespace, so what
    is an audience is decided here, once, by the layer that also knows what its destinations file is
    called. It used to be decided in two places that disagreed: `share_dir.py` excluded that filename
    and `audiences.py` globbed `*.json`, so a team directory holding both produced a phantom audience
    called `destinations` — a baseline with no terms that every audience could inherit.
    """

    def __init__(self, origin: str, directory: str, audiences: str) -> None:
        self.origin = origin
        self.directory = directory
        self.audiences = audiences

    @property
    def destinations(self) -> str:
        return os.path.join(self.directory, "destinations.json")

    def audience_files(self) -> list[str]:
        return [p for p in sorted(glob.glob(os.path.join(self.audiences, "*.json")))
                if p != self.destinations]

    def __repr__(self) -> str:
        return f"<Layer {self.origin} {self.directory}>"


def layers() -> list[Layer]:
    """Every place data comes from, nearest first: yours, then each directory your team keeps, then
    the set that ships with the plugin.

    One list, because the two mechanisms that read layers each built their own and came out with
    different powers by accident. Destinations read `off` from the first layer only, so a team could
    add a destination for everybody and could not retire a shipped one for anybody; audiences said
    nothing when a shared file displaced a shipped baseline, while destinations printed
    `(shadowed by yours)` for the same event. Neither difference was a decision.

    What is NOT shared is how a layer wins. A destination routes one call to one place, so the first
    match wins and the nearer layer overrides; an audience is a measured whole, so a later layer
    replaces an earlier one by name and a partial override would produce a vocabulary of unknown
    provenance. Each mechanism reads this list in its own direction and combines it its own way.
    """
    out = [Layer("yours", home(), at("audiences"))]
    out += [Layer("shared", d, d) for d in shared()]
    out.append(Layer("built in", SHIPPED, os.path.join(SHIPPED, "audiences")))
    return out


def mine() -> Layer:
    """Your own layer — the only one anything writes to."""
    return layers()[0]
