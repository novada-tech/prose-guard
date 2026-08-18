---
name: setup
description: Set up prose-guard — choose how much checking to do, install the communication rule, and configure which tools count as sending prose. Use when the user asks to set up, configure, enable or disable prose-guard, asks why it is or is not checking their messages, or asks it to check a tool it currently ignores.
---

# Setting up prose-guard

One question at a time, and show what you wrote. Everything lands in plain files.

## 1. Say what is set now

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/checks/config.py"
python3 "${CLAUDE_PLUGIN_ROOT}/lib/audiences.py" list
python3 "${CLAUDE_PLUGIN_ROOT}/lib/install_rule.py"
```

## 2. Choose a level

What each level adds per message sent. Read the ordering rather than the digits — one fixture, one
model:

| level | what runs | added per message sent |
|---|---|---|
| `disabled` | nothing | — |
| `low` | the two deterministic checks only, no model call | +12s |
| `medium` | plus one advisory writing check | +19s |
| `high` | one separate check per concern, all asked at the same time | +12s |

Cost is not what separates `medium` from `high`, and two results are worth saying out loud because
neither is what somebody expects:

- **`low` is not the cheap option.** No model call, but holding a message back costs a whole agent
  turn on their own context, which is dearer than the small call `medium` adds.
- **`medium`'s judgement half has never been measured changing anything.** Advice reaches the model
  after the call has already run, so there is no turn in which the message could change: 41 messages
  got advice and went out, and none was corrected afterwards. `high` asks the same concerns separately
  and can hold a message, which is the only mechanism here shown to change what goes out.

So **`high`** for somebody who wants the judgement checks to do something, and **`medium`** for
somebody who wants the two arithmetic checks and nothing that can cost a held turn. The full argument,
and the caveat on those 41 messages, is in
[docs/design-notes.md](../../../../docs/design-notes.md).

Take their answer and write it — this is the only place a level is set:

```
python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/lib'); \
from checks import config; print(config.save('<their answer>'))"
```

## 3. Offer the rule

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/install_rule.py" --install
```

Say what it is: 250 words that apply while a message is being written, rather than when it is sent,
and the only part of this tool that costs nothing per message. It is copied rather than linked
because the plugin directory is replaced on update, so re-run this after upgrading — `--status` says
whether it has drifted.

## 4. Work out what counts as outgoing

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/discover.py"
```

That prints what is already covered, plus four kinds of evidence about what is not: MCP servers
configured here, outbound command-line tools on PATH, how often each appears in their shell history,
and anything that has already carried long prose past the guard unclaimed.

The last list is the one to trust: those already happened. The guard also mentions such a tool by
itself, once, on about its third use — and only once ever, so nothing here is urgent.

**Then ask whether you may read their past conversations**, because it answers this far better than
anything above:

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/discover.py" --from-transcripts
```

Ask first, and say exactly what it does: it reads the transcripts under `~/.claude/projects` and
counts shapes — a tool name and a field name — and never a value from any message. Nothing leaves
the machine and nothing is written but the count.

It is worth asking because the other four kinds of evidence are all blind in the same place. An MCP
call never touches a shell, so shell history cannot see one — and it cannot see a command an *agent*
ran either, because the Bash tool does not write there. On one real machine nothing a whole session
had run appeared in shell history, while the transcripts held `add_comment_to_pending_review` 49
times and `slack_send_message` 9. Those are the destinations that matter, and setup was blind to
every one of them.

If they say no, nothing is lost that was not already lost: carry on with the four lists above.

Then do the part no script can:

- **Name the tools you can actually see.** For each MCP server it listed, say which of your own
  available tools belong to it and which of those send prose to a person. You can see your tool
  list; the script cannot.
- **Read the tool's parameters and say what the reader already has.** Fetch the schema of any tool
  you are about to propose and look at its other fields. They describe themselves: `thread_ts` says
  *"provide another message's ts value to make this message a reply"*, `line` says *"the line of the
  blob in the pull request diff that the comment applies to"*, `subjectType` is `FILE` or `LINE`.
  A field like that means the reader is already looking at something, and the checks judge much
  better when told — without it, "as I said" reads as having no antecedent when the antecedent is
  three messages up the thread.

  The common ones are already defaults and need nothing from you: a thread reply, a `path` with a
  `line`, a pull request or issue number, a reply to a comment. Propose a `when` entry only for a
  field those do not cover, in the destination's own words:

  ```
  "when": {"parent_page_id": "a comment on a page the reader has open"}
  ```

  A `when` entry the destination declares replaces the default for that field rather than repeating
  it, so there is no harm in wording one yourself.
- **Propose, do not assume.** Show the user a short list of what you would add and what field
  carries the text. Ask before writing.
- **Say what each addition costs, and ask what it is worth.** Every added destination is more messages
  checked, at the per-message price above — and the price is per destination, not just per install:

  ```
  python3 "${CLAUDE_PLUGIN_ROOT}/lib/destinations.py" worth "slack message" high
  ```

  Ask it for anything whose answer is not the level they just set. An announcement to a wide channel is
  worth more than the level they chose for everything; a scratch file or a bot channel is worth less.
  `disabled` is available and is the honest answer for a destination they do not want checked at all.

  This is worth pressing on, because the dial existed before and nobody moved it: on one real machine 8
  of 9 destinations left it unset, so every message got the same budget whatever it was worth. The level
  they set caps whatever they say here, so there is no way for this to cost more than they agreed to.

## 5. Say what the destinations they already have will cost

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/destinations.py" list
```

Every row now ends in what that destination will actually run at and why — `runs at high (your level)`,
`runs at low (the destination caps it)`, `runs at medium (you said so)`.

**Go through the ones that say `(your level)`.** Those are the destinations nobody has decided about: they
are getting the level by default rather than because it fits. This step exists because the previous one
only covers destinations being added, and most destinations arrive some other way — the shipped set, a
directory their team keeps, a colleague's pull request. On the machine this was written on, all six of the
team's destinations arrived shared and none of them had ever been considered.

Two questions per row, and the second is the one people have an opinion about:

- Does this reach a person who will act on it? If not, `worth <name> disabled` and it costs nothing.
- Is it worth more or less than the rest? A wide announcement is worth more; a bot channel or a scratch
  file is worth less.

Take `no` for an answer and move on — a destination left at the level is not broken, it is just
undecided. What is worth avoiding is leaving them undecided *silently*, which is what happened before this
step existed.
- **Ask the two questions that decide how hard it is checked.** Adding a destination is not one
  decision but three, and these two are the ones you cannot work out for them:

  1. *Does anybody read it before its audience does?* If yes — a draft, a preview, anything that lands
     in their own compose box — set `"max_severity": "advise"`. Blocking is only justified when text is
     about to reach a reader with nobody in between.
  2. *Does it have an addressee and an ask?* If not — a record, a changelog, a tag message — set
     `"max_effort": "low"`. The checks above `low` ask whether the reader will care and whether the ask
     is clear, and neither question means anything without a reader. Measured: every destination costs
     about 15 seconds and 5 model calls at `high`, so this is about what applies, not about speed.

  `discover.py` prints a suggested answer for each candidate where the name is evidence, with the
  reason. Read it out and let them disagree — it is a guess from a name.

**If they say no to something, record it** — otherwise the same suggestion comes back the next time
they use that tool, which is the fastest way to get a tool switched off:

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/discover.py" --decline '<shape>'
```

Once they are confirmed, offer to share them. Working out which tool sends prose and which field
carries it takes this conversation, and a destination is the same fact for everyone using that tool — so
nobody should have this conversation twice:

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/discover.py" --share <a directory their team clones>
```

It copies only what this machine added, never the shipped set, and skips anything already there.
Everyone else registers the directory once, or has their team's setup script do it.

Write confirmed entries with `add`, which refuses what the loader would have dropped — a cap that is
not a level, a tool with no field carrying the prose, a pattern that does not compile:

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/destinations.py" add "our chat" \
  --tool chat_send --text-field body --max-severity advise
```

Yours are read before the shipped set, so giving one the same name overrides it. To stop checking a
shipped one entirely, `destinations.py off "<name>"`.

Already covered without asking: `git commit` and `git tag -m`, `gh pr` and `gh issue` comments and
descriptions, and prose files that are inside a git working tree and not ignored. Chat, issue trackers
and the rest are what this step is for — they are not in the shipped file because it cannot see the tool
list, and you can.

One known gap worth stating rather than hiding: `git commit` with no `-m` opens an editor, and that text
never reaches a tool call.

A body passed as `--body "$(cat file)"` used to be a second gap. The prose is a shell substitution the
tool call does not contain, so nothing was checked — and passing silently reads exactly like a check that
passed. That is held back now, naming `--body-file`, which is read. Write long bodies to a file and pass
them that way and it never comes up.

## 6. Offer audiences, and be honest about what it buys

Until an audience is measured, the tool knows what developers in general know and nothing about the
people they write to, so it reports unexplained terms as a guess and does not block. Point at
`/prose-guard:audiences`. Optional, a few minutes, and it is what turns advice into enforcement.

## 7. Say what is running now, and what is next

The level is live from the moment it is written — the hook reads it on every call, so nothing has to be
reloaded for it. The rule is different: `~/.claude/rules/` is read at session start, so a rule installed
in step 3 does not apply until the next session they open.

End by telling them, in this order, and in one short paragraph rather than a checklist:

- **What is on.** The level, and which of their tools it now watches. Name the two or three they will
  hit today, not the whole list.
- **What they will see.** One line on every message that goes out —
  `prose-guard · medium · no audience · clean` — and that its absence means nothing was checked.
  Warn them the third field says `no audience` until step 5 happens, which is what stops anything being
  held back on terms.
- **The one thing left.** `/prose-guard:audiences` if they skipped it, or a new session if they took the
  rule. Not both, and not a list of everything they could do.

Do not tell them to restart Claude Code. An install is active as soon as Claude Code says `Plugin is now
active`, and `/reload-plugins` covers the case where it says otherwise.
