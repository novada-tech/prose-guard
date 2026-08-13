# measure

The harnesses [CONTRIBUTING.md](../CONTRIBUTING.md) asks you to run. None of them is part of the
plugin and nothing at runtime imports them.

| | |
|---|---|
| `measure_check.py` | does a check catch planted defects **and** pass ordinary prose, and how often does it disagree with itself |
| `measure_cost.py` | what a level costs the person using it, against a control in the same run |
| `measure_rule.py` | does a change to `rule/` change what the agent writes |
| `measure_thresholds.py` | re-derive the author cut and the share threshold on your own audiences |
| `fixtures/well-built/` | ordinary messages every check must pass |
| `fixtures/one-reader/` | messages whose correctness depends on having a single addressee |

Standard library only, like everything else here. All except `measure_thresholds.py` spend real
tokens, which is the point: a cost measurement that costs nothing is measuring nothing.

They are **not** in continuous integration for that reason. CI runs the two deterministic suites
under `tests/`, which make no model calls at all.

## What you can and cannot reproduce

Worth being exact, because several numbers quoted in
[docs/design-notes.md](../docs/design-notes.md) are not re-runnable by anyone but their author.

**Reproducible here, by anyone.** The check-discrimination table, the per-level cost table, and both
test suites. The fixtures they need are in this directory.

**Reproducible only with your own data.** The author cut and the share threshold. `measure_thresholds.py`
is here; the two corpora it was calibrated on are not, and one of them is a private chat channel. Point
it at your own audiences and you will get your own numbers, not a check of ours.

**Not reproducible at all.** The deadlock finding, the freezing finding, and the 50–70% figure for how
often a judgement check agrees with a provenance label. Those harnesses were never contributed. The
findings stand as records of what happened, not as results anyone can verify, and they are labelled that
way where they are quoted.

## Instruments deliberately absent

Four measuring tools were built and then refuted. They are not here, because a refuted instrument in a
repository is worse than none: someone will use it.

- **A pairwise judge**, asking a model which of two messages is better. Measured verbosity bias of
  +0.200 — it prefers the longer text — and at chance on equal-length pairs. It was validated against a
  set that every judge passes, which was never a test of the thing it was being used for.
- **Syntactic complexity metrics**: dependency depth, clauses per sentence, subject-verb distance,
  words before the verb. The hand-written target text scored *worst* of everything measured on all of
  them. Clause counts and words-before-verb were at chance, 53%, against published expert rewrites.
- **A regex prose linter** that flagged long or nested sentences. It pushed sentence fragments from 2.2%
  to 6.1% by rewarding chopping, because non-judgemental feedback about a sentence's shape is best
  satisfied by breaking it.
- **A per-turn placement**, running the checks after every assistant turn rather than on the way out.
  3.4× the wall clock and 2.9× the tokens of the same task, for prose nobody was sending.
