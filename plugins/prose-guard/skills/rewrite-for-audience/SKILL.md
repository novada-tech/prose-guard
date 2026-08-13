---
name: rewrite-for-audience
description: Rewrite a specific piece of text so a named audience can act on it after one read. Use when asked to rewrite, tighten, clarify or "make this land better" for a particular reader — a Slack message, a PR description, a design note, a status update. Invoke it deliberately on text you already have; the engineer-communication rule covers writing from scratch.
---

# Rewriting a piece of text for its reader

## Run the checks first, before you read any further

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/check_prose.py" <file> --for <audience>
python3 "${CLAUDE_PLUGIN_ROOT}/lib/check_prose.py" <file> --who "who reads this, in your own words"
```

These are the same checks prose-guard runs on a message you send, so what it
says here is what the hook would say. It runs the most thorough level whatever the hook is set
to, because this is one deliberate run rather than every message someone sends: the deterministic
term check, then four separate checks for relevance, structure, sentences and reference. Four
model calls of a few seconds each.

The two flags do different jobs. **`--for` sets the vocabulary** — run
`python3 "${CLAUDE_PLUGIN_ROOT}/lib/audiences.py" list` to see what exists. **`--who` describes the
reader in a sentence** for the model-based checks; it cannot change which terms are known, because a
sentence is not a vocabulary.

If no measured audience fits, pass both: `--for engineers` for the terms and `--who` for everything
else. `engineers` is the shipped baseline, and naming it explicitly lets the term check hold a message
back — you asked for that standard rather than the tool guessing at one. Without `--for` nothing is
enforced at all, and the output says so.

Pass `--effort low` if you only want the term check — instant, no model call — or `medium` for one
combined judgement call instead of five.

Do this first because the rest of this file is self-assessment, and self-assessment is the part
that fails: in the one session where this skill was used on real work, the agent applied the
passes below, reported having done so, and had skipped both of the concrete outputs. Running a
command cannot be skipped by accident.

Run it again on the rewrite. The check is on the current wording, not on the draft you started from.

Then stop. Every finding is put back to the same check and kept only if it objects to the same sentence,
so what you are shown reproduces — but findings printed under "raised once and not reproduced" are nits,
and they are endless. Measured: on one document already through six rounds, ten runs produced nine
findings and not one of them twice. Two passes is normally the whole job. If a third pass is still
finding things you agree with, the text has a real problem; if it is finding different things each time,
it is finished.

## What you hand back

Two things, both of them, every time:

1. **The rewrite.**
2. **A change note** — one line per change, naming the concern it came from. This is what lets
   the person disagree with a specific edit instead of the whole rewrite, and it is the output
   most likely to go missing.

## Then name the reader

Before changing a word, say who reads this and what they already know. Everything below depends
on it, and the answer differs: an engineer on this team, a client, a public repository outsiders read. If the
person asking has not said, ask them — a rewrite aimed at the wrong reader is worse than the
original, because it looks finished.

## Then work outside in, in this order

The order matters. Each pass can create work for the ones after it and never for the ones
before, so going inside out means redoing your own edits.

**1. What belongs here at all.** Does the text say why this matters to the reader, or what
changes for them? Is anything they need in order to act missing? Then cut what they will not
act on: backstory they lived through, internal identifiers nobody types, reassurance nobody
asked for, and proof that the work was tested. That last one is the most common and the hardest
to see in your own writing.

**2. What order it goes in.** One idea per paragraph, and each paragraph's idea in its first
sentence. No paragraph should depend on something stated only later.

**3. One idea per sentence.** The test is mechanical: if a sentence could be split in two with
nothing lost, split it. A fact the reader needs must not sit in a parenthesis or a trailing
"which" clause. Length itself is not the problem — a long plain sentence reads easily where a
short crowded one does not, and fragments, dropped articles and telegraphic phrasing are worse
than either.

**4. Words.** Plainer wherever it carries the same meaning exactly, and no plainer than that.
Never trade precision for brevity: the exact technical term beats a simpler word that is close.

**5. Terms the reader may not know.** Explain each one where it first appears, by anchoring it
to something they already work with. Expanding an acronym is not explaining it — an expansion
with no familiar reference still leaves them stuck.

Do not silently drop a fact to make the text shorter. If you think something should go and you
are not sure, leave it in and say so in the note.

## One thing the mechanical check gets wrong

It flags acronym-shaped tokens, so a code identifier written in prose can trip it — `LOGGER` in
a sentence about a logging call is a field name, not jargon. Capitalised English words and
common constants are filtered out, but if a flag looks like a symbol from the code rather than a
term the reader must understand, say so and move on rather than explaining it.
