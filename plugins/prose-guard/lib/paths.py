"""Where everything this tool remembers lives. One answer, in one place.

    PROSE_GUARD_HOME, or $XDG_CONFIG_HOME/prose-guard, or ~/.config/prose-guard

Deliberately NOT CLAUDE_PLUGIN_DATA, though that is the blessed per-plugin directory. It is exported
into a hook's environment but not into a skill's shell, so resolving it first gave a config the setup
skill wrote to one place and the hook read from another: setup looked like it worked and the guard
stayed disabled. Nothing said so.

One location that every caller can reach without help is worth more than one that survives an
uninstall. This one survives updates too, and it can be read, diffed and edited by hand.
"""
import os


def home():
    return (os.environ.get("PROSE_GUARD_HOME")
            or os.path.join(os.environ.get("XDG_CONFIG_HOME")
                            or os.path.join(os.path.expanduser("~"), ".config"),
                            "prose-guard"))


def at(*parts):
    return os.path.join(home(), *parts)


def ensure():
    os.makedirs(home(), exist_ok=True)
    return home()
