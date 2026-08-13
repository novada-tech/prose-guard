---
name: learn-vocabulary
description: Measure which technical terms and acronyms the user's audience actually shares, from writing that audience has already done, and write it to prose-guard's vocabulary. Use when the user wants prose-guard to stop flagging their house vocabulary, asks to learn or update the vocabulary, or asks why a term they all use is being flagged.
---

# Measuring what this audience already knows

The point is to stop the term check guessing. Until a vocabulary is measured it reports unexplained
terms as advice; afterwards it holds them back, because then it has evidence.

**Author breadth, not frequency.** One person's favourite acronym is not shared knowledge however
often they type it — on the corpus this was calibrated against, one term appeared 149 times from a
single author. Every source must therefore carry an author. The cut is 4 distinct people.

## 1. Ask what to read

Suggest these in order of how much they yield, and let the user pick. Nothing leaves their machine.

- **Their repositories' issues, pull requests and review comments** — the best source by far,
  because a review comment is written to a colleague and so uses exactly the shared vocabulary.
  Needs the `gh` CLI, already logged in.
- **Commit messages** — free and present in every repo, but thin: few people put acronyms in a
  commit subject, so this alone will under-measure.
- **Any prose they can export** — chat history, a wiki, meeting notes. Text with no author counts
  as one voice, which stops it reaching the threshold on its own.

Ask which repositories, rather than guessing. The audience is the people who write in them.

## 2. Scan

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/vocab.py" scan \
  --gh OWNER/REPO --gh OWNER/OTHER --git . --out /tmp/candidates.json
```

It prints three piles: reached the cut, sitting one author short, and below that.

## 3. Bring them only the middle pile

The first and third piles need no human. The borderline pile is the whole reason this is a
conversation: one author short of the cut is exactly where the count cannot decide.

Show the borderline terms with their use counts and ask, in one message rather than one at a time,
which of them everyone in their audience would already understand. Say plainly what each answer
costs them: a term wrongly marked known means messages go out with it unexplained; a term wrongly
left out means the guard asks them to explain something everybody knows.

If the list is long, say so and offer to take the top ones by use count and leave the rest — being
wrong here is cheap and reversible, and `known-terms.txt` takes a term at any time.

## 4. Apply, and show them the file

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/vocab.py" apply /tmp/candidates.json \
  --also-known TERM1 TERM2 --not-known TERM3
```

Then read the written `vocabulary.json` back to them — it is theirs to edit, and a term added by
hand needs no rerun.

## 5. Tell them what changed

Unexplained terms are now held back rather than reported as a guess. Re-run this whenever the
vocabulary moves; nothing does it automatically.

## When someone disagrees with a single flag

They do not need this skill. One line, and it applies immediately:

```
python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/lib'); \
import vocabulary; print(vocabulary.accept('TERM'))"
```
