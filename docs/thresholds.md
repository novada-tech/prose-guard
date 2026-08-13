# The two numbers that decide whether a message is held back

Both are measured, both are on one corpus, and both are here so they can be argued with.

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

## Re-running this

`docs/measure_thresholds.py` takes two corpora of `{"author": ..., "text": ...}` lines and prints the
table above for your own audiences. Worth doing if your writing looks unlike either corpus here.
