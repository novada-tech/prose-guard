---
name: setup
description: Set up prose-guard — choose how much checking to do, and optionally measure the vocabulary your audience actually shares. Use when the user asks to set up, configure, enable, disable or change prose-guard, or asks why it is or is not checking their messages.
disable-model-invocation: false
---

# Setting up prose-guard

Do this conversationally, one question at a time, and show the user what you wrote. Everything
lands in plain files they can read, diff and hand-edit — there is no hidden state.

## 1. Say what is set now

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/checks/config.py"
python3 "${CLAUDE_PLUGIN_ROOT}/lib/vocabulary.py"
```

The first prints the effort level and where it is stored, the second what vocabulary is loaded and
whether unexplained terms are held back or only reported.

## 2. Ask which level, if they have not said

Give them the trade honestly. The numbers come from five paired sessions on one fixture and one
model, so the ordering is the finding, not the digits:

| level | what runs | added per message sent |
|---|---|---|
| `disabled` | nothing | — |
| `low` | the term check only, no model call | +12s |
| `medium` | plus one advisory judgement call | +19s |
| `high` | four gating checks, each re-verified after any edit | +75s |

Two things worth telling them, because both are counter-intuitive:

- **`low` is not the cheap option.** It spends no model call, but holding a message back costs a
  whole agent turn on their own context, which is dearer than the small call `medium` adds.
- **`high` is not known to be better than `medium`.** Both satisfied every concern on every message
  measured, which is a judge at its ceiling rather than evidence they are equal.

`medium` is the level the evidence supports. Then:

```
python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/lib'); \
from checks import config; print(config.save('medium'))"
```

## 3. Offer to measure their vocabulary, and say what it buys

Until they do, the tool knows what developers in general know and nothing about the people they
write to, so an unrecognised acronym is a guess: it reports it and does not block. Measuring turns
that into evidence, and then it blocks.

Point them at `/prose-guard:learn-vocabulary`. Optional, and worth saying it takes a few minutes.

## 4. Mention the two things they may need to add, then stop

- **A destination it does not know.** `lib/../data/destinations.json` lists what counts as outgoing
  prose. Their own file at `<config dir>/destinations.json` is read first, so they can add or
  override an entry. Offer to write one only if they name a tool that is being missed.
- **Which repository owners are public.** Empty by default, because telling someone a private repo
  is public makes them strip links their colleagues could have opened. It changes what the checks
  say about internal links and shorthand.

Do not walk them through either unless they ask. The tool works without both.

## 5. Say what happens next

Nothing changes until Claude Code restarts, because hooks load at startup.
