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


def _dictionary():
    """The system word list, used to tell an acronym from a capitalised English word.

    An acronym is by definition not a word, so this belongs here rather than in any audience:
    THE, WAS, LOGGER, NULL, ERROR and ASCII all lowercase to real words and were being reported as
    jargon nobody had explained. A hand-kept exclusion list would grow for ever. A missing word list
    means the filter simply does not fire.
    """
    for path in ("/usr/share/dict/words", "/usr/dict/words"):
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                return {w.strip().lower() for w in fh if len(w.strip()) > 2}
        except OSError:
            continue
    return set()


WORDS = _dictionary()


def is_acronym(token):
    return token.lower() not in WORDS


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
    """(short, long) pairs written as 'Long Form (SF)' or 'SF (Long Form)'."""
    out = {}
    for m in re.finditer(r"([^()]{2,120}?)\s*\(([^()]{2,80}?)\)", text):
        before, inside = m.group(1), m.group(2)
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


def scan(text, is_known):
    """(unexplained, considered). `considered` is every acronym-shaped term the reader had to
    handle, known or not — the denominator for asking whether the audience model is wrong.
    """
    body = prose(text)
    written = pairs(body)
    considered = sorted(t for t in set(ACRONYM.findall(body)) if is_acronym(t))
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
