"""What a hand-written file may contain, declared once, and checked when it is read.

Every file this tool reads can be edited by hand, and three of them are meant to be: a setup skill
tells an agent to write destinations as JSON, a team pulls audiences out of a shared repository, and
the effort level is a word somebody types. So the interesting question is not what a correct file
looks like. It is what happens to a slightly wrong one.

What used to happen was nothing, and always in the same direction:

    max_effort: "lo"        ignored, so the destination ran at FULL effort and could block
    max_severity: "Advise"  compared exactly, so the cap that stops a draft blocking did not apply
    shared_context: "sdwys" reached the model as the words "how much they already know: sdwys"
    off: "chat message"     a string where a list was expected, iterated as twelve letters
    effort: "medim"         disabled, silently
    max_effot: "low"        a typo in the KEY, which nothing looked at at all
    [1, 2]                  valid JSON of the wrong shape: an AttributeError at import, and a
                            PreToolUse hook that exits non-zero lets the tool call through unchecked

Every one of those fails OPEN, and open here means the guard is more aggressive than asked, or absent
while looking present. Both are worse than an error. The only one that was ever caught was the effort
level, by a function written for it alone — this is that function generalised, so a field added later
gets the same treatment without anybody remembering to write it.

A complaint is a sentence for the person who wrote the file, naming the file, the field and what was
expected. Reading never raises: a bad value falls back to the safe end and the complaint travels
alongside, because a tool that refuses to start is a tool somebody switches off.
"""
from __future__ import annotations

import difflib
import json
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    # Never evaluated: `str | None` inside a runtime expression would raise before Python 3.10, and
    # this runs on whatever python3 the machine has. A checker reads it; the interpreter never does.
    Rule = Callable[[Any], tuple[Any, str | None]]

# ------------------------------------------------------------------ what a value may be
# A rule takes the value found and returns (usable_value, complaint). Either may be None: None for the
# value means "nothing usable here, fall back", and None for the complaint means "nothing to say".


def one_of(*allowed: str) -> Rule:
    """One of a short list. Compared without case or surrounding space, because a person typing into a
    free-text box types `Low `, and refusing that would be pedantry rather than safety."""
    def rule(value: Any) -> tuple[str | None, str | None]:
        if value is None:
            return None, None
        text = str(value).strip().lower()
        if text in allowed:
            return text, None
        return None, f"is {value!r}, which is not one of: {', '.join(allowed)}"
    return rule


def text(value: Any) -> tuple[str | None, str | None]:
    if value is None or isinstance(value, str):
        return value, None
    return None, f"is {type(value).__name__}, which should be text"


def flag(value: Any) -> tuple[bool | None, str | None]:
    if value is None or isinstance(value, bool):
        return value, None
    return None, f"is {value!r}, which should be true or false"


def whole_number(value: Any) -> tuple[int | None, str | None]:
    if value is None or (isinstance(value, int) and not isinstance(value, bool)):
        return value, None
    return None, f"is {value!r}, which should be a whole number"


def each(rule: Rule) -> Rule:
    """A list of things, every one of which follows `rule`.

    One name written without brackets is read as a list holding that one name, because that is what
    somebody who writes `"off": "chat message"` means, and iterating it as twelve one-letter names
    switched nothing off and said nothing about it.
    """
    def check(value: Any) -> tuple[list[Any] | None, str | None]:
        if value is None:
            return None, None
        items = [value] if isinstance(value, (str, bytes)) else value
        try:
            items = list(items)
        except TypeError:
            return None, f"is {type(value).__name__}, which should be a list"
        out: list[Any] = []
        wrong: list[str] = []
        for item in items:
            got, complaint = rule(item)
            if complaint:
                wrong.append(complaint)
            elif got is not None:
                out.append(got)
        return out, ("; ".join(sorted(set(wrong))) or None)
    return check


def mapping(value: Any) -> tuple[dict[str, Any] | None, str | None]:
    if value is None or isinstance(value, dict):
        return value, None
    return None, f"is {type(value).__name__}, which should be a set of key/value pairs"


def anything(value: Any) -> tuple[Any, None]:
    return value, None


# ------------------------------------------------------------------ the declarations
LEVELS = ("disabled", "low", "medium", "high")
SEVERITIES = ("block", "advise")
CONTEXTS = ("low", "medium", "high")

CONFIG: dict[str, Rule] = {
    "effort": one_of(*LEVELS),
    "shared": each(text),
    "unresolved_audience": text,
    # Terms never assumed known, whichever audience applies. See audiences.never_known.
    "not_known": each(text),
    # What each destination is worth checking, by name: {"slack message": "high"}. Effort was one number
    # for a whole install, which is a per-install answer to a per-message question — a commit message and
    # an announcement to two hundred people got the same budget. `max_effort` on a destination already
    # said what that KIND of destination is worth, and on one real machine 8 of 9 left it unset because
    # there was no way to set it after the destination existed.
    #
    # Here rather than in destinations.json, because how hard you want something checked is your policy
    # and not part of what the destination IS. Putting it there also broke the destination: the layers
    # replace a whole entry by name, so an override carrying only a name and a level threw away the
    # pattern that recognises it, and the destination stopped matching anything at all.
    "worth": mapping}

# A destination: which tool calls carry prose to which readers, and how hard to look. `max_effort` and
# `max_severity` are the two that exist to make the guard LESS aggressive, which is why a typo in
# either is the one that must not pass.
DESTINATION: dict[str, Rule] = {
    "name": text, "note": text, "caveat": text,
    "tool": each(text), "bash": text, "file": text,
    "text_fields": each(text), "text_arg": each(text),
    "identifiers": mapping, "when": mapping, "context_from": mapping,
    # Fields naming what this text is pinned to — a file and a line for a review comment. The checks are
    # told, because a reader looking at that code already has the terms it defines.
    "anchored_to": each(text),
    "require_tracked": flag,
    # Whether the first line is a subject: a title with no room for an explanation under it. See
    # checks/context.py, where it decides what the term check reads.
    "subject_line": flag,
    "max_effort": one_of(*LEVELS),
    "max_severity": one_of(*SEVERITIES)}

DESTINATIONS_FILE: dict[str, Rule] = {
    "destinations": anything, "public_owners": each(text), "off": each(text),
    "_meta": anything, "public_owners_help": anything}

AUDIENCE: dict[str, Rule] = {
    "name": text, "who": text, "inherits": each(text),
    "matches": mapping, "vocabulary": mapping, "expansions": mapping,
    "members": each(text), "assumptions": mapping,
    "_meta": anything, "_note": anything}

# What `learn.py scan --out` writes and `learn.py create` reads back. A person edits this one: the
# audiences skill walks them through the borderline pile, and taking a term out of `known` by hand is
# the expected way to answer. So it gets a declaration like every other file somebody types into.
CANDIDATES: dict[str, Rule] = {
    "known": each(text), "borderline": each(text), "needs_explaining": each(text),
    "members": each(text), "counts": mapping, "expansions": mapping,
    "_meta": anything}

ASSUMPTIONS: dict[str, Rule] = {"shared_context": one_of(*CONTEXTS)}


def checked(data: Any, shape: dict[str, Rule], where: str) -> tuple[dict[str, Any], list[str]]:
    """A copy of `data` holding only values that follow `shape`, and a complaint for each that did not.

    An unknown key is a complaint too. `max_effot: "low"` is the same mistake as `max_effort: "lo"` and
    used to be the quieter of the two, because nothing looked at key names at all.
    """
    if not isinstance(data, dict):
        kind = type(data).__name__
        return {}, [f"{where} holds {kind} where it should hold key/value pairs, so it was not read"]
    clean: dict[str, Any] = {}
    complaints: list[str] = []
    for key, value in data.items():
        rule = shape.get(key)
        if rule is None:
            near = difflib.get_close_matches(str(key), list(shape), n=1, cutoff=0.7)
            complaints.append(f"{where} has no field {key!r}"
                              + (f" — did you mean {near[0]!r}?" if near else ""))
            continue
        got, complaint = rule(value)
        if complaint:
            complaints.append(f"{where}: {key} {complaint}")
        if got is not None:
            clean[key] = got
    return clean, complaints


def read(path: str, shape: dict[str, Rule],
         where: str | None = None) -> tuple[dict[str, Any], list[str]]:
    """One JSON file, checked against its declaration. Missing or unreadable is empty and silent.

    Silent because a file that is not there is the ordinary case — nobody has a destinations.json until
    they write one — while a file that IS there and is wrong is the case worth a sentence.
    """
    # One name for the file, used by every branch. These two used to interpolate the full path while
    # `checked` used `where`, so the same audience file answered "team.json holds list where it should
    # hold key/value pairs" for a bad shape and "/var/folders/vl/0mhb…/audiences/team.json is not valid
    # JSON" for a bad parse. A caller that says what to call a file means it for all of its complaints.
    name = where or path
    try:
        with open(path) as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return {}, []
    except OSError as exc:
        return {}, [f"{name} could not be read ({exc.strerror})"]
    except ValueError as exc:
        return {}, [f"{name} is not valid JSON ({exc}), so nothing in it was used"]
    return checked(raw, shape, name)
