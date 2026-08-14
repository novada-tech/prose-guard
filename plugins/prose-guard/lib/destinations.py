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
    """Yours first, then your team's, then the shipped set. First match wins, so an earlier layer
    overrides a later one — which is how a team stops something being checked, or checks it differently,
    for everybody at once.

    A destination is worth more shared than an audience is. An audience is measured from a corpus and
    describes one group of readers; a destination is a fact about which tool sends prose and which field
    carries it, and that fact is the same for everyone using that tool. One person working it out with
    /prose-guard:setup is the whole team's answer.
    """
    layers = [("yours", _read(os.path.join(config_dir(), "destinations.json")))]
    layers += [("shared", _read(os.path.join(directory, "destinations.json")))
               for directory in paths.shared()]
    layers.append(("built in", _read(SHIPPED)))
    # Names switched off in YOUR file, whatever layer they came from. There is no deleting a shipped
    # destination — the file is inside the plugin and is replaced on update — so this is how you stop one.
    off = {str(n).lower() for n in (layers[0][1].get("off") or [])}
    found, owners = [], set()
    for origin, layer in layers:
        for entry in layer.get("destinations") or []:
            if str(entry.get("name", "")).lower() in off:
                continue
            found.append(dict(entry, _origin=origin))
        owners |= {str(o).lower() for o in (layer.get("public_owners") or [])}
    return found, owners


DESTINATIONS, PUBLIC_OWNERS = load()
SWITCHED_OFF = [str(n) for n in (_read(os.path.join(config_dir(), "destinations.json")).get("off") or [])]


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


def _from_bash(dest, cmd, cwd=None):
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
            joined = joined.replace('\\"', '"')
            # The prose may be behind a substitution rather than in the command. Where it can be had
            # without risking a side effect, have it: nobody should have to restructure a command to
            # get their writing checked.
            if joined.strip().startswith("$"):
                return resolve(joined, cwd)
            return joined
    return None


def resulting(dest, tool, tool_input, cwd=None):
    """The document as it will be AFTER this call, and which part of it is new.

    An edit was being judged as though the hunk were the whole document. Both "no sentence stating what
    this list is for" complaints landed on a file whose first thirty lines are exactly that, because the
    edit only touched the middle; a reference resolved forty lines up read as unresolved for the same
    reason. Any edit into the middle of a document looked context-free.

    The file on disk is right here — `previous` already reads it — so the checks get the document, and the
    caller is told which sentences this call actually wrote. Returns (text, new_fragment) with
    new_fragment empty when the whole thing is new.
    """
    path = tool_input.get("file_path")
    if not (dest.get("file") and path):
        return None, ""
    fresh = tool_input.get("new_string")
    if not isinstance(fresh, str):
        return None, ""                       # a whole-file write: the content IS the document
    before = tool_input.get("old_string")
    try:
        with open(path, errors="replace") as fh:
            whole = fh.read()
    except OSError:
        return None, ""
    if isinstance(before, str) and before and before in whole:
        return whole.replace(before, fresh, 1), fresh
    return None, ""


def extract(dest, tool, tool_input, cwd=None):
    """The prose about to leave, or None if there is not enough of it to judge."""
    if tool == "Bash":
        text = _from_bash(dest, str(tool_input.get("command") or ""), cwd)
    else:
        whole, _ = resulting(dest, tool, tool_input, cwd)
        if whole and len(whole.split()) >= MIN_WORDS:
            return whole
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


# Substitutions the tool can work out for itself, so nobody has to restructure a command to be checked.
#
# Reading a file needs no execution at all. Running a command does, and the hook cannot know whether the
# one it is looking at is read-only: `$(curl -X POST ...)` would fire twice. So execution is limited to
# a whitelist of git subcommands that report — and even that is not enough on its own, because
# `git log --output=FILE` writes a file, so a flag that can write is refused. Chaining is prevented by
# something stronger than a check: the command is run as a list of arguments, with no shell, so `;` and
# `&&` reach git as arguments and git rejects them. CHAINS is redundancy for anything that later runs
# this through a shell — removing it changes no behaviour today, which a test cannot show.
READS_A_FILE = re.compile(r"""^\$\(\s*(?:cat|<)\s+['"]?([^'"\s)]+)['"]?\s*\)$""")
REPORTS = ("log", "show", "cat-file", "describe", "rev-parse", "rev-list", "tag", "notes")
CAN_WRITE = ("--output", "-o ", "--output-directory")
CHAINS = (";", "&&", "||", "|", "`", "$(", ">", "<")


def resolve(value, cwd=None):
    """The text behind a substitution, where it can be had without risking a side effect.

    Returns None when it cannot, which is the honest answer for `${SUMMARY}` — the hook is a separate
    process and never sees the caller's shell variables — and for any command it declines to run.
    """
    value = value.strip()
    m = READS_A_FILE.match(value)
    if m:
        path = m.group(1)
        if not os.path.isabs(path) and cwd:
            path = os.path.join(cwd, path)
        try:
            with open(os.path.expanduser(path), errors="replace") as fh:
                return fh.read()
        except OSError:
            return None
    if not (value.startswith("$(") and value.endswith(")")):
        return None
    inner = value[2:-1].strip()
    words = inner.split()
    if len(words) < 2 or words[0] != "git" or words[1] not in REPORTS:
        return None
    if any(bad in inner for bad in CAN_WRITE) or any(bad in inner[2:] for bad in CHAINS):
        return None
    try:
        got = subprocess.run(words, capture_output=True, text=True, timeout=20,
                             cwd=cwd or os.getcwd())
    except Exception:
        return None
    return got.stdout if got.returncode == 0 else None


# A text argument whose value the tool call does not contain: `--body "$(git log -1 --format=%b)"`,
# `--body "$(cat notes.md)"`, `--message "${SUMMARY}"`. The prose is real and is about to be published;
# it just is not here.
SUBSTITUTED = re.compile(r"""['"]?\$[({]""")


def unreadable(dest, tool, tool_input, cwd=None):
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
            # Only complain about what could not be worked out. A substitution the tool can resolve is
            # not a gap, and telling someone to restructure a command that already works would be
            # noise.
            whole = re.search(re.escape(flag) + r"[= ]\s*(?:\"([^\"]*)\"|'([^']*)'|(\S+))", cmd)
            if whole and resolve(next(g for g in whole.groups() if g is not None), cwd):
                continue
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
# Nothing is excluded for writing a file, and that was a mistake worth recording. The reasoning was
# that the prose-file destination already decides which files count — but it only claims a file that
# is TRACKED, and discovery is asked only about calls nothing claimed. So excluding Write silenced the
# one case that needed saying: a blog plan written to ~/novada, which is not a git repository at all,
# was never checked and, with the exclusion in place, was never mentioned either.


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


# This tool's own commands. Checking a check is circular, and the `--who` argument to check_prose.py is
# a sentence describing a reader, so it passes the prose test and was offered as a destination to add.
OWN_COMMANDS = ("check_prose.py", "learn.py", "audiences.py", "discover.py", "install_rule.py",
                "share_dir.py", "fetch.py", "measure_check.py", "measure_cost.py", "measure_rule.py",
                "measure_thresholds.py", "measure_destinations.py")


def _shape(tool, tool_input):
    """The SHAPE of a call carrying outgoing prose, never the text.

    For an MCP tool that is the tool name and the field. For Bash it is the binary, its subcommand and
    the flag that held the long argument, so `git commit -m` becomes discoverable the first time it is
    used rather than only if someone thought to configure it.
    """
    if tool == "Bash":
        cmd = str(tool_input.get("command") or "")
        if any(own in cmd for own in OWN_COMMANDS):
            return None
        # A heredoc is a script, not a message. Prose inside one — a docstring, a comment, a test fixture
        # — is prose, so the prose test passes it and `cd somewhere` was offered as a destination on the
        # strength of a docstring in a heredoc it happened to carry. The cost of this, stated rather than
        # hidden: `cat > notes.md <<MD ... MD` writes a prose file and is no longer noticed. The shape it
        # would have recorded is `bash: cat`, which is not worth acting on, and heredocs carrying scripts
        # are far more common than heredocs writing documents.
        cmd = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?^\1", " ", cmd, flags=re.S | re.M)
        # From before the first quote, or the shape of `echo "<a paragraph>"` becomes `echo "The`.
        words = re.split(r"['\"]", cmd.strip(), 1)[0].split()
        head = " ".join(w for w in words[:2] if not w.startswith("-"))
        for m in re.finditer(r"(--?[A-Za-z][-\w]*)[= ]\s*['\"]([^'\"]{80,})['\"]", cmd):
            if _reads_like_prose(m.group(2)):
                return f"bash: {head} {m.group(1)}"
        # Prose does not always arrive behind a flag. `echo "<a paragraph>"` and `somecli post "<a
        # paragraph>"` put it in a positional argument, and neither was recorded at all — so the one
        # example asked about would never have surfaced. The prose test is what keeps a grep pattern out.
        for m in re.finditer(r"['\"]([^'\"]{80,})['\"]", cmd):
            if _reads_like_prose(m.group(1)):
                return f"bash: {head}"
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


# ---------------------------------------------------------------------------- managing them
def _user_path():
    return os.path.join(config_dir(), "destinations.json")


def _user_file():
    return _read(_user_path()) or {}


def _save_user(data):
    os.makedirs(config_dir(), exist_ok=True)
    with open(_user_path(), "w") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    return _user_path()


def find(name):
    """The destination of that name, and which layer it came from."""
    for entry in DESTINATIONS:
        if str(entry.get("name", "")).lower() == name.lower():
            return entry
    return None


def remove(name):
    """Delete one of your own. A shipped or shared one is switched off instead — see `off`."""
    data = _user_file()
    rows = list(data.get("destinations") or [])
    keep = [r for r in rows if str(r.get("name", "")).lower() != name.lower()]
    if len(keep) == len(rows):
        entry = find(name)
        if entry is None:
            raise KeyError(name)
        raise PermissionError(
            f"{name} is {entry['_origin']}, so it is not yours to delete. `off {name}` stops it being "
            f"checked on this machine; a shared one is retired for everybody by removing it from the "
            f"directory it comes from.")
    data["destinations"] = keep
    return _save_user(data)


def switch(name, on):
    """Stop, or resume, checking a destination on this machine, whichever layer it came from."""
    data = _user_file()
    off = [str(n) for n in (data.get("off") or [])]
    lowered = [n.lower() for n in off]
    if on:
        if name.lower() not in lowered:
            return None
        data["off"] = [n for n in off if n.lower() != name.lower()]
    else:
        if find(name) is None:
            raise KeyError(name)
        if name.lower() in lowered:
            return None
        data["off"] = off + [name]
    return _save_user(data)


def share(directory, only=None):
    """Copy destinations from this machine into a directory a team keeps.

    Only ever your own: the shipped set is already everywhere, and copying it would put a stale duplicate
    in front of the maintained one. `only` names one, for the common case where some of what you have
    worked out is the team's business and some is not.
    """
    rows = [r for r in (_user_file().get("destinations") or [])
            if only is None or str(r.get("name", "")).lower() == only.lower()]
    if not rows:
        return ("nothing to share: " + (f"you have no destination called {only}" if only else
                "no destinations have been added on this machine. The shipped ones are already "
                "everywhere; /prose-guard:setup works out what is missing."))
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, "destinations.json")
    existing = _read(target) or {}
    have = {json.dumps(x, sort_keys=True) for x in (existing.get("destinations") or [])}
    fresh = [{k: v for k, v in r.items() if k != "_origin"} for r in rows]
    added = [x for x in fresh if json.dumps(x, sort_keys=True) not in have]
    merged = dict(existing)
    merged["destinations"] = list(existing.get("destinations") or []) + added
    merged.setdefault("_meta", {})["what"] = (
        "Destinations this team has worked out. Read after your own file and before the shipped set, so "
        "your own destinations.json still wins locally.")
    with open(target, "w") as fh:
        json.dump(merged, fh, indent=1)
        fh.write("\n")
    names = ", ".join(x.get("name", "?") for x in added) or "nothing new"
    return (f"{len(added)} added to {target}: {names}\n"
            f"Nothing is shared until you commit it. Then anyone whose config lists that directory has "
            f"them, with no setup conversation of their own.\n"
            f"Your own copy still wins locally, so improvements the team makes to it will not reach you. "
            f"`rm` the local one once it is committed, or keep it if yours is deliberately different.")


def _how(entry):
    if entry.get("bash"):
        return "a command: " + entry["bash"][:44]
    if entry.get("file"):
        return "a file matching " + entry["file"][:38]
    tools = entry.get("tool") or []
    return f"{len(tools)} tool(s): " + ", ".join(tools[:2]) + (" …" if len(tools) > 2 else "")


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="Inspect and manage destinations — what counts as sending.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="every destination, where it came from, and how it is recognised")
    p = sub.add_parser("show", help="one destination in full")
    p.add_argument("name")
    p = sub.add_parser("rm", help="delete one of your own")
    p.add_argument("name")
    p = sub.add_parser("off", help="stop checking one on this machine, whichever layer it came from")
    p.add_argument("name")
    p = sub.add_parser("on", help="resume checking one you switched off")
    p.add_argument("name")
    p = sub.add_parser("share", help="copy your own into a directory your team keeps")
    p.add_argument("--to", required=True, metavar="DIR")
    p.add_argument("--only", metavar="NAME", help="just this one, rather than everything you added")
    a = ap.parse_args()

    if a.cmd == "list":
        # First match wins, so a name in two layers means the earlier one decides and the later one is
        # dead. That is the point of the layering — you can override the team's copy — but it also means
        # your copy stops you receiving their improvements to it, and silence about that is unhelpful.
        seen = set()
        for entry in DESTINATIONS:
            lowered = str(entry.get("name", "")).lower()
            entry["_shadowed"] = lowered in seen
            seen.add(lowered)
        for entry in DESTINATIONS:
            caps = " ".join(filter(None, [
                f"effort<={entry['max_effort']}" if entry.get("max_effort") else "",
                f"severity<={entry['max_severity']}" if entry.get("max_severity") else ""]))
            mark = "  (shadowed by yours)" if entry.get("_shadowed") else ""
            print(f"{entry['name']:44s} {entry['_origin']:9s} {_how(entry):50s} {caps}{mark}")
        for name in SWITCHED_OFF:
            print(f"{name:44s} off        not checked on this machine")
        print(f"\nyours:  {_user_path()}")
        for directory in paths.shared():
            print(f"shared: {os.path.join(directory, 'destinations.json')}")
        print(f"shipped: {SHIPPED}")
        return

    if a.cmd == "share":
        print(share(a.to, a.only))
        return

    if a.cmd in ("off", "on"):
        try:
            where = switch(a.name, a.cmd == "on")
        except KeyError:
            raise SystemExit(f"no destination called {a.name!r}. Try: list")
        if where is None:
            print(f"{a.name} was already {'on' if a.cmd == 'on' else 'off'}; nothing to change")
        else:
            print(f"{a.name} is now {'checked' if a.cmd == 'on' else 'not checked'} -> {where}")
        return

    if a.cmd == "rm":
        try:
            print("deleted from", remove(a.name))
        except KeyError:
            raise SystemExit(f"no destination called {a.name!r}. Try: list")
        except PermissionError as exc:
            raise SystemExit(str(exc))
        return

    entry = find(a.name)
    if entry is None:
        raise SystemExit(f"no destination called {a.name!r}. Try: list")
    print(f"name       {entry['name']}")
    print(f"origin     {entry['_origin']}")
    print(f"recognised {_how(entry)}")
    for key in ("tool", "bash", "file", "text_fields", "text_arg", "identifiers", "max_effort",
                "max_severity", "require_tracked", "note", "caveat"):
        if entry.get(key) is not None:
            print(f"{key:10} {json.dumps(entry[key]) if not isinstance(entry[key], str) else entry[key]}")


if __name__ == "__main__":
    _cli()
