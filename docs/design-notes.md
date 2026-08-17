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

## Context that tells a check what to conclude silences it

Telling the checks what the reader already has — "attached to line 129 of Diag.java" — was meant to stop
`reference` flagging terms that the anchored code defines. The first wording added the conclusion too:
*"so a term the code there defines is already explained for them, and a fragment of it needs no gloss"*.

Re-run against the six real drafts that had been held on one pull request review, **every complaint passed
on its first run** — including three stacked `file:line` citations and a "these two assertions" that named
one. Stacking is a structural fault whatever the reader has open, and a second assertion that does not
exist cannot be anchored into existence. The person who received those complaints had judged five of the
six fair. A clause about what needs no gloss reads as a general licence to stop objecting.

Every other entry in `situation` is a bare fact — "private: colleagues can open internal links". So are
these now: where the text sits, and nothing about what follows from it.

**What this measurement could not settle**, and the reason to distrust the numbers above as a comparison:
the same condition run three times fired on 3 of 6 drafts every time, but on *different* drafts each time
— `..F.FF`, `F..F.F`, `F..F.F`. The count is stable and the identity is not, so at six drafts and three
passes a per-draft before/after tells you nothing. The 0-of-6 under the first wording was outside that
range and is believable; the remaining effect of the bare-fact version is not measurable at this sample
size. Settling it needs `measure/measure_check.py` against labelled fixtures, not six drafts.

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

## Findings did not reproduce, so the rewrite loop did not terminate

On one 370-word document already through six rounds of editing, ten runs of the five model-based checks
gave one clean result and nine findings, with no finding raised twice — `reference` objected on every run
and to a different sentence almost every time. Past the substantive problems, the checks generate nits,
and chasing nits is work with no end.

Every finding is now put back to the same check and can hold a message back only if it objects to the
same sentence. One extra call for a check that fired, nothing for one that did not. With confirmation,
four runs of that same document reported nothing to act on. Three of five well-built fixtures produce a
finding on a single run of all five checks; with confirmation, two of those three report nothing to
change and the third reproduces — which is the point: what survives is worth reading.

Confirmation filters the symptom. The cause is that two runs choose differently between near-equal
candidates, and the checks that point at a span now say to quote the earliest failing one rather than the
most interesting. On the document that produced no repeated finding at all in ten runs, that took
agreement between two runs from nothing to about two in five — so a real finding survives confirmation
instead of being filtered with the nits.

That instruction is deliberately not on `relevance` or `address`. Neither reports a span — one asks what
is missing and the other who is being spoken to — and telling them to quote the earliest failing span
changed what they looked for, which showed up immediately as findings on fixtures that had been quiet.

## Asking a check for more items does not get more items

A check returns exactly one item, and that is not a contract that can be widened. Asked for up to five
items on a 295-word document with about ten known defects, every check returned one — the same as asking
for one:

```
python3 measure/measure_batching.py --reps 3
```

So the objection holds: a 100-word document and a 1,000-word one both get one item per check per pass, and
the long one is held to a lower bar for the same number of passes. And each pass costs a round trip, which
is an agent turn spent reading a finding and editing — dearer than the check's own call.

What varies between runs is WHICH item, and that is the fix. Each run picks one item from those above the
bar, so runs sample items, and how many runs is decided by the text rather than by a flag. One run that
adds nothing is tolerated, because a run repeating itself does not prove the well is dry and stopping at
the first repeat loses whatever came after it; two in a row stops it. A fixed number of runs was the
alternative and it is refuted: it cuts a document with ten real defects off at the same point as a clean
one. The base of six is on the ceiling and not on the runs for the same reason — a 44-word message capped
at two runs could never be observed to run dry, so length decided everything and quality decided nothing.

Splitting the document was the other candidate for scaling, and it is refuted above.

What the run rule costs, measured per document over every check:

| document | words | calls | items found |
|---|---|---|---|
| badly written | 295 | 14 | 5 |
| well edited | 371 | 8 | 2 |
| agent-written | 68 | 11 | 3 |
| human-edited | 44 | 10 | 3 |

The badly written document spends most and the well edited one least, at a similar length. A check that
passes on its first run costs one call, so the extra calls are paid only where something was found. At
the top end, measured on a badly written 1,475-word document at `high`, one denial cost 16 calls and 147
seconds — which is why the hook budgets 20 calls for one message. On that same document, one pass found
two findings and three pooled runs found six across four checks, including two checks that were silent in
the single pass.

`medium` is exempt from pooling, and asking that question is what caught it: adding pooling had quietly
turned the level documented as "one advisory call" into three. Pooling pays where a check picks one item
from many candidates of one narrow concern, because two runs then pick differently and the difference is
coverage. `medium` is one combined verdict over every concern at once, so it has nothing to pick between —
measured, three runs cost three calls and 16 seconds against one call and 4, and found the same single
item. So the ladder is: `low` costs no call, `medium` costs one, and `high` separates the concerns and
works each until its runs stop finding anything, which is what makes the separation worth its calls.

## Freezing a passed check loses nothing measurable

Zero checks passed during a walk and then failed on the message's own final text, across 20 sessions.
The re-verification is kept anyway, because the phase most likely to expose a regression was the broken
one above, so the test could not have shown a problem even if there were one.

## Effort levels, priced against a control in the same run

Five paired sessions per level on one task, medians, one fixture, with `claude-sonnet-5` writing the
message. Read the ordering rather than the digits: your own traffic and your own model will move them.

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

The wall clock was measured when `high` ran four model-backed checks. It runs six now — a fifth and
then a sixth were added afterwards and neither has been measured, so `high`'s figure is a floor. Rather
than restating a count that keeps moving, ask the code: `python3 -c "import sys;
sys.path.insert(0, 'plugins/prose-guard/lib'); from checks import for_effort, costs_a_call;
print(sum(1 for c in for_effort('high') if costs_a_call(c)))"`. Refresh the whole table with:

```
python3 measure/measure_cost.py --levels disabled,high --reps 5
```

That spends real model calls doing it.

## Two proposals that did not survive contact

**Subset elimination.** If audience A's members all sit inside audience B, dropping A when both are in
scope looks free. It is not: breadth measured across B does not imply every member of B knows the term,
and dropping an audience only ever widens the vocabulary, which is the unsafe direction. Removed, with a
test that fails if it comes back.

**Computable overlap.** Storing members looked like it made overlap between audiences computable. Sources
name people differently — a chat export gives "Sam", a repository gives "sam-t" — so a set
intersection reported **zero shared members while ten people were in both**. `overlap` now prints a
prefix-matched guess, labelled as one, and nothing depends on it.

## When is a text finished: no honest answer yet

This is the gap in the design rather than in the documentation.

```
python3 measure/measure_stopping.py --reps 3
```

That runs every comparative check over three real documents: a message an agent wrote, the same content
after a senior engineer rewrote it that day, and a long document already taken through six rounds of this
tool. Confirmed findings per pass, five passes each:

| document | words | checks with something to say, per pass |
|---|---|---|
| agent-written | 68 | 2.2 — `[2, 1, 4, 2, 2]` |
| human-edited | 44 | 1.2 — `[1, 2, 1, 1, 1]` |
| heavily edited | 371 | 0.2 — `[0, 0, 0, 0, 1]` |

Three passes gave 2.0, 1.3 and 0.7, and a single pass in isolation once put the human-edited version above
the agent-written one — the spread is about ±1, so one pass is not a measurement. At five passes the order
holds, so the count measures relative quality, and zero IS reachable: the document taken through six rounds
scored zero in four passes of five.

One finding a pass is where a senior engineer's own rewrite landed. That is a reference point and not a
target: his writing is not perfect either, and the bar here is allowed to be higher than it. What the
number is for is the trend — the stopping rule is that the count has stopped falling, and a reader who
disagrees with what is left is allowed to be right.

Calibrating it means tuning the bar until the human-edited version passes and the agent-written one does
not. That needs more pairs than the one in `measure/fixtures/gold`, and from more than one author —
tuning five prompts against a single pair would fit the pair rather than the bar.

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
- `capped` given its own copy of the levels with one missing, so a destination whose `max_effort`
  names that level runs at full effort with nothing said
- a second `def` reusing an existing test name, which replaces the first in `globals()` and leaves the
  count unchanged. The runner's own guard could not see this one until it counted definitions instead
  of comparing two sets of names, so the mutation was green before it was red

## One config directory, not two

The hook and the skills were reading different files. The per-plugin data directory reaches a hook's
environment but not a skill's shell, so the setup skill wrote settings to one path and the guard read
another: setup reported success and the guard stayed disabled, with nothing anywhere saying why.

The cause was three copies of the path resolution, one per file. There is one now, and a test resolves
it in a subprocess with the per-plugin variable set and asserts it is ignored.

## The word list is from 1913

The dictionary is web2, Webster's Second International of 1934, and it now ships with the plugin
rather than being read from the machine. It has no modern computing vocabulary, so the filter that
tells an acronym from a capitalised English word passes THE and WAS and flags INLINE.

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

## What a survey of proofreading tools and writing research would add

The seven checks accumulated one at a time, from problems that happened to come up. So the field was
surveyed deliberately — every rule Vale's Microsoft, Google, Red Hat and proselint packages enforce,
plus write-good, retext, alex, textlint, LanguageTool, Hemingway, Grammarly, ProWritingAid and Acrolinx;
and the writing canon from word level up: Williams' *Style*, Gopen & Swan, the given-new contract,
BLUF and the inverted pyramid, plainlanguage.gov, the GDS style guide, Diátaxis.

**Most of the canon is already here.** Word level (know your reader's terms, do not coin) is `terms`
and `reference`; sentence level (one action, the thing to do in the stress position) is `sentence`;
sentence-to-sentence (given before new, resolvable reference) is `reference`; paragraph (one point, in
a predictable place) is `structure`; document (so what, and who is being spoken to) is `relevance` and
`address`. `relevance` (b) turns out to be Williams' "so what" test almost exactly.

**One gap: above the paragraph.** Nothing here asks whether the opening still describes what the rest
of the message does. That is Williams' issue/discussion — "the issue promises; the discussion
delivers" — and it is the only part of the canon that operates on a whole document rather than a
sentence or a paragraph.

### Passive voice: rejected, and this is the one to point at

Every tool checks it. It is rejected here on two independent grounds.

Measured: the Microsoft `Passive` rule fires on **22.8% of sentences across 451 sentences of this
repository's own documentation, and hits 7 of 7 files**. That is the same order as the four punctuation
rules dropped above for flagging a third of everything written. Samples, from prose already judged well
built: "Writes are unaffected, so nothing *is being lost*." — "The seconds *were measured* when the tool
ran four checks." — "Four more *were tried* and dropped." Every one is correct, and making any of them
active would make it worse.

Published: Pullum, *Fear and Loathing of the English Passive*
(https://pullum.ppls.ed.ac.uk/passive_loathing.pdf) shows the advice is not merely wrong sometimes.
Style guides routinely flag things that are not passives at all, and the writers giving the advice use
passives heavily: in E. B. White's own introduction to *The Elements of Style*, 5 of 6 transitive verbs
are passive; in the opening of Orwell's *A Hanging*, all of them. There is no rate at which the rule is
right, because passive is a construction and not a defect.

### Readability scores: rejected, including as a hint

Flesch-Kincaid, fog, SMOG, Coleman-Liau, Dale-Chall. Redish, *Readability formulas have even more
limitations than Klare discusses* (https://redish.net/wp-content/uploads/Redish_on_Readability_Formulas.pdf)
reports the finding that settles it: when Charrow & Charrow rewrote jury instructions and tested them,
**comprehension went up while the readability scores got worse** — because the rewrite added words to
show how the pieces related to each other. A formula penalises exactly what `reference` asks for.

And it would not fire anyway: 0 of 14 documents here exceed grade 12. Lowering the gate until it fired
would rank documents by how technical their vocabulary is, which is what `terms` measures properly.

### Candidates measured and not shipped

**Unfinished or unsendable text** — `TODO`, `FIXME`, `TBD`, a `localhost` link, a `/Users/<name>/`
path. The most promising candidate in the survey: absolute rather than comparative, objective, a
one-word fix, no model call. Measured on **1,897 real commit messages, 73,918 words**:

| form | hits | share of messages |
|---|---|---|
| including `WIP` | 111 | 5.85% |
| without `WIP` | 18 | 0.95% |
| only where it is a marker — opening a line, or followed by `:` | 1 | 0.05% |

`WIP` had to go first: "WIP: refactoring" is a deliberate label, not an accident. What remains is quiet
enough, but **not one of the hits is a true positive** — every inspectable one is a message *about* a
placeholder ("remove outdated TODO comments"). So the false-positive half is measured and the
true-positive half is not: on this corpus the failure never happens. Not shipped, for want of evidence
that it catches anything, rather than for noise.

**Heading skeleton** — a skipped heading level, a section with nothing in it. Deterministic and free.
Measured on 742 real markdown files: level skips 3.6% of files, empty sections **19.7%**. Both above the
~2% band the two shipped mechanical rules occupy. (A first run said 55.9%, because it counted a heading
followed by a *sub*-heading as empty. That is ordinary markdown. The corrected number is the one that
decides it.)

**Sticky sentences, sentence-length caps, weasel words, adverbs, hedging, echo detection, nominalisation,
wordy-phrase lists.** All measured, all either above the band (echo detection fires 442 times across 11
of 14 good documents) or silent on both good and bad text, which is zero value at non-zero cost.

### What would have to exist first

The one candidate worth building — does the opening still describe the body — cannot be measured today,
and that is the finding to act on before any of it.

```
$ wc -w measure/fixtures/well-built/*.md
      93 decision.md      102 deploy-fix.md     77 incident-update.md
      58 release-note.md   80 review-comment.md
```

Every negative is 56 to 102 words, and the largest fixture anywhere in this repository is 371. A message
of 80 words has no opening segment to compare against a body. Any above-the-paragraph check would either
pass all five trivially, measuring nothing, or fire on all five — which is the failure recorded at the
top of this file as carrying no information.

So the first cost of structure work is **negatives at 200 to 800 words, from real messages judged well
built rather than written for the purpose**. Until those exist, a structure check cannot be shown to
pass good prose, and this repository does not ship a rule on an argument.

## The dictionary is shipped, because two machines gave two answers

The filter that tells an acronym from a capitalised English word read the machine's own word list, and
which list that was decided the verdict. macOS ships `web2`; Ubuntu ships `wamerican`, which contains
`api`, `amd`, `aws`, `ids` and `ads`. So the same message was held back on one machine and let through
on another, a CI run went red over exactly that, and a container with no dictionary at all was a third
answer again — one that reported THE and WAS as unexplained jargon until `common-words.txt` was written
to stop it.

web2 now ships in `data/english-words.txt.gz`: 234,428 words, 0.70MB gzipped, 21ms to read on first
use and never read at all unless a message is being checked. Its 1934 copyright has lapsed.

Pinning it makes every machine give the answer macOS already gave, which is also the correct one — API
and AWS are acronyms, and Ubuntu was wrong to treat them as English words. Two ordinary plurals came
out of that, `IDS` and `ADS`, and went into the floor beside `id` and `ad`.

`common-words.txt` is still there and is not a fallback: measured, it contributes 190 terms web2 does
not have, and dropping it makes 38 of 42 everyday terms report as jargon **on a machine that has a
dictionary** — `email`, `www`, `config`, `todo`, `usd`, and the inflections `has` and `using`, which
web2 omits because it lists headwords.

The `english-words` package was measured rather than assumed: it ships this same list, at 17MB
installed, and would add a `pip` step to a plugin whose install is one command.

## Thresholds

The author cut and the share threshold, with the corpora behind them and what the measurement fails to
show: [thresholds.md](thresholds.md). `measure_thresholds.py` re-runs it on your own audiences.
