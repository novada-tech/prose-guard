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

import paths
import re
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED = os.path.join(_HERE, "..", "data", "destinations.json")

# A short message is not the failure this catches, and is not worth a model call.
MIN_WORDS = 25
FILE_TOOLS = ("Write", "Edit", "NotebookEdit")


def config_dir():
    return paths.home()


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


# A text argument whose value the tool call does not contain: `--body "$(git log -1 --format=%b)"`,
# `--body "$(cat notes.md)"`, `--message "${SUMMARY}"`. The prose is real and is about to be published;
# it just is not here.
SUBSTITUTED = re.compile(r"""['"]?\$[({]""")


def unreadable(dest, tool, tool_input):
    """Why a matched destination yielded no text, when the reason is worth telling somebody.

    The alternative is what happened when the pull request for this very change was opened: the guard
    matched `gh pr create`, found the body was a shell substitution, and allowed the call in silence. A
    gap that says nothing is indistinguishable from a check that passed, and `--body-file` — which is
    read — is one flag away.
    """
    if tool != "Bash":
        return None
    cmd = str(tool_input.get("command") or "")
    for flag in dest.get("text_arg") or ():
        if flag.endswith("-file") or flag in ("-F", "--file"):
            continue
        m = re.search(re.escape(flag) + r"[= ]\s*(\S{0,3})", cmd)
        if m and SUBSTITUTED.match(m.group(1)):
            readable = next((f for f in dest.get("text_arg") or () if f.endswith("-file")), None)
            return (f"This is going to {dest['name']} and the text came from a shell substitution, so "
                    f"nothing was checked — the prose is not in the command."
                    + (f" Write it to a file and pass {readable} if you want it checked."
                       if readable else ""))
    return None


def previous(dest, tool, tool_input, cwd=None):
    """The text this one replaces, where there is one. Empty string when there is not.

    A term already in the text being replaced is not a term this message introduces. Someone was asked
    to scrub a client's name from published commit messages, which meant reproducing each message
    verbatim apart from that name — and the guard held the amend over two acronyms the original author
    had written a year earlier. Nothing the agent could do would fix that, because the text was not
    theirs to rewrite. It worked around the guard with plumbing, and asked the user to approve a bypass.

    This is deliberately a property of the repository or the disk rather than a claim by the caller, so
    it cannot be used to wave anything through.
    """
    if dest.get("bash") and re.search(r"\bgit\s+commit\b", str(tool_input.get("command") or "")):
        if re.search(r"--amend\b", str(tool_input.get("command") or "")):
            try:
                got = subprocess.run(["git", "-C", cwd or os.getcwd(), "log", "-1", "--format=%B"],
                                     capture_output=True, text=True, timeout=10)
                return got.stdout if got.returncode == 0 else ""
            except Exception:
                return ""
        return ""
    # An edit to a file: at PreToolUse the write has not happened, so the file on disk still holds the
    # version being replaced.
    path = tool_input.get("file_path")
    if path and dest.get("file"):
        try:
            with open(path, errors="replace") as fh:
                return fh.read()
        except OSError:
            return ""
    return ""


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


# Passive discovery. A shape is mentioned to the user AT MOST ONCE, ever, and only once it has been
# used enough times to be worth interrupting for. Declining is permanent and stops the counting, so
# the sequence "used, suggested, declined, used again, suggested again" cannot happen.
MENTION_AFTER = 3
MAX_TRACKED = 50


def _candidates_path():
    return os.path.join(config_dir(), "unclaimed-destinations.json")


# Fields that carry long text which is not being sent anywhere. `old_string` is what an edit replaces,
# `prompt` is an instruction to another agent, `pattern` and `command` are code. Long is not the same as
# outgoing, and discovery gets one mention per shape — spending it on these is spending it on nothing.
NOT_OUTGOING = ("old_string", "prompt", "pattern", "command", "query", "regex", "expression",
                "description", "script", "code", "diff", "input")
# Tools where a file destination already decides. A prose file is claimed by extension and by being
# tracked; suggesting "add Write" would add a rule that ignores both.
WRITES_A_FILE = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def _reads_like_prose(text):
    """Long text that is prose rather than a pattern, a script or a payload.

    Passive discovery has one mention per shape and had been spending it on `git grep -E`, on the text
    an edit replaces, and on subagent prompts — six mentions in real use, none of them a destination.
    Word count alone cannot tell a paragraph from a regex; sentences and ordinary words can.
    """
    words = text.split()
    if len(words) < MIN_WORDS:
        return False
    if sum(text.count(c) for c in ".!?") < 2:
        return False                         # a paragraph has sentences; a pattern does not
    alpha = sum(1 for w in words if w.strip(".,;:!?()[]\"'").isalpha())
    return alpha >= 0.7 * len(words)


def _shape(tool, tool_input):
    """The SHAPE of a call carrying outgoing prose, never the text.

    For an MCP tool that is the tool name and the field. For Bash it is the binary, its subcommand and
    the flag that held the long argument, so `git commit -m` becomes discoverable the first time it is
    used rather than only if someone thought to configure it.
    """
    if tool == "Bash":
        cmd = str(tool_input.get("command") or "")
        for m in re.finditer(r"(--?[A-Za-z][-\w]*)[= ]\s*['\"]([^'\"]{80,})['\"]", cmd):
            if _reads_like_prose(m.group(2)):
                words = cmd.strip().split()
                head = " ".join(w for w in words[:2] if not w.startswith("-"))
                return f"bash: {head} {m.group(1)}"
        return None
    if tool in WRITES_A_FILE:
        return None
    for field, value in tool_input.items():
        if field in NOT_OUTGOING:
            continue
        if isinstance(value, str) and _reads_like_prose(value):
            return f"tool: {tool} [{field}]"
    return None


def _load_candidates():
    data = _read(_candidates_path())
    return data if isinstance(data, dict) else {}


def _save_candidates(data):
    try:
        os.makedirs(config_dir(), exist_ok=True)
        with open(_candidates_path(), "w") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
    except OSError:
        pass


def decline(shape):
    """Never mention or count this shape again.

    This is what makes passive discovery safe to have at all. Without it, declining a suggestion and
    then using the tool again would produce the same suggestion a second time, which is the failure
    that makes people turn a tool off.
    """
    data = _load_candidates()
    entry = data.setdefault(shape, {"uses": 0})
    entry["declined"] = True
    entry["mentioned"] = True
    _save_candidates(data)
    return _candidates_path()


# Words in a tool or command name that say something about what it does with the text. A suggestion
# only: never applied without someone confirming it, because a wrong guess here is a destination that
# quietly stops holding anything back.
REVIEWED_FIRST = ("draft", "preview", "unsent", "scratch", "compose", "stage")
# Specific forms, not bare words. "note" on its own matched `glab mr note`, which is a comment on
# a merge request and has an addressee — the exact mistake this suggestion exists to avoid
# making silently.
NO_ADDRESSEE = ("git commit", "git tag", "git notes", "changelog", "release_note",
                "release-note")


def suggest_caps(shape):
    """What a new destination probably deserves, and why, in words a person can agree or disagree with.

    Discovery used to be a yes-or-no question, so everything it added ran at full effort and blocked.
    That is the wrong default in two specific cases, and they are the two things only a person knows:
    whether anybody sees the text before its audience does, and whether it has an addressee at all. The
    name is weak evidence about both — enough to open with a proposal rather than a blank question.
    """
    lowered = shape.lower()
    out = {}
    if any(word in lowered for word in REVIEWED_FIRST):
        out["max_severity"] = ("advise", "the name says draft, so you would read it before it went "
                                         "anywhere — blocking would argue about text you were about "
                                         "to read")
    if any(word in lowered for word in NO_ADDRESSEE):
        out["max_effort"] = ("low", "this looks like a record rather than a message to somebody, and "
                                    "the checks above `low` ask whether the reader will care and "
                                    "whether the ask is clear")
    return out


def record_candidate(tool, tool_input):
    """Count a call nothing claimed, and return a one-line note if now is the moment to say so.

    Returns None almost always: at most one note per shape for the lifetime of the config.
    """
    shape = _shape(tool, tool_input)
    if not shape:
        return None
    data = _load_candidates()
    entry = data.get(shape)
    if entry and (entry.get("declined") or entry.get("mentioned")):
        return None                          # already settled, one way or the other
    if entry is None and len(data) >= MAX_TRACKED:
        return None                          # stop growing rather than track for ever
    entry = data.setdefault(shape, {"uses": 0})
    entry["uses"] = entry.get("uses", 0) + 1
    note = None
    if entry["uses"] >= MENTION_AFTER:
        entry["mentioned"] = True
        caps = suggest_caps(shape)
        note = (f"prose-guard has seen long text go out through `{shape}` {entry['uses']} times and "
                f"does not check it. Add it with /prose-guard:setup if that is worth checking"
                + (f" — probably as {', '.join(v[0] for v in caps.values())} rather than a block, "
                   f"going by the name" if caps else "")
                + f". This is the only time it will be mentioned.")
    _save_candidates(data)
    return note
