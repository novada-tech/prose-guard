Pool several runs of a check instead of asking it for a list

Both objections to one-finding-per-pass hold. A 100-word document and a 1,000-word one each get one item
per check per pass, so the long one is held to a lower bar for the same number of passes. And each pass
costs a round trip — an agent turn spent reading a finding and editing — which is dearer than the check's
own call.

Asking for a list does not fix it, and that is measured rather than assumed. On a 295-word document with
about ten known defects, every check asked for up to five items returned exactly one, identical to asking
for one. `measure/measure_batching.py` reproduces it. The single item is what the check does, not a
contract that can be widened.

What varies between runs is WHICH item, and that is the fix. `--passes N` runs each check N times and pools
what they find: N calls, one round trip. On that same document one pass found two findings and three pooled
runs found six across four checks, including two checks that were silent in the single pass — and the six
are the same things a hand-driven rewrite took eleven sequential passes to find. Each item reports how
often it came up.

Pooling and confirming want opposite things, so they are separate modes. The hook blocks, so it confirms
and shows one item: precision. A rewrite pass pools, because on a document with real defects an item seen
once in three runs is a different real defect rather than noise, and confirmation would discard it. The
rewrite skill asks for three passes now.

check_prose also reports the count and whether it is falling, which is the only stopping rule available.
Five passes per document rather than three, which changes the numbers reported last time: a message an agent
wrote scores 2.2 checks a pass, the same content after a senior engineer rewrote it 1.2, and a document
through six rounds 0.2. Zero is reachable after all — the last one hit it in four passes of five. What zero
is not is what a good first draft scores: one finding a pass is where a good writer lands, so a text
sitting there is not unfinished.

One pass in isolation once put the human-edited version above the agent-written one. The spread is about
plus or minus one, so a single pass is not a measurement, and the docs say so now.
