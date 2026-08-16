# Long negatives: prose that a check must not complain about

Five well-built fixtures already exist next door, and they are 56 to 102 words. That was enough while
every check reported on a word, a sentence or a paragraph. It is not enough for a check that reads a
whole document, because a message of 80 words has no opening segment to compare against a body — such a
check would pass all five trivially, measuring nothing, or fire on all five, which
[design-notes.md](../../../docs/design-notes.md) records as the failure that carries no information.

These six are 342 to 482 words, which is the band where an opening and a body both exist.

## Where they came from, and what that costs

They are commit messages from this repository's own history, written before the review that asked for
them. That matters in two directions and both are worth stating.

**Why they are usable.** They were not written to be fixtures, so they cannot have been shaped to pass a
check that did not exist yet. They were kept, which is the only evidence available that somebody
considered them good. And they already pass every shipped check, which is what a negative is for: the
question a negative answers is whether a NEW check fires on prose the tool currently accepts.

**What they cannot prove.** One author, one subject, one genre. A check that passes all six has been
shown not to fire on careful technical writing about this tool by the person who built it. It has not
been shown to leave alone a release note, a client-facing update, an incident summary, or anything
written by somebody else. A rule measured only here should say so where it is defined.

What would improve this set, in order: messages by other authors; messages with a reader who is not an
engineer; and messages that were sent rather than committed — a chat thread, a design document, a status
update — since a commit message has a conventional shape that flatters a structure check.

## Using them

`measure/measure_check.py` defaults to the short negatives. Point it here when what is being measured
reads more than a paragraph:

```
python3 measure/measure_check.py --negatives 'measure/fixtures/well-built-long/*.md' --negatives-only
```

`--negatives-only` skips the planted defects, which is what you want while asking the one question a
negative answers: does this check leave good prose alone. It spends one model call per file per rep.
