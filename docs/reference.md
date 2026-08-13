# Reference

Detail that would get in the way of [the README](../README.md). Read it when you
need it.

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

## One message, two audiences

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

## Managing audiences

```
python3 lib/audiences.py list
python3 lib/audiences.py show platform-team
python3 lib/audiences.py accept platform-team GKE      # one term is wrong; applies immediately
python3 lib/audiences.py match platform-team channel C054ZDE533R   # change when it applies
python3 lib/audiences.py rm platform-team
```

Files on disk, one per audience. Read them, diff them, edit them.

What an audience *knows* comes from scanning writing those people already did, from any source you can
pipe — [sources.md](sources.md) has the contract and recipes for chat, mail and wikis. What an audience
*applies to* is the separate list of identifiers `match` edits. Confusing the two is easy, and the
flags are named to make it harder.

`engineers` is a shipped baseline: 96 acronyms any developer knows, with no identifiers of its own, so
it never applies alone — audiences inherit it. That is where the tool's bias lives, and it is
deliberate. Other baselines are welcome as data files beside it.

## Where everything lives

`$XDG_CONFIG_HOME/prose-guard`, or `~/.config/prose-guard`. Move it with `PROSE_GUARD_HOME`.

| file | what |
|---|---|
| `config.json` | effort level, and which baseline to assume when no audience matches |
| `audiences/*.json` | one per audience: who they are, what they know, who is in them |
| `destinations.json` | your own or overridden destinations, read before the shipped ones |
| `unclaimed-destinations.json` | shapes passive discovery noticed, and what you decided |
| `sessions/` | per-session bookkeeping |

One directory, so the hook and the skills cannot disagree about where your settings are — an earlier
version had them reading two different places, and setup reported success while the guard stayed off.

`audiences/*.json` holds colleagues' names. Local, and not something to commit or publish.

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
