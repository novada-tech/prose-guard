# prose-guard

You have read a review comment from an agent that nobody could digest: technically right, three
clauses deep, and impossible to act on. You have seen a Slack message with six bolded section labels
over four lines of content. You have been told a deploy is fixed in a paragraph that never says what
you now have to run.

Nothing about those messages is badly written. They fail because they were not written for anybody in
particular.

prose-guard is a Claude Code plugin that checks a message on its way out — a chat message, a review
comment, a commit message, a document — against two questions:

**Who is going to read this, and what do they already know?**
**Why should they care?**

Everything below is those two questions, made checkable.

## Question one is answered from data, not judgement

An acronym is not hard or easy in the abstract. `ADC` is obvious to the person who set up your
authentication and opaque to everyone else, and no style guide can tell them apart. So the tool
measures it: for a group of readers, how many distinct people have actually used a term in writing?

That is an **audience** — a name, the identifiers that say a message is going to them, and a
vocabulary counted from writing they have already done.

```json
{ "name": "platform-team",
  "who": "Engineers who run our Kubernetes and Terraform. They read incident threads cold.",
  "matches": { "slack_channels": ["C054ZDE533R"], "repos": ["your-org/infra"] },
  "vocabulary": { "KUBECTL": 6, "GKE": 5 } }
```

**Breadth, not frequency.** One person's favourite acronym is not shared knowledge however often they
type it: in the corpus this was built against, one acronym appeared 149 times from a single author.
Four distinct people is the cut.

Under every audience sits a **baseline** — a shipped vocabulary it inherits. `engineers` is the one
that ships: 104 acronyms any developer knows, so nobody starts from zero and nobody has to teach it
what `JSON` is.

Send to that channel and the guard knows `GKE` is safe and `SFTR` is not. Send somewhere it has never
heard of and it says so instead of guessing at you.

## Question two is asked of a model, because nothing else can

Whether a message says why it matters, whether it leaves out the thing you need in order to act,
whether a paragraph is doing two jobs, whether a phrase makes you stop and decode it — no algorithm
decides those. One model call does, reading the audience description above so it is judging against
*your* readers rather than a general idea of good writing.

That call only ever advises, and the reason is worth knowing before you trust it. I collected real
messages from before agents existed and real messages written by agents, then asked the check to tell
them apart. It managed 50–70%, and unstably: the same check scored 5/10 and then 7/10 on the same ten
texts. Useful as a prompt to look again. Not something to gate on.

## Setting it up is the product, not the paperwork

Skipping setup leaves you with a tool that knows what developers in general know and nothing about
the people you write to. It will still find unexplained acronyms, but it reports them as a guess and
never holds anything back — because a tool that blocks on a guess spends your first day arguing with
you about your own house vocabulary.

Two commands, and the second one is the one that matters:

```
/plugin marketplace add novada-tech/prose-guard
/plugin install prose-guard@novada
/prose-guard:setup            pick a level, install the rule, confirm what counts as sending
/prose-guard:audiences        teach it who reads what — this is what turns advice into enforcement
```

`audiences` is a conversation. It reads writing your readers have already done — issues and review
comments through the `gh` CLI, a chat export, commit messages — counts how many people used each
term, and asks you only about the ones sitting one person short of the cut. That middle pile is the
only part where counting cannot decide, so it is the only part you are asked about. Nothing leaves
your machine.

Needs `python3` and nothing else. No packages, no virtualenv, no API key beyond the one Claude Code
already has.

### Pick a level

| level | what runs | added per message sent |
|---|---|---|
| `disabled` | nothing | — |
| `low` | the term check only, no model call | +12s |
| `medium` | plus one advisory judgement call | +19s |
| `high` | four separate checks, re-verified after each edit | +75s |

**`medium`.** Two results make that less obvious than it looks, from five paired sessions per level
against an unguarded control in the same run:

- **`low` is not the cheap option.** It spends no model call, but holding a message back costs a whole
  agent turn on your own context — dearer than the small call `medium` adds.
- **`high` is not known to be better.** Both satisfied every concern on every message measured, which
  is a judge at its ceiling rather than evidence they are equal.

One fixture, one model. Read the ordering, not the digits.

## What it does when it disagrees with you

It names one problem and hands the message back. It does not rewrite: a check that rewrites cannot
tell you what it disagreed with.

And it stops insisting when it is probably the one that is wrong. Severity depends on the **share** of
the terms you used that are unknown to your reader, not the count — three unknown out of twenty in a
long document is an oversight worth fixing, fifteen out of twenty means the tool has the wrong reader
in mind. Above a third it says so instead of demanding twenty explanations. That threshold is the 90th
percentile of the share seen when a message *is* scored against the audience it was written for,
measured both directions on 3,170 real messages: [docs/thresholds.md](docs/thresholds.md), including
what the measurement fails to show.

Three limits keep that bounded. Each check gets two attempts. A session gets six holds in total, and
twelve model calls. Past those, everything turns advisory — so two checks that genuinely disagree make
one message expensive and then let it through, rather than hanging your turn.

## What counts as sending

Chat, GitHub and GitLab comments and descriptions, documentation pages, issue trackers, **`git commit`
and `git tag -m`**, and prose files inside a git working tree that are not ignored.

That last rule replaces matching on `.md`. What matters is whether somebody other than you will read
the file, and "it gets committed" is a deterministic proxy — so your README is checked and your scratch
notes are not.

Two gaps, stated rather than hidden: `git commit` with no `-m` opens an editor and that text never
reaches a tool call, and `--body "$(cat file)"` cannot be read.

**Your tools are not mine**, so setup asks rather than assumes. `lib/discover.py` reads four local
sources — MCP servers you have configured, outbound command-line tools on your `PATH`, how often each
appears in your **shell history** (much better evidence than "installed"), and anything that has
already gone out unchecked. Then the agent names the tools it can actually see, proposes destinations,
and waits for you.

You will install something new next month, and the guard notices on its own: when nothing claims a
call carrying long prose it records the *shape* — `bash: git commit -m`, `tool: example__post [body]` —
never the text. It mentions it **once**, on about the third use, and never again. Decline and it is
declined for good.

## The rule

```
python3 lib/install_rule.py --install
```

250 words that apply while a message is being written rather than when it is sent, and the only part
of this that costs nothing per message. It reaches subagents, which an output style does not — both
halves verified.

A plugin cannot ship a rule, so this copies the file. **Copies, not symlinks**: the plugin directory
is versioned and replaced on update, so a link into it breaks the moment you upgrade. The cost is that
upgrading does not refresh it, which is why `--status` compares the two.

## Checking something before you send it

```
python3 lib/check_prose.py draft.md --for platform-team
python3 lib/check_prose.py draft.md --who "the ops rota, who did not see the incident" --effort low
```

Same checks and prompts as the hook, defaulting to `high` because one deliberate run can afford what
every message cannot. `/prose-guard:rewrite-for-audience` runs it first and then works outside in.

---

## Reference

### One message, two audiences

Audiences overlap, and a channel can hold two of them. Combining is one operation per dimension:

| dimension | combinator | why |
|---|---|---|
| vocabulary | intersection | only what everyone knows is safe to leave unexplained |
| shared context | minimum | assume the least-informed reader |
| reach | maximum | the widest reader decides whether internal links resolve |

Measured on two real audiences — 268 people on a public data-model repository, 20 in a client-services
channel — intersecting costs 103 of the modellers' 220 terms and leaves 117. It does not collapse,
because both inherit the same baseline and that floors the intersection.

There is deliberately **no subset elimination**. Dropping an audience whose members sit inside another
looks like a free simplification and is not sound: breadth measured in the larger group does not imply
every member knows the term, and dropping an audience only ever widens the vocabulary. A test pins it.

Exact overlap between audiences is **not computable**, and the tool says so rather than pretending. A
chat export names someone "Sam"; a repository names the same person "sam-t". A plain
intersection reported zero shared members while ten people were in both, so `overlap` prints a
prefix-matched guess, labelled as one, and nothing depends on it.

### Managing audiences

```
python3 lib/audiences.py list
python3 lib/audiences.py show platform-team
python3 lib/audiences.py accept platform-team GKE      # one term is wrong; applies immediately
python3 lib/audiences.py rm platform-team
```

Files on disk, one per audience. Read them, diff them, edit them.

`engineers` is a shipped baseline: 96 acronyms any developer knows, with no identifiers of its own, so
it never applies alone — audiences inherit it. That is where the tool's bias lives, and it is
deliberate. Other baselines are welcome as data files beside it.

### Where everything lives

`$XDG_CONFIG_HOME/prose-guard`, or `~/.config/prose-guard`. Move it with `PROSE_GUARD_HOME`.

| file | what |
|---|---|
| `config.json` | effort level, and which baseline to assume when no audience matches |
| `audiences/*.json` | one per audience: who they are, what they know, who is in them |
| `destinations.json` | your own or overridden destinations, read before the shipped ones |
| `unclaimed-destinations.json` | shapes passive discovery noticed, and what you decided |
| `sessions/` | per-session bookkeeping |

Not `CLAUDE_PLUGIN_DATA`, though that is the blessed per-plugin directory: it reaches a hook's
environment but not a skill's shell, so using it gave a config that setup wrote to one place and the
guard read from another. Setup looked like it worked and the guard stayed off.

`audiences/*.json` holds colleagues' names. Local, and not something to commit or publish.

### Why it behaves the way it does

**One problem at a time, not a list.** Running the checks in parallel deadlocked — one wanted every
term explained, another counted those explanations as padding, and the turn ended with no message at
all. So a check names one problem and the next one waits its turn.

**A pass belongs to the exact text that earned it.** Edit a message for one check and the earlier ones
look again. That is the only thing that catches "make this sentence simpler" dropping a fact the reader
needed.

**A check that fires on everything carries no information**, so every check here had to prove it passes
ordinary prose as well as catching a planted defect. One of them originally failed almost every real
message it saw, including messages written with no guidance at all.

The numbers behind each of these, and the two that did not survive contact, are in
[docs/design-notes.md](docs/design-notes.md).

### Tests

```
python3 tests/test_prose_guard.py
```

Standard library only, so it runs anywhere `python3` does. Every case pins a design decision rather
than an implementation detail, and each one was checked by breaking the thing it protects — the list of
what was broken is in [docs/design-notes.md](docs/design-notes.md).

### Notes for anyone building a similar plugin

Verified on Claude Code 2.1.228 rather than read:

- **`userConfig` works and reaches a hook as `CLAUDE_PLUGIN_OPTION_<KEY>`.** Set it with
  `/plugin configure <plugin>` or `--config KEY=VALUE`; it lands in settings under
  `pluginConfigs.<plugin>.options`. Guessing that shape without the `options` level gets you nothing
  and no error.
- **`CLAUDE_PLUGIN_ROOT` is the marketplace *source* for a directory marketplace and the install
  *cache* for a git one.** A git install copies only the plugin directory, so everything a hook needs
  must live inside it. A sibling path resolves to nothing and the hook fails open in silence.
- **A PreToolUse payload carries `cwd`**, which is how a commit message resolves its repository.
- **A plugin cannot ship a rule.** A `rules/` directory in a plugin does not load.

### If you are building something that needs data it cannot ship

1. **Tier 0 works with nothing**, or nobody adopts it.
2. **Never enforce on data you do not have.** Confidence gates enforcement.
3. **Setup is a skill, not a wizard.** Deciding which terms a group shares needs judgement an agent
   can propose and a person only has to confirm.
4. **Deterministic extraction, agent judgement, human confirmation** — in that order, each step's
   output inspectable.
5. **Write plain files**, where they can be read, diffed and edited by hand.

## Licence

MIT. See [LICENSE](LICENSE).
