"""Where everything this tool remembers lives. One answer, in one place.

    PROSE_GUARD_HOME, or $XDG_CONFIG_HOME/prose-guard, or ~/.config/prose-guard

Deliberately NOT CLAUDE_PLUGIN_DATA, though that is the blessed per-plugin directory. It is exported
into a hook's environment but not into a skill's shell, so resolving it first gave a config the setup
skill wrote to one place and the hook read from another: setup looked like it worked and the guard
stayed disabled. Nothing said so.

One location that every caller can reach without help is worth more than one that survives an
uninstall. This one survives updates too, and it can be read, diffed and edited by hand.
"""
import json
import os


def home():
    return (os.environ.get("PROSE_GUARD_HOME")
            or os.path.join(os.environ.get("XDG_CONFIG_HOME")
                            or os.path.join(os.path.expanduser("~"), ".config"),
                            "prose-guard"))


def at(*parts):
    return os.path.join(home(), *parts)


def config():
    """Your choices: the effort level, the directories a team shares, the audience to assume when
    nothing matches. One file, read one way, so no two callers can disagree about its shape.

    There were four readers of this file and each had its own opinion about a missing file and about a
    payload that is not an object. Three swallowed everything; the fourth, share_dir.py, read the key
    outside its own try and put an AttributeError in front of anyone whose config.json had been
    hand-edited to `[1, 2]`. Anything that is not a JSON object is no configuration at all, and that is
    decided here so a caller cannot be the one that forgot.
    """
    try:
        with open(at("config.json")) as fh:
            got = json.load(fh)
    except Exception:
        return {}
    return got if isinstance(got, dict) else {}


def update_config(**values):
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


def shared():
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


def ensure():
    os.makedirs(home(), exist_ok=True)
    return home()
