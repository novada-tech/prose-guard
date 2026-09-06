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

## Telling a check what the reader already has: measured three times, three answers

Prose is usually attached to something the reader has in front of them: a review comment to a line of a
diff, a reply to the thread above it. Telling the checks looked obviously right, and it was built as a
shipped default so every install would get it — `thread_ts` on 243 real calls, `path`+`line` on 83.

It is not shipped, and the reason is worth more than the feature.

**First measurement, six drafts, before and after.** Every complaint disappeared with the context. That
looked like a clear answer and it was noise: the same condition run three times fired on 3 of 6 drafts
every time but on *different* drafts each time.

**The instability was in the harness, not the checks.** One draft's raw first-run rate over eight
repetitions: draft 6 fires 8/8, draft 3 fires 6/8. Stable enough to measure. What was unstable was asking
`pooled` instead of the check —

- the harness used `passes=3` where production uses `ceiling_for(text)`, 6 for a review comment;
- `firm` needs two runs pointing at the same item;
- and `pooled` returns after **one** empty run, so a clean first sample means there is no second.

That last is the tool, not the harness: **for a check that fires half the time, whether a message is
checked at all rides on one sample.** Deliberate — a clean first run costs one call — and worth knowing
before believing any single result, including the ones below.

**Second measurement, the draft with the stable baseline**, eight repetitions each way:

    without the context sentence:  FFFFFFFF   8/8
    with it:                       .F......   1/8

The finding it silences is "These two assertions" where only one was introduced, which the agent who wrote
that comment called a real error of its own. Removing the clause that told the check what to conclude —
*"so a term the code there defines is already explained for them"* — did not fix it. A bare fact about
which file the reader has open suppressed it just as thoroughly.

**Third measurement, five drafts, four repetitions each way.** No effect at all:

    draft 1 sentence   3/4 -> 2/4      draft 4 reference  3/4 -> 3/4
    draft 2 sentence   0/4 -> 1/4      draft 5 reference  2/4 -> 0/4
    draft 3 sentence   3/4 -> 4/4      total             11/20 -> 10/20

So draft 6 is an outlier rather than the rule, and the honest summary is **one measured harm and no
measured benefit anywhere**: no draft showed a false positive being removed, which is what the change was
for. A default that can take a blocking check from 8/8 to 1/8 on one draft and does nothing on five is not
something to ship on the strength of an idea.

`when` survives, so a destination can still say what a call means in its own words — local, deliberate,
and visible in a file somebody edited. `measure/measure_check.py` with a bigger labelled set is what would
settle whether this can be made to work, and `measure/held_drafts.py` builds the corpus.

## Advisory findings are never acted on

`medium`'s judgement question only advises, and `high` demotes a blocking finding to advice once a check
has asked twice about a message. On one machine's transcripts, **41 messages got advice and went out and 0
were followed by a correction.** `measure/measure_advice.py --transcripts` recomputes it.

Asked directly, the same notes are usable: given a held draft and its note, an agent said it would edit in
4 of 6 cases when told the message had already gone out, and revise in 5 of 6 when told it could still
change the text. That is a leading question — asking "what do you do next" makes a note salient in a way
an ordinary turn does not — so it is an upper bound on willingness rather than a prediction. But it points
at the mechanism rather than the wording: an advisory finding reaches the model as `additionalContext` on
PreToolUse and the call then proceeds, so there is no turn in which the message could have changed.

**The fix is not to pay for it until it can be acted on.** A check that can never hold a message back is
not asked until something else has, and then its findings ride along on that denial, which
`other_concerns` already arranges. Advice attached to an interruption reaches the model while it is
rewriting anyway; advice on its own reaches it after the call has run.

At `medium` that is the whole of the token cost. The only paying check there is `judgement`, it only
advises, and what can block is the two arithmetic checks — which cost nothing and answer before any model
call. So a clean message at `medium` now costs **0 model calls** rather than 1, with no extra waiting,
because the gate is free:

    clean    prose-guard medium …: nothing to say.            (no model call)
    held     Hold this message.
             "the the" — a word typed twice
             Also worth fixing while you are here, though none of it is holding this back:
             (judgement) Consider: … is backstory the reader didn't live through …

At `high` the same rule gates `promise`, where the gate is the five blocking checks, so it costs one more
round of waiting on a message that is being held anyway — 1% of claimed calls, at most 7% — and saves a
call on the rest.

Three denial sites had to route through one closure, and patching one of them was the first attempt: at
`medium` what blocks is a free check, so the paid-check site never fires and the advice was never asked at
all.

## A count that matched the refusal text anywhere counted files as messages

Every number about held messages in this repository came from one grep, and it was wrong. Matching
`"Hold this message"` anywhere in a tool result counts a file that merely *contains* the phrase — reading
this repository's own notes produced four phantom held `Read` calls, and 47 phantoms out of 59.

Corrected by requiring the result to BEGIN with the refusal, the real distribution is 59 held messages: 44
went out after one round, 7 after two, 6 after three, and none needed a fourth. The earlier published
figure was 95 and 74/13/6. The shape survived — nothing ever needs a fourth round, which is what the
per-check bound rests on — and the number did not.

## Asking the checks together costs the slowest, not the sum

The six checks at `high` were asked one after another, and each answer is a `claude -p` subprocess taking
about eight seconds. On a real pull request review: **39 guarded calls, median 50.3s**, 217.7s for a
925-word summary comment, and **34.5 minutes of a 168-minute session** spent waiting on the guard.

They are independent — each reads the same unmodified text and none can see another's verdict — so when
they are asked was always free to change. A/B on one 78-word review comment at `high`, same input, same
config:

    one after another   34.3s
    at the same time    12.4s     same six model calls, same verdict

The entry above about parallel checks is a different thing and worth not confusing with this one: it is
about two checks that could each HOLD A MESSAGE BACK, each undoing the other's demand. That is about what
may block, not about what may run, and exactly one finding blocks either way.

What this does not fix is a check that keeps finding things: pooling asks it again until a run adds
nothing, and those runs are sequential. The 217.7s comment was one check pooling repeatedly, so it
improves by less than the ratio above.

## There is no cheap way to find out whether a message is worth checking

`low` costs 0 model calls, `medium` 1, `high` 6 — one per paying check, since pooling stops on the first
empty run. So the obvious saving is to find the messages worth six calls and spend one on the rest. Two
ways were measured and both fail.

**A free signal: none exists.** Comparing review comments the checks HELD against review comments that went
out clean — same genre both sides, which matters, because comparing held code-review comments against
well-built Slack messages produces a beautiful 72% on "backticked spans" that is measuring genre and not
quality. Within one genre:

    feature                held   passed
    words                   47.0     60.0
    longest sentence        25.5     30.0
    mean sentence           15.9     18.0
    backticked spans         4.0      4.0

Held drafts are *shorter*, with shorter sentences. The best free rule reaches **0% recall** at under 25%
false alarms. Nothing cheap predicts which messages have faults.

**The one cheap question as an alarm: 4 of 8.** `medium`'s combined judgement question was measured as a
verdict before and rejected as one. As a gate it needs recall and almost no precision, which is a much
lower bar, so `measure_gate.py` asked it against real held drafts and the well-built fixtures:

    recall     4/8 of drafts the specific checks held were flagged
    precision  10/11 well-built fixtures passed cleanly

Recall is half. And the precision figure is measured against eleven fixtures, which cannot carry a rate,
so it was measured again against **42 review comments that the six specific checks approved** — same genre,
real messages, known to have passed:

    36 of 42 passed the cheap question.  It objects to 14% of messages the expensive checks approved.

That settles two proposals at once. A **cascade** on this gate lets four of eight faulty messages through
to save five calls, which is a cheaper way to miss things. **Blocking once on it** — one guaranteed
interruption for one call — would hold roughly one good message in seven, and a held turn is the most
expensive thing this tool does: a review session posting forty comments would be interrupted about six
times for nothing. `high`'s blocking checks pass 9 or 10 of 10 well-built messages by comparison, and now
cost 12 seconds of wall clock rather than 34.

Two false starts on the way to that number, both the same mistake, and worth more than the number:

- the first clean set was 11 well-built fixtures — too few to carry a rate at all;
- the second was 17 of this repository's own commit messages, of which only 6 passed. That reads as a 65%
  false-alarm rate and is measuring the wrong genre: the shipped commit-message destination caps at `low`
  precisely *because* the judgement questions do not apply to a commit message, which has neither an
  addressee nor an ask. Measuring a check against prose it is not meant for produces a confident number
  about nothing — the same error as comparing held code-review comments against well-built Slack messages
  and discovering "backticked spans".

**So the cost of finding a fault is the cost of asking about it**, and effort cannot be saved by checking
fewer messages or by checking them more cheaply first. What is left is choosing which messages deserve the
spend — which is what a destination knows and an install-wide number cannot. Hence `worth`.

For the same reason, splitting the text to check less is already ruled out twice over: it finds no more at
nine times the calls, and the judgement checks are comparative, so a smaller window lowers the bar rather
than saving money.

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

## Scoping a resend to what it changed saves no model call

A held message is sent again with one clause different, and the guard reads the whole of it again. The
obvious saving is to check only what changed, and on this repository's own prose there is plenty to
narrow: across **80 consecutive revisions of 41 markdown files**, the contiguous span between two
versions covers a median **21%** of the document and the sentences that literally differ are **14%**.
A revision of a document is a proxy for a resend after a hold and not the thing itself — nobody has
published a corpus of held-then-resent drafts — but it bounds the narrowing at about a fifth.

That saving is not where the calls are. One real session reported **20 model calls** for a pull request
body over three sends. At `high`, every prompt file in `phases/` is asked once per send and the
advisory one once per denial, which is a floor of 17 calls with no pooling at all. So pooling
contributed 3 runs across 17 invocations, against a `ceiling_for` that was offering ten — **the ceiling
never bound**, and lowering it with the span, or dividing a smaller budget in `all_at_once`, would have
saved nothing on the session that prompted the question. What costs 20 calls is sending three times.

Two ways of spending the span that do not survive, both of which let a defect out in silence:

- **Scoping what may hold the message back.** The guard blocks on one check and hands the rest over as
  context; the agent fixes the blocker and sends again, and the next round is where a concern that
  merely rode along the first time becomes the blocker. Scope that to what changed and a defect the
  writer read and chose to leave goes out labelled "already in the file". The writer of a resend wrote
  every sentence of it and can fix any of them, which is the whole difference from an edit into
  somebody else's document.
- **Scoping the repeat ledger.** `repeated()` suppresses a finding already said about text this call
  did not write. Point it at what a resend did not change and the third round of an argument drops a
  blocking finding entirely — `found` empties, the check records a pass, and the message goes.

What is left is the ride-along list itself: up to `MOST_TO_SAY // 2` characters of other checks'
findings, handed over a second and a third time about sentences the writer has since read and decided
about. Nothing in that list is holding the message back, so leaving it out loses nothing — a concern
that still matters is said again in the round its own check is the one blocking. That is the only use
`Context.resent` has, and it buys transcript tokens rather than model calls.
## An edit is priced on what it changes, and read in the whole document

Two different questions, and answering them the same way is what made a one-word edit to a long
document cost what writing the document costs.

**What it costs follows the change.** `ceiling_for` is linear in words above a base of six, and the
whole document is what it reads unless the caller narrows it. At `high`, where five checks can block
and six pay, a document written whole:

| words written | budget | runs a check |
|---|---|---|
| 400 | 36 | 6 |
| 1,000 | 66 | 11 |
| 2,000 | 90 | 18 |
| 5,000 | 90 | 18 |

A one-word edit into the 2,000-word document sat in that same row. It now sits in the first one: 36 and
6, because the sentence it changed is what it is priced on. **Runs a check is where the waiting is** —
the checks are asked at the same time and the runs of one check are sequential — so that is a third of
the wall clock on the case where the ceiling binds.

On a one-sentence edit to each of this repository's own markdown files of 200 words or more, 31 of them:

```
python3 - <<'EOF'
import glob, sys
sys.path[:0] = ["plugins/prose-guard/lib", "plugins/prose-guard/hooks/scripts"]
from checks import ceiling_for, just_these, placing, wrote_which
from outgoing_guard import budget_for
def runs(c): return min(c, max(1, budget_for(c, 6) // 5))
for path in sorted(glob.glob("**/*.md", recursive=True)):
    text = open(path, errors="replace").read()
    ends = placing.SENTENCE_END.split(" ".join(text.split()))
    if len(text.split()) < 200 or len(ends) < 3: continue
    span = just_these(text, wrote_which(text, ends[len(ends) // 2]))
    print(f"{len(text.split()):>5}w  budget {budget_for(ceiling_for(text), 6):>2} ->"
          f" {budget_for(ceiling_for(span), 6):>2}   runs a check"
          f" {runs(ceiling_for(text)):>2} -> {runs(ceiling_for(span)):>2}   {path}")
EOF
```

The budget summed over the 31 falls to 65% of what the file-sized version allows, and the runs one
check may make fall to 6 from as many as 18 — on every file above 600 words, which is 13 of the 31.
Below that the file already sat on the base and nothing changes.

The widest of those 31 spans is 37 words, so every one of them lands on the base of six. The scaling
only starts to grade at a changed span of about 500 words, and a change that big has earned it. The
base is the floor for the same reason it is the base: a check allowed fewer runs than it takes to be
observed running dry can never be observed at all, so the smallest possible edit still gets six runs of
every paying check.

Writing a document whole is untouched, because then the change is the document.

**What it is judged against does not follow the change.** Asking the checks about the span was the other
half of the same proposal and it is refuted twice over: paragraph-at-a-time finds no more at nine times
the calls (above), and every check except `mechanics` is comparative, so a smaller window lowers the bar
for what counts as the worst instance rather than sharpening it.

The budget only ever binds on a document whose checks keep yielding — pooling stops when a run adds
nothing, so a clean document costs one call a check at any length. That is the case the issue reported:
the document being edited is the one the guard is objecting to, so its runs keep paying out, and the
ceiling bound hardest on the edits made to satisfy the guard's own previous advisory.

Sized on the span, the whole-message budget can be reached in fewer rounds of one argument, so a check
the budget stops now says so in the line that follows every checked message. Before, it recorded a pass
and said nothing — and a check that did not run answers exactly what a check with nothing to say
answers.

A **resend** is the other thing a span can be computed from, and it is a different regime:
[Scoping a resend to what it changed saves no model call](#scoping-a-resend-to-what-it-changed-saves-no-model-call)
measured a short message sent again three times, where the ceiling never bound at all and narrowing it
would have saved nothing. Both spans are `wrote_which` of a fragment, which is why there is one
arithmetic and not two — but a resend of a short message has no ceiling to lower, and a one-line edit
to a long document has one that is 18 runs a check too high. The budget follows the change where there
is a document for it to be a fraction of.

## One hook cannot run for three quarters of an hour

`checks/ask.py` allows a model call 180 seconds and `MOST_AT_ONCE` runs six at a time, so a budget of
`MOST_CALLS` calls is `MOST_CALLS // MOST_AT_ONCE` rounds — 45 minutes inside one `PreToolUse` hook,
which shows nothing while it runs and cannot be interrupted on its own. Nothing bounded that, and one
reported run produced no output and timed out the tool call.

The allowance is five minutes for every call one hook makes, and a call is never given more time than
is left of it, so the bound is the allowance rather than the allowance plus one call. Five minutes is
above anything measured here — the slowest guarded message on record is 217.7s for a 925-word comment,
from before the checks were asked together, and one denial on a badly written 1,475-word document cost
147s — and it is a bound rather than a target, so it can only bind where a call is hanging.

Not derived from the hang, which is an observation and not a reproduction. It is derived from the three
constants above, and it is worth having whether or not the hang was ever real.

A check the deadline stops reports itself through `telling.could_not_run`, the same way a timed-out
call already did. Unbounded time and a silent drop are two different defects and the fix for one must
not be the other.

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
- `chosen()` answering a level when no source names one, so an install nobody has set up looks
  configured and says nothing about checking nothing. Caught by 11 cases
- the held draft reaching `ctx.previous`, so `terms` subtracts the very term it blocked on and the
  resend that kept it goes out. Caught by 8 cases, one of them written for it
- what may hold a message back scoped to what a resend changed, so a defect the writer read and chose
  to leave goes out as advice
- the ride-along list not scoped at all, so a resend is read out its own untouched sentences again
- `what_changed` without its common suffix, so the span runs from the change to the end of the message
- `what_changed` not word-aligned, so a one-letter change gives a fragment — `"s read"` — that matches
  inside `is reading` a sentence earlier and scopes the resend to a sentence it never touched. This one
  survived the first sweep and is recorded as a gap that was closed, not as an equivalent mutation
- `rounds.last_draft` answering the first draft of an argument rather than the newest
- the `mine` guard dropped from the repeat filter, so a complaint that starts as scenery and ends up
  inside the paragraph an edit rewrites is suppressed as already-said — a defect the edit owns, allowed
  in silence. The first version of its test did not catch this, because it only ever showed one
  complaint staying somebody else's; what pins it is the one that MOVES
- the escape hatch decided from something other than the field `skipped` reads. Three mutations, all
  red: the predicate inverted (8 cases), one fixed shell sentence for every kind of call, which is the
  defect itself (7 cases), and the way out named on every denial rather than only the last (1 case,
  the one that pins the timing)
- the `gh api` pattern stopped at a chain operator, which a title holding a semicolon then hides behind
- `_from_bash` reading the first body a command carries instead of every one
- a named field never naming a file, so `-F body=@reply.md` is read as the literal text `@reply.md`
- a JSON payload handed to the checks as it stands, braces and field names included. The first version
  of its test did not catch this: it asserted that both bodies were present, and both bodies are
  present in the raw JSON too. What pins it is asserting what is ABSENT, and a bodyless payload long
  enough to clear the word floor — the short one it replaced was silent either way
- the repository read from the directory the command runs in rather than from the URL it names
- a `name=value` argument no longer yielded under `flag name`, so every `gh api -f body=…` goes unread
- the outcome of a claimed call not counted at all, which is the state that made a destination matching
  and finding no words indistinguishable from a clean pass
- a destination that HAS recovered text before still reported for its silent calls, which turns the one
  interruption this adds into a nag about every `git commit --amend --no-edit`
- `under the floor` collapsed into `no text found`, so a `text_arg` recovering a fragment of the real
  message reads as a commit that carried none
- the never-recovered note sent to the model and not to the person, which leaves it reaching nobody who
  can change a destination
- a local name in `discover.main()` shadowing the module function that reads the per-destination tally,
  which raises `UnboundLocalError` for the whole report. That one was found by writing the case, not by
  breaking the code: nothing had ever run `discover.py` end to end
- the per-check ceiling sized on the file again, and `all_at_once` deriving it from the file itself
  rather than being handed it. Each of these was hidden by the other while `budget_for` took a text and
  called `ceiling_for` a second time: the budget is the ceiling times the checks that pay, so a share
  and a ceiling both sized on the change are equal by construction and `min` took whichever came out
  smaller. `budget_for` now takes the ceiling, which is what makes each of the two catchable
- the whole-message budget sized on the file again. Invisible in a single round, and provably so: the
  share a check gets is at least the ceiling, so `min(ceiling, share)` is the ceiling whatever the
  budget. What it changes is how long an argument over one message may go on, and what pins it is the
  notice naming the allowance — the one place the allowance is readable from outside
- `just_these` ignoring the sentence numbers it was given, and keeping the sentences the call did NOT
  write
- no floor on the runs a check gets, so a one-word edit stops being checked at all
- a check the budget stopped saying nothing, and saying it once per check rather than once per message
- the hook never arming the deadline, so the allowance is correct and nothing switches it on
- a call started past the deadline, a call past it passing in silence, and one call allowed a timeout
  longer than what is left of the whole allowance

- `examine` no longer dropping a term from `unexplained` when the message writes it out, which is the
  clause that makes the flagged terms and the expanded terms disjoint. Three cases of
  `test_a_term_the_message_writes_out_is_never_one_it_is_held_back_over` go red, and one of
  `test_detection`. The first fixture written for it survived, because its expansion was ALSO found by
  `expanded_in_prose` and that route still excluded the term — a mutation the test could not see needed
  a fixture where only one of the two routes fires

One survivor, recorded rather than claimed equivalent: marking not-mine findings from `found` instead
of from what `one_message` actually showed. The two differ only when the turn's budget drops a finding,
and the budget cannot bind at `low`, where mechanics and terms each return one short finding. Binding it
needs model calls, so this is pinned by `one_message`'s own contract — it reports the findings it
carried — and not end to end.

## A destination pattern cannot stay inside one command of a chain

Claiming `gh api` needs a pattern that reaches from the binary to the flag carrying the body, and the
careful-looking version forbids a chain operator in between: `\bgh\s+api\b[^;&|]*?…`, so that a read
piped into `jq` cannot borrow a body flag from a command further down the line.

Measured over 25,878 unique Bash commands from local transcripts, that character class lost a real
`-X PATCH` whose title was `Fix a thing; and another`. The text a command sends is exactly where `;`,
`&&` and `|` turn up — `command.carrying` says the same thing about splitting a chain, and it is
quote-aware for that reason. A destination pattern is a plain regex over the command string and cannot
be.

So the span between the two is `[\s\S]*?` and the narrowing is done by what it has to reach: a body
field or `--input`. What that gives up is a tool call holding both a `gh api` read and, further along,
some other command passing a literal `-f body=` — which is a call that carries prose either way, and
the extractor reads the whole call regardless.

## The level is not a plugin setting

A plugin can declare a `userConfig` field, and Claude Code then asks for its value in a dialog when the
plugin is enabled. That is the obvious home for the effort level and it is not used, for two reasons that
only show up once you try it.

`userConfig` has no enumerated type — `string`, `number`, `boolean`, `directory` and `file` are the whole
list — so the dialog is a free-text box. There is no picker, and no way to mark `medium` as the answer
the measurements support. What reaches the user is a question with four valid answers, none of them
recommended, asked before anything has told them that `low` is not the cheap option and `high` is not
measurably better.

It also arrives at the worst moment: the dialog opens on install, which is the one point at which nobody
has read anything about the tool yet.

The second reason is that it is a second home for one fact. The value lands in
`~/.claude/settings.json`, and `config.json` holds the same setting, and the two can disagree about
whether the guard is on at all.

`/prose-guard:setup` asks the same question with the cost table beside it, and writes one file.

## Generic "you" is not the second person the address check is for

`address` failed a README opening — "You have read a review comment from an agent that nobody could
digest" — in three runs of three, and at `high` that holds the message back. Nothing was wrong with it.

The check exists for a "you" only one person in the audience can answer to: a pull request body saying
"the two files worth your review", an announcement saying "your comment was right". Most readers are not
that person and cannot tell whether it means them. A "you" addressed to every reader alike names nobody
in particular, so nobody is left wondering — and the same README says "you give it an audience" and
"nothing leaves your machine" a dozen times without the check minding at all. What it was reacting to
was an experience attributed to the readership, which is a figure of speech.

The clause now says which of the two it means and gives the non-example. Both arms measured in one
session, `claude-sonnet-5` at medium effort, `--check address --reps 2`:

| | catches | passes real prose | disagrees with itself |
|---|---|---|---|
| unchanged | 5/8 | 9/10 | 22% |
| narrowed | 6/8 | 10/10 | 0% |

Better in all three columns, and the direction that matters most is the middle one: the unchanged prompt
false-alarmed on `release-note.md` for "it changes one thing you have to act on", which is the same
mistake on prose already judged well built.

Two positives still get past, both of them "restates what the destination shows", which is clause (d)
and was missed by the unchanged prompt as well.

A first attempt is recorded here because it failed and the failure is the useful part. It added a
paragraph ending "PASS all of it", which scored 3/8 and 44% — worse than doing nothing, and it stopped
catching positives under clauses it had not touched. A permissive block in a prompt whose shape is
"FAILS only if you can point to one of these" does not narrow one clause, it lowers the whole bar. The
change that worked went inside the clause it was about and added six words of non-example.

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

## Naming the explanation that failed costs a round trip nobody is making

A pull request body was held by `terms` for one unknown term, rewritten to explain it in terms of a
second, and held again for both. Two hops where one would do, and the shape of the fix looks obvious:
say *"the first term is still unexplained because the word you explained it with is unknown too"*, out
of the expansions the check already has in `said`. So the frequency was measured before the sentence
was written.

```
python3 measure/measure_explanation_chain.py --repo ~/src/one-repo --repo ~/src/another
```

Free and deterministic — it reads git history and runs `terms`, which makes no model call. The run
behind the numbers below was four private product repositories: 8,370 documents, of which 8,328 are
commit messages scored against a vocabulary held out from the oldest fifth of the same history at four
authors, the rest this repository's own markdown and fixtures. `terms` finds something in 400 of them
and lists two or more unknown terms in 55. Within those 55, three readings of "one term was the attempt
to explain another", loosest last:

| the relationship | documents | true positives |
|---|---|---|
| the term appears inside `said[other]` | 0 | 0 |
| inside a bracket whose preceding word is the other term | 1 | 0 |
| within 120 characters of the other term's first mention, same sentence | 42 | 0 |

The first row is zero for a reason no larger corpus will change. `examine` drops a term from
`unexplained` exactly when it is a key of `written`, so the flagged terms and the terms with a
written-out form are disjoint sets — a flagged term has no expansion to look inside, and the one case
that reads like a chain runs backwards, from the term that WAS explained to the one still missing.
That is not a chain a writer can act on. `test_a_term_the_message_writes_out_is_never_one_it_is_held_back_over`
pins it so the next person does not build on `said` before finding out.

The other two rows are the "quiet is necessary and not sufficient" case again, beside the
unfinished-text markers. Every hit was read. The single bracket hit puts a two-letter tag in brackets
after a name, which is not an explanation of it. All 42 of the loose hits are co-occurrence, and they
fall into four kinds: two client or standards-body abbreviations in one configuration change, two
version numbers in one upgrade, two infrastructure abbreviations in one deployment change, and a run of
work-in-progress markers numbered in sequence. Not one is a writer explaining a term with a term.

The corpus is not publishable, so this belongs with the thresholds under "reproducible only with your
own data" in [measure/README.md](../measure/README.md) — the harness is here, its input is yours. What
it would take to overturn the second and third rows is a corpus where the same command finds hits that
survive being read one by one.

Shipping the sentence anyway would spend words on the one message in eight thousand that has the shape,
and be wrong on it. The two hops in the story stay two hops.

## Thresholds

The author cut and the share threshold, with the corpora behind them and what the measurement fails to
show: [thresholds.md](thresholds.md). `measure_thresholds.py` re-runs it on your own audiences.
