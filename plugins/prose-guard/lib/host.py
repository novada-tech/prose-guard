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

`CLAUDE_PLUGIN_OPTION_EFFORT` belongs to a `userConfig` field this plugin deliberately does not declare;
`checks/config.py` says why.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any

# The binary a model-backed check shells out to. One name, so a check and the thing that reports the
# check could not run cannot disagree about what was missing.
CLI = "claude"

# How much of what the CLI says about a failure is worth repeating to somebody. Long enough for an
# `API Error: 429 ...` line, short enough that a stack trace does not become the notice.
ENOUGH_OF_IT = 120


def answered(returncode: int, stdout: str) -> tuple[str | None, str, dict[str, Any]]:
    """The checker's reply, a sentence saying why there is none, and the invocation's own JSON.

    The JSON comes back so that a caller reading anything else out of it — what the call cost, say —
    parses the reply once, here, rather than deciding for a second time what shape it is in.

    The one place that decides whether a `claude -p --output-format json` invocation reached a model.
    It belongs here rather than in the check that calls it because the shape below is a fact about the
    host, and a host can change it in a release — the same reason the plugin manifests are read here.

    A refusal is well-formed JSON from a process that ran, which is why nothing downstream could see
    one: the refusal text lands in `result`, the field the verdict is read from, and a reply stating
    no verdict is a pass. Established against the shipped CLI without spending a token, by pointing
    `ANTHROPIC_BASE_URL` at a local server that answers every request with an error — exit 1, and

        {"subtype": "success", "is_error": true, "api_error_status": 400,
         "terminal_reason": "api_error", "result": "API Error: 400 ..."}

    So `subtype` still says success and only the flags say otherwise. What is read here is structural —
    the exit status, `is_error`, an error `subtype`, an HTTP status, stdout that is not JSON, no reply
    at all. Deliberately NOT the words of the refusal: those are a string a vendor changes and may
    localise, and matching them would make the check stop working the same silent way it does now.
    They are quoted into the sentence as evidence and never branched on.

    An unknown `subtype` is treated as success, so a key this stops recognising does not turn every
    check into a notice. The exit status covers that case from the other side.
    """
    try:
        blob = json.loads(stdout)
    except Exception:
        blob = None
    if not isinstance(blob, dict):
        return None, f"`{CLI}` exited {returncode} without printing a reply that could be read", {}
    said = blob.get("result")
    said = said if isinstance(said, str) else ""
    status = blob.get("api_error_status")
    if isinstance(status, int):
        # The status and nothing else: it is the actionable half — 429 is a spent quota, 401 is nobody
        # logged in — and it is the same string on every refused call in a run, so the ledger that says
        # a thing once has something to recognise. The message beside it can carry a reset time, and
        # then one refused round becomes a line per check.
        return None, f"`{CLI}` was refused with HTTP {status}", blob
    errors = blob.get("errors")
    # No status, so the invocation's own words are the only account there is of what went wrong.
    trouble = _one_line(said or (errors[0] if isinstance(errors, list) and errors else ""))
    if returncode != 0 or blob.get("is_error") or blob.get("subtype", "success") != "success":
        return None, (f"`{CLI}` did not answer: {trouble}" if trouble
                      else f"`{CLI}` exited {returncode} without answering"), blob
    if not said.strip():
        return None, f"`{CLI}` came back with no reply at all", blob
    return said, "", blob


def _one_line(text: str) -> str:
    """The first line of what something said about itself, cut to `ENOUGH_OF_IT`."""
    first = (str(text).strip().splitlines() or [""])[0].strip()
    return first if len(first) <= ENOUGH_OF_IT else first[:ENOUGH_OF_IT - 3] + "..."


def dot_dir() -> str:
    """`~/.claude` — rules, plugin cache, settings."""
    return os.path.join(os.path.expanduser("~"), ".claude")


def rules_dir() -> str:
    """Where a rule has to be for every session to load it. A plugin cannot ship one, so the rule this
    plugin carries is COPIED here — which is why an upgrade does not refresh it."""
    return os.path.join(dot_dir(), "rules")


def user_config() -> str:
    """`~/.claude.json` — the user's own Claude Code configuration, including MCP servers."""
    return os.path.join(os.path.expanduser("~"), ".claude.json")


def plugin_manifests() -> list[str]:
    """Every installed plugin's manifest, from the plugin cache."""
    return sorted(glob.glob(os.path.join(dot_dir(), "plugins", "cache", "*", "*", "*",
                                         ".claude-plugin", "plugin.json")))


def declared_servers() -> list[str]:
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


def missing() -> list[str]:
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
