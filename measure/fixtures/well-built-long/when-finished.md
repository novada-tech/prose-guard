Measure whether a text can ever be finished, and report that it cannot yet

Asked how you would ever know a text is done, if a comparative check always reports the worst thing it can
find. The answer needed measuring, and it is not the reassuring one.

`measure/measure_stopping.py` runs all five comparative checks over three real documents: a message an
agent wrote, the same content after a senior engineer rewrote it the same day for the same readers, and a
long document already taken through six rounds of this tool. Findings that survive being put back to the
same check, per pass, three passes each:

    agent-written    68 words    2.0 confirmed    1.3 raised once only
    human-edited     44 words    1.3 confirmed    0.0
    heavily edited  371 words    0.7 confirmed    0.3

The order is right, so the count measures relative quality. But the human-edited version never scored
zero. A colleague's own writing, for his own readers, draws one or two confirmed findings a pass — so
"nothing confirmed" is not a finished signal, because good prose does not reach it. The stopping rule is
that the count stops falling, and a reader who disagrees with a confirmed finding is allowed to be right.

Calibrating the bar means tuning until the human-edited version passes and the agent-written one does not.
That needs more before-and-after pairs than the one now in `measure/fixtures/gold`, and from more than one
author: tuning five prompts against a single pair would fit the pair rather than the bar. The pair and the
harness are contributed so the next person can add to them instead of starting over.

Also settles whether a check should return a list instead of one item. The contract is one line, and
asking the sentence check for up to three items returned exactly one on every document tried, good and
bad. So the single-item contract costs no coverage, and the reason to keep it is separate: for a
comparative check the second-worst item is by construction nearer the bar than the first, which is where
false positives would concentrate.
