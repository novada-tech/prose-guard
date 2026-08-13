#!/usr/bin/env python3
"""Count acronyms used without ever being expanded. Deterministic, no model involved.

Every other check here is a model and therefore carries the biases we are trying to avoid. This
one is an algorithm: Schwartz & Hearst (PSB 2003), reported at 96% precision and 82% recall on the
Medstract gold standard with no training data. So a number from this cannot be a brevity detector
in disguise.

It detects the weaker of the two failures. "ADC" used with no expansion anywhere is caught here.
"Application Default Credentials (a different auth mechanism)" -- expanded but still not explained
in a way the reader can act on -- is NOT caught. That one needs judgement, which is what the
model-based checks are for. Both matter; only this one is bias-free.

Which terms count as known lives in vocabulary.py.

    python3 lib/jargon.py <file>
    cat draft.md | python3 lib/jargon.py
"""
import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vocabulary import HAVE_MEASURED, needs_explaining  # noqa: E402,F401

FENCE = re.compile(r"```.*?```", re.S)
INLINE = re.compile(r"`[^`]+`")
# A quoted line is someone else's words, so it is not checked. Free to skip: dropping blockquotes
# removed zero detections across 301 real messages, whereas skipping any term that appears in
# backticks anywhere would have silenced 24 of 75 - a third of the true positives.
QUOTE = re.compile(r"^\s*>.*$", re.M)
# acronym-shaped: 2-6 characters, capitals and digits
ACRONYM = re.compile(r"\b([A-Z][A-Z0-9]{1,5})\b")


def _valid_short(s):
    if not (2 <= len(s) <= 10):
        return False
    if len(s.split()) > 2:
        return False
    if not re.search(r"[A-Za-z]", s):
        return False
    return s[0].isalnum()


def _best_long(short, long_candidate):
    """Schwartz-Hearst right-to-left match. Returns the matched long form or None."""
    s = short.lower()
    l = long_candidate.lower()
    si = len(s) - 1
    li = len(l) - 1
    while si >= 0:
        c = s[si]
        if not c.isalnum():
            si -= 1
            continue
        while li >= 0 and l[li] != c:
            li -= 1
        # the first character of the short form must start a word in the long form
        if li < 0:
            return None
        if si == 0 and not (li == 0 or not l[li - 1].isalnum()):
            # keep searching leftwards for a word-initial match
            while li >= 0 and not (l[li] == c and (li == 0 or not l[li - 1].isalnum())):
                li -= 1
            if li < 0:
                return None
        si -= 1
        li -= 1
    return long_candidate[li + 1:].strip() if li + 1 < len(long_candidate) else long_candidate


def extract_pairs(text):
    """Find (short, long) pairs written as 'Long Form (SF)' or 'SF (Long Form)'."""
    pairs = {}
    for m in re.finditer(r"([^()]{2,120}?)\s*\(([^()]{2,80}?)\)", text):
        before, inside = m.group(1), m.group(2)
        # pattern 1: long form outside, short form in parentheses
        if _valid_short(inside):
            words = before.split()
            n = min(len(inside) + 5, len(inside) * 2)
            cand = " ".join(words[-n:]) if words else ""
            got = _best_long(inside, cand) if cand else None
            if got and len(got) >= len(inside) and inside.lower() not in got.lower().split():
                pairs[inside] = got
        # pattern 2: short form outside, long form in parentheses
        tail = before.split()[-1] if before.split() else ""
        if _valid_short(tail) and not _valid_short(inside):
            got = _best_long(tail, inside)
            if got and len(got) >= len(tail):
                pairs[tail] = got
    return pairs


def initials_present(short, text):
    """Also count it as expanded if a phrase whose initials match appears anywhere, e.g.
    'Application Default Credentials' with '(ADC)' never written. Schwartz-Hearst only sees
    parenthetical pairs, and writers often expand in prose instead.

    Every initial has to begin a word of at least three letters. Without that floor a
    one-letter word could stand in for an initial, so "we ran a docker container" counted ADC
    as explained and the check passed a message that never explained it. The floor removed no
    detection across 351 real messages, where every genuine expansion is three content words.
    """
    letters = [c for c in short.lower() if c.isalpha()]
    if len(letters) < 2:
        return False
    pat = r"\b" + r"\s+".join(re.escape(c) + r"[a-z]{2,}" for c in letters) + r"\b"
    return re.search(pat, text, re.I) is not None


def unexplained(text):
    prose = INLINE.sub(" ", QUOTE.sub(" ", FENCE.sub(" ", text)))
    pairs = extract_pairs(prose)
    used = ACRONYM.findall(prose)
    bad = sorted({a for a in used
                  if needs_explaining(a) and a not in pairs and not initials_present(a, prose)})
    return bad, pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if not a.files and not a.all:
        # no arguments: read the text from stdin, so a draft can be piped straight in
        text = sys.stdin.read()
        if not text.strip():
            ap.print_help()
            return
        bad, pairs = unexplained(text)
        if bad:
            print("used without explanation: " + ", ".join(bad))
        else:
            print("no unexplained terms")
        if pairs:
            print("explained in the text: " + ", ".join(pairs))
        return

    files = a.files or sorted(glob.glob("grid_out/*.txt"))
    for f in files:
        if "__canary" in f:
            continue
        bad, pairs = unexplained(open(f).read())
        print(f"{os.path.basename(f):48s} unexplained={len(bad):2d}  {','.join(bad[:6])}"
              + (f"   [expanded: {','.join(pairs)}]" if pairs else ""))


if __name__ == "__main__":
    main()
