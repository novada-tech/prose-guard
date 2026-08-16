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

import command
import paths
import settings
import re
import subprocess

# A short message is not the failure this catches, and is not worth a model call.
MIN_WORDS = 25
FILE_TOOLS = ("Write", "Edit", "NotebookEdit")

# The fields whose value is a regular expression run against a command or a path.
PATTERNS = ("bash", "file")


def _user_path():
    return paths.mine().destinations


def _read(path):
    """One layer, checked against its declaration. Complaints are collected rather than raised."""
    got, complaints = settings.read(path, settings.DESTINATIONS_FILE, os.path.basename(path))
    rows, kept = got.get("destinations") or [], []
    if not isinstance(rows, list):
        complaints.append(f"{os.path.basename(path)}: destinations should be a list, so none were read")
        rows = []
    for n, entry in enumerate(rows):
        where = f"{os.path.basename(path)} destination {n + 1}"
        clean, said = settings.checked(entry, settings.DESTINATION, where)
        said = said + _uncompilable(clean, where)
        # A destination with no name cannot be switched off, shown or shared, so it is not one.
        if clean.get("name"):
            kept.append(clean)
        elif not said:
            said = [f"{where} has no name, so it was not read"]
        complaints.extend(said)
    got["destinations"] = kept
    return got, complaints


def _uncompilable(entry, where):
    """Complaints for any pattern that will not compile. The field is dropped rather than kept.

    A pattern is the one thing the declaration cannot check by shape: `"bash": "gh pr ("` is perfectly
    good text and raises `re.error` out of `_matches` at the moment the hook runs it. A PreToolUse hook
    that exits non-zero lets the tool call through unchecked, so an unbalanced bracket in a
    hand-written file is the guard switching itself off for every call, silently.
    """
    out = []
    for key in PATTERNS:
        if entry.get(key) is None:
            continue
        try:
            re.compile(entry[key])
        except re.error as exc:
            entry.pop(key)
            out.append(f"{where}: {key} does not compile as a pattern ({exc}), so it was not read")
    return out


def load():
    """Yours first, then your team's, then the shipped set. First match wins, so an earlier layer
    overrides a later one — which is how a team stops something being checked, or checks it differently,
    for everybody at once.

    A destination is worth more shared than an audience is. An audience is measured from a corpus and
    describes one group of readers; a destination is a fact about which tool sends prose and which field
    carries it, and that fact is the same for everyone using that tool. One person working it out with
    /prose-guard:setup is the whole team's answer.

    `off` is read from every layer rather than from yours alone. There is no deleting a shipped
    destination — the file is inside the plugin and is replaced on update — so `off` is the only way to
    retire one, and reading it from one layer meant a team could add a destination for everybody and
    could not stop one for anybody. Each name comes back with the layer that switched it off and how
    many entries it actually stopped: a name that stops nothing is one somebody renamed in a release,
    and printing it as switched off is how a person comes to believe a check is not running.
    """
    layers, complaints = [], []
    for layer in paths.layers():
        got, said = _read(layer.destinations)
        layers.append((layer.origin, got))
        complaints.extend(said)
    silenced = {}
    for origin, layer in layers:
        for name in layer.get("off") or []:
            silenced.setdefault(str(name).lower(), [str(name), origin, 0])
    found, owners = [], set()
    for origin, layer in layers:
        for entry in layer.get("destinations") or []:
            stopped = silenced.get(str(entry.get("name", "")).lower())
            if stopped:
                stopped[2] += 1
                continue
            found.append(dict(entry, _origin=origin))
        owners |= {str(o).lower() for o in (layer.get("public_owners") or [])}
    return found, owners, [tuple(v) for v in silenced.values()], complaints


DESTINATIONS, PUBLIC_OWNERS, SWITCHED_OFF, COMPLAINTS = load()


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
        # The whole name, or the whole name after an MCP server's prefix. A substring match made
        # `slack_send_message` claim `slack_send_message_draft` too, and the shipped file only escaped
        # that because the draft happens to be listed first — so putting an ordinary chat destination in
        # your own layer, which is read before the shipped one, silently removed the draft's advise-only
        # cap and started blocking drafts.
        if any(tool == n or tool.endswith("__" + n) for n in names):
            return True
    if dest.get("bash") and tool == "Bash":
        return bool(re.search(dest["bash"], command.command_itself(str(tool_input.get("command") or ""))))
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
    passed = list(command.flag_values(cmd))
    for flag in dest.get("text_arg") or ():
        values = [v for f, v in passed if f == flag]
        if not values:
            continue
        # A flag ending in -file, or the short -F, names a file whose contents are the prose. That
        # is how a long body is really passed, so it is read rather than matched. The path came from the
        # command's own argument, so a hidden one is the caller's choice.
        if flag.endswith("-file") or flag in ("-F", "--file"):
            for value in values:
                got = command.read_prose_file(value, cwd, inside=False)
                if got is not None:
                    return got
            continue
        # Several -m flags concatenate into one message, which is how a subject and body are given.
        joined = "\n\n".join(values)
        # The prose may be behind a substitution rather than in the command. Where it can be had
        # without risking a side effect, have it: nobody should have to restructure a command to
        # get their writing checked.
        if joined.strip().startswith("$"):
            return command.resolve(joined, cwd)
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


def unreadable(dest, tool, tool_input, cwd=None):
    """Why a matched destination yielded no text, when the reason is worth telling somebody.

    The alternative is what happened when the pull request for this very change was opened: the guard
    matched `gh pr create`, found the body was a shell substitution, and allowed the call in silence. A
    gap that says nothing is indistinguishable from a check that passed, and `--body-file` — which is
    read — is one flag away.
    """
    if tool != "Bash":
        return None
    passed = list(command.flag_values(str(tool_input.get("command") or "")))
    for flag in dest.get("text_arg") or ():
        if flag.endswith("-file") or flag in ("-F", "--file"):
            continue
        for value in (v for f, v in passed if f == flag):
            if not value.startswith(command.SUBSTITUTED):
                continue
            # Only complain about what could not be worked out. A substitution the tool can resolve is
            # not a gap, and telling someone to restructure a command that already works would be
            # noise. `resolve` is answered from the cache `extract` already filled, so asking again
            # here runs nothing.
            if command.resolve(value, cwd):
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
    cmd = command.command_itself(str(tool_input.get("command") or ""))
    if dest.get("bash") and re.search(r"\bgit\s+commit\b", cmd):
        if re.search(r"--amend\b", cmd):
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


# ---------------------------------------------------------------------------- managing them
def _user_file():
    return _read(_user_path())[0]


def _save_user(data):
    paths.ensure()
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


def switched_off_by(name):
    """The layers whose `off` list holds this name: yours, shared, built in."""
    return [origin for n, origin, _ in SWITCHED_OFF if n.lower() == name.lower()]


def switch(name, on):
    """Stop, or resume, checking a destination on this machine, whichever layer it came from.

    Only your own file is written. A name your team switched off is refused rather than quietly left
    off, because "already on" while it stays off is the answer that costs somebody an afternoon.
    """
    data = _user_file()
    off = [str(n) for n in (data.get("off") or [])]
    lowered = [n.lower() for n in off]
    elsewhere = [o for o in switched_off_by(name) if o != "yours"]
    if on:
        if name.lower() not in lowered:
            if elsewhere:
                raise PermissionError(
                    f"{name} is switched off in the {elsewhere[0]} destinations.json, not in yours, so "
                    f"it is not yours to switch back on. Take the name out of the `off` list in that "
                    f"file and it is checked again for everybody.")
            return None
        data["off"] = [n for n in off if n.lower() != name.lower()]
    else:
        # Checked before `find`, which cannot see a destination that is already switched off.
        if name.lower() in lowered or elsewhere:
            return None
        if find(name) is None:
            raise KeyError(name)
        data["off"] = off + [name]
    return _save_user(data)


def add(entry):
    """Write one destination into your own file. The only writer, checked by the same declaration
    `load` reads with, so the file cannot hold a shape the loader will drop.

    What created a destination before this was prose: /prose-guard:setup told an agent to hand-write
    JSON into the config directory. Nothing checked it, and the two fields that exist to make the guard
    LESS aggressive fail open — `max_effort: "lo"` was ignored, so the destination that was meant to
    stop at a cheap check ran every check and could block.

    Refuses rather than repairs. A destination that matches nothing, or matches and can never find the
    prose, is worse than no destination: it looks configured.
    """
    clean, complaints = settings.checked(entry, settings.DESTINATION, "this destination")
    complaints += _uncompilable(clean, "this destination")
    if not clean.get("name"):
        complaints.append("this destination has no name, and a name is how you show, share or "
                          "switch off a destination later")
    if not any(clean.get(k) for k in ("tool", *PATTERNS)):
        complaints.append("nothing says when this applies: give it a tool, a command pattern (bash) "
                          "or a file pattern (file), or it can never match a call")
    if clean.get("tool") and not clean.get("text_fields"):
        complaints.append("a tool destination needs text_fields — which field of the call carries the "
                          "prose — or it matches the call and never finds anything to check")
    if clean.get("bash") and not clean.get("text_arg"):
        complaints.append("a command destination needs text_arg — which flag carries the prose — or it "
                          "matches the command and never finds anything to check")
    if clean.get("name") and any(str(r.get("name", "")).lower() == clean["name"].lower()
                                 for r in (_user_file().get("destinations") or [])):
        complaints.append(f"you already have a destination called {clean['name']} — `rm` it first, or "
                          f"give this one another name")
    if complaints:
        raise ValueError("\n".join(complaints))
    shadowed = find(clean["name"])
    data = _user_file()
    data["destinations"] = list(data.get("destinations") or []) + [clean]
    return _save_user(data), (shadowed or {}).get("_origin")


def share(directory, only=None, with_off=False):
    """Copy destinations from this machine into a directory a team keeps.

    Only ever your own: the shipped set is already everywhere, and copying it would put a stale duplicate
    in front of the maintained one. `only` names one, for the common case where some of what you have
    worked out is the team's business and some is not.

    `with_off` takes the names you have switched off with it, which is what retiring a shipped
    destination for a whole team looks like — the copy of `off` in a shared file is read on every
    machine that reads that directory. Asked for rather than automatic: switching something off here is
    usually about this machine, and doing it for eleven colleagues because one person muted it is the
    surprise worth a flag.
    """
    mine = _user_file()
    rows = [r for r in (mine.get("destinations") or [])
            if only is None or str(r.get("name", "")).lower() == only.lower()]
    off = [str(n) for n in (mine.get("off") or [])] if with_off else []
    if not rows and not off:
        return ("nothing to share: " + (f"you have no destination called {only}" if only else
                "no destinations have been added on this machine. The shipped ones are already "
                "everywhere; /prose-guard:setup works out what is missing."))
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, "destinations.json")
    existing = _read(target)[0]
    have = {json.dumps(x, sort_keys=True) for x in (existing.get("destinations") or [])}
    fresh = [{k: v for k, v in r.items() if k != "_origin"} for r in rows]
    added = [x for x in fresh if json.dumps(x, sort_keys=True) not in have]
    merged = dict(existing)
    merged["destinations"] = list(existing.get("destinations") or []) + added
    theirs = [str(n) for n in (existing.get("off") or [])]
    retired = [n for n in off if n.lower() not in {t.lower() for t in theirs}]
    if theirs or retired:
        merged["off"] = theirs + retired
    merged.setdefault("_meta", {})["what"] = (
        "Destinations this team has worked out. Read after your own file and before the shipped set, so "
        "your own destinations.json still wins locally.")
    with open(target, "w") as fh:
        json.dump(merged, fh, indent=1)
        fh.write("\n")
    names = ", ".join(x.get("name", "?") for x in added) or "nothing new"
    return (f"{len(added)} added to {target}: {names}\n"
            + (f"{len(retired)} switched off for everyone who reads that directory: "
               f"{', '.join(retired)}\n" if retired else "")
            + f"Nothing is shared until you commit it. Then anyone whose config lists that directory has "
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


def _identifiers(pairs):
    """`channel=channel_id`, `repo=owner,name` or `cwd_repo=true`, as the map audiences route on.

    An identifier is what turns a tool call into a reader: the channel id in the call is what says
    which audience is about to read this. A destination without one is checked against whatever
    baseline is configured rather than against the people it is going to.
    """
    out = {}
    for pair in pairs:
        key, _, source = str(pair).partition("=")
        if not key or not source:
            raise ValueError(f"{pair!r} is not KEY=FIELD — for example channel=channel_id, or "
                             f"cwd_repo=true for the repository the command runs in")
        out[key] = True if source.lower() == "true" else (
            source.split(",") if "," in source else source)
    return out


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="Inspect and manage destinations — what counts as sending.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="every destination, where it came from, and how it is recognised")
    p = sub.add_parser("show", help="one destination in full")
    p.add_argument("name")
    p = sub.add_parser("add", help="add one of your own, checked as it is written")
    p.add_argument("name", help="what to call it — how you show, share or switch it off later")
    p.add_argument("--tool", nargs="+", metavar="NAME",
                   help="tool names that carry prose. The whole name, or the name after an MCP "
                        "server's prefix: slack_send_message matches mcp__slack__slack_send_message")
    p.add_argument("--bash", metavar="REGEX", help="a pattern matching the command itself")
    p.add_argument("--file", metavar="REGEX", help="a pattern matching the path being written")
    p.add_argument("--text-field", nargs="+", metavar="FIELD",
                   help="which field of the tool call carries the prose. Required with --tool")
    p.add_argument("--text-arg", nargs="+", metavar="FLAG",
                   help="which flag carries it, for --bash. A flag ending in -file, or -F, names a "
                        "file whose contents are read")
    p.add_argument("--identifier", nargs="+", metavar="KEY=FIELD",
                   help="what the call reveals about who will read it, so an audience can be matched: "
                        "channel=channel_id, repo=owner,name, cwd_repo=true")
    p.add_argument("--note", metavar="TEXT", help="what this destination is, for the checks to read")
    p.add_argument("--caveat", metavar="TEXT", help="what a person should know before it holds a call")
    p.add_argument("--max-effort", choices=settings.LEVELS,
                   help="never check harder than this here, whatever the configured level")
    p.add_argument("--max-severity", choices=settings.SEVERITIES,
                   help="advise: this destination may never block a call")
    p.add_argument("--require-tracked", action="store_true",
                   help="with --file: only a file inside a git working tree and not ignored, which is "
                        "the line between a document colleagues read and a scratch file")
    p = sub.add_parser("rm", help="delete one of your own")
    p.add_argument("name")
    p = sub.add_parser("off", help="stop checking one on this machine, whichever layer it came from")
    p.add_argument("name")
    p = sub.add_parser("on", help="resume checking one you switched off")
    p.add_argument("name")
    p = sub.add_parser("share", help="copy your own into a directory your team keeps")
    p.add_argument("--to", required=True, metavar="DIR")
    p.add_argument("--only", metavar="NAME", help="just this one, rather than everything you added")
    p.add_argument("--with-off", action="store_true",
                   help="take the names you have switched off too, which retires them for everyone "
                        "who reads that directory rather than only here")
    a = ap.parse_args()

    if a.cmd == "list":
        # First match wins, so a name in two layers means the nearer one decides and the further one is
        # dead. That is the point of the layering — you can override the team's copy — but it also means
        # their improvements to it stop reaching you, and silence about that is unhelpful.
        seen = {}
        for entry in DESTINATIONS:
            caps = " ".join(filter(None, [
                f"effort<={entry['max_effort']}" if entry.get("max_effort") else "",
                f"severity<={entry['max_severity']}" if entry.get("max_severity") else ""]))
            lowered = str(entry.get("name", "")).lower()
            mark = f"  (shadowed by the {seen[lowered]} one)" if lowered in seen else ""
            seen.setdefault(lowered, entry["_origin"])
            print(f"{entry['name']:44s} {entry['_origin']:9s} {_how(entry):50s} {caps}{mark}")
        for name, origin, stopped in SWITCHED_OFF:
            said = (f"not checked, switched off {origin}" if stopped else
                    "switched off, but no destination has that name — renamed or removed?")
            print(f"{name:44s} off        {said}")
        print()
        for layer in paths.layers():
            print(f"{layer.origin + ':':9s} {layer.destinations}")
        return

    if a.cmd == "add":
        entry = {"name": a.name, "tool": a.tool, "bash": a.bash, "file": a.file,
                 "text_fields": a.text_field, "text_arg": a.text_arg, "note": a.note,
                 "caveat": a.caveat, "max_effort": a.max_effort, "max_severity": a.max_severity,
                 "require_tracked": a.require_tracked or None}
        try:
            if a.identifier:
                entry["identifiers"] = _identifiers(a.identifier)
            where, shadowed = add({k: v for k, v in entry.items() if v is not None})
        except ValueError as exc:
            raise SystemExit(str(exc))
        print(f"{a.name} -> {where}")
        if shadowed:
            print(f"  a {shadowed} destination has that name as well. Yours is read first, so yours is "
                  f"the one that applies — and their improvements to it will not reach you")
        print("  it applies to the next tool call; `list` shows it, `share --to DIR` gives it to your "
              "team")
        return

    if a.cmd == "share":
        print(share(a.to, a.only, with_off=a.with_off))
        return

    if a.cmd in ("off", "on"):
        try:
            where = switch(a.name, a.cmd == "on")
        except KeyError:
            raise SystemExit(f"no destination called {a.name!r}. Try: list")
        except PermissionError as exc:
            raise SystemExit(str(exc))
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
