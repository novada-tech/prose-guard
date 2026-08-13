---
name: audiences
description: Add, inspect or delete an audience for prose-guard — a named group of readers with a measured vocabulary. Use when the user asks about audiences, wants prose-guard to learn who reads a channel or repository, asks to stop flagging their house vocabulary, or asks why a term everybody knows is being flagged.
---

# Audiences

An audience is a named group of readers, prose describing them, the identifiers that say a message
is going to them, and a vocabulary measured from writing they have already done.

Everything lives in one JSON file per audience under `<config dir>/audiences/`. Read them, diff
them, edit them by hand — there is no hidden state, and every command below just reads or writes
those files.

## Inspect

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/audiences.py" list
python3 "${CLAUDE_PLUGIN_ROOT}/lib/audiences.py" show <name>
python3 "${CLAUDE_PLUGIN_ROOT}/lib/audiences.py" overlap
```

`show` prints what the audience knows, what it nearly knows, who is in it and where it came from.
`overlap` says which audiences share people, which is worth reading before adding a third that
covers the same team twice.

## One term is wrong

Reach for this before anything else. It applies immediately and needs no re-measuring.

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/audiences.py" accept <audience> <TERM>
```

## Delete

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/audiences.py" rm <name>
```

Built-in baselines cannot be deleted. To change one, write a file of the same name in the user
directory: it replaces the built-in rather than merging with it.

## Add one

This is a conversation, not a form. Do it in this order.

### 1. Ask who, and ask for identifiers

Two different things, and conflating them is the mistake to avoid:

- **Identifiers** decide when the audience applies: Slack channel ids, `owner/repo` slugs, GitHub
  owners, path globs. Routing uses these and only these, because a routing mistake happens before
  any check runs and so corrupts all of them.
- **`who`** is prose describing the people. The checks read it. Routing never does.

If they cannot give an identifier, say so plainly: an audience with none can never apply, and the
tool would be no different with it than without it.

### 2. Ask what to read, and say what each source is worth

- **Issues, pull requests and review comments** (`--gh owner/repo`) — the best source. A review
  comment is written to a colleague, so it uses exactly the vocabulary they share.
- **A chat channel** — as good, and needs a command that exports it. Anything printing one JSON
  object per line, `{"author": ..., "text": ...}`, works: pass it as `--command`. Do not read the
  channel yourself and retype it — a page of a hundred messages costs about 12,000 tokens of your
  context to move text a shell command moves for nothing, and retyping can introduce errors into the
  very corpus being measured. If no export command exists, offer to write one; `docs/sources.md` has
  working recipes for Slack, Teams, Discord and mail. Skip anything recent enough to have been
  written by an agent, or the measurement learns the agent's vocabulary rather than the team's.

If the source needs a credential, do not ask for "a token". Name the kind, the minimum scope, and give
the URL that creates it — someone handed over the token they already had, which authenticated and then
failed on the first read, and they had to go and find the right page themselves. If you do not know
which kind that service uses, say so and find out before asking.
- **Commit messages** (`--git .`) — free and always present, but thin: few people put acronyms in a
  commit subject, so on its own it will under-measure.

### 3. Scan

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/learn.py" scan \
  --gh owner/repo --command './export-chat.sh general' --out /tmp/candidates.json
```

Sources combine, and the counts merge. A failing command is reported rather than silently dropped, so
check the warnings before reading the piles.

It prints three piles: reached the cut of 4 distinct people, exactly one person short, and below.

### 4. Bring them only the middle pile

The first and third piles need no human. One person short of the cut is exactly where counting
cannot decide, which is the whole reason this is a conversation.

Show those terms with their use counts, in one message rather than one at a time, and ask which
everyone in this audience would already understand. Price both mistakes: a term wrongly marked known
means messages go out with it unexplained; a term wrongly left out means being asked to explain
something everybody knows. Being wrong is cheap either way — `accept` fixes one in a second.

If the list is long, offer to take the most-used ones and leave the rest.

**The third pile is not yours to take.** Terms below the borderline mark have one or two people
behind them, which is the least evidence of all — a term one person used is exactly what breadth
exists to exclude. If some of them are obviously shared vocabulary, say which and ask, rather than
folding them in. Say how many there are, because the answer for 3 is different from the answer for
80.

### 5. Create it, then read it back

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/learn.py" create <name> /tmp/candidates.json \
  --who "..." --match-channel C0123 --match-repo owner/repo --also-known TERM1 TERM2
```

The `--match-*` flags say when the audience applies. They are not sources — reading them as "learn
from this channel" is the mistake to avoid. To change them later, without editing the file by hand:

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/audiences.py" match <name> channel C0123
python3 "${CLAUDE_PLUGIN_ROOT}/lib/audiences.py" match <name> repo owner/repo --rm
```

Then `show` it and read the result back to them. Say what changed: unexplained terms for that
audience are now held back rather than reported as a guess.

## When a message reaches two audiences at once

Nothing to configure. If a destination matches two audiences, only what **both** know is treated as
safe, the least-informed reader sets how much context to assume, and the widest reader decides
whether internal links are worth including.

Say the consequence if it comes up: a channel holding two groups with little shared vocabulary will
have most of its terms flagged, and the tool reports that as "the audience is probably wrong"
rather than insisting on explaining all of them.
