---
name: contribute
description: Send something back to the repository prose-guard came from — a check that fired on good prose, a message it should have caught and did not, a tool it does not watch, or a fix. Use when the user says the guard was wrong or unfair, asks how to report a bug, file an issue or open a pull request against prose-guard, or asks how to contribute to it.
---

# Sending something back to prose-guard

This skill decides whether what happened here is a defect at all, and gets the evidence for it into a
form somebody who cannot see this machine can run.

The repository is **https://github.com/novada-tech/prose-guard** — Apache 2.0, issues open. Everything
about making a change to it lives in
[CONTRIBUTING.md](https://github.com/novada-tech/prose-guard/blob/main/CONTRIBUTING.md) rather than
here.

## Read this before you copy anything

Everything this tool remembers lives in the person's own config directory, and **the repository is
public.** The evidence for the most useful report there is — a check that fired on good prose — is a
real message they sent to real people.

- **They read the exact body before it goes.** The body, not a summary of it. Print it and ask.
- **No measured vocabulary, ever.** An audience's term counts are a list of what an organisation works
  on and who it talks to. CONTRIBUTING says the same of corpora: ship the measuring, never the
  measurements.
- **No channel identifiers, repository or customer names, hostnames, internal ticket numbers.** These
  arrive by accident, as often in what the guard recorded about a message as in the message itself.
- **Nothing is pasted out of the config directory.** Read it, reduce it, show the reduction.

If they are unsure whether something can be published, it does not go in. A report missing a field is
reviewable. A leaked message cannot be taken back.

## 1. Read the envelope before deciding anything

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/rounds.py" list
python3 "${CLAUDE_PLUGIN_ROOT}/lib/rounds.py" show 1
```

That prints what the checks were told before they read a word — which level actually ran, which
audience applied or that none did, what the destination told the checks about who would be reading,
and which check held the message.

`/prose-guard:feedback` reads the same file for a different question, so run this rather than that one:
the question here is whether the check was right, not what it said.

Nothing recorded? Then no message has been held back here, and the complaint is about advice rather
than a block. The text is still worth reporting; there is just no envelope to go with it.

## 2. Decide whether the fix is theirs or ours

Most of what feels like a false alarm is configuration, and an issue about configuration helps nobody.
The envelope decides it:

| what happened | where the fix is |
|---|---|
| `held by terms`, and those readers genuinely do know the term | **theirs.** `audiences.py accept <audience> <TERM>` for one term; `/prose-guard:audiences` if it keeps happening, because that is a vocabulary that needs measuring again |
| `held by terms` on something that is not a term at all — a code identifier, a product name, a ticker | **ours.** The term check flags acronym-shaped tokens and excludes English words and common constants, and something got past that exclusion. The reproduction is one publishable line |
| `guessing` in the envelope, and nothing was held back | **working as designed.** No audience matched, so terms can only advise. `/prose-guard:audiences` is the fix |
| `capped from high`, and it missed something the higher level asks about | **theirs.** That destination is capped on purpose, and `destinations.py show <name>` says why |
| a judgement check objected to prose that is fine | **ours, and it is the report CONTRIBUTING asks for above all others** |
| it let through a message a reader could not act on | **ours.** Harder to notice and worth as much |

Say which one it is out loud before going further. Sending a vocabulary problem upstream costs the
person a wait and gets them a link back to `/prose-guard:audiences`.

## 3. Reduce it to something a maintainer can run

A verdict cannot be reproduced from a description of one. What turns a complaint into a defect report
is text a maintainer can run the check on and watch it fail.

Build that text with the person. Keep the shape of what was objected to and replace the rest:

- **keep exactly** — the term, the sentence, the paragraph structure, the span the check quoted
- **replace** — names, identifiers, numbers, and what the change was actually about, with something
  unremarkable of the same shape and about the same length

Then run it, at the level the envelope named:

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/check_prose.py" repro.md --for engineers --effort high
```

Name `engineers` rather than their own audience. It is the baseline that ships, so it is the one a
maintainer also has, and a report naming a private audience is one nobody else can run.

Keep the reproduction over 25 words. Below that nothing is checked at all, so a shorter one proves
nothing either way.

**If it no longer fails, that is the finding — report it that way.** A check disagreeing with itself
between runs is a measured property of this tool rather than a surprise, and CONTRIBUTING carries the
rate for each one. Say how many times it was run and how often it fired. Do not file the version that
passes and describe it as failing.

## 4. Show them the body, then file it

Four things, and nothing else is required:

1. **The text**, reduced as above, in a fenced block.
2. **What should have happened** in a sentence — passed clean, or been held for something else.
3. **The envelope**, reduced: the level that ran, whether an audience applied, which check held it, and
   whether the destination capped anything. Not the raw output.
4. **The version**, which nobody remembers and every report needs:

```
python3 -c "import json; print(json.load(open('${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json'))['version'])"
```

Print the whole body and get a yes. Then file it against `novada-tech/prose-guard` with `gh`, writing
the body to a file and passing `--body-file`. Not `--body "$(cat report.md)"`: a shell substitution is
not in the tool call, so the guard cannot see the text and holds the call back. This is `gh` creating an
issue, which prose-guard watches — so the report is checked on its way out like anything else.

No `gh` on the machine? Print the body and give them
https://github.com/novada-tech/prose-guard/issues/new/choose — the forms there ask for these same four
things.

## A tool it does not watch

A destination entry is the most reusable thing anybody can send here. It is the same fact for everyone
who uses that tool, and the destinations file that ships with the plugin cannot see anybody's tool list
— so today every user works the same entry out from scratch. `discover.py --share` copies an entry to
their own team; an issue puts it in the shipped file.

```
python3 "${CLAUDE_PLUGIN_ROOT}/lib/destinations.py" show "<name>"
```

Check the entry carries nothing local before it goes: a `bash` pattern naming their host, an
`identifiers` field naming their workspace. What ships has to be about the tool rather than about them.

Include their answers to the two questions `/prose-guard:setup` asks about a destination — whether
anybody reads a message sent there before its audience does, and whether such a message has an
addressee and an ask. Those two answers set `max_severity` and `max_effort`, and they are the fields a
reviewer cannot work out from a tool name.

## If the fix is a change rather than a report

```
git clone https://github.com/novada-tech/prose-guard
```

Everything from there is in `CONTRIBUTING.md` in that checkout: the two suites to run, breaking your own
test before trusting it, which measurement your change owes and what running it costs. Read it there
rather than from memory — it carries numbers, and numbers move.

The checkout is not the plugin they have installed. Editing it changes nothing about their next message.

The harnesses under `measure/` spend real model tokens. That is why continuous integration does not run
them, and why nobody should reach for one by accident.
