"""Everything this plugin knows about Claude Code, which is its host rather than its library.

`paths.py` answers where OUR state lives. This answers where the HOST's things live, and the two are
worth separating because they fail differently. Ours is a decision we made and can change. This is a
layout somebody else owns, which can move under us in a release — and when it does, the failure is
silent: a glob matches nothing, a list gets shorter, and everything carries on looking fine. That
already happened. The manifest glob below resolves 22 plugins on one machine and finds `mcpServers` in
none of them, because seven declare theirs in a sibling `.mcp.json` the glob never read — so a quarter
of what discovery is for contributed nothing and said nothing.

Six modules each held one of these facts. Collected here so that a layout change is one file to edit
and one place to look, and so that `exists()` can say plainly when something expected is not there.

What is NOT here, deliberately: `${CLAUDE_PLUGIN_ROOT}`, which a skill expands for itself and no
Python ever needs, and `CLAUDE_PLUGIN_DATA`, whose story is in paths.py — it reaches a hook and not a
skill, so resolving state through it split the config in two.
"""
import glob
import json
import os

# The setting Claude Code puts in a hook's environment from the plugin's own `userConfig`. Verified to
# reach a hook and NOT a skill's shell, which is why it can never be the only way to read a setting.
EFFORT_VAR = "CLAUDE_PLUGIN_OPTION_EFFORT"
# The binary a model-backed check shells out to. One name, so a check and the thing that reports the
# check could not run cannot disagree about what was missing.
CLI = "claude"


def dot_dir():
    """`~/.claude` — rules, plugin cache, settings."""
    return os.path.join(os.path.expanduser("~"), ".claude")


def rules_dir():
    """Where a rule has to be for every session to load it. A plugin cannot ship one, so the rule this
    plugin carries is COPIED here — which is why an upgrade does not refresh it."""
    return os.path.join(dot_dir(), "rules")


def user_config():
    """`~/.claude.json` — the user's own Claude Code configuration, including MCP servers."""
    return os.path.join(os.path.expanduser("~"), ".claude.json")


def plugin_manifests():
    """Every installed plugin's manifest, from the plugin cache."""
    return sorted(glob.glob(os.path.join(dot_dir(), "plugins", "cache", "*", "*", "*",
                                         ".claude-plugin", "plugin.json")))


def declared_servers():
    """MCP server names every installed plugin declares, wherever it declares them.

    Two places, because plugins use both: inside `plugin.json` under `mcpServers`, and in a sibling
    `.mcp.json`. Reading only the first found none at all on a machine with 22 plugins installed, seven
    of which declare servers in the second — the difference between a source that works and a source
    that is silently absent.
    """
    names = set()
    for manifest in plugin_manifests():
        beside = os.path.join(os.path.dirname(os.path.dirname(manifest)), ".mcp.json")
        for path, key in ((manifest, "mcpServers"), (beside, "mcpServers")):
            try:
                with open(path) as fh:
                    got = json.load(fh)
            except Exception:
                continue
            if isinstance(got, dict) and isinstance(got.get(key), dict):
                names.update(got[key])
    return sorted(names)


def missing():
    """What this plugin expects of its host and cannot find, in sentences.

    Empty on a healthy install. Not empty means a layout changed or this is not Claude Code, and either
    way the honest thing is to say which source stopped working rather than quietly return less.
    """
    out = []
    if not os.path.isdir(dot_dir()):
        out.append(f"{dot_dir()} is not there, so nothing about the local Claude Code install could "
                   f"be read")
        return out
    if not os.path.isfile(user_config()):
        out.append(f"{user_config()} is not there, so MCP servers configured by hand were not read")
    if not plugin_manifests():
        out.append(f"no plugin manifests under {dot_dir()}/plugins/cache, so MCP servers that plugins "
                   f"declare were not read")
    return out
