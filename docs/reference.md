# Reference

How the tool behaves once you are using it: what counts as sending, what the caps do, where your files
live, and how to check a draft before you send it. Read it when you need it.

A section belongs here if a reader acts on it. Anything whose subject is a measurement, or a design
decision that did not survive one, belongs in [design-notes.md](design-notes.md) instead, and this file
links to it where the two meet.

## What it does when it disagrees with you

It names one problem and hands the message back. It does not rewrite: a check that rewrites cannot
tell you what it disagreed with.

Two mechanical rules run at every level, free and instant: a word typed twice, and `a` where `an`
belongs. Both are objective and both are a one-word fix, so they hold a message back rather than
mentioning it. Grammar in general is not checked; a third-party checker was measured and is not here,
along with four more mechanical rules that flagged a third of everything written
([design-notes.md](design-notes.md)).

Which checks can be trusted to hold a message back turns on one distinction. `mechanics` is
**absolute**: a word typed twice is wrong whatever surrounds it, so it reports every instance rather
than the worst one and the size of the input makes no difference to the verdict — which is also why it
is stable enough to hold a message back on its own. Every other check is **comparative**: asked about a
piece of text it reports the worst instance of its concern in that text. So a smaller piece does not
sharpen a comparative check, it lowers the bar for what counts as worst. Measured: asked about one
paragraph the same check found nothing wrong 3 times in 3, and asked about that paragraph plus
everything before it, `reference` found something 3 times in 5. Splitting a long document to sharpen
those checks was measured and dropped: [design-notes.md](design-notes.md).

Every finding a model-based check reports is put back to the same check, and only a finding that
objects to the same sentence twice can hold a message back. Unconfirmed findings are still printed,
marked `consider` rather than `must fix`, because a finding only one run raised is either a real defect
that run happened to reach first or a near-tie between two candidates — and which of those it is cannot
be told from the finding. Nothing is filtered away, so there is no filter to turn off: what confirmation
decides is whether a message can be held back, not whether you get to read the finding. What it was for,
and what it cost: [design-notes.md](design-notes.md).

And it stops insisting when it is probably the one that is wrong. Severity depends on the **share** of
the terms you used that are unknown to your reader, not the count — three unknown out of twenty in a
long document is an oversight worth fixing, fifteen out of twenty means the tool has the wrong reader
in mind. Above a third it says so instead of demanding twenty explanations. That threshold is the 90th
percentile of the share seen when a message *is* scored against the audience it was written for,
measured both directions on 3,170 real messages: [thresholds.md](thresholds.md), including
what the measurement fails to show.

Three limits keep that bounded. Each check gets two attempts, and a session gets six holds in total.
Model calls are capped per message rather than per session, and the cap is scaled by the length of the
text rather than flat: what one check would spend if it kept finding things, times the checks that cost
anything, up to ninety. A check that cannot be paid for is skipped for that message. So two checks that
genuinely disagree make one message expensive and then let it through, rather than hanging your turn.

A flat cap was tried first, and it was a cap for a chat message quietly applied to documents as well —
twenty divided among six checks is three runs each, for two hundred words and for ten thousand alike. A
clean document is unaffected either way, because pooling stops as soon as a run adds nothing: one call
per check is what good prose costs at any length. The cap only binds on a document with real defects.

## What counts as sending

Out of the box: **`git commit` and `git tag -m`**, `gh pr` and `gh issue` comments and descriptions, and
prose files inside a git working tree that are not ignored. Those are the ones worth shipping — on
essentially every developer machine, and each carrying something a tool schema does not show: which flag
holds the body, that a commit message has no addressee, that a tracked file is one somebody will read.

Everything else is yours and is found rather than assumed. Chat, issue trackers, wikis and vendor
command-line tools go in at `/prose-guard:setup`, which reads the tool list `data/destinations.json`
cannot see. See [Managing destinations](#managing-destinations) for adding one by hand.

The rule about prose files replaces matching on `.md`. What matters is whether somebody other than you will read
the file, and "it gets committed" is a deterministic proxy — so your README is checked and your scratch
notes are not.

Two gaps are stated rather than hidden.

`git commit` with no `-m` opens an editor, and that text never reaches a tool call. Nothing can be done
about that from here.

The plumbing — `git commit-tree`, `filter-branch --msg-filter`, `filter-repo` — is not matched, because
those rewrite text somebody else wrote, usually in bulk, which is not the act this checks.

`--body "$(...)"` used to be a third gap. The destination matches, the prose is a shell substitution the
tool call does not contain, and nothing was checked — which reads exactly like a check that passed. Most
forms are now worked out rather than complained about:

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
not stuck. "Resolved but too short to judge" is silent — that is not a gap, and sending someone to
fix a working command would be noise.

All of it is per destination without naming any: both halves read the destination's own `text_arg`, so
`git commit -m "$(...)"` and the `--message` of a command-line destination setup added for you — `glab
mr note`, say — behave the same, and one added later does too.

**Your tools are not mine**, so setup asks rather than assumes. `lib/discover.py` reads four local
sources — MCP servers you have configured, outbound command-line tools on your `PATH`, how often each
appears in your **shell history** (much better evidence than "installed"), and anything that has
already gone out unchecked. Then the agent names the tools it can actually see, proposes destinations,
and waits for you.

You will install something new next month, and the guard notices on its own. For every call carrying
outgoing prose that nothing has claimed it records the *shape* — `bash: git commit -m`,
`tool: example__post [body]` — never the text. It mentions it **once**, on the third use, and never
again, so nothing can nag you twice about the same thing; decline and it is declined for good. At most
50 shapes are tracked.

You see these, not just the agent. A hook has two channels — `additionalContext` reaches the model and
`systemMessage` reaches the person, and the docs are explicit that neither sees the other. Discovery used
only the first, so a decision that is yours was being made available only to whatever agent happened to be
running. It goes to both now: you see the notice, and the agent knows enough to offer to act on it.

## What you see when a message is checked

One line, on the message that goes out. Claude Code prefixes it with `PreToolUse:<tool> says:`, which is
its own and nothing here can shorten:

```
prose-guard · low · platform-team · clean
prose-guard · high · platform-team · 2 rewrites, 1 note · 7 calls · /prose-guard:feedback
prose-guard · low · no audience · 1 note
```

The fields never move: the level that ran, who it was judged for, what came of it, what it cost, and
where to read the argument back if there was one. **`no audience`** in the third position is the one
worth knowing — nothing was held back on terms, because the reader was assumed rather than measured, and
`/prose-guard:audiences` is what changes it.

`rewrites` is how many times the agent was sent back before this text passed. A denial carries no such
line, because a denial is a permission prompt and you have already seen it.

The point of printing it when there is nothing to say is what silence then means. Advice goes to the
model and not to you, so before this the only outcome you ever saw was a block — and a check that had
quietly stopped covering something looked exactly like a check with nothing to object to. Now the
absence of that line means one thing: nothing was checked. That is how a gap becomes visible without
reading a transcript, and it is worth knowing which gaps are deliberate: under 25 words, a `git commit`
with no `-m`, and text the guard could not read and said so about.

It costs the agent nothing. `systemMessage` never enters the conversation the model is paying for.

### Reading back an argument

A held message is an exchange you never see: the guard objects, the agent rewrites, and only the last
version reaches anybody. So a fair complaint and an unfair one look identical afterwards, and there is
no way to tell whether the rewrite improved the message or merely satisfied the tool. The drafts are
kept so you can judge that:

```
/prose-guard:feedback
```

Ask for it in words — "why was that rewritten", "show me the drafts", "was that fair", "clear it". The
tally line names the skill when there is something to read, so you do not have to remember anything.

Underneath it is `lib/rounds.py`, with `list`, `show N` and `forget`, if you would rather read the
drafts yourself than have them read back to you.

**This is the only thing here that writes message text.** Passive discovery records the shape of a call
and never its content, deliberately, and the rule that lets both be true is narrow: nothing is written
unless a check actually held a message back. A message that passes leaves no trace, and no `rounds`
directory is created until the first time one is refused. It lives in your own config directory beside
everything else this tool remembers, bounded at 40 arguments and 6,000 characters a draft — never in a
repository, and never anywhere it can be pushed.

A deliberate run of `check_prose.py` needs none of this — it prints every finding, the ceiling it was
working to, and what it actually spent, straight to the terminal you ran it in.

Long is not the same as outgoing, and getting that wrong is expensive: one mention per shape means a
mention spent on a search pattern is a mention gone. In real use it spent all six of them on nothing —
`git grep -E` with a long alternation, the text an `Edit` replaces, an `Agent` prompt, a `Write` to a
file the prose-file destination already decides on. So a candidate now has to read like prose: at least
25 words, at least two sentences, and at least 70% ordinary words. A regex has words and no sentences; a
script has punctuation and few real words. Fields that are structurally not outgoing — `old_string`,
`prompt`, `command`, `pattern` — are skipped whatever they contain. Writing a file is not excluded: the
prose-file destination only claims a file git already tracks, so a document written outside any git
repository is exactly the case that needs mentioning.

## Not every destination is worth the same effort

A destination can cap two things, for two different reasons.

**`max_effort` — the questions do not apply here.** The commit message caps at `low`: the term check
only, whatever you have configured. Not because it is expensive. Measured across the eight destinations
that shipped then, on the same 77 words of well-built prose, three runs each, every one costs about 15
seconds and 5 model calls — the cost is in the phases and the phases do not care where the text is going. There is no such
thing as an expensive destination.

What varies is whether the questions apply. The phases ask whether this reader will care and whether the
ask is clear. A commit message has neither an addressee nor an ask; it is read years later by somebody
finding out when a line changed. The term check still applies, because an acronym nobody expands is
exactly as unhelpful in a permanent record as anywhere, and it costs no model call and a tenth of a
second.

**`max_severity` — nothing is about to reach anyone unreviewed.** A draft is its own destination and
caps at `advise`. Blocking is justified by text being about to reach a reader with nobody in between; a
draft tool — `slack_send_message_draft`, if setup added it for you — lands in your own compose box, so
it has a reader already, and holding it back spends a turn arguing about text you were about to read. The finding is identical either way — the
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

Measured on two real audiences — 268 people on a public data-model repository, 20 in a client-services
channel — intersecting costs 103 of the modellers' 220 terms and leaves 117. It does not collapse,
because both inherit the same baseline and that floors the intersection.

Two things it will not do, both of which looked like free simplifications and are not. An audience whose
members sit inside another is still combined in, never dropped. And exact overlap between audiences is
**not computable**, so `overlap` prints a prefix-matched guess, labelled as one, and nothing depends on
it. Why neither survived: [design-notes.md](design-notes.md).

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

## How many times a check runs

A check returns exactly one item per run, and each run picks one item from those above its bar — so runs
sample findings rather than enumerate them, and asking a check for a list instead does not work.

**A check keeps running while its runs keep finding something new, and stops when two runs in a row add
nothing.** How many runs that takes is decided by the text and not by a flag, so a document with ten real
defects is not cut off at the same point as a clean one. Every item you are shown says how often it came
up.

The ceiling is linear in length above a base of six, because a longer document has more places to be
wrong: 6 runs up to 600 words, 9 at 800, 21 at 2,000, and 25 as a hard bound so one pathological file
cannot spend a session.

The hook and a deliberate run call the same function on the same text, so they cannot drift apart: one bar
per effort level, whichever way the text is going out. What differs is what they do with the runs, because
the two callers want opposite things. The hook blocks, so it needs precision: one item, confirmed by
reproducing. A rewrite pass wants coverage, so it pools — and on a document with real defects "seen once in
three runs" means the check sampled a different real defect that run, not that the item is noise.
Confirmation would throw those away. `medium` pools nothing, because one combined verdict over every
concern has nothing to pick between.

What the run rule costs per document, and the two ways of scaling it replaced:
[design-notes.md](design-notes.md).

## Managing destinations

The same verbs as audiences, on the same three layers:

```
python3 lib/destinations.py list                      # every one, and which layer it came from
python3 lib/destinations.py show "commit message"
python3 lib/destinations.py add "our wiki" --tool wiki_create --text-field content
python3 lib/destinations.py off "github cli"          # stop checking one here, whatever layer it is from
python3 lib/destinations.py on "github cli"
python3 lib/destinations.py rm "my wiki"              # delete one of your own
python3 lib/destinations.py share --to DIR --only "our chat" --with-off
```

Yours is read first, then any directory your team shares, then the shipped set, and the first match wins.
So local and shared coexist: a team shares the chat tool everyone posts to, and the document one person
writes invoices in stays on that person's machine. `--only` exists for exactly that split.

`add` is the one thing that writes a destination, and it refuses what the loader would drop: a cap that
is not a level, a tool with no field carrying the prose, a pattern that does not compile. Each of those
was written by hand before and failed open — `max_effort: "lo"` was ignored, so the destination meant to
stop at the cheapest check ran every check and could block. `--help` lists the fields.

`rm` works on your own. A shipped destination is inside the plugin and is replaced on update, so there is
nothing to delete — `off` records the name in a file instead and it stops being read, whichever layer it
came from. `off` is read from every layer, so a team retires a shipped destination for everybody by
sharing it with `--with-off`, and `on` says so rather than pretending when the name was switched off in
somebody else's file. A shared destination itself is retired by removing it from the directory it comes
from.

`list` marks an entry as shadowed when a name appears in more than one layer. That is the layering working
— your copy overrides the team's — but it also means their improvements to it stop reaching you, and `share`
says so when you have just created that situation.

## Managing audiences

[audiences.md](audiences.md) is the whole of it: every command, the three layers that get read, how one
person measures an audience and everybody else gets it by pulling, and what does and does not travel
with it. Files on disk, one per audience — read them, diff them, edit them.

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

The level is a word you type, in `config.json` or in `PROSE_GUARD_EFFORT`, and a typo means no checking
at all — which reads exactly like switching it off. A level set to something that is not a level says so
once a session, as a message to you rather than to the agent. `/prose-guard:setup` writes it for you and
is the way to avoid the question.

Earlier versions also offered it in `/plugin configure`, as a free-text box: `userConfig` supports
`string`, `number`, `boolean`, `directory` and `file` and has no enumerated type, so there was no picker
and no way to mark the recommended answer. Asking for a level in a dialog at install, before anybody had
been told what one costs, was a worse first minute than not asking. That field is gone and so is the
setting behind it — if you had answered the dialog, run `/prose-guard:setup` once and the level moves to
`config.json`.
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

It records how many findings each pass confirmed and tells you when to stop, which is the count having
stopped falling rather than the count reaching zero. Zero is not the target and there is no calibrated
bar yet — what is and is not known about when a text is finished is in
[design-notes.md](design-notes.md).
