# Reference

Detail that would get in the way of [the README](../README.md). Read it when you
need it.

## Spelling and grammar

Two mechanical rules run at every level, free and instant: a word typed twice, and `a` where `an`
belongs. Measured on 3,000 real messages they produce 62 findings, about 2%, and nothing at all on the
five documents already judged well built. Both are objective and both are a one-word fix, so they hold a
message back rather than mentioning it.

Four more rules were tried and dropped, with the numbers: space before punctuation (1,131 hits, almost
every one a line break before a full stop), stray punctuation (592), no space after punctuation (512,
mostly URLs and version numbers), unbalanced brackets (498, mostly brackets spanning lines). Together
they flagged a third of everything written.

Grammar in general is not checked, and a third-party checker was measured rather than dismissed.
LanguageTool 6.6 locally: 240MB to download, 390MB unpacked, Java, 1.6 seconds a run. It found nothing on
the sentence that prompted the question — a fragment with no main verb — nor on three other fragments
tried. It caught word repeats and `a`/`an`, which are already here, plus subject-verb agreement, which is
one rule more. On prose judged well built it flagged four documents of six, mostly its spell checker
firing on technical terms, which is the noise a measured vocabulary exists to prevent.

The fragment class is caught by the checks that already exist, when the text is short enough. Asked about
that sentence on its own, `structure` found it in three runs of three and `sentence` in two of three. It
got through inside 370 words.

Checking long text one paragraph at a time was the obvious fix, and it was measured and dropped. Pooled
over eight runs of a 371-word document with that fragment planted in it, the whole document caught it
twice in eight and so did paragraph-at-a-time — no difference in what was found, nine times the model
calls, and a complaint about prose already judged well built in nearly every pass instead of one pass in
five. Reproduce it with:

```
python3 measure/measure_splitting.py --reps 5
```

The reason is worth knowing, because it explains the instability above as well. These checks are
comparative: asked about a piece of text they report the worst thing in it, so a smaller piece does not
sharpen them, it lowers the bar for what counts as worst. Asked about one paragraph the same check found
nothing wrong 3 times in 3, and asked about the paragraph plus everything before it, `reference` found
something 3 times in 5.

The split that matters is not how much text a check sees. It is whether the check is **absolute** or
**comparative**.

`mechanics` is absolute. A word typed twice is wrong whatever surrounds it, so the size of the text makes
no difference to the verdict — it runs on whatever it is given and finds every instance, not the worst
one. That is also why it is stable enough to hold a message back on its own.

Everything else is comparative: each reports the worst instance of its concern in what it was shown. That
is why they need the whole document, and why a smaller piece does not sharpen them.

A rule for missing spaces between sentences was tried on the same evidence and is not here. Tightened to
a real sentence boundary — lowercase, full stop, capital, lowercase — it hit 21 times in 3,000 messages,
and every hit was machine text: GitHub notification footers ("mentioned.Message ID:"), a Java import
path, a filename with dots. Not one was a person's missing space. The looser version hit 494 times, all
of them filenames and abbreviations.

## What it does when it disagrees with you

It names one problem and hands the message back. It does not rewrite: a check that rewrites cannot
tell you what it disagreed with.

And it stops insisting when it is probably the one that is wrong. Severity depends on the **share** of
the terms you used that are unknown to your reader, not the count — three unknown out of twenty in a
long document is an oversight worth fixing, fifteen out of twenty means the tool has the wrong reader
in mind. Above a third it says so instead of demanding twenty explanations. That threshold is the 90th
percentile of the share seen when a message *is* scored against the audience it was written for,
measured both directions on 3,170 real messages: [docs/thresholds.md](docs/thresholds.md), including
what the measurement fails to show.

Three limits keep that bounded. Each check gets two attempts. A session gets six holds in total, and
twelve model calls. Past those, everything turns advisory — so two checks that genuinely disagree make
one message expensive and then let it through, rather than hanging your turn.

## What counts as sending

Chat, GitHub and GitLab comments and descriptions, documentation pages, issue trackers, **`git commit`
and `git tag -m`**, and prose files inside a git working tree that are not ignored.

That last rule replaces matching on `.md`. What matters is whether somebody other than you will read
the file, and "it gets committed" is a deterministic proxy — so your README is checked and your scratch
notes are not.

Two gaps, stated rather than hidden, and one that used to be a gap.

`git commit` with no `-m` opens an editor, and that text never reaches a tool call. Nothing can be done
about that from here.

The plumbing — `git commit-tree`, `filter-branch --msg-filter`, `filter-repo` — is not matched, because
those rewrite text somebody else wrote, usually in bulk, which is not the act this checks.

`--body "$(...)"` used to pass in silence. The destination matches, the prose is a shell substitution the
tool call does not contain, and nothing was checked — which reads exactly like a check that passed.

Most of those are now worked out rather than complained about, because asking somebody to restructure a
command that already works is a poor trade:

| written as | what happens |
|---|---|
| `--body "$(cat notes.md)"`, `$(< notes.md)` | the file is read. No command runs |
| `--body "$(git log -1 --format=%B)"` | run, and the output is checked |
| `--body-file notes.md` | read, as it always was |
| `--body "${SUMMARY}"` | **held back**. A hook is a separate process and never sees your shell variables |
| `--body "$(anything-else)"` | **held back**. Running it to find out would fire it twice |

The whitelist is narrow on purpose. Only git subcommands that report, and not even all of those
unconditionally: `git log --output=FILE` writes a file, so a flag that can write is refused. Chaining is
prevented by running the command as a list of arguments with no shell, so `;` and `&&` reach git as
arguments and git rejects them.

What is held back is held back rather than mentioned, because advice was tried first and was not enough:
the pull request that introduced the note went out unchecked while the note explained, afterwards, that
it had. Bounded at two like every other denial, then said as advice, so a caller that cannot comply is
not stuck. And "resolved but too short to judge" is silent — that is not a gap, and sending someone to
fix a working command would be noise.

All of it is per destination without naming any: both halves read the destination's own `text_arg`, so
`git commit -m "$(...)"` and `glab mr note --message "$(...)"` behave the same, and one added later does
too. And the plumbing — `git commit-tree`,
`filter-branch --msg-filter`, `filter-repo` — is not matched at all, deliberately: those rewrite text
somebody else wrote, usually in bulk, which is not the act this checks.

**Your tools are not mine**, so setup asks rather than assumes. `lib/discover.py` reads four local
sources — MCP servers you have configured, outbound command-line tools on your `PATH`, how often each
appears in your **shell history** (much better evidence than "installed"), and anything that has
already gone out unchecked. Then the agent names the tools it can actually see, proposes destinations,
and waits for you.

You will install something new next month, and the guard notices on its own: when nothing claims a
You see these, not just the agent. A hook has two channels — `additionalContext` reaches the model and
`systemMessage` reaches the person, and the docs are explicit that neither sees the other. Discovery used
only the first, so a decision that is yours was being made available only to whatever agent happened to be
running. It goes to both now: you see the notice, and the agent knows enough to offer to act on it.

For every call carrying outgoing prose it records the *shape* — `bash: git commit -m`, `tool: example__post
[body]` — never the text. It mentions it **once**, on the third use, and never again. Decline and it is
declined for good, so nothing can nag you twice about the same thing. At most 50 shapes are tracked.

Long is not the same as outgoing, and getting that wrong is expensive: one mention per shape means a
mention spent on a search pattern is a mention gone. In real use it spent all six of them on nothing —
`git grep -E` with a long alternation, the text an `Edit` replaces, an `Agent` prompt, a `Write` to a
file the prose-file destination already decides on. So a candidate now has to read like prose: at least
25 words, at least two sentences, and at least 70% ordinary words. A regex has words and no sentences; a
script has punctuation and few real words. Fields that are structurally not outgoing — `old_string`,
`prompt`, `command`, `pattern` — are skipped whatever they contain, and the file-writing tools are left
to the destination that already claims prose files.

## Not every destination is worth the same effort

A destination can cap two things, for two different reasons.

**`max_effort` — the questions do not apply here.** The commit message caps at `low`: the term check
only, whatever you have configured. Not because it is expensive. Measured across all eight destinations
on the same 77 words of well-built prose, three runs each, every one costs about 15 seconds and 5 model
calls — the cost is in the phases and the phases do not care where the text is going. There is no such
thing as an expensive destination.

What varies is whether the questions apply. The phases ask whether this reader will care and whether the
ask is clear. A commit message has neither an addressee nor an ask; it is read years later by somebody
finding out when a line changed. The term check still applies, because an acronym nobody expands is
exactly as unhelpful in a permanent record as anywhere, and it costs no model call and a tenth of a
second.

**`max_severity` — nothing is about to reach anyone unreviewed.** A draft is its own destination and
caps at `advise`. Blocking is justified by text being about to reach a reader with nobody in between;
`slack_send_message_draft` lands in your own compose box, so it has a reader already, and holding it
back spends a turn arguing about text you were about to read. The finding is identical either way — the
destination changes what is done about it, never whether the tool noticed.

Reproduce the cost table with:

```
python3 measure/measure_destinations.py --effort high --reps 3
```

False positives were rare: one complaint in 24 runs over text already judged well built. So neither cap
is there to quieten a noisy check.

Both fields work on any destination, and your own `destinations.json` is read before the shipped one, so
changing either is a two-line file.

They also change what discovery asks. Adding a destination used to be yes or no, which meant everything
discovered ran at full effort and could block — the wrong default for exactly the two cases only a person
can judge. `discover.py` now prints a suggested cap per candidate, with its reason, where the name is
evidence: a shape saying draft or preview suggests `advise`, and `git commit`, `git tag`, `git notes` or
a changelog suggests `low`. Suggestions only. Applying one unasked would quietly stop a destination
holding anything back, and a first version of this heuristic did exactly that to `glab mr note`, which is
a comment on a merge request and has a reader.

## When the words were already there

A term the previous version already used is not a term this text introduces, so it is not held against
you. Amending a commit message compares against the message being replaced; editing a document compares
against the file on disk, which at that moment still holds the version being replaced.

This exists because of a job nobody could finish otherwise. Someone was asked to scrub a client's name
out of published commit messages, which meant reproducing each one verbatim apart from that name — and
the guard blocked the amend over two acronyms the original author had written a year earlier. No edit
could have cleared it. It is per term, not per command: an amend that introduces a term the old message
did not have is still checked.

It reads the repository rather than believing the caller, so it is not a way to wave anything through.

## Excusing one command

```
PROSE_GUARD_SKIP="republishing a message I did not write" git commit --amend -m '...'
```

For the cases the rule above does not cover. It applies to the command it is written on and nothing
else — there is deliberately no way to turn the check off for a session, because that is the switch that
gets left off, and the absence of complaints reads exactly like clean prose.

The reason is required. Nothing checks whether it is a good one; requiring it means writing a sentence
somebody reads later, which is a different act from flipping a switch. `PROSE_GUARD_SKIP=1` is refused.
Each use is echoed back, counted, and after the third the tool points at `/prose-guard:audiences`, which
is the fix that lasts when the check is wrong about a term in general.

## One message, two audiences

Audiences overlap, and a channel can hold two of them. Combining is one operation per dimension:

| dimension | combinator | why |
|---|---|---|
| vocabulary | intersection | only what everyone knows is safe to leave unexplained |
| shared context | minimum | assume the least-informed reader |
| reach | maximum | the widest reader decides whether internal links resolve |

Measured on two real audiences — 268 people on a public data-model repository, 20 in a client-services
channel — intersecting costs 103 of the modellers' 220 terms and leaves 117. It does not collapse,
because both inherit the same baseline and that floors the intersection.

There is deliberately **no subset elimination**. Dropping an audience whose members sit inside another
looks like a free simplification and is not sound: breadth measured in the larger group does not imply
every member knows the term, and dropping an audience only ever widens the vocabulary. A test pins it.

Exact overlap between audiences is **not computable**, and the tool says so rather than pretending. A
chat export names someone "Sam"; a repository names the same person "sam-t". A plain
intersection reported zero shared members while ten people were in both, so `overlap` prints a
prefix-matched guess, labelled as one, and nothing depends on it.

## Findings have to reproduce

Every finding from a model-based check is put back to the same check, and kept only if it objects to the
same sentence. One extra call for a check that fired, nothing for one that did not.

This exists because the rewrite loop did not terminate. On one 370-word document already through six
rounds of editing, ten runs of the five model-based checks gave one clean result and nine findings, with
no finding raised twice — `reference` objected on every run and to a different sentence almost every
time. Past the substantive problems, the checks generate nits, and chasing nits is work with no end. With
confirmation, four runs of that same document reported nothing to act on.

Unconfirmed findings are still printed, under a heading that says not to chase them. `--unconfirmed`
turns the filter off and costs less.

Confirmation filters the symptom. The cause is that two runs choose differently between near-equal
candidates, and the checks that point at a span now say to quote the earliest failing one rather than the
most interesting. On the document that produced no repeated finding at all in ten runs, that took
agreement between two runs from nothing to about two in five — so a real finding survives confirmation
instead of being filtered with the nits.

That instruction is deliberately not on `relevance` or `address`. Neither reports a span — one asks what
is missing and the other who is being spoken to — and telling them to quote the earliest failing span
changed what they looked for, which showed up immediately as findings on fixtures that had been quiet.

Three of five well-built fixtures produce a finding on a single run of all five checks. With confirmation,
two of those three report nothing to change, and the third reproduces — which is the point: what survives
is worth reading.

## One abbreviation, two meanings

An audience records what each term was **written out as**, and by how many people, alongside the count of
people who used it:

```json
"expansions": { "LF": { "Linux Foundation": 3, "line feed": 2 } }
```

The scan already found `Long Form (SF)` pairs and used to discard them. A count of authors cannot tell
Linux Foundation from a line feed, and both are LF.

Two recorded meanings is the audience telling you the abbreviation is overloaded for them, so a message
using it without saying which is reported. Writing it out silences that — the reader can tell, whatever
else the abbreviation does elsewhere. And a message that writes a known term out differently from the
recorded sense is reported the other way round: "ADC is written out here as air data computer, and this
audience has it as application default credential."

What is deliberately not attempted: deciding which sense a message means where it never says. That is not
decidable from the text, and guessing would be worse than saying nothing.

## One finding at a time, and what to do about it

A check returns exactly one item, and that is not a contract that can be widened. Asked for up to five
items on a 295-word document with about ten known defects, every check returned one — the same as asking
for one:

```
python3 measure/measure_batching.py --reps 3
```

So the objection holds: a 100-word document and a 1,000-word one both get one item per check per pass, and
the long one is held to a lower bar for the same number of passes. And each pass costs a round trip, which
is an agent turn spent reading a finding and editing — dearer than the check's own call.

What varies between runs is WHICH item, and that is the fix. Each run picks one item from those above the
bar, so runs sample items — and how many runs is decided by the text, not by a flag.

**A check keeps running while its runs keep finding something new, and stops when a run adds nothing.** One
run that adds nothing is tolerated, because a run repeating itself does not prove the well is dry and
stopping at the first repeat loses whatever came after it. Two in a row stops it. So a document with ten
real defects is not cut off at the same point as a clean one — which a fixed number of runs did.

The ceiling is linear in length above a base of six, because a longer document has more places to be wrong:
6 runs up to 600 words, 9 at 800, 21 at 2,000, and 25 as a hard bound so one pathological file cannot spend
a session. The base is on the ceiling and not on the runs — a 44-word message capped at two runs could
never be observed to run dry, so length decided everything and quality decided nothing.

What that costs, measured per document over every check:

| document | words | calls | items found |
|---|---|---|---|
| badly written | 295 | 14 | 5 |
| well edited | 371 | 8 | 2 |
| agent-written | 68 | 11 | 3 |
| human-edited | 44 | 10 | 3 |

The badly written document spends most and the well edited one least, at a similar length. A check that
passes on its first run costs one call, so the extra calls are paid only where something was found.

The hook and a deliberate run call the same function on the same text, so they cannot drift apart: one bar
per effort level, whichever way the text is going out. The hook adds a budget of 20 calls for one message,
because a check that may run twenty times makes "one call per check" false — measured on a badly written
1,475-word document at `high`, one denial cost 16 calls and 147 seconds. `medium` is one judgement check
rather than five, and is the level the measurements support. On that same document, one pass found two findings and three pooled runs found
six across four checks, including two checks that were silent in the single pass. Every item says how
often it came up.

Which mode is right depends on the caller, and they want opposite things. The hook blocks, so it needs
precision: one item, confirmed by reproducing. A rewrite pass wants coverage, so it pools — and on a
document with real defects "seen once in three runs" means the check sampled a different real defect that
run, not that the item is noise. Confirmation would throw those away.

Splitting the document was the other candidate for scaling and it stays refuted: measured, it finds no more
than the whole document does and costs nine times the calls, because a smaller piece lowers the bar for
what counts as its worst sentence rather than sharpening the aim.

## When is a text finished

There is no honest answer yet, and this is the gap in the design rather than in the documentation.

```
python3 measure/measure_stopping.py --reps 3
```

That runs every comparative check over three real documents: a message an agent
wrote, the same content after a senior engineer rewrote it that day, and a long document already taken
through six rounds of this tool. Confirmed findings per pass, three passes each:

| document | words | checks with something to say, per pass |
|---|---|---|
| agent-written | 68 | 2.2 — `[2, 1, 4, 2, 2]` |
| human-edited | 44 | 1.2 — `[1, 2, 1, 1, 1]` |
| heavily edited | 371 | 0.2 — `[0, 0, 0, 0, 1]` |

Five passes each. Three passes gave 2.0, 1.3 and 0.7, and a single pass in isolation once put the
human-edited version above the agent-written one — the spread is about ±1, so one pass is not a
measurement.

At five passes each the numbers are 2.2, 1.2 and 0.2. The order holds, so the count measures relative
quality, and zero IS reachable — the document taken through six rounds scored zero in four passes of five.

One finding a pass is where a senior engineer's own rewrite landed. That is a reference point and not a
target: his writing is not perfect either, and the bar here is allowed to be higher than it. What the
number is for is the trend — the stopping rule is that the count has stopped falling, and a reader who
disagrees with what is left is allowed to be right.

Calibrating it means tuning the bar until the human-edited version passes and the agent-written one does
not. That needs more pairs than the one in `measure/fixtures/gold`, and from more than one author —
tuning five prompts against a single pair would fit the pair rather than the bar.

## Managing audiences

```
python3 lib/audiences.py list
python3 lib/audiences.py show platform-team
python3 lib/audiences.py accept platform-team GKE      # one term is wrong; applies immediately
python3 lib/audiences.py match platform-team channel C054ZDE533R   # change when it applies
python3 lib/audiences.py share platform-team --to ~/work/team-scripts/claude/audiences
```

Files on disk, one per audience. Read them, diff them, edit them.

[audiences.md](audiences.md) is the whole of it: the three layers that get read, how one person
measures an audience and everybody else gets it by pulling, and what does and does not travel with it.

What an audience *knows* comes from scanning writing those people already did, from any source you can
pipe — [sources.md](sources.md) has the contract and recipes for chat, mail and wikis. What an audience
*applies to* is the separate list of identifiers `match` edits. Confusing the two is easy, and the
flags are named to make it harder.

`engineers` is a shipped baseline: acronyms any developer knows, with no identifiers of its own, so it
never applies alone — audiences inherit it. That is where the tool's bias lives, and it is deliberate.
Other baselines are welcome as data files beside it, and a team can override this one for everybody by
sharing a file of the same name.

## Where everything lives

`$XDG_CONFIG_HOME/prose-guard`, or `~/.config/prose-guard`. Move it with `PROSE_GUARD_HOME`.

| file | what |
|---|---|
| `config.json` | effort level, which baseline to assume when no audience matches, and any shared directories |

`/plugin configure` shows the effort level as a free-text box, because `userConfig` supports `string`,
`number`, `boolean`, `directory` and `file` and has no enumerated type — there is no picker to offer. So a
typo means no checking at all, which reads exactly like switching it off. A level set to something that is
not a level now says so once a session, as a message to you rather than to the agent.
| `audiences/*.json` | one per audience: who they are, what they know, who is in them |
| `destinations.json` | your own or overridden destinations, read before the shipped ones |
| `unclaimed-destinations.json` | shapes passive discovery noticed, and what you decided |
| `sessions/` | per-session bookkeeping |

One directory, so the hook and the skills cannot disagree about where your settings are — an earlier
version had them reading two different places, and setup reported success while the guard stayed off.

`audiences/*.json` holds colleagues' names. Local, and not something to commit or publish.

## The rule

```
python3 lib/install_rule.py --install
```

250 words that apply while a message is being written rather than when it is sent, and the only part
of this that costs nothing per message. It reaches subagents, which an output style does not — both
halves verified.

A plugin cannot ship a rule, so this copies the file. **Copies, not symlinks**: the plugin directory
is versioned and replaced on update, so a link into it breaks the moment you upgrade. The cost is that
upgrading does not refresh it, which is why `--status` compares the two.

## Checking something before you send it

```
python3 lib/check_prose.py draft.md --for platform-team
python3 lib/check_prose.py draft.md --who "the ops rota, who did not see the incident" --effort low
```

Same checks and prompts as the hook, defaulting to `high` because one deliberate run can afford what
every message cannot. `/prose-guard:rewrite-for-audience` runs it first and then works outside in.
