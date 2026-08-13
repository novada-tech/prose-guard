# prose-guard

Checks a message on its way out — a chat message, a review comment, a commit message, a document —
and hands it back with one problem named. A Claude Code plugin.

```
/plugin marketplace add novada-tech/prose-guard
/plugin install prose-guard@novada
/prose-guard:setup
```

Off until you choose a level. Needs nothing but `python3` — no packages, no virtualenv, no API key
beyond the one Claude Code already has.

## The idea

Most advice about writing well is about *how* to say things. The failure that actually costs a reader
time is *what* you said: a term they do not know, a message that never says why it matters to them, a
phrase they have to decode. Those depend on **who is reading**, which a tool can know and a style guide
cannot.

So the tool's model of the world is audiences, and everything else follows from that.

## Audiences

An audience is a named group of readers, prose describing them, the identifiers that say a message is
going to them, and a vocabulary measured from writing they have already done.

```json
{ "name": "platform-team",
  "who": "Engineers who run our Kubernetes and Terraform. They read incident threads cold.",
  "matches": { "slack_channels": ["C054ZDE533R"], "repos": ["your-org/infra"],
               "paths": ["docs/runbooks/*"] },
  "members": ["alice", "bob", "carol"],
  "inherits": ["engineers"],
  "vocabulary": { "KUBECTL": 6, "GKE": 5 } }
```

`matches` decides when the audience applies, and nothing else does. **Prose is a bad router**: a routing
mistake happens before any check runs, so it corrupts every check downstream. `who` is for the checks to
read.

```
/prose-guard:audiences                     add, inspect, delete — like memory, files on disk
python3 lib/audiences.py list
python3 lib/audiences.py show platform-team
python3 lib/audiences.py accept platform-team GKE
```

Vocabulary is measured by **author breadth, not frequency**: one person's favourite acronym is not
shared knowledge however often they type it. On the corpus this was built against, one acronym appeared
149 times from a single author.

### One message, two audiences

Audiences overlap. When a destination matches more than one, the combination is **one operation per
dimension** — not one operation:

| dimension | combinator | why |
|---|---|---|
| vocabulary | intersection | only what everyone knows is safe to leave unexplained |
| shared context | minimum | assume the least-informed reader |
| reach | maximum | the widest reader decides whether internal links resolve |

Measured on two real audiences — 268 people on a public data-model repository, 20 in a client-services
channel — intersecting them costs 103 of the modellers' 220 terms and leaves 117. It does not collapse,
because both inherit the same baseline and that acts as a floor under the intersection. That is what
makes the mixed case survivable rather than unusable.

There is deliberately **no subset elimination**. Dropping an audience whose members sit inside another
looks like a free simplification and is not sound: measured breadth in the larger group does not imply
every member knows the term, and dropping an audience only ever widens the vocabulary. A test pins it.

### Exact overlap is not computable, and the tool says so

Sources name people differently — a chat export gives display names, a repository gives logins — so
"Sam" and "sam-t" are one person that no comparison here can join. A plain intersection
reports zero shared members while ten people are in both, which is worse than useless. `overlap`
therefore prints a prefix-matched **guess**, labelled as one, and nothing depends on it.

## It advises until it has evidence

Out of the box nothing is measured about *your* readers, so an unrecognised acronym is a guess. It says
so and does not block:

> Possibly unexplained for this reader: GKE. … This is a guess — no audience is configured for this
> destination.

Measure an audience and the same finding becomes evidence, and then it blocks. Enforcement follows
evidence, because a tool that blocks on a guess spends your first day arguing about your own house
words.

### And it stops insisting when it is probably wrong

Severity is decided per message on the **share** of the terms the reader met that are unknown — not a
count, because a long document legitimately carries more terms. Three unknown of twenty is a fixable
oversight; fifteen of twenty is the tool having the wrong reader in mind, and insisting then is worse
than saying so.

The threshold is 1/3, measured: the 90th percentile of the share seen when a message *is* scored against
the audience it was written for, in both directions independently. See
[docs/thresholds.md](docs/thresholds.md), including what the measurement does **not** show.

## Choosing a level

| level | what runs | added per message sent | model calls |
|---|---|---|---|
| `disabled` | nothing | — | 0 |
| `low` | the term check only | +12s | **0** |
| `medium` | plus one advisory judgement call | +19s | 1 |
| `high` | four gating checks instead of that one | +75s | 4–6 |

Five paired sessions per level against an unguarded control in the same run, medians, one fixture and
one model. Read the ordering, not the digits. Two counter-intuitive results:

- **`low` is not the cheap option.** No model call, but holding a message back costs a whole agent turn
  on your own context, which is dearer than the small call `medium` adds.
- **`high` is not known to be better than `medium`.** Both satisfied every concern on every message
  measured — a judge at its ceiling rather than evidence they are equal.

## What counts as sending

[`data/destinations.json`](plugins/prose-guard/data/destinations.json) is the list, as data: which
tools, which field holds the text, and which identifiers reveal the reader. Shipped: chat, GitHub and
GitLab comments and descriptions, documentation pages, issue trackers, **`git commit` and `git tag
-m`**, and prose files inside a git working tree that are not ignored.

That last rule replaces matching on `.md`. What matters is whether someone other than the author will
read the file, and "it gets committed" is a deterministic proxy — so a README is checked and the agent's
scratch notes are not.

Two gaps stated rather than hidden: `git commit` with no `-m` opens an editor and that text never
reaches a tool call, and `--body "$(cat file)"` cannot be read.

### Discovery, because your tools are not mine

```
python3 lib/discover.py
```

Four deterministic local sources: MCP servers configured for Claude Code, outbound CLIs on `PATH`, how
often each appears in your **shell history** — much better evidence than "installed" — and anything that
has already carried long prose past the guard unclaimed. Only command *names* are read from history,
never arguments.

`/prose-guard:setup` then does the part no script can: it names the tools it can actually see, proposes
destinations, and asks you to confirm. Your file at `<config dir>/destinations.json` is read **first**,
so it overrides a shipped entry as well as adding one.

**Passive discovery** covers the tool you install next month. When nothing claims a call carrying long
prose, the hook records its *shape* — `bash: git commit -m`, or `tool: example__post [body]` — with no
model call and **no message text**. Setup reads that and offers to add them.

## The rule

```
python3 lib/install_rule.py --install
```

250 words that apply while a message is being written rather than when it is sent, and the only part of
this that costs nothing per message. It reaches subagents, which an output style does not — both halves
verified.

A plugin cannot ship a rule (a `rules/` directory in a plugin does not load; tested), so this copies the
file. **Copies, not symlinks**: the plugin directory is versioned and replaced on update, so a link into
it breaks the moment you upgrade. The cost is that an upgrade does not refresh it, which is why
`--status` compares the two and says so.

## Checking a draft on demand

```
python3 lib/check_prose.py draft.md --for platform-team
python3 lib/check_prose.py draft.md --who "the ops rota, who did not see the incident" --effort low
```

Same checks and prompts as the hook, defaulting to `high` because a deliberate run can afford what every
message cannot. `/prose-guard:rewrite-for-audience` runs it first and then works outside in.

## Design decisions that cost something to learn

**One problem at a time, not a list.** Running the checks in parallel deadlocked: "explain every term the
reader may not know" adds text, "contains nothing they will not act on" removes it, each undid the other,
and the turn ended with **no message at all** — 0 of 5 sessions, twice. The agent diagnosed it itself:
*"one requires terraform and docker be explained; the other flags that as padding."*

**A pass belongs to the exact text that earned it.** An edit made for a later check sends the earlier ones
round again, which is the only thing that can catch "make this sentence simpler" dropping a fact the
reader needed. Bounded by two attempts per check, six denials per session and twelve model calls, so two
checks that genuinely disagree make a message expensive and then let it go.

**A check that fires on everything carries no information.** The sentence check originally failed 14 of 15
real messages, including ones written with no guidance at all. Rewritten to require naming what the reader
would get wrong: 12 of 15 pass, all three planted defects still caught — and the judge's disagreement with
itself fell from 20–27% to 0–5%. Every check is validated in both directions.

**It denies rather than rewrites**, because a check that rewrites cannot tell you what it disagreed with.

## What it stores, and where

Under `CLAUDE_PLUGIN_DATA` (`~/.claude/plugins/data/prose-guard-novada/`), which survives plugin updates.
Never in the plugin directory, which is replaced.

| file | what |
|---|---|
| `config.json` | effort level, and which baseline to assume when no audience matches |
| `audiences/*.json` | one file per audience: who they are, what they know, who is in them |
| `destinations.json` | your own or overridden destinations |
| `unclaimed-destinations.json` | shapes passive discovery noticed |
| `sessions/` | per-session denial bookkeeping |

`members` holds colleagues' names. Local, and not something to commit or publish.

`PROSE_GUARD_HOME` moves all of it. Outside a plugin install it defaults to
`$XDG_CONFIG_HOME/prose-guard`.

## Tests

```
python3 tests/test_prose_guard.py
```

Standard library only, and **mutation-checked**. Each of these breaks at least one case: union instead of
intersection, max instead of min for shared context, min instead of max for reach, subset elimination
reintroduced, an unresolved audience allowed to block, the share threshold removed, prose files no longer
needing to be tracked, shipped destinations read before the user's, candidate recording writing the text,
the session ledger resetting on send, and the rule symlinked instead of copied.

## Notes for anyone building a similar plugin

Verified on Claude Code 2.1.228 rather than read:

- **`userConfig` works and reaches a hook as `CLAUDE_PLUGIN_OPTION_<KEY>`.** Set it with
  `/plugin configure <plugin>` or `--config KEY=VALUE`; it lands in settings under
  `pluginConfigs.<plugin>.options`. Guessing that shape without the `options` level gets you nothing and
  no error.
- **`CLAUDE_PLUGIN_ROOT` is the marketplace *source* for a directory marketplace and the install *cache*
  for a git one.** A git install copies only the plugin directory, so everything the hook needs must live
  inside it. A sibling path resolves to nothing and the hook fails open in silence.
- **`CLAUDE_PLUGIN_DATA` is exported into the hook environment**, not merely interpolated into the
  command, and it survives updates.
- **A PreToolUse payload carries `cwd`**, which is how a commit message resolves its repository.
- **A plugin cannot ship a rule.**

## Setting up a plugin that needs data it cannot ship

1. **Tier 0 works with nothing**, or nobody adopts it.
2. **Never enforce on data you do not have.** Confidence gates enforcement.
3. **Setup is a skill, not a wizard.** Deciding which terms an audience shares needs judgement an agent
   can propose and a human only has to confirm.
4. **Deterministic extraction, agent judgement, human confirmation** — in that order, each step's output
   inspectable.
5. **Write plain files**, where they can be read, diffed and edited by hand.

## Licence

MIT. See [LICENSE](LICENSE).
