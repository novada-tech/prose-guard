"""Which terms this audience can be assumed to know, and how confident we are about that.

Two layers, and the difference between them decides whether the check is allowed to block.

    general      shipped with the tool, hand-curated, ~96 acronyms any developer knows.
                 Discloses nothing about anyone and needs no setup.
    measured     yours, written by /prose-guard:learn-vocabulary from sources you choose.
                 Absent until you run it.

Without a measured layer the tool knows what developers in general know and nothing about the
people you actually write to, so an unrecognised acronym is a guess. It says so and does not
block. Once you have measured your own audience, the same finding is evidence and it does block.
Enforcement follows the evidence rather than the other way round, which is the only way tier 0 is
usable: otherwise the first day is spent arguing with it about your own house vocabulary.

Author BREADTH, not frequency, is what a measured file records. One person's favourite acronym is
not shared knowledge however often they type it: in the corpus this was first built on, one
acronym occurred 149 times from a single author.
"""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED = os.path.join(_HERE, "..", "data", "general-vocabulary.json")

# How many distinct people have to have used a term before the audience is assumed to know it.
# 4 rather than 3 because on the corpus this was calibrated against, a term the team lead said
# plainly needed explaining reached exactly 3.
MIN_AUTHORS = 4


def config_dir():
    """Where your own files live. CLAUDE_PLUGIN_DATA when the plugin provides it, so the data
    survives a plugin update; otherwise the usual XDG spot."""
    return (os.environ.get("PROSE_GUARD_HOME")
            or os.environ.get("CLAUDE_PLUGIN_DATA")
            or os.path.join(os.environ.get("XDG_CONFIG_HOME")
                            or os.path.join(os.path.expanduser("~"), ".config"),
                            "prose-guard"))


def _load(path, key=None):
    try:
        with open(path) as fh:
            d = json.load(fh)
        return d.get(key) if key else d
    except Exception:
        return None


def _general():
    return {t.upper() for t in (_load(SHIPPED, "general") or [])}


def _measured():
    """{TERM: distinct_author_count}. Also accepts a bare list, meaning "known", for hand editing."""
    raw = _load(os.path.join(config_dir(), "vocabulary.json"), "terms")
    if raw is None:
        return None
    if isinstance(raw, list):
        return {str(t).upper(): MIN_AUTHORS for t in raw}
    return {str(t).upper(): int(n) for t, n in raw.items()}


def _accepted():
    """Terms you told it to stop flagging. One per line, '#' comments, hand-editable on purpose."""
    path = os.path.join(config_dir(), "known-terms.txt")
    try:
        with open(path) as fh:
            return {l.strip().upper() for l in fh
                    if l.strip() and not l.lstrip().startswith("#")}
    except OSError:
        return set()


def _dictionary():
    """The system word list, used to tell an acronym from a capitalised English word.

    An acronym is by definition not a word. LOGGER, NULL, ERROR and ASCII all lowercase to real
    words and were being flagged as unexplained jargon; a hand-maintained exclusion list would
    have grown forever. A missing word list means this filter simply does not fire.
    """
    for path in ("/usr/share/dict/words", "/usr/dict/words"):
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                return {w.strip().lower() for w in fh if len(w.strip()) > 2}
        except OSError:
            continue
    return set()


GENERAL = _general()
MEASURED = _measured()
ACCEPTED = _accepted()
WORDS = _dictionary()
# Whether we know anything about THIS audience, as opposed to developers in general.
HAVE_MEASURED = bool(MEASURED)


def needs_explaining(term):
    """True if this audience cannot be assumed to know the term."""
    t = term.upper()
    if t in GENERAL or t in ACCEPTED:
        return False
    if t.lower() in WORDS:
        return False                          # a capitalised English word, not an acronym
    if MEASURED is not None and t in MEASURED:
        return MEASURED[t] < MIN_AUTHORS
    return True


def accept(term):
    """Record that this term is fine, so it is never flagged again. What the guard offers when it
    is guessing rather than measuring."""
    d = config_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "known-terms.txt")
    with open(path, "a") as fh:
        fh.write(term.strip().upper() + "\n")
    return path


def status():
    """One line for a human, for the setup skill and the README to print."""
    if HAVE_MEASURED:
        return (f"{len(GENERAL)} general terms plus {len(MEASURED)} measured for your audience"
                f"{f', {len(ACCEPTED)} accepted by hand' if ACCEPTED else ''}. "
                "Unexplained terms are held back.")
    return (f"{len(GENERAL)} general terms, nothing measured for your audience yet"
            f"{f', {len(ACCEPTED)} accepted by hand' if ACCEPTED else ''}. "
            "Unexplained terms are reported as advice, not held back — run "
            "/prose-guard:learn-vocabulary to change that.")


if __name__ == "__main__":
    print(status())
    print("config directory:", config_dir())
