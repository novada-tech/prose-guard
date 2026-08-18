---
name: feedback
description: Show what prose-guard objected to before a message went out — every draft it held back, which check held it, and what finally went. Use when the user asks why a message was rewritten, what the guard said, whether a complaint was fair, to see the drafts, or to clear that history.
---

# What the guard argued about

A held message is an exchange the person never sees: the guard objects, the agent rewrites, and only
the last version reaches anybody — so a fair complaint and an unfair one look identical afterwards.
This is how they read that exchange back.

## Show them what happened

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/rounds.py" list
```

Newest first, one line each: when, where it was going, how many rewrites, which check held it.

Then the one they mean:

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/rounds.py" show 1
```

Every draft in full, what each was held for, the text that finally went out — and above all of it,
**what the checks were told before they read a word**: which level actually ran and whether the
destination capped it, which audience applied and whether one applied at all, what the destination said
the moment was, which checks ran, and what it cost.

Read the envelope first. "Why did it say that" is almost never answered by the finding:

- **`capped from high`** — the destination is worth less than the level they set, so most checks never
  ran. That is the answer to "why did it not catch X", and it is configuration rather than a defect.
- **`guessing`** — no audience matched, so nothing could be held back on terms at all. If they are
  asking why a message went out unchallenged, this is usually why, and `/prose-guard:audiences` is the
  fix.
- **`judged for <name>`** — a measured audience applied. A term flagged here was flagged because those
  particular people have not been seen writing it, which is a claim they can disagree with.
- **the destination line** — what the model-backed checks were told the moment was. If a complaint
  reads as though the check misunderstood the situation, this is where to look.

**Read it back to them rather than pasting it.** They asked because they want to judge something, and
the something is almost always one of three questions. Answer the one they asked:

- **"Why was this rewritten?"** — name the check and quote the span it objected to. One sentence.
- **"Was that fair?"** — say what changed between the last held draft and what went out, and whether
  the change addressed the complaint or worked around it. If the fix was to delete the term rather than
  explain it, say so; that is the tool being satisfied rather than the message being improved.
- **"Is it firing on the wrong thing?"** — if the same check holds messages for the same term more than
  once, that is not a message problem, it is a vocabulary problem. Point at `/prose-guard:audiences`,
  which is the lasting fix, and offer to run it.

That last answer only covers terms. A judgement check that objected to prose which was fine, or let
through a message its reader could not act on, is a defect in the check rather than in this machine's
configuration, and nothing here can fix it. `/prose-guard:contribute` turns what `show` just printed
into a report the people who maintain the checks can run — it decides first whether the fix is
configuration after all, and it will not let a real message out of this machine unreduced.

## If there is nothing to show

Nothing is recorded unless a check actually held a message back. So an empty list means no message has
been refused on this machine — not that the tool is off. If they expected something and there is
nothing, the useful checks are whether a level is set at all, and whether the destination they were
sending to is one the guard claims:

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/checks/config.py"
python3 "${CLAUDE_PLUGIN_ROOT}/lib/destinations.py" list
```

## Clearing it

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/rounds.py" forget
```

Say what it costs before running it: the drafts are the only record of what was objected to, and there
is no other copy. Offer it when they ask to clear it, when they are about to share a screen, or when
they say they are done looking.

## What is kept, and where

Only arguments — a message that passed leaves no trace at all. At most 100 across the whole machine,
oldest dropped as new ones arrive, each draft capped so a long document cannot fill a disk. It lives in
their own config directory beside everything else this tool remembers, never in a repository.

This is the only part of prose-guard that writes message text to disk. If they are surprised by that,
they are right to be: everything else records the shape of a call and never its content. Tell them
`forget` exists and that nothing is written unless something was held back.
