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

_HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED = os.path.join(_HERE, "..", "data", "destinations.json")

# A short message is not the failure this catches, and is not worth a model call.
MIN_WORDS = 25
FILE_TOOLS = ("Write", "Edit", "NotebookEdit")


def config_dir():
    return paths.home()


def _user_path():
    return os.path.join(config_dir(), "destinations.json")


def _read(path):
    """One layer, checked against its declaration. Complaints are collected rather than raised."""
    got, complaints = settings.read(path, settings.DESTINATIONS_FILE, os.path.basename(path))
    rows, kept = got.get("destinations") or [], []
    if not isinstance(rows, list):
        complaints.append(f"{os.path.basename(path)}: destinations should be a list, so none were read")
        rows = []
    for n, entry in enumerate(rows):
        clean, said = settings.checked(entry, settings.DESTINATION,
                                       f"{os.path.basename(path)} destination {n + 1}")
        # A destination with no name cannot be switched off, shown or shared, so it is not one.
        if clean.get("name"):
            kept.append(clean)
        elif not said:
            said = [f"{os.path.basename(path)} destination {n + 1} has no name, so it was not read"]
        complaints.extend(said)
    got["destinations"] = kept
    return got, complaints


def load():
    """Yours first, then your team's, then the shipped set. First match wins, so an earlier layer
    overrides a later one — which is how a team stops something being checked, or checks it differently,
    for everybody at once.

    A destination is worth more shared than an audience is. An audience is measured from a corpus and
    describes one group of readers; a destination is a fact about which tool sends prose and which field
    carries it, and that fact is the same for everyone using that tool. One person working it out with
    /prose-guard:setup is the whole team's answer.
    """
    where = [("yours", _user_path())]
    where += [("shared", os.path.join(directory, "destinations.json")) for directory in paths.shared()]
    where.append(("built in", SHIPPED))
    layers, complaints = [], []
    for origin, path in where:
        got, said = _read(path)
        layers.append((origin, got))
        complaints.extend(said)
    # Names switched off in YOUR file, whatever layer they came from. There is no deleting a shipped
    # destination — the file is inside the plugin and is replaced on update — so this is how you stop one.
    switched_off = [str(n) for n in (layers[0][1].get("off") or [])]
    off = {n.lower() for n in switched_off}
    found, owners = [], set()
    for origin, layer in layers:
        for entry in layer.get("destinations") or []:
            if str(entry.get("name", "")).lower() in off:
                continue
            found.append(dict(entry, _origin=origin))
        owners |= {str(o).lower() for o in (layer.get("public_owners") or [])}
    return found, owners, switched_off, complaints


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
    existing = _read(target)[0]
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
            caps = " ".join(filter(None, [
                f"effort<={entry['max_effort']}" if entry.get("max_effort") else "",
                f"severity<={entry['max_severity']}" if entry.get("max_severity") else ""]))
            lowered = str(entry.get("name", "")).lower()
            mark = "  (shadowed by yours)" if lowered in seen else ""
            seen.add(lowered)
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
