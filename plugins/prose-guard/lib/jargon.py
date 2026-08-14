#!/usr/bin/env python3
"""Find acronyms used without ever being explained. Deterministic, no model involved.

Every other check here is a model and therefore carries the biases we are trying to avoid. This one
is an algorithm: Schwartz & Hearst (PSB 2003), reported at 96% precision and 82% recall on the
Medstract gold standard with no training data. So a number from this cannot be a brevity detector in
disguise.

It detects the weaker of the two failures. "ADC" used with no expansion anywhere is caught here.
"Application Default Credentials (a different auth mechanism)" — expanded but still not explained in
a way the reader can act on — is not. That one needs judgement, which the model-based checks do.

This module knows nothing about who the reader is. It takes an `is_known` predicate, so the same
detection serves any audience. audiences.py decides what is known.

    python3 lib/jargon.py <file>
    cat draft.md | python3 lib/jargon.py
"""
import os
import re
import sys

FENCE = re.compile(r"```.*?```", re.S)
INLINE = re.compile(r"`[^`]+`")
# A quoted line is someone else's words, so it is not their prose to answer for. Free to skip:
# dropping blockquotes removed zero detections across 301 real messages, whereas skipping any term
# appearing in backticks anywhere would have silenced 24 of 75 — a third of the true positives.
QUOTE = re.compile(r"^\s*>.*$", re.M)
# acronym-shaped: 2-6 characters, capitals and digits
ACRONYM = re.compile(r"\b([A-Z][A-Z0-9]{1,5})\b")
# What is in the brackets, and the phrase before them. See pairs().
INSIDE = re.compile(r"\(([^()]{2,80}?)\)")
BEFORE = re.compile(r"[^()]{2,}$")
LOOK_BACK = 120         # how far before a bracket the phrase may start


def _system_words():
    """The system word list, used to tell an acronym from a capitalised English word.

    An acronym is by definition not a word, so this belongs here rather than in any audience: THE,
    WAS, LOGGER, NULL, ERROR and ASCII all lowercase to real words and were being reported as jargon
    nobody had explained. A hand-kept exclusion list would grow for ever.
    """
    for path in ("/usr/share/dict/words", "/usr/dict/words"):
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                # two-letter words included, or IS, IT, ON and AS survive as "acronyms". The cost is
                # that IT as in information technology is filtered too, which is the right way
                # round: a message using "IT" is almost never using it as a term to explain.
                return {w.strip().lower() for w in fh if len(w.strip()) > 1}
        except OSError:
            continue
    return set()


def _shipped_words():
    """The floor, for a machine with no system dictionary at all.

    Many Linux containers have none. Without this the filter never fires and every capitalised
    English word is reported as unexplained jargon — the tool degrades into noise, and says nothing
    about having done so.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data",
                        "common-words.txt")
    try:
        with open(path, encoding="utf-8") as fh:
            return {w for line in fh if not line.startswith("#")
                    for w in line.split() if len(w) > 1}
    except OSError:
        return set()


SHIPPED_WORDS = _shipped_words()
SYSTEM_WORDS = _system_words()
WORDS = SYSTEM_WORDS | SHIPPED_WORDS


# The system word list carries base forms, so FAILS and COINED survive it. Stripping these suffixes
# catches the inflections without pulling in a stemmer.
_SUFFIXES = ("s", "es", "ed", "ing", "d")
# What is left has to be a word in its own right, not two letters. Without this floor AMD reduced to
# "am" and AWS to "aw" — both in the dictionary — so neither was ever reported, and adding any
# two-letter abbreviation to the word list silently retired a whole family of acronyms with it.
_SHORTEST_STEM = 3
# English turns a final y into i before these two suffixes, and a word list carries the base form only,
# so stripping the suffix is not enough on its own: "denied" reduces to "deni", which is in no
# dictionary, so DENIED read as an acronym and the check held back a commit message that wrote it in
# capitals for emphasis. RELIED, APPLIES, COPIES, IDENTIFIED, QUERIED and VERIFIED went the same way on
# this machine, while TRIED, CARRIED, SIMPLIFIED and STUDIED escaped only because web2 lists those four
# outright — which words a machine reports was luck, and on a machine with no system dictionary it is
# all of them. Only these two suffixes: putting the y back after any of the five instead reduced GUID
# to "guy" and retired a real acronym.
_Y_BEFORE = ("ed", "es")


def _base_forms(low):
    """The base forms this word could be an inflection of, for the word list to be asked about."""
    for sfx in _SUFFIXES:
        if low.endswith(sfx) and len(low) - len(sfx) >= _SHORTEST_STEM:
            stem = low[: -len(sfx)]
            yield stem
            if sfx in _Y_BEFORE and stem.endswith("i"):
                yield stem[:-1] + "y"


def is_acronym(token):
    """False when this is a capitalised English word rather than an acronym.

    An acronym is by definition not a word. THE, WAS, LOGGER, NULL and ASCII all lowercase to real
    words and were being reported as jargon nobody had explained.
    """
    low = token.lower()
    return low not in WORDS and not any(base in WORDS for base in _base_forms(low))


def prose(text):
    return INLINE.sub(" ", QUOTE.sub(" ", FENCE.sub(" ", text or "")))


def _valid_short(s):
    return 2 <= len(s) <= 10 and len(s.split()) <= 2 and bool(re.search(r"[A-Za-z]", s)) \
        and s[0].isalnum()


def _best_long(short, candidate):
    """Schwartz-Hearst right-to-left match. Returns the matched long form, or None."""
    s, l = short.lower(), candidate.lower()
    si, li = len(s) - 1, len(l) - 1
    while si >= 0:
        c = s[si]
        if not c.isalnum():
            si -= 1
            continue
        while li >= 0 and l[li] != c:
            li -= 1
        if li < 0:
            return None
        # the first character of the short form must start a word in the long form
        if si == 0 and not (li == 0 or not l[li - 1].isalnum()):
            while li >= 0 and not (l[li] == c and (li == 0 or not l[li - 1].isalnum())):
                li -= 1
            if li < 0:
                return None
        si -= 1
        li -= 1
    return candidate[li + 1:].strip() if li + 1 < len(candidate) else candidate


def pairs(text):
    """(short, long) pairs written as 'Long Form (SF)' or 'SF (Long Form)'.

    Anchored on the parenthesis, and the phrase read backwards from it. Written the other way round —
    `([^()]{2,120}?)\\s*\\(([^()]{2,80}?)\\)` — the leading run was tried at every offset in the text
    and expanded to its full 120 characters before failing at almost all of them, which is ~120
    character comparisons per input character. Linear, but the constant cost 914 ms on 100,000 words
    and 96% of a term check; anchored, the same text takes 3.7 ms for identical output, and learn.py
    over 20,000 documents drops from 17.4 s to 0.4 s.
    """
    out = {}
    hunt = 0                    # where the last pair ended: finditer never overlapped its matches
    for m in INSIDE.finditer(text):
        inside = m.group(1)
        # The phrase runs up to the bracket, minus the whitespace the old \s* absorbed, and reaches back
        # LOOK_BACK characters or as far as the last bracket, whichever is nearer. The slice is what
        # bounds the look-back, so BEFORE needs no second bound of its own.
        end = m.start()
        while end > hunt and text[end - 1].isspace():
            end -= 1
        found = BEFORE.search(text[max(hunt, end - LOOK_BACK):end])
        before = found.group(0) if found else ""
        hunt = m.end()
        if _valid_short(inside):
            words = before.split()
            n = min(len(inside) + 5, len(inside) * 2)
            cand = " ".join(words[-n:]) if words else ""
            got = _best_long(inside, cand) if cand else None
            if got and len(got) >= len(inside) and inside.lower() not in got.lower().split():
                out[inside] = got
        tail = before.split()[-1] if before.split() else ""
        if _valid_short(tail) and not _valid_short(inside):
            got = _best_long(tail, inside)
            if got and len(got) >= len(tail):
                out[tail] = got
    return out


def expanded_in_prose(short, text):
    """Also count it as expanded when a phrase whose initials match appears anywhere, e.g.
    'Application Default Credentials' with '(ADC)' never written. Schwartz-Hearst sees only
    parenthetical pairs, and writers often expand in running prose instead.

    Every initial must begin a word of at least three letters. Without that floor a one-letter word
    could stand in for an initial, so "we ran a docker container" counted ADC as explained and the
    check passed a message that never explained it. The floor removed no detection across 351 real
    messages, where every genuine expansion is three content words.
    """
    letters = [c for c in short.lower() if c.isalpha()]
    if len(letters) < 2:
        return False
    pat = r"\b" + r"\s+".join(re.escape(c) + r"[a-z]{2,}" for c in letters) + r"\b"
    return re.search(pat, text, re.I) is not None


def uses(text, term):
    """Whether this text already contains that term.

    Deliberately the scan's own machinery rather than a substring test or a second regex: the question
    is "would this term have been found here", and answering it any other way lets the two disagree.
    `RC` is not found inside `SOURCE`, and is found in `RC-1`, because that is what the scan does.
    """
    return term in set(ACRONYM.findall(prose(text)))


def scan(text, is_known):
    """(unexplained, considered). `considered` is every acronym-shaped term the reader had to
    handle, known or not — the denominator for asking whether the audience model is wrong.
    """
    body = prose(text)
    written = pairs(body)
    # A term the audience is known to use IS a term the reader had to handle, whatever the local
    # dictionary thinks of it. Without that clause the denominator moves between machines: Ubuntu's
    # wamerican contains "api" and macOS's web2 does not, so API counted as an acronym on one and as
    # an English word on the other — and the share threshold is computed against this count.
    considered = sorted(t for t in set(ACRONYM.findall(body))
                        if is_known(t) or is_acronym(t))
    unexplained = sorted(t for t in considered
                         if not is_known(t) and t not in written
                         and not expanded_in_prose(t, body))
    return unexplained, considered


def main():
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import audiences
    text = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    resolved = audiences.resolve({})
    bad, considered = scan(text, resolved.is_known)
    print(f"audience: {'unresolved, assuming ' + str(resolved.fallback) if not resolved.resolved else ', '.join(resolved.names)}")
    print(f"terms the reader met: {len(considered)}  unexplained: {len(bad)}")
    if bad:
        print("  " + ", ".join(bad))


if __name__ == "__main__":
    main()
