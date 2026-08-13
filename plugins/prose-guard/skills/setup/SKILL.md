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

The numbers are five paired sessions on one fixture and one model, so the ordering is the finding
and the digits are not:

| level | what runs | added per message sent |
|---|---|---|
| `disabled` | nothing | — |
| `low` | the term check only, no model call | +12s |
| `medium` | plus one advisory writing check | +19s |
| `high` | four separate checks, re-verified after each edit | +75s |

Both counter-intuitive results are worth saying out loud:

- **`low` is not the cheap option.** No model call, but holding a message back costs a whole agent
  turn on their own context, which is dearer than the small call `medium` adds.
- **`high` is not known to be better than `medium`.** Both satisfied every concern on every message
  measured, which is a judge at its ceiling rather than evidence they are equal.

`medium` is what the evidence supports. Set it with `/plugin configure prose-guard@novada`, which is
the first-class path, or write the file:

```
python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/lib'); \
from checks import config; print(config.save('medium'))"
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

Then do the part no script can:

- **Name the tools you can actually see.** For each MCP server it listed, say which of your own
  available tools belong to it and which of those send prose to a person. You can see your tool
  list; the script cannot.
- **Propose, do not assume.** Show the user a short list of what you would add and what field
  carries the text. Ask before writing.
- **Say what each addition costs.** Every added destination is more messages checked, at the
  per-message price above.

Write confirmed entries to `<config dir>/destinations.json`, whose shape is documented in
[`data/destinations.json`](../../data/destinations.json). User entries are read first, so the same
file also overrides a shipped entry — that is how to stop checking something.

Already covered without asking: chat messages, GitHub and GitLab comments and PR descriptions,
documentation pages, issue trackers, `git commit` and `git tag -m`, and prose files that are inside
a git working tree and not ignored.

Two known gaps worth stating rather than hiding: `git commit` with no `-m` opens an editor and that
text never reaches a tool call, and `--body "$(cat file)"` cannot be read.

## 5. Offer audiences, and be honest about what it buys

Until an audience is measured, the tool knows what developers in general know and nothing about the
people they write to, so it reports unexplained terms as a guess and does not block. Point at
`/prose-guard:audiences`. Optional, a few minutes, and it is what turns advice into enforcement.

## 6. Restart

Hooks and rules load at startup. Nothing takes effect until then.
