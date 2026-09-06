# measure

The harnesses [CONTRIBUTING.md](../CONTRIBUTING.md) asks you to run. None of them is part of the
plugin and nothing at runtime imports them.

| | |
|---|---|
| `measure_check.py` | does a check catch planted defects **and** pass ordinary prose, and how often does it disagree with itself |
| `measure_cost.py` | what an effort level — how many checks run before a message goes out — costs the person using it, against a control in the same run |
| `measure_rule.py` | does a change to `rule/` change what the agent writes |
| `measure_thresholds.py` | re-derive the author cut and the share threshold on your own audiences |
| `measure_advice.py` | is advisory feedback ever acted on, and would an agent act if it arrived in time |
| `held_drafts.py` | build a corpus out of the messages this machine has actually held back |
| `measure_gate.py` | could the one cheap question stand in for the six expensive ones — it cannot, 4/8 recall |
| `measure_silence.py` | of the calls each destination claims, how many does it ever find the words in |
| `measure_explanation_chain.py` | is one unexplained term ever the writer's attempt to explain another — it is not |
| `fixtures/well-built/` | ordinary messages every check must pass |
| `fixtures/one-reader/` | messages whose correctness depends on having a single addressee |

Standard library only, like everything else here.

Most spend real tokens, which is the point: a cost measurement that costs nothing is measuring nothing.
These read what is already on the machine instead, and ask no model at all:
`measure_thresholds.py`, `held_drafts.py`, `measure_silence.py`, `measure_explanation_chain.py` and
`measure_advice.py --transcripts`.

The four that read past conversations:

```
python3 measure/held_drafts.py --out /tmp/held.json     # the messages this machine held back
python3 measure/measure_advice.py --transcripts          # was advice ever acted on: 41 given, 0 acted on
python3 measure/measure_advice.py --probe /tmp/held.json # would an agent act if it could. Spends tokens
python3 measure/measure_silence.py --unique   # per destination: claimed, checked, never a word found
```

`held_drafts.py` keeps message text, unlike everything else here — that is what makes it a corpus.
Write it somewhere temporary and do not commit what comes out.

`measure_gate.py` wants positives — real messages that were held — as JSON holding `{"body": ...}`:

```
python3 measure/measure_gate.py --held /tmp/held.json --reps 2
```

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

The same goes for the explanation chain. `measure_explanation_chain.py` is here and costs nothing to
run; the four private repositories it was run against are not, so what you can reproduce is the
question and not the answer. Its answer, and what would overturn it, are in
[docs/design-notes.md](../docs/design-notes.md).

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
