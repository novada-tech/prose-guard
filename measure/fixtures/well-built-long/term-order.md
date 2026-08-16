Flag a term used before it is explained, and drop the plan to split long text

Splitting a long document to check it a paragraph at a time was written into the last commit as the
obvious next step. It is measured and dropped. Pooled over eight runs of a 371-word document with a
fragment planted in it, the whole document caught the fragment twice in eight and paragraph-at-a-time also
twice in eight — no difference in what was found, nine times the model calls, and a complaint about prose
already judged well built in nearly every pass instead of one pass in five.

The reason explains the instability that started all this. These checks are comparative: asked about a
piece of text they report the worst thing in it, so a smaller piece does not sharpen them, it lowers the
bar for what counts as worst. The same check asked about one paragraph found nothing wrong three times in
three. `reference` asked about a paragraph alone found nothing in five runs, and asked about that
paragraph plus everything before it found something in three. `measure/measure_splitting.py` reproduces
all of it, and docs/reference.md now carries a table of which check needs how much context and why.

`reference` gains one concern, because it was only looking backwards. A term used before it is explained —
"the staged writer described below" — makes a reader either hold an undefined term or jump ahead, and that
was not flagged in three runs of three. It now is, three times in three, quoting the right span. The
destination decides: in a documentation page with headings that is normal navigation and passes, and the
same text in a chat message does not. Nothing new was flagged on the five documents already judged well
built.

Discovery no longer excludes writing a file, and excluding it was a mistake with a cost. The reasoning was
that the prose-file destination already decides which files count — but it claims a file only when the
file is TRACKED, and discovery is asked only about calls that nothing claimed. So the exclusion silenced
exactly the case that needed saying: a blog plan written to a directory that is not a git repository at
all went unchecked, and would now also have gone unmentioned. The mention is back on the third write, and
a tracked file in a repository is still claimed and checked rather than mentioned.
