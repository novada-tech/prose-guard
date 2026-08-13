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

From these two central questions of effective communication, six checks follow, and they are what actually runs. The first is arithmetic and can
hold a message back; the other five are judgement and only ever advise.

| | |
|---|---|
| **Terms they do not know** | an acronym never explained, judged against what your audience has actually written. Deterministic, and the only check that can hold a message back. |
| **No reason to care** | it never says what changed for them or why it matters. |
| **Missing what they need** | the command to run, the version, the deadline, the choice — absent. |
| **Things they will not act on** | backstory they lived through, identifiers nobody types, reassurance nobody asked for, proof that you tested it. |
| **A paragraph doing two jobs** | two unrelated ideas in one, or an opening sentence that does not state its own. |
| **Something they have to decode** | a coined label like "the silent row", a pronoun whose subject is four sentences back, the thing they must do buried under a subordinate clause. |

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

That is also why the five judgement checks only ever advise. Asked to sort real messages by whether a
colleague or an agent wrote them, they manage 50–70%, unstably. Useful as a prompt to look again. Not
something to gate on.

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
| `low` | the term check only, no model call | +12s |
| `medium` | plus one advisory judgement call | +19s |
| `high` | four separate checks, re-verified after each edit | +75s |

**Pick `medium`.** `/prose-guard:setup` asks and writes the answer for you. Two measured results make
that choice less obvious than it looks:

- **`low` is not the cheap option.** It spends no model call, but holding a message back costs a whole
  agent turn on your own context — dearer than the small call `medium` adds.
- **`high` is not known to be better.** Both satisfied every concern on every message measured, so the
  measurement could not tell them apart — which is not the same as their being equal.

Those figures come from five paired sessions per level on one task, with `claude-sonnet-5` writing the
message. Read the ordering rather than the digits: your own traffic and your own model will move them.

## Reading further

| | |
|---|---|
| [docs/reference.md](docs/reference.md) | what counts as sending, managing audiences, where files live, checking a draft by hand |
| [docs/design-notes.md](docs/design-notes.md) | what was measured, and the two ideas that did not survive it |
| [docs/thresholds.md](docs/thresholds.md) | the two numbers that decide whether a message is held back |
| [CONTRIBUTING.md](CONTRIBUTING.md) | how to test and measure a change |
| [measure/](measure/) | the harnesses that do the measuring |

## Licence

Apache 2.0, copyright NovAda BV. See [LICENSE](LICENSE).
