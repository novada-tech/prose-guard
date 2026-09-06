# The numbers that decide whether a message is held back

All measured, all here so they can be argued with.

## Author cut: 4 distinct people

How many people must have used a term before an audience is assumed to know it.

Breadth, not frequency. On the corpus this was first built on, one acronym appeared **149 times from
a single author** — one person's vocabulary, which a frequency threshold would have called shared
knowledge.

4 rather than 3 because a term the team lead said plainly needed explaining reached exactly 3
distinct authors on combined data. 3 would have exempted it.

## Share above which a finding is reported rather than enforced: 1/3

Not a count. A 2,000-word document using twenty acronyms with three unknown is a fixable oversight;
using twenty with fifteen unknown is the tool having the wrong reader in mind, and insisting then is
worse than saying so. So the measure is the share of the acronym-shaped terms the reader met that are
unknown to them.

Measured on two real audiences, each corpus scored against both, by `measure_thresholds.py` below.
2,763 issue and pull-request bodies from a public data-model repository written by 268 people, and 407
messages from a 20-person client-services chat channel.

| messages written for | scored for | zero unexplained | share p50 | share p90 |
|---|---|---|---|---|
| modellers | **modellers** | 84% | 0.00 | 0.33 |
| modellers | client-services | 51% | 0.00 | **1.00** |
| client-services | **client-services** | 69% | 0.00 | 0.50 |
| client-services | modellers | 69% | 0.00 | 0.50 |

The first two rows are the result: pointing the wrong audience at a message takes the zero rate from
84% to 51% and the 90th-percentile share from a third to everything. The audience mechanism
discriminates.

**1/3 is the 90th percentile of the right-audience share.** Above it, a message scored against the
audience it was written for is rare, so a finding above it is better explained by the audience being
wrong than by the message being wrong. At that threshold 90.5% of right-audience findings still block
and 34.7% of wrong-audience ones become advice.

### Two honest caveats

**Only one direction discriminates.** The last two rows are identical: client-services messages score
the same against either audience, because the terms they use are mostly in the shared baseline. The same
was true of a third corpus of engineering messages, 0.3 either way. So one direction sets this number
and the other three rows merely fail to contradict it. Two independent directions would have been
better evidence.

**The remaining 65% of wrong-audience findings still block, and that is intended.** They are mostly
one or two terms — a demand you can act on in a minute, whichever audience is right. The threshold
exists to stop unactionable demands, not to detect every misconfiguration. The `ALWAYS_ACTIONABLE`
floor of 2 terms is what keeps a 1-of-1 or 2-of-2 finding enforceable, since a share is meaningless
when almost nothing is in play.

## Words below which a model call is not worth making: 25

This is a floor on **spending**, not on checking, and it lives in `checks.MIN_WORDS_FOR_A_CALL`. The
two deterministic checks — `terms`, which asks whether the reader knows the words, and `mechanics`,
which finds a doubled word or `a` where `an` belongs — are arithmetic and cost nothing, so every
message reaches them whatever its length. Only the checks that spend a model call are capped away, and
`checks.worth_paying_for` returns that cap as an effort level, so the line the person sees names the
level that actually ran.

It cannot be a floor on checking, because the kind of message that is shortest is the commit message,
and that is the one kind nobody edits later. Across 4,282 commit messages from four repositories,
**80.8% are under 25 words**, median 8. A floor on checking leaves four commit messages in five with no
block, no note and nothing recorded — which is what four in five passing cleanly also looks like.

What comes through, on 3,425 held-out messages from that corpus, scored against a vocabulary learned by
the 4-author rule above from the oldest fifth:

| | short (2,719) | long (706) |
|---|---|---|
| mechanics | 0.11% | 0.42% |
| terms | 0.44% | 11.47% |

The short column is what a floor on checking costs, and it sits well inside the roughly 2% that the two
shipped mechanical rules set as the bar. Of those 15 findings, the 3 from `mechanics` are unarguable —
`"action action"`, `"a assignment"` — and the 12 from `terms` are only as sound as the audience, which
here is a deliberately thin one: see the caveat below.

## Where a term has to be explainable: the body, not the subject

A subject line is one line and has nowhere to put a gloss, so a term found only there is a demand
nobody can satisfy — the same shape as the `previous` rule in `checks/terms.py`, which subtracts terms
the version being replaced already used. Each kind of message this tool watches is declared in
`destinations.json`, and one of the things a declaration can say is `subject_line`;
`Context.where_an_explanation_fits` is what acts on it.

On the same 3,425 messages, **95 of 193 terms findings were carried by the subject alone** — `Fix CVE
failures`, `Remove DRR if syntax`, `Updated testing pom to allow J17`. Scoring the body instead removes
exactly those, and takes terms on the messages that were already being checked from 14.87% to 11.47%.
`mechanics` still reads the whole message, because a doubled word in a subject is fixable where it
stands, and its rate does not move.

Two thirds of commit messages — 66.1% of the 4,282 — have no body at all, so `terms` says nothing about
them. That is the intended reading of a message that is all subject. The case it gives up is a long
message written on one line, which is 0.19% of the corpus; a rule to catch those would be a special
case bought with eight messages.

### The caveat on both numbers

The vocabulary above is learned from commit messages, and `learn.py from_git` says in its own docstring
that they are a thin corpus: 857 of them yield one term past the 4-author cut, and learning from four
times as many yields seven. So `terms` here is scored against an audience that knows almost nothing
beyond the shipped baseline, and it flags `CVE`, `FINOS` and `XSD` accordingly. A real audience, measured
from chat and pull requests, knows those words. **These terms rates are therefore ceilings that a
configured audience only moves down, and that has not been measured** — the only audience available to
measure it against is a private one.

## Re-running this

`measure/measure_thresholds.py` takes two corpora of `{"author": ..., "text": ...}` lines and prints the
table above for your own audiences. Worth doing if your writing looks unlike either corpus here.
