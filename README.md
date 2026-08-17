# prose-guard

A Claude Code plugin that reads what Claude is about to send — a chat message, a review comment, a
commit message, a pull request description, a document — and asks whether the person receiving it could
act on it. Where the answer is objectively no, such as an acronym those readers have never used or a
word typed twice, it holds the message back and names the problem, so Claude fixes the draft before
anybody sees it. On everything softer than that it says what it found and lets the message go.

Two questions decide everything below: **who is going to read this**, and **why should they care**.

## Install

```
/plugin marketplace add novada-tech/prose-guard
/plugin install prose-guard@novada
/prose-guard:setup
```

If the install summary says `Run /reload-plugins to activate`, run that first — otherwise the hooks are
not loaded yet and `/prose-guard:setup` has nothing to configure.

**`/prose-guard:setup` is not optional**: nothing runs until a level is chosen and this is where you
choose one. It takes a few minutes, asks one question at a time, and does three things.

- Asks how much checking you want, with what each level costs. **Pick `medium`.**
- Offers to install the writing rule: 250 words that reach Claude while a message is being written
  rather than when it is sent, and the only part of this that costs nothing per message.
- Reads what is on your machine and proposes which of your tools count as sending prose, rather than
  assuming. Chat, issue trackers and vendor command-line tools go in here.

Skip it and prose-guard says so at the start of every session, because an install that checks nothing
looks exactly like one that has nothing to object to.

Then, when you have a few more minutes:

```
/prose-guard:audiences
```

Optional, and it is what turns advice into enforcement. Until an audience is measured, prose-guard knows
what developers in general know and nothing about the people you write to, so an unexplained term is
reported as a guess and nothing is held back.

Needs `python3` and nothing else — no packages, no virtualenv, no API key beyond the one Claude Code
already has. Nothing leaves your machine.

## Why

Agents write review comments nobody can digest: technically right, three clauses deep, and impossible
to act on. Slack messages carrying six bolded section labels over four lines of content. A paragraph
announcing that a deploy is fixed which never says what anybody now has to run.

Nothing about those messages is badly written. They fail because they were not written for anybody in
particular.

## What it checks

Eight checks follow from those two questions, and they are what actually runs. Two are arithmetic — no
model call, and they run at every level. Six are judgement.

| | | |
|---|---|---|
| **Terms they do not know** | an acronym never explained, judged against what your audience has actually written | arithmetic |
| **A word typed twice, `a` where `an` belongs** | objective, and a one-word fix | arithmetic |
| **No reason to care** | it never says what changed for them or why it matters | judgement |
| **Missing what they need** | the command to run, the version, the deadline, the choice — absent | judgement |
| **Things they will not act on** | backstory they lived through, identifiers nobody types, reassurance nobody asked for, proof that you tested it | judgement |
| **A paragraph doing two jobs** | two unrelated ideas in one, or an opening sentence that does not state its own | judgement |
| **Something they have to decode** | a coined label like "the silent row", a pronoun whose subject is four sentences back, the thing they must do buried under a subordinate clause | judgement |
| **An opening that no longer fits** | the message turns out to be about something the top never mentions, so a reader who acts on the opening alone acts on the wrong thing | judgement, advice only |

**What can hold a message back depends on the level.** The two arithmetic checks always can: both are
objective and both are a small fix. At `high` five of the six judgement checks can too, because each
names one concern and quotes the span it means, and a finding two runs agree on is specific enough to
act on.

At `medium` those five concerns are asked as one combined question, and that only ever advises. Asked to
sort real messages by whether a colleague or an agent wrote them, it gets 50–70% right and disagrees with
itself between runs, which is a prompt to look again rather than something to gate on.

The sixth, the one about the opening, advises at every level and says so in its own filename. It passes
11 of 14 well-built messages where the blocking checks pass 9 or 10 of 10, and the gap is not worth
closing by tuning against the handful of fixtures long enough to measure it on. The scores and what
would settle it are in [CONTRIBUTING.md](CONTRIBUTING.md).

**Under 25 words nothing is checked at all.** A short message is not the failure this catches, and it is
not worth a model call — so a one-line commit message is the wrong thing to test it with.

## How it knows who is reading

An acronym is not hard or easy in the abstract. `ADC` is obvious to whoever set up your authentication
and opaque to everyone else, and no style guide can tell them apart. So the tool measures it. You give
it an **audience** — a name, the channels and repositories that reach those people, and it counts how
many of them have actually used each term in writing they have already done.

```json
{ "name": "platform-team",
  "who": "Engineers who run our Kubernetes and Terraform. They read incident threads cold.",
  "matches": { "channels": ["C054ZDE533R"], "repos": ["your-org/infra"] },
  "vocabulary": { "KUBECTL": 6, "GKE": 5 } }
```

Send to that channel and it knows `GKE` is safe and `SFTR` is not. Send somewhere it has never heard
of and it says so rather than guessing at you: **findings become advice, and nothing is held back**,
because a tool that blocks on a guess spends your first day arguing about your own house vocabulary.

`/prose-guard:audiences` builds one for you. It reads writing those readers have already done and counts
how many of them used each term. Four different people writing a term makes it shared. It asks you about
the ones that reached three, since that is the only place counting cannot decide.

## What you see

One line on every message that goes out, whether or not anything was wrong with it:

```
prose-guard · low · platform-team · clean
prose-guard · high · platform-team · 2 rewrites, 1 note · 7 calls · /prose-guard:feedback
prose-guard · low · no audience · 1 note
```

The fields never move: the level that ran, who it was judged for, what came of it, what it cost, and
where to read the argument back when there was one. **When no such line appears, nothing was checked** —
that is the only thing its absence can mean, and it is how a gap becomes visible without reading a
transcript.

**`no audience`** is what a new install shows in the third position. It means nothing could be held back
on terms, because your reader was assumed rather than measured. `/prose-guard:audiences` is what changes
it.

## Which level

| level | what runs | added per message sent |
|---|---|---|
| `disabled` | nothing | — |
| `low` | the two arithmetic checks only, no model call | +12s |
| `medium` | plus one advisory judgement call over the five concerns | +19s |
| `high` | one separate check per concern, re-verified after each edit | +12s |

`low` and `medium` were measured when `high` ran four model-backed checks one after another, at +75s.
It runs six now, and asks them at the same time: **34.3s to 12.4s** on a 78-word review comment, for the
same six model calls and the same verdict. The checks are independent — each reads the same unmodified
text and none can see another's answer — so only the waiting changed.

The figures above are per message sent, and a slow message costs whatever its slowest check costs rather
than the sum of all of them. On a real pull request review before this change: 39 guarded calls, median
50.3s, 217.7s for a 925-word summary comment, and 34.5 minutes of a 168-minute session spent waiting on
the guard.

**Pick `medium`.** `/prose-guard:setup` asks and writes the answer for you. `low` is not the cheap
option and `high` is not measurably better, which is less obvious than it looks — the numbers, the
unguarded run they were priced against, and what the measurement cannot tell you are in
[docs/design-notes.md](docs/design-notes.md).

## Reading further

| | |
|---|---|
| [docs/reference.md](docs/reference.md) | how it behaves once you are using it: what counts as sending, what the caps do, where files live, checking a draft by hand |
| [docs/design-notes.md](docs/design-notes.md) | what was measured, and the designs that did not survive it |
| [docs/audiences.md](docs/audiences.md) | managing audiences, and sharing one with a team |
| [docs/sources.md](docs/sources.md) | where a vocabulary comes from: the contract, and recipes for chat, mail and wikis |
| [docs/thresholds.md](docs/thresholds.md) | the two numbers that decide whether a message is held back |
| [CONTRIBUTING.md](CONTRIBUTING.md) | how to test and measure a change |
| [measure/](measure/) | the harnesses that do the measuring |

## Licence

Apache 2.0, copyright NovAda BV. See [LICENSE](LICENSE).
