"""Where prose leaves for a person, what field carries it, and who reads it there.

Every fact about the audience comes from the tool call itself, so it costs no extra calls and
cannot be wrong about what is happening. Without it each check has to infer the audience from the
text, which is fragile and duplicated: a reply in a thread reads as missing context when it is
simply continuing a conversation, and an edit to a document reads as an incoherent message when it
is a diff.

Which tools count, and what they imply, is data rather than code — data/destinations.json, plus
your own file which is tried FIRST so you can override an entry as well as add one. What cannot be
derived is declared: whether a repository is public, and who the readers are by role.
"""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED = os.path.join(_HERE, "..", "data", "destinations.json")

# A short message is not worth a model call, and a one-line reply is not the failure this catches.
MIN_WORDS = 25


def _config_dir():
    return (os.environ.get("PROSE_GUARD_HOME")
            or os.environ.get("CLAUDE_PLUGIN_DATA")
            or os.path.join(os.environ.get("XDG_CONFIG_HOME")
                            or os.path.join(os.path.expanduser("~"), ".config"),
                            "prose-guard"))


def _read(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return {}


def load():
    """Yours first, then the shipped defaults. Also returns the merged public-owner list."""
    mine = _read(os.path.join(_config_dir(), "destinations.json"))
    theirs = _read(SHIPPED)
    return (list(mine.get("destinations") or []) + list(theirs.get("destinations") or []),
            {str(o).lower() for o in (mine.get("public_owners") or [])}
            | {str(o).lower() for o in (theirs.get("public_owners") or [])})


DESTINATIONS, PUBLIC_OWNERS = load()


def _matches(dest, tool, tool_input):
    if dest.get("tool"):
        names = dest["tool"]
        if isinstance(names, str):
            names = [names]
        if any(n in tool for n in names):
            return True
    if dest.get("bash") and tool == "Bash":
        return bool(re.search(dest["bash"], str(tool_input.get("command") or "")))
    if dest.get("file") and tool in ("Write", "Edit", "NotebookEdit"):
        return bool(re.search(dest["file"], str(tool_input.get("file_path") or ""), re.I))
    return False


def match(tool, tool_input):
    """The first destination that claims this call, or None if nothing does."""
    if not isinstance(tool_input, dict):
        return None
    for dest in DESTINATIONS:
        if _matches(dest, tool, tool_input):
            return dest
    return None


def extract(dest, tool, tool_input):
    """The prose this call is about to send, or None if there is not enough of it to judge."""
    text = None
    if dest.get("text_arg") and tool == "Bash":
        cmd = str(tool_input.get("command") or "")
        for flag in dest["text_arg"]:
            # --body-file is how a long body is really passed, so it is read rather than matched.
            # --body "$(cat x)" stays out of reach and is not attempted.
            m = re.search(re.escape(flag) + r"[= ]\s*['\"]?([^\s'\"]+)", cmd)
            if m and flag.endswith("-file"):
                try:
                    with open(os.path.expanduser(m.group(1))) as fh:
                        text = fh.read()
                except OSError:
                    text = None
            elif not m:
                continue
            else:
                m2 = re.search(re.escape(flag) + r"[= ]\s*['\"](.+?)['\"]", cmd, re.S)
                text = m2.group(1) if m2 else None
            if text:
                break
    else:
        for field in dest.get("text_fields") or ():
            v = tool_input.get(field)
            if isinstance(v, str) and len(v.split()) >= MIN_WORDS:
                text = v
                break
    if not text or len(text.split()) < MIN_WORDS:
        return None
    return text


def envelope(dest, tool, tool_input):
    """What the checks are told about the situation. Derived where possible, declared otherwise."""
    e = dict(dest.get("audience") or {})
    frm = dest.get("audience_from") or {}
    field, mapping = frm.get("field"), frm.get("map") or {}
    if field:
        value = str(tool_input.get(field) or "")
        # longest matching prefix wins, so a specific id beats the '*' fallback
        for prefix in sorted((k for k in mapping if k != "*"), key=len, reverse=True):
            if value.startswith(prefix):
                e.update(mapping[prefix])
                break
        else:
            e.update(mapping.get("*") or {})
        if field == "owner" and value:
            e["reach"] = (
                "a PUBLIC repository: readers outside your company can see this, so internal "
                "links and internal shorthand are useless to them"
                if value.lower() in PUBLIC_OWNERS else
                "a private repository: colleagues can open internal links")
    for key, text in (dest.get("when") or {}).items():
        if key == "_edit":
            if tool in ("Edit", "NotebookEdit"):
                e["situation"] = text
        elif tool_input.get(key):
            e["situation"] = text
    path = tool_input.get("file_path")
    if path:
        e["document"] = os.path.basename(str(path))
    if not e:
        # Say so rather than guessing. An unknown audience is why a check advises instead of
        # blocking, and a check that invented an audience would block on the invention.
        e["audience"] = "unknown: nothing is configured for this destination"
    return e
