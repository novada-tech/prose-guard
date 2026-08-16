"""What a hand-written file may contain, declared once, and checked when it is read.

Every file this tool reads can be edited by hand, and three of them are meant to be: a setup skill
tells an agent to write destinations as JSON, a team pulls audiences out of a shared repository, and
`/plugin configure` offers a free-text box for the effort level because `userConfig` has no enumerated
type. So the interesting question is not what a correct file looks like. It is what happens to a
slightly wrong one.

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
import difflib
import json

# ------------------------------------------------------------------ what a value may be
# A rule takes the value found and returns (usable_value, complaint). Either may be None: None for the
# value means "nothing usable here, fall back", and None for the complaint means "nothing to say".


def one_of(*allowed):
    """One of a short list. Compared without case or surrounding space, because a person typing into a
    free-text box types `Low `, and refusing that would be pedantry rather than safety."""
    def rule(value):
        if value is None:
            return None, None
        text = str(value).strip().lower()
        if text in allowed:
            return text, None
        return None, f"is {value!r}, which is not one of: {', '.join(allowed)}"
    return rule


def text(value):
    if value is None or isinstance(value, str):
        return value, None
    return None, f"is {type(value).__name__}, which should be text"


def flag(value):
    if value is None or isinstance(value, bool):
        return value, None
    return None, f"is {value!r}, which should be true or false"


def whole_number(value):
    if value is None or (isinstance(value, int) and not isinstance(value, bool)):
        return value, None
    return None, f"is {value!r}, which should be a whole number"


def each(rule):
    """A list of things, every one of which follows `rule`.

    One name written without brackets is read as a list holding that one name, because that is what
    somebody who writes `"off": "chat message"` means, and iterating it as twelve one-letter names
    switched nothing off and said nothing about it.
    """
    def check(value):
        if value is None:
            return None, None
        items = [value] if isinstance(value, (str, bytes)) else value
        try:
            items = list(items)
        except TypeError:
            return None, f"is {type(value).__name__}, which should be a list"
        out, wrong = [], []
        for item in items:
            got, complaint = rule(item)
            if complaint:
                wrong.append(complaint)
            elif got is not None:
                out.append(got)
        return out, ("; ".join(sorted(set(wrong))) or None)
    return check


def mapping(value):
    if value is None or isinstance(value, dict):
        return value, None
    return None, f"is {type(value).__name__}, which should be a set of key/value pairs"


def anything(value):
    return value, None


# ------------------------------------------------------------------ the declarations
LEVELS = ("disabled", "low", "medium", "high")
SEVERITIES = ("block", "advise")
CONTEXTS = ("low", "medium", "high")

CONFIG = {"effort": one_of(*LEVELS),
          "shared": each(text),
          "unresolved_audience": text,
          # Terms never assumed known, whichever audience applies. See audiences.never_known.
          "not_known": each(text)}

# A destination: which tool calls carry prose to which readers, and how hard to look. `max_effort` and
# `max_severity` are the two that exist to make the guard LESS aggressive, which is why a typo in
# either is the one that must not pass.
DESTINATION = {"name": text, "note": text, "caveat": text,
               "tool": each(text), "bash": text, "file": text,
               "text_fields": each(text), "text_arg": each(text),
               "identifiers": mapping, "when": mapping, "context_from": mapping,
               "require_tracked": flag,
               "max_effort": one_of(*LEVELS),
               "max_severity": one_of(*SEVERITIES)}

DESTINATIONS_FILE = {"destinations": anything, "public_owners": each(text), "off": each(text),
                     "_meta": anything, "public_owners_help": anything}

AUDIENCE = {"name": text, "who": text, "inherits": each(text),
            "matches": mapping, "vocabulary": mapping, "expansions": mapping,
            "members": each(text), "assumptions": mapping,
            "_meta": anything, "_note": anything}

ASSUMPTIONS = {"shared_context": one_of(*CONTEXTS)}


def checked(data, shape, where):
    """A copy of `data` holding only values that follow `shape`, and a complaint for each that did not.

    An unknown key is a complaint too. `max_effot: "low"` is the same mistake as `max_effort: "lo"` and
    used to be the quieter of the two, because nothing looked at key names at all.
    """
    if not isinstance(data, dict):
        kind = type(data).__name__
        return {}, [f"{where} holds {kind} where it should hold key/value pairs, so it was not read"]
    clean, complaints = {}, []
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


def read(path, shape, where=None):
    """One JSON file, checked against its declaration. Missing or unreadable is empty and silent.

    Silent because a file that is not there is the ordinary case — nobody has a destinations.json until
    they write one — while a file that IS there and is wrong is the case worth a sentence.
    """
    try:
        with open(path) as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return {}, []
    except OSError as exc:
        return {}, [f"{path} could not be read ({exc.strerror})"]
    except ValueError as exc:
        return {}, [f"{path} is not valid JSON ({exc}), so nothing in it was used"]
    return checked(raw, shape, where or path)
