# Working on prose-guard

[CONTRIBUTING.md](CONTRIBUTING.md) is the mechanics: how to run the suites, when to bump the version,
what a pull request needs. This is how to make a change that belongs here, and it is written down
because most of it was learned by getting it wrong first.

## Nothing ships on an argument

Every rule in this repository arrived with a number: hit counts on real text, before and after. That
is not ceremony. Four mechanical rules were dropped for flagging a third of everything written, and
the only way anybody knew was by counting.

So before adding a check, a rule or a threshold, measure it on prose already judged good — and expect
to drop it. Recent examples, all in [docs/design-notes.md](docs/design-notes.md): passive voice fires
on 22.8% of this repository's own documentation; a heading-skeleton rule on 19.7% of 742 markdown
files; unfinished-text markers were quiet at 0.05% of 1,897 real commit messages but produced **not
one true positive**, so they did not ship either. Quiet is necessary and not sufficient.

The bar the two shipped mechanical rules set is about **2% of messages**, with every hit a true
positive. `measure/measure_check.py` scores a model-based check in both directions and reports how
often it disagrees with itself. Corpora that cost nothing and are already here: this repository's own
markdown, its commit messages, and the fixtures under `measure/fixtures/`.

When a measurement contradicts a plan, the measurement wins and the plan goes in design-notes as
something that did not survive. That file is as valuable as the code.

## Fix by reducing

A finding is a symptom. Look for the missing abstraction underneath it before writing a guard.

Worked examples from one review: config values failing open at six call sites were one missing
declaration (`lib/settings.py`); five hand-rolled "say this once" mechanisms were one ledger
(`lib/telling.py`); six modules each holding a fact about Claude Code were one module (`lib/host.py`).
Each deleted more than it added, and each closed findings nobody had reported yet.

If a fix genuinely must add code, add it in one place rather than at every caller, and say in the
commit why the reducing version was not available.

Then **finish the sweep before claiming the class is closed.** `lib/settings.py` was introduced for
`config.json` and `destinations.json`, the review comment said every reader went through it, and the
third one did not — a hand-edited audience file of the wrong shape crashed the hook, which allows the
call, for months. When you route one caller through a new abstraction, grep for the rest in the same
commit and say in the message which ones you found and why any are exempt.

## The failure that matters most is silence

This tool holds messages back. Every failure path allows the call, which is right — a broken writing
check must never block outbound work — and it means **a check that stopped working looks exactly like
a check with nothing to say**. Most of the worst defects found here were that shape:

- an unreadable phases directory silently dropped the effort level from `high` to `low` — five
  checks fewer, no model calls, and nothing said about either
- `git commit -F - <<EOF` went out unchecked and unmentioned, 151 times in a real corpus
- a `bash` pattern that did not compile crashed the hook, and a `PreToolUse` hook that exits non-zero
  lets the call through
- a never-configured install was silent forever, so working correctly and being broken were identical

So when you change a path that can fail, ask what somebody sees when it does. If the answer is
"nothing", that is the defect. `lib/telling.py` is how something gets said once without nagging.

**`systemMessage` is a sibling of `hookSpecificOutput`, never a field inside it.** Nested it is
well-formed JSON that Claude Code discards, and for this tool's whole life every transparency line went
out that way — the level, the audience, the rewrite count, the checks that could not run. The hook
exited 0, the JSON parsed, and nine tests agreed with the code because they read the field back out of
the same wrong place. Asserting a value you just set, from where you set it, proves only that you agree
with yourself: read what a real run printed, and check where the field sits, not that it exists.

## Write the test that would have caught it, and watch it fail

Before the fix, not after. A test written after a fix pins the fix; a test written before pins the
defect.

Then break it deliberately — invert a boundary, drop a filter term, return `None` early — and check
the suite goes red. A survivor is a finding. A recent audit ran 152 mutations for 149 catches, and
the three survivors each came with a proof that they were equivalent rather than a gap.

Two traps this suite has actually fallen into:

- **Vacuous assertions.** `{... for p in phases if p.advises} <= {ADVISE}` is true when nothing
  advises. Name the thing rather than filtering for it.
- **Reading the developer's own config.** The suite points `PROSE_GUARD_HOME` at a temporary directory
  at import, before anything else runs. Do not undo that; a developer with their own audience once
  failed 33 of 71.

Check the exit code, not the last line. `python3 tests/... | tail` exits with `tail`'s status, and
three failures have been committed that way.

## Do not restate a number

A count written in two places is wrong in one of them eventually. `high` ran five phase checks while
eight places said four; `reference.md` said twelve model calls where the code said twenty and said
twenty itself three hundred lines later.

Derive it, or point at where it lives. `sequence.py` states no count at all — a phase is a file. When
prose must carry a number, put it in one place and link the rest.

`tests/test_docs_match_code.py` checks every documented command against the real interface, in both
directions, including flags named only in a sentence. If it fails, the documentation is wrong, not the
test — unless the test itself has a gap, which has happened twice and is worth fixing there.

## Heavy comments are the point

Much of what reads as over-explanation is a recorded measurement or a rejected alternative. That is
this repository's memory and it is not clutter to strip. What *is* worth removing is the same
rationale in three places, because copies drift and then nobody can tell which is current.

One home per explanation, and links from anywhere else. When you change code that a comment describes,
change the comment in the same commit — prose that has drifted from its code is a correctness problem
wearing a comment's clothes.

## No history

State what is true. Never what used to be true.

"This used to be X", "earlier versions did Y", "that was true before" — none of it belongs in code,
documentation or a skill. A reader arriving today has to carry the old design through the new one to
understand either, and the note is stale from the commit after the one that added it. It is worst in a
skill, where the audience is a model that will faithfully act on the version it read last.

That is not the same as the rationale above, which stays. **A rejected alternative is a fact about the
design; a superseded implementation is a fact about the repository.** "Splitting a long document was
measured and finds no more, at nine times the calls" tells the next person not to try it. "The notice
used to fire on the first tool call" tells them nothing they can use.

Where the old shape genuinely explains the new one, `git log` is where that lives, and
[docs/design-notes.md](docs/design-notes.md) is where a design that did not survive a measurement goes.

## Commit messages carry the evidence

One coherent change each, subject saying what changes for a user rather than what was edited, body
carrying the measurement. `git log` is where the reasoning lives, and several of the fixtures under
`measure/fixtures/well-built-long/` are commit messages from this repository's own history.

## Before you finish

```
PROSE_GUARD_HOME=$(mktemp -d) python3 tests/test_prose_guard.py; echo "exit=$?"
python3 tests/test_docs_match_code.py; echo "exit=$?"
```

Never run anything under `measure/` casually — those spend real model tokens, and one harness rewrites
prompt files in place. Run one deliberately when a change needs a number, and put the number in the
commit.

Do not touch the user's `~/.config/prose-guard/`, and put nothing from it in a commit, an issue or a
pull request. This repository is public.
