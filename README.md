# prose-guard

Checks a message on its way out — a chat message, a review comment, a documentation page, a
document written to disk — and hands it back with one problem named. A Claude Code plugin.

```
/plugin marketplace add novada-tech/prose-guard
/plugin install prose-guard@novada
/prose-guard:setup
```

It is off until `setup` runs, and it needs nothing but `python3`. No packages, no virtualenv, no
API key beyond the one Claude Code already has.

## What it actually catches

Two kinds of thing, and only the first is exact.

**Terms the reader will not know.** Deterministic, no model involved: Schwartz & Hearst (PSB 2003)
expansion detection over acronym-shaped tokens, judged against a vocabulary. `API` and `JSON` pass
out of the box; `ADC` and `GKE` do not.

**What a term check cannot see** — whether the message says why it matters to this reader, whether
anything they need in order to act is missing, whether it carries spans they will never act on,
whether a paragraph is doing two jobs, whether a sentence buries the thing they must do, and
whether a phrase makes them work out what it refers to.

That last one came from a real reviewer stopping at *"The silent row is the one worth
prioritising"* and having to reason back to which row was meant. The check now reproduces his
objection nearly verbatim.

## Choosing a level

| level | what runs | added per message sent | model calls |
|---|---|---|---|
| `disabled` | nothing | — | 0 |
| `low` | the term check only | +12s, +1,500 of your tokens | **0** |
| `medium` | plus one advisory judgement call | +19s, +1,600 of your tokens | 1 |
| `high` | four gating checks instead of that one | +75s, +2,300 of your tokens | 4–6 |

Deltas are against an unguarded control **in the same run**, five paired sessions per level,
medians, on one fixture and one model. Read the ordering rather than the digits.

Two results worth knowing before you choose:

- **`low` is not the cheap option.** It spends no model call, but holding a message back costs a
  whole agent turn on your own context, and that is dearer than the small call `medium` adds.
  `medium` dominates it unless your traffic is already clean.
- **`high` is not known to be better than `medium`.** Scored against all four concerns, every
  message from both levels satisfied all four — a judge at its ceiling, not evidence they are
  equal. `high` exists because separate checks and re-verification are what would show up on
  harder material.

## It advises until it has evidence

Out of the box the tool knows what developers in general know and nothing about the people you
write to, so an unrecognised acronym is a guess. It says so, and does not block:

> Possibly unexplained for this reader: GKE. … This is a guess — nothing has been measured about
> your audience's vocabulary yet.

Measure your audience and the same finding becomes evidence, and then it blocks. Enforcement
follows the evidence rather than the other way round, because a tool that blocks on a guess spends
your first day arguing with you about your own house words.

```
/prose-guard:learn-vocabulary
```

It reads writing your audience has already done — issues, pull requests and review comments via the
`gh` CLI, commit messages, or any prose you can export — counts **how many distinct people** used
each term, and asks you only about the ones sitting one author short of the cut. Nothing leaves your
machine. To silence a single term instead, one line:

```
python3 -c "import sys; sys.path.insert(0,'<plugin>/lib'); import vocabulary; vocabulary.accept('GKE')"
```

**Author breadth, not frequency.** One person's favourite acronym is not shared knowledge however
often they type it — in the corpus this was calibrated on, one term appeared 149 times from a single
author. The cut is 4 distinct people, because a term the team lead said plainly needed explaining
reached exactly 3.

## Where prose counts as leaving

[`data/destinations.json`](plugins/prose-guard/data/destinations.json) is the list, as data rather
than code: which tools, which field carries the text, and what that destination implies about the
reader. Shipped entries cover Slack, GitHub (including `gh pr create --body-file`), Notion,
Airtable and prose files on disk; Linear, Jira and Confluence are stubbed but untested.

Your own file at `<config dir>/destinations.json` is read **first**, so you can override an entry
as well as add one:

```json
{
  "destinations": [
    {"name": "our briefing tool", "tool": ["send_briefing"], "text_fields": ["note"],
     "audience": {"audience": "the operations rota, who did not see the incident"}},
    {"name": "stop checking markdown", "file": "\\.md$", "text_fields": []}
  ],
  "public_owners": ["my-open-source-org"]
}
```

`public_owners` is empty by default and has to be declared, because telling someone a private
repository is public makes them strip links their colleagues could have opened.

## How the audience is worked out

Register turned out to be the wrong axis to model — the team this was built for is blunt to clients
and colleagues alike, and their client-facing channel is *terser* than their engineering one. What
actually varies is three things, all derived from the call itself so they cost nothing and cannot be
wrong about what is happening:

| dimension | decides | derived from |
|---|---|---|
| shared context | whether framing is needed | direct message vs channel, thread reply vs new message |
| reach | whether internal links and shorthand resolve | repository owner, channel visibility, file path |
| vocabulary | which terms need explaining | measured, or unknown |

A fourth — who the readers are by role — cannot be inferred and is declared per destination. When a
destination is not configured at all, the envelope says `audience: unknown` rather than inventing
one, because a check that invented an audience would block on the invention.

## Design decisions that cost something to learn

**One problem at a time, not a list.** Running the checks in parallel deadlocked: "explain every
term the reader may not know" adds text, "contains nothing they will not act on" removes it, each
undid the other, and the turn ended with **no message at all** — 0 of 5 sessions, twice, in two
configurations. The agent diagnosed it itself: *"one requires terraform and docker be explained;
the other flags that as padding."*

**On its way out, not every turn.** The same checks after every assistant turn cost 3.4× the wall
clock of the task without them. Fine for a message posted once; intolerable in a session.

**It denies rather than rewrites**, because a check that rewrites cannot tell you what it disagreed
with.

**A pass belongs to the exact text that earned it.** At `high`, an edit made for a later check
sends the earlier ones round again — the only thing that can catch "make this sentence simpler"
dropping a fact the reader needed. Bounded by two attempts per check, six denials per session and
twelve model calls, so two checks that genuinely disagree make a message expensive and then let it
go.

**A check that fires on everything carries no information.** The sentence check originally failed 14
of 15 real messages, including ones written with no guidance at all. Rewritten to require naming
what the reader would get wrong: 12 of 15 pass, all three planted defects still caught. The same
rewrite took the judge's disagreement with itself from 20–27% down to 0–5%. Every check here is
validated in both directions — it catches planted defects **and** passes ordinary prose — and
`tests/` pins that.

**The judgement checks are advisory, deliberately.** Measured against a provenance-based label they
agree 50–70% of the time, and unstably: the same condition scored 5/10 then 7/10 on the same ten
texts. Only the deterministic check ever blocks.

## The rule

[`rule/engineer-communication.md`](rule/engineer-communication.md) is 246 words of disposition that
does the work no hook can: it applies while the message is being written rather than when it is
sent. Plugins cannot ship rules — I tested it, a `rules/` directory in a plugin does not load — so
install it by hand if you want it:

```
ln -s "$PWD/rule/engineer-communication.md" ~/.claude/rules/engineer-communication.md
```

It reaches subagents, which an output style does not. Both halves verified: an ordinary subagent
quoted the rule verbatim, and a built-in `Explore` subagent reported seeing none.

Growing it from 156 to 246 words cost nothing measurable — three nested versions, 18 sessions each,
no difference in unexplained terms, command-block presence, length or long-sentence share. At that
sample size that rules out a large regression, not a small one.

## Checking a draft on demand

```
python3 <plugin>/lib/check_prose.py draft.md --audience "the #dev channel, arriving cold"
python3 <plugin>/lib/check_prose.py draft.md --effort low     # no model call
```

Same checks, same order, same prompts as the hook. It defaults to `high` whatever the hook is set
to, because a deliberate one-off run can afford what every outgoing message cannot. There is also a
`/prose-guard:rewrite-for-audience` skill that runs it first and then works outside in.

## Tests

```
python3 tests/test_prose_guard.py
```

Standard library only, and **mutation-checked** rather than trusted on a green run. Each of these
breaks at least one case: blocking on an unmeasured guess, reading the shipped destinations before
the user's, moving the author cut from 4 to 3, resetting the session ledger when a message goes out,
falling back to a state directory inside the plugin, and ignoring `known-terms.txt`.

## Setting up a plugin that needs data it cannot ship

The pattern here generalises, and it is the interesting part of the design:

1. **Tier 0 works with nothing.** Ship something useful that needs no setup, or nobody adopts it.
2. **Never enforce on data you do not have.** Confidence gates enforcement, not the other way round.
3. **Setup is a skill, not a wizard.** Deciding which terms an audience shares needs judgement, and
   an agent with repository access can propose answers a user only has to confirm. A shell script
   cannot.
4. **Deterministic extraction, agent judgement, human confirmation** — in that order, each step's
   output inspectable.
5. **Write plain files.** Everything lands where the user can read, diff and hand-edit it.

## Licence

MIT. See [LICENSE](LICENSE).

### One divergence from the measured text

The rule's closing line originally named two skills from the repository it grew in. Here it says
"read whatever conventions your team keeps for it" instead, since pointing at skills that do not
exist would be worse than a generic sentence. Same length, same shape, but it is the one sentence
the A/B above did not test in this wording.
