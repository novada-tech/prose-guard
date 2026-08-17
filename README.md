# prose-guard

You have read a review comment from an agent that nobody could digest: technically right, three
clauses deep, and impossible to act on. You have seen a Slack message with six bolded section labels
over four lines of content. You have been told a deploy is fixed in a paragraph that never says what
you now have to run.

Nothing about those messages is badly written. They fail because they were not written for anybody in
particular.

`prose-guard` is a Claude Code plugin that checks a message on its way out — a chat message, a review
comment, a commit message, a document — against two questions:

**Who is going to read this?**
**Why should they care?**

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
act on. At `medium` those five concerns are asked as one combined question, and that only ever advises —
measured against a real label it agrees 50–70% of the time and disagrees with itself between runs, which
is a prompt to look again rather than something to gate on.

The sixth, the one about the opening, advises at every level and says so in its own filename. It passes
11 of 14 well-built messages where the blocking checks pass 9 or 10 of 10, and the gap is not worth
closing by tuning against the handful of fixtures long enough to measure it on. The scores and what
would settle it are in [CONTRIBUTING.md](CONTRIBUTING.md).

**Under 25 words nothing is checked at all.** A short message is not the failure this catches, and it is
not worth a model call — so a one-line commit message is the wrong thing to test it with.

Everything below is those two questions, made checkable.

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

That is also why `medium`'s combined judgement call only ever advises. Asked to sort real messages by
whether a colleague or an agent wrote them, it manages 50–70%, unstably. Useful as a prompt to look
again. Not something to gate on. `high` asks the same concerns one at a time and each answer quotes the
span it means, which is specific enough to hold a message for.

## Setting it up

```
/plugin marketplace add novada-tech/prose-guard
/plugin install prose-guard@novada
```

Then two skills. Both are conversations, and each is worth five minutes.

```
/prose-guard:setup
```

Required: nothing runs until a level is set, and this is where you set one. It does three things.

- Asks which level you want, and writes your answer.
- Offers to install the writing rule.
- Reads what is on your machine and proposes what should count as sending, rather than assuming.

```
/prose-guard:audiences
```

Optional. Run it and unexplained terms start being held back; skip it and they are reported as a guess,
because the tool knows nothing about your readers yet.

It reads writing those readers have already done and counts how many of them used each term. Four
different people writing a term makes it shared. It asks you about the ones that reached three, since
that is the only place counting cannot decide. Nothing leaves your machine.

Restart Claude Code afterwards. Hooks and rules load at startup.

Needs `python3` and nothing else — no packages, no virtualenv, no API key beyond the one Claude Code
already has.

### Which level

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

The figures above are per message sent, and what a slow message costs is the check with the most to say
rather than the sum of all of them. On a real pull request review before this change: 39 guarded calls,
median 50.3s, 217.7s for a 925-word summary comment, and 34.5 minutes of a 168-minute session spent
waiting on the guard.

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
