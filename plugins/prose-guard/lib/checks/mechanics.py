"""Errors you can find without understanding the sentence. Deterministic, instant, no model call.

Two rules, and only two. Both are objective, both are a one-word fix, and neither needs to know what the
text is about: a word typed twice, and `a` where `an` belongs.

Absolute, not comparative — which is the property that matters here. The model-based checks each report
the WORST instance of their concern in what they were shown, so the amount of text changes the verdict.
These rules report every instance, and a doubled word is wrong whatever surrounds it, so the size of the
input is irrelevant to them.

A missing space between sentences looks like it belongs here and does not. Tightened to a real sentence
boundary — lowercase, full stop, capital, lowercase — it hit 21 times in 3,000 real messages, and every
hit was machine text: GitHub notification footers, a Java import path, a filename with dots. Telling a
person's missing space from `Trade.Message` needs to know which side is a word and which is an
identifier, and in real traffic only the identifiers turn up.

Four more were tried and dropped, measured on 3,000 real messages: space before punctuation (1,131
hits, nearly all a line break before a full stop), stray punctuation (592), no space after punctuation
(512, mostly URLs and version numbers) and unbalanced brackets (498, mostly brackets spanning lines).
Together they flagged a third of every message written. A check that fires on a third of good prose
teaches people to ignore it.

A third-party grammar checker was measured rather than assumed. LanguageTool 6.6, run locally so nothing
left the machine: 240MB to download, 390MB unpacked, needs Java, 1.6 seconds a run. It found **nothing**
on the fragment that prompted all this, and nothing on "Which was the right call in the end." or "The
payload rebuilt before the API can serve it again." or "Their going to check the logs later." What it did
catch was word repeats and a-vs-an, which are the two rules below, plus subject-verb agreement, which is
one rule more. On prose already judged well built it flagged four documents of six, mostly its spell
checker firing on technical terms — the exact noise the measured audience vocabulary exists to prevent.

What is deliberately NOT here is grammar in general. The sentence that prompted this was a fragment
with no main verb, and it needs the sentence understood, not pattern-matched. Asked about that
sentence on its own, the existing checks find it: `structure` in three runs of three and `sentence` in
two of three, all pointing at the same sentence. It got through because it was one sentence inside 370
words — so this adds no sixth model call to re-find what two checks already find. Splitting the document
to sharpen those checks was measured and dropped; see docs/reference.md.
"""
import re

NAME = "mechanics"
COSTS_A_CALL = False

# Same line and same case. Across a line break, "Meeting\n\nMeeting" is two headings, and "labels
# Labels" is a heading followed by its text — both were false positives before this narrowed.
DOUBLED = re.compile(r"\b(\w+)[ \t]+\1\b")
# One space, and the following word lowercase: "an   through" and "A and" were broken formatting rather
# than article errors. All-caps is excluded because the rule is about pronunciation and not spelling —
# "an FpML" is correct, and so is "a UPI".
NEEDS_AN = re.compile(r"\ba ([aeiou][a-z]{2,})\b")
# No h in that class, so the rule says nothing about a word beginning with one. Deliberate: "an hour",
# "an heir" and "an honest answer" are correct, and so are "an historic" and "an herb" for plenty of
# writers, which is a judgement about pronunciation this rule cannot make. A SILENT_H exclusion list
# used to sit here for a case that could never reach it.
NEEDS_A = re.compile(r"\ban ([bcdfgjklmnpqrstvwxyz][a-z]{2,})\b")
# Vowel letter, consonant sound.
SOUNDS_LIKE_YOU = ("one", "uni", "una", "use", "usu", "uti", "eu", "ubi", "ufo", "ewe")
# A word that cannot follow an article at all means the text is broken somewhere else, and there is
# nothing useful to say about the article.
FUNCTION_WORDS = ("and", "the", "in", "on", "of", "to", "for", "with", "through", "or", "is", "are",
                  "as", "at", "if", "it", "an", "a", "that", "this", "but", "not", "no")
# A word doubled deliberately: "had had" is correct, and a table row repeats a heading.
DOUBLED_ON_PURPOSE = ("that", "had", "long")


# What a strip leaves behind. Not a space: DOUBLED matches two identical words separated by spaces and
# tabs, so stripping a span between them made them adjacent and invented a doubled word. That held back
# two reviewers' own issue posts — "in `2`, `3` and `4` and deliberately absent", and three channel
# names in backticks with "versus" abbreviated between them — and a held turn is the most expensive
# thing this tool does. Not a placeholder word either, because two spans in a row would double that
# word instead. GAP has no word characters in it and both rules below need one on each side of it, so a
# strip can now only ever remove a finding, never invent one.
GAP = " -- "


def prose(text):
    """The text minus what is not prose. A doubled identifier in code is not a typo."""
    text = re.sub(r"```.*?```", GAP, text, flags=re.S)
    text = re.sub(r"`[^`]*`", GAP, text)
    text = re.sub(r"^\s{4,}.*$", GAP, text, flags=re.M)        # indented blocks
    text = re.sub(r"^\s*\|.*$", GAP, text, flags=re.M)         # table rows repeat headings
    text = re.sub(r"https?://\S+", GAP, text)
    return text


def scan(text):
    body = prose(text)
    out = []
    for m in DOUBLED.finditer(body):
        if m.group(1).lower() not in DOUBLED_ON_PURPOSE:
            out.append(f'"{m.group(0)}" — a word typed twice')
    for m in NEEDS_AN.finditer(body):
        if m.group(1) not in FUNCTION_WORDS and not m.group(1).startswith(SOUNDS_LIKE_YOU):
            out.append(f'"{m.group(0)}" wants "an"')
    for m in NEEDS_A.finditer(body):
        if m.group(1) not in FUNCTION_WORDS:
            out.append(f'"{m.group(0)}" wants "a"')
    return out


def run(text, ctx):
    from . import BLOCK, Finding
    found = scan(text)
    if not found:
        return None
    # Held back rather than mentioned: each of these is objective and is a one-word fix, and on prose
    # already judged well built the rules found nothing at all. 64 findings across 3,000 real messages,
    # which is 2% — low enough that a finding means something.
    return Finding(BLOCK, "; ".join(found[:4])
                   + (f"; and {len(found) - 4} more" if len(found) > 4 else ""))
