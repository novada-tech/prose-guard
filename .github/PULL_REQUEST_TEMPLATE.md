<!--
CONTRIBUTING.md is the whole convention and this is only its shape. Read it there: it carries the
commands, what each measurement costs to run, and the scores a check has to reach.

Delete any heading below that does not apply to your change, and say why it does not.
-->

## What changes, and for whom

<!-- The defect or the goal, in a sentence or two. What somebody using this notices afterwards. -->

## The numbers

<!--
Quote the command that produced each figure, so a reviewer can re-run it. Quote the before as well as
the after.

If you could not measure something, say so. An unmeasured change with an honest note is reviewable; an
unmeasured change presented as safe is not.

Which measurement your change owes is in CONTRIBUTING.md, along with what each one costs to run.
-->

## The mutation

<!--
What you broke to prove the test would have caught this, and which case went red. A test written after a
fix pins the fix; a test written before pins the defect.

Add it to the list in docs/design-notes.md.
-->

## Checked

- [ ] `python3 tests/test_prose_guard.py` and `python3 tests/test_docs_match_code.py` both pass, checked
      by their exit code rather than their last line
- [ ] Anything under `plugins/` moved the version in **both** `plugins/prose-guard/.claude-plugin/plugin.json`
      and `.claude-plugin/marketplace.json`
- [ ] Nothing here came out of `~/.config/prose-guard/` — no measured vocabulary, no real message, no
      channel or customer names. This repository is public.
