# What was measured, and what did not survive it

The README states how the tool behaves. This is the evidence, and the parts of the design that were
proposed, looked sensible, and turned out to be wrong.

## Parallel checks deadlock

Two checks that can each hold a message back, running against the same draft, pull in opposite
directions. "Explain every term the reader may not know" adds text; "contains nothing they will not act
on" removes it. Each undid the other and the session ended with **no message at all** — 0 of 5 usable,
twice, in two different configurations. The agent diagnosed it itself: *"one requires terraform and
docker be explained; the other flags that as padding."*

I nearly reported the opposite. The first scoring pass showed "0.00 unexplained terms" for both broken
configurations, which was empty files scoring perfectly.

## A check that fires on everything carries no information

The sentence check originally failed **14 of 15** real messages, including ones written with no guidance
at all. It cost a model call and a blocked turn every time and told you nothing.

Rewritten to require naming what the reader would get wrong: 12 of 15 real messages pass, and all three
planted defects are still caught. The same rewrite took the judge's disagreement with itself from 20–27%
down to 0–5%, which is the more interesting result — a check that has to point at a consequence is a
more stable check.

Every check is now validated in both directions: it catches planted defects **and** passes ordinary
prose. `measure/measure_check.py` is the harness, and `--reps 2` also reports how often a check disagrees
with itself, which bounds how much of any difference is real.

At `claude-sonnet-5`, medium effort, 13 positives and 5 negatives:

| check | catches the defect | passes real prose | disagrees with itself |
|---|---|---|---|
| terms | 2/2 | 10/10 | 0% |
| relevance | 6/6 | 10/10 | 0% |
| structure | 6/6 | 9/10 | 12% |
| sentence | 6/6 | 8/10 | 0% |
| reference | 5/6 | 10/10 | 12% |

`structure` and `reference` are the weak ones: `structure` false-alarms and `reference` misses an
invented name in one run of two. Both are advisory, which is the right severity for a check at that
reliability.

## Freezing a passed check loses nothing measurable

Zero checks passed during a walk and then failed on the message's own final text, across 20 sessions.
The re-verification is kept anyway, because the phase most likely to expose a regression was the broken
one above, so the test could not have shown a problem even if there were one.

## Effort levels, priced against a control in the same run

Five paired sessions per level, medians, one fixture and one model.

| level | wall clock | your turns | your output tokens | model calls |
|---|---|---|---|---|
| unguarded | 26.8s | 3 | 1,290 | 0 |
| `low` | +12s | +1 | +1,500 | 0 |
| `medium` | +19s | +1 | +1,600 | 1 |
| `high` | +75s | +2 | +2,300 | 4–6 |

`low` spends no model call and is still not the cheap option: a hold costs a whole agent turn on your
own context, which is dearer than the small call `medium` adds.

`high` satisfied every concern on every message measured, and so did `medium`. That is a judge at its
ceiling, not evidence they are equal.

## Two proposals that did not survive contact

**Subset elimination.** If audience A's members all sit inside audience B, dropping A when both are in
scope looks free. It is not: breadth measured across B does not imply every member of B knows the term,
and dropping an audience only ever widens the vocabulary, which is the unsafe direction. Removed, with a
test that fails if it comes back.

**Computable overlap.** Storing members looked like it made overlap between audiences computable. Sources
name people differently — a chat export gives "Sam", a repository gives "sam-t" — so a set
intersection reported **zero shared members while ten people were in both**. `overlap` now prints a
prefix-matched guess, labelled as one, and nothing depends on it.

## The tests were checked by breaking things

A green test run proves nothing on its own. Each of these mutations breaks at least one case, which is
how the cases are known to be load-bearing:

- union instead of intersection when two audiences are in scope
- maximum instead of minimum for shared context, and minimum instead of maximum for reach
- subset elimination reintroduced
- an unresolved audience allowed to hold a message back
- the share threshold removed
- prose files no longer needing to be tracked by git
- shipped destinations read before the user's, so an override stops working
- passive discovery recording the message text rather than the call shape
- the session ledger resetting when a message goes out
- declining a suggested destination not being permanent
- the acronym filter dropped, so capitalised English words are reported as jargon
- the rule symlinked instead of copied

## One config directory, not two

The hook and the skills were reading different files. The per-plugin data directory reaches a hook's
environment but not a skill's shell, so the setup skill wrote settings to one path and the guard read
another: setup reported success and the guard stayed disabled, with nothing anywhere saying why.

The cause was three copies of the path resolution, one per file. There is one now, and a test resolves
it in a subprocess with the per-plugin variable set and asserts it is ignored.

## Thresholds

The author cut and the share threshold, with the corpora behind them and what the measurement fails to
show: [thresholds.md](thresholds.md). `measure_thresholds.py` re-runs it on your own audiences.
