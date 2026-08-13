# Contributing

This tool holds people's messages back. A change that makes it wrong wastes their time on every message
they send, and a change that makes it slow gets it switched off. So there is one thing asked of you
beyond the usual: **measure what your change costs and what it catches, and put the numbers in the pull
request.** Every command you need is below and none of them takes long.

If you cannot measure something, say so in the pull request. An unmeasured change with an honest note is
reviewable. An unmeasured change presented as safe is not.

## Bump the version if you change anything under `plugins/`

Nobody's installed copy moves unless the version does. `claude plugin install` is a no-op when the
plugin is already present at any version, and `claude plugin update` only moves on a version change.
Eight commits once shipped under `0.1.0`, and the people who had installed it kept running a skill
documenting a flag that no longer existed.

Bump it in **both** `plugins/prose-guard/.claude-plugin/plugin.json` and
`.claude-plugin/marketplace.json`. Continuous integration fails the pull request if you forget, or if
the two disagree.

## Before you open a pull request

Six steps. The first two always, the rest when they apply.

### 1. The tests must pass

```
python3 tests/test_prose_guard.py
python3 tests/test_docs_match_code.py
```

Standard library only, no setup, about fifteen seconds, and no model calls — continuous integration
runs both on every pull request, on Linux and macOS, and proves the second point by removing `claude`
from `PATH`. The measurement harnesses under `measure/` are deliberately not in CI: they spend real
tokens, so they stay something you run deliberately and report here.

The second suite reads every SKILL.md, finds the commands it tells someone to run, and checks each
against the real interface — a skill documented
`--audience` for a script that takes `--for`, and the person who hit it lost time before anything else
could go wrong. Every case pins a design decision, so a failure
usually means you changed a decision rather than broke an implementation — say which in the pull
request.

### 2. Break your own test before you trust it

A green run proves nothing about a test you just wrote. Change the code your test protects, confirm the
test goes red, then put it back:

```
cp plugins/prose-guard/lib/audiences.py /tmp/backup
# make the mistake your test exists to catch, e.g. union instead of intersection
python3 tests/test_prose_guard.py          # must fail, and name your case
cp /tmp/backup plugins/prose-guard/lib/audiences.py
python3 tests/test_prose_guard.py          # green again
```

Say in the pull request what you broke and which case caught it. The list of mutations already checked
is in [docs/design-notes.md](docs/design-notes.md); add yours to it.

### 3. If you touched a check, measure whether it discriminates

```
python3 measure/measure_check.py --reps 2
python3 measure/measure_check.py --check sentence --reps 2      # just yours
```

A check that fails everything carries no information, and neither does one that fails nothing. Both cost
a model call. This asks in both directions and reports how often the check disagrees with **itself** on
the same text, which is the number that decides whether any threshold on top of it can mean anything.

Adding a check means adding fixtures for it: three positives in `POSITIVES` in that script, written to
carry your defect and nothing else. Negatives live in `measure/fixtures/well-built/` and every check shares
them.

Where it stands today, at `claude-sonnet-5` and medium effort, 13 positives and 5 negatives:

| check | catches the defect | passes real prose | disagrees with itself |
|---|---|---|---|
| terms | 2/2 | 10/10 | 0% |
| relevance | 6/6 | 10/10 | 0% |
| structure | 5/6 | 10/10 | 12% |
| sentence | 5/6 | 10/10 | 12% |
| reference | 5/6 | 9/10 | 25% |
| address | 7/8 | 10/10 | 11% |

**These figures move between runs on unchanged prompts.** Three consecutive runs of `address` alone gave
5/5, 5/5 and 4/5 on the negatives. So a one-cell difference is not a result, and a change worth claiming
has to move more than that or be run more times.

Do not make one column better by making the other worse without saying so. Both directions matter, and
the failure that actually loses users is a check that fires on good prose.

### 4. Measure what it costs the person using it

```
python3 measure/measure_cost.py --levels disabled,medium --reps 5
```

These are real sessions. Five reps of two levels means ten of them, so expect a few minutes and expect
to spend tokens. That is the point: a cost measurement that costs nothing is measuring nothing.

It prints, per level, the wall clock, how many turns **your** session took, your own output tokens, the
checker's tokens, and the dollar cost, then the difference against the `disabled` control **in the same
run**. Quote that difference. Do not quote a number from a run someone else did: the unguarded control
moves between runs by more than some levels differ from each other.

Report the model and effort you used. A cost measured on one model says little about another.

Today, on one fixture: `low` adds about 12s, `medium` 19s, `high` 75s per message sent. If your change
moves any of those by more than a few seconds, say so in the title of the pull request, not the body.

### 5. If you touched the rule, measure what it changes

```
python3 measure/measure_rule.py --rule rule/engineer-communication.md --rule none --reps 6
```

The rule is the only always-on part, which makes a change to it the hardest to notice and the easiest
to get wrong. Each `--rule` is an arm and `none` is the unguarded control; both belong in every run.

Read the bootstrap intervals rather than the means. At six replicates the interval on the code-block
share is about nine points wide, so this rules out a large regression and not a small one. Growing the
rule from 156 words to 246 cost nothing measurable on it; a longer draft before that measurably diluted
adherence, so the effect it looks for is real.

### 6. If you touched a threshold, re-measure it

```
python3 measure/measure_thresholds.py --corpus a.jsonl --audience audience-a \
                                   --corpus b.jsonl --audience audience-b
```

Each corpus is lines of `{"author": ..., "text": ...}` written **for** the audience named beside it. The
existing values and what their measurement fails to show are in [docs/thresholds.md](docs/thresholds.md).
Do not move a number in the code without moving the evidence beside it.

## What a good pull request looks like

State the defect or the goal in a sentence or two, then the numbers. Something like:

> The reference check missed an invented name in one of two runs. Narrowed the prompt to require naming
> what the reader cannot resolve.
>
> `measure_check.py --check reference --reps 2`, sonnet-5, medium effort: catches 6/6 (was 5/6), passes
> 10/10 (unchanged), disagrees with itself 0% (was 12%).
> `measure_cost.py --levels disabled,high --reps 5`: high adds 74s against 75s before. No change.
> Tests pass. Mutation: reverting the prompt makes `check/reference` fail.

Numbers with the command that produced them, so a reviewer can re-run it. That is the whole convention.

## The usual things, briefly

- **One change per pull request.** A prompt change and a cost optimisation are two reviews.
- **No new dependencies.** Standard library only, on purpose: it means the tool needs `python3` and
  nothing else, which is most of why it is easy to adopt. If you genuinely need a package, open an issue
  first and argue for it.
- **Comments say why, not what.** The code says what. Where a decision cost something to learn, the
  comment is where that goes — several in here exist because a plausible alternative turned out to be
  wrong, and the next person deserves to know which.
- **Prompts are prose files**, in `lib/checks/`, so they can be read and edited as prose. Keep them
  there rather than moving them into Python strings.
- **Do not add a vocabulary that came from a corpus you cannot publish.** The shipped `engineers`
  baseline is hand-curated for exactly this reason: a measured vocabulary lists who your organisation
  talks to. Ship the measuring, not the measurements.
- **A new baseline is welcome.** `data/audiences/engineers.json` is one file; product managers,
  designers, data scientists and support engineers would all be reasonable siblings. Say where the terms
  came from.

## Reporting a false alarm

The most useful issue you can open. Include the text that was flagged, which check flagged it, and which
audience was in scope — `python3 plugins/prose-guard/lib/audiences.py show <name>` prints the last one.
A false alarm on ordinary prose is a defect even when the check's reasoning sounds plausible.

## Licence

Contributions are under the MIT licence, the same as the rest of the repository.
