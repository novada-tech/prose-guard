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

The scores live in one place, [CONTRIBUTING.md](../CONTRIBUTING.md), because that is where somebody who
has just changed a prompt is told to re-run the harness and paste the new ones. They were also here, from
an earlier run, and by the time anyone noticed the two tables four of five shared rows disagreed and this
copy was missing the `address` check entirely — so the reader could not tell which was current.

What the numbers say, and this has held across every run: the checks that report on the *shape* of a
paragraph are the weak ones, they are the ones that disagree with themselves most, and they are advisory.
That is the right severity for a check at that reliability, and it is why only the arithmetic one blocks.

## Four more mechanical rules flagged a third of everything written

Two mechanical rules ship: a word typed twice, and `a` where `an` belongs. Measured on 3,000 real
messages they produce 62 findings, about 2%, and nothing at all on the five documents already judged
well built. That rate is what makes them safe to hold a message back on.

Four more were tried and dropped, with the numbers: space before punctuation (1,131 hits, almost every
one a line break before a full stop), stray punctuation (592), no space after punctuation (512, mostly
URLs and version numbers), unbalanced brackets (498, mostly brackets spanning lines). Together they
flagged a third of everything written.

A rule for missing spaces between sentences was tried on the same evidence and is not here. Tightened to
a real sentence boundary — lowercase, full stop, capital, lowercase — it hit 21 times in 3,000 messages,
and every hit was machine text: GitHub notification footers ("mentioned.Message ID:"), a Java import
path, a filename with dots. Not one was a person's missing space. The looser version hit 494 times, all
of them filenames and abbreviations.

## A grammar checker was measured, not dismissed

Grammar in general is not checked, and a third-party checker was measured rather than assumed to be the
answer. LanguageTool 6.6 locally: 240MB to download, 390MB unpacked, Java, 1.6 seconds a run. It found
nothing on the sentence that prompted the question — a fragment with no main verb — nor on three other
fragments tried. It caught word repeats and `a`/`an`, which are already here, plus subject-verb
agreement, which is one rule more. On prose judged well built it flagged four documents of six, mostly
its spell checker firing on technical terms, which is the noise a measured vocabulary exists to prevent.

The fragment class is caught by the checks that already exist, when the text is short enough. Asked about
that sentence on its own, `structure` found it in three runs of three and `sentence` in two of three. It
got through inside 370 words.

## Splitting a long document finds no more, at nine times the calls

Checking long text one paragraph at a time was the obvious fix for a fragment that got through inside
370 words, and it was measured and dropped. Pooled over eight runs of a 371-word document with that
fragment planted in it, the whole document caught it twice in eight and so did paragraph-at-a-time — no
difference in what was found, nine times the model calls, and a complaint about prose already judged
well built in nearly every pass instead of one pass in five. Reproduce it with:

```
python3 measure/measure_splitting.py --reps 5
```

The reason is that every check except `mechanics` is comparative: asked about a piece of text it reports
the worst instance of its concern in that text, so a smaller piece does not sharpen it, it lowers the
bar for what counts as worst. That distinction decides which checks can be trusted to block, so it is
stated where a reader using the tool will meet it: [reference.md](reference.md).

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
- maximum instead of minimum for shared context
- a git subcommand that writes allowed to run behind a substitution
- a substitution resolved from text a command carries rather than from the command itself
- an audience name allowed to be a path
- `--with-names` treating "could not tell whether this repository is public" as private
- a checked message allowed to write its own verdict past the delimiter
- a code strip leaving the words either side of it adjacent
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

## The word list is from 1913

`/usr/share/dict/words` is the web2 dictionary. It has no modern computing vocabulary, so the filter
that tells an acronym from a capitalised English word passes THE and WAS and flags INLINE.

Someone ran the checker on a real draft and the only thing it reported was `INLINE` — from their own
scaffolding header, not from the text they were about to post. Probing 44 common technical terms found
29 in the same position: KUBECTL, TERRAFORM, CIDR, SUBNET, GRPC, MONOREPO, ZSH and the rest.

80 of them are now in the `engineers` baseline, grouped by kind so a reviewer can argue with a group
rather than a list. Measured effect on 800 real messages from two corpora: **one detection**, because
those corpora are financial-model discussions and barely mention infrastructure. The class is real and
the measured impact here is small; an infrastructure-heavy corpus would show more.

Nothing that should be flagged was swallowed: ADC, GKE, SFTR, MSCI, FTSE, CDM, DRR, FQN, GAV and ISDA
all still need explaining. A test asserts both halves, and asserts the *outcome* rather than baseline
membership — two mechanisms produce it, and KAFKA is handled by the word list because Kafka was an
author.

## Thresholds

The author cut and the share threshold, with the corpora behind them and what the measurement fails to
show: [thresholds.md](thresholds.md). `measure_thresholds.py` re-runs it on your own audiences.
