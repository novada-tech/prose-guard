One bar for the guard and a deliberate run, and passes that scale on their own

`--passes` was a flag nobody would ever type, and the two callers had drifted into different rules: the hook
ran each check once and confirmed, a deliberate run pooled three. Those were the same mechanism all along —
running a check twice to see whether it repeats IS pooling with two runs.

So there is one function now. `passes_for(text)` gives two runs for a short message and up to five for a long
document, and both callers call it on the same text, so the same effort level means the same bar whichever
way the text is going out. Never fewer than two, because one run cannot tell a reliable finding from a
near-tie. A check that passes on its first run still costs one call: the extra calls are paid only where
something was found. `--passes` remains as an override for measuring.

The hook now sends one message carrying everything a check found, blocking only on what more than one run
pointed at. That pays one turn to fix several things instead of one turn each.

An abbreviation is not one term, so an audience records what each was written out as and by how many
people: `"LF": {"Linux Foundation": 3, "line feed": 2}`. The scan already found those pairs and discarded
them. Two recorded meanings means a message using the abbreviation without saying which is reported, and
writing it out silences that. A message that writes a known term out differently from the recorded sense is
reported the other way round. Which sense a message means where it never says is not decidable from the
text and is not guessed at.

Discovery reaches the person now. A hook has two channels and the docs are explicit that neither sees the
other: `additionalContext` goes to the model, `systemMessage` goes to the human. Discovery used only the
first, so a decision that belongs to the person was being offered only to an agent. It goes to both.

Two more from the same review. `echo "<a paragraph>"` was never recorded at all, because the shape function
wanted a flag — prose in a positional argument is recorded now, with the same prose test keeping grep
patterns out. And a misspelt effort level meant no checking with nothing said: `userConfig` has no
enumerated type, only string, number, boolean, directory and file, so `/plugin configure` offers free text
and "medim" was indistinguishable from off. It now says so, to the person, once a session. The bash
pre-filter had to stop swallowing that case for the message to arrive at all.

One reference point corrected rather than kept: one finding a pass is where a senior engineer's own rewrite
landed, and that is not a target. His writing is not perfect either and the bar is allowed to be higher.
