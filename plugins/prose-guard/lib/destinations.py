"""Is text leaving, what carries it, and which identifiers say who will read it.

Routing only. What the reader knows is audiences.py; whether to complain is checks/.

Everything here is derived from the tool call, so it costs nothing and cannot be wrong about what is
happening. Without it each check would have to infer the situation from the prose, which is fragile
and duplicated: a reply in a thread reads as missing context when it is simply continuing, and an
edit to a document reads as an incoherent message when it is a diff.

Which tools count is data — data/destinations.json, plus your file which is tried first so you can
override an entry as well as add one.
"""
import json
import os
import re
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED = os.path.join(_HERE, "..", "data", "destinations.json")

# A short message is not the failure this catches, and is not worth a model call.
MIN_WORDS = 25
FILE_TOOLS = ("Write", "Edit", "NotebookEdit")


def config_dir():
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
    mine = _read(os.path.join(config_dir(), "destinations.json"))
    theirs = _read(SHIPPED)
    return (list(mine.get("destinations") or []) + list(theirs.get("destinations") or []),
            {str(o).lower() for o in (mine.get("public_owners") or [])}
            | {str(o).lower() for o in (theirs.get("public_owners") or [])})


DESTINATIONS, PUBLIC_OWNERS = load()


def _repo_at(path):
    """owner/name for the git remote at `path`, or None. Used to resolve an audience for a commit
    message or a `gh` invocation, where the repository is the cwd rather than an argument."""
    try:
        url = subprocess.run(["git", "-C", path or ".", "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return None
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def _is_tracked_prose(path):
    """True when the file sits in a git working tree and is not ignored.

    That is the line between a document colleagues will read and a scratch file: one gets
    committed. Cheaper and more honest than a list of filenames to skip, and it is why an agent's
    own notes under a temp directory are left alone.
    """
    d = os.path.dirname(os.path.abspath(path)) or "."
    while not os.path.isdir(d):
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent
    try:
        inside = subprocess.run(["git", "-C", d, "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, text=True, timeout=10)
        if inside.stdout.strip() != "true":
            return False
        ignored = subprocess.run(["git", "-C", d, "check-ignore", "-q", os.path.abspath(path)],
                                 capture_output=True, timeout=10)
        return ignored.returncode != 0
    except Exception:
        return False


def _matches(dest, tool, tool_input):
    names = dest.get("tool")
    if names:
        if isinstance(names, str):
            names = [names]
        if any(n in tool for n in names):
            return True
    if dest.get("bash") and tool == "Bash":
        return bool(re.search(dest["bash"], str(tool_input.get("command") or "")))
    if dest.get("file") and tool in FILE_TOOLS:
        path = str(tool_input.get("file_path") or "")
        if not re.search(dest["file"], path, re.I):
            return False
        return _is_tracked_prose(path) if dest.get("require_tracked") else True
    return False


def match(tool, tool_input):
    if not isinstance(tool_input, dict):
        return None
    for dest in DESTINATIONS:
        if _matches(dest, tool, tool_input):
            return dest
    return None


def _from_bash(dest, cmd):
    for flag in dest.get("text_arg") or ():
        # A flag ending in -file, or the short -F, names a file whose contents are the prose. That
        # is how a long body is really passed, so it is read rather than matched.
        if flag.endswith("-file") or flag in ("-F", "--file"):
            m = re.search(re.escape(flag) + r"[= ]\s*['\"]?([^\s'\"]+)", cmd)
            if m:
                try:
                    with open(os.path.expanduser(m.group(1))) as fh:
                        return fh.read()
                except OSError:
                    continue
            continue
        # Several -m flags concatenate into one message, which is how a subject and body are given.
        parts = re.findall(re.escape(flag) + r"[= ]\s*(?:\"((?:[^\"\\]|\\.)*)\"|'([^']*)')", cmd)
        joined = "\n\n".join(a or b for a, b in parts if (a or b))
        if joined:
            return joined.replace('\\"', '"')
    return None


def extract(dest, tool, tool_input):
    """The prose about to leave, or None if there is not enough of it to judge."""
    if tool == "Bash":
        text = _from_bash(dest, str(tool_input.get("command") or ""))
    else:
        text = None
        for field in dest.get("text_fields") or ():
            v = tool_input.get(field)
            if isinstance(v, str) and len(v.split()) >= MIN_WORDS:
                text = v
                break
    return text if text and len(text.split()) >= MIN_WORDS else None


def identifiers(dest, tool, tool_input, cwd=None):
    """What the call reveals about who will read it. audiences.py matches on exactly this."""
    spec = dest.get("identifiers") or {}
    out = {}
    for key, source in spec.items():
        if source is True and key == "cwd_repo":
            repo = _repo_at(cwd or os.getcwd())
            if repo:
                out["cwd_repo"] = repo
        elif isinstance(source, list):
            values = [str(tool_input.get(f) or "") for f in source]
            if all(values):
                out[key] = "/".join(values)
        elif isinstance(source, str):
            v = tool_input.get(source)
            if v:
                out[key] = str(v)
    if "cwd_repo" in out and "repo" not in out:
        out["repo"] = out["cwd_repo"]
    return out


def situation(dest, tool, tool_input):
    """Facts about the moment rather than the reader: a thread reply, an edit, a public repo."""
    out = {}
    if dest.get("note"):
        out["destination"] = dest["name"] + " — " + dest["note"]
    else:
        out["destination"] = dest.get("name", "")
    cf = dest.get("context_from") or {}
    field, mapping = cf.get("field"), cf.get("map") or {}
    if field:
        value = str(tool_input.get(field) or "")
        for prefix in sorted(mapping, key=len, reverse=True):
            if value.startswith(prefix):
                if mapping[prefix].get("note"):
                    out["situation"] = mapping[prefix]["note"]
                out["_shared_context"] = mapping[prefix].get("shared_context")
                break
    for key, text in (dest.get("when") or {}).items():
        if key == "_edit":
            if tool in ("Edit", "NotebookEdit"):
                out["situation"] = text
        elif tool_input.get(key):
            out["situation"] = text
    owner = str(tool_input.get("owner") or "").lower()
    if owner:
        out["reach"] = ("PUBLIC: readers outside your company can see this, so internal links and "
                        "internal shorthand are useless to them"
                        if owner in PUBLIC_OWNERS else
                        "private: colleagues can open internal links")
    return out


def record_candidate(tool, tool_input):
    """Passive discovery: a tool carrying long prose that no destination claims.

    Records the SHAPE only — never the text. For an MCP tool that is the tool name and the field;
    for Bash it is the binary, its subcommand and the flag that held the long argument, so
    `git commit -m` becomes discoverable the first time it is used rather than only if someone
    thought to configure it. /prose-guard:setup reads this and offers to add them.
    """
    shape = None
    if tool == "Bash":
        cmd = str(tool_input.get("command") or "")
        m = re.search(r"(--?[A-Za-z][-\w]*)[= ]\s*['\"]([^'\"]{80,})['\"]", cmd)
        if m:
            words = cmd.strip().split()
            head = " ".join(w for w in words[:2] if not w.startswith("-"))
            shape = f"bash: {head} {m.group(1)}"
    else:
        for field, value in tool_input.items():
            if isinstance(value, str) and len(value.split()) >= MIN_WORDS:
                shape = f"tool: {tool} [{field}]"
                break
    if not shape:
        return
    path = os.path.join(config_dir(), "unclaimed-destinations.json")
    try:
        seen = _read(path) or {}
        seen[shape] = seen.get(shape, 0) + 1
        os.makedirs(config_dir(), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(seen, fh, indent=1, sort_keys=True)
    except OSError:
        pass
