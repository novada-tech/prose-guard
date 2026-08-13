# Where a vocabulary comes from

An audience's vocabulary is a count: how many distinct people have written each term in prose they
already wrote. Nothing about that count cares where the prose came from, so `learn.py scan` takes a
**command** and reads its output, rather than growing a special case per product.

The contract is one JSON object per line, on stdout:

```json
{"author": "ann", "text": "the BSP run failed, NFS again"}
```

Only `author` and `text` are read. Anything else on the line is ignored, so an export you already
have usually needs no reshaping beyond renaming two fields. Author identity only has to be stable
within one run — the count is of distinct authors, so logins, display names and ids all work, as
long as one person is not two of them.

```
python3 lib/learn.py scan --command './export-chat.sh general' --out candidates.json
python3 lib/learn.py create platform-team candidates.json \
    --who 'Engineers who run our Kubernetes. They read incident threads cold.' \
    --match-channel C054ZDE533R
```

Bot authors are dropped by name. Two sources can be combined in one scan, and the counts merge.

## Why a command and not a source per product

`--gh` shells out to the `gh` CLI, so repository text goes from GitHub to a temporary file and never
enters an agent's context. Reading a chat channel had no such path: the only way was an agent
reading a page and retyping the messages into a file. That is expensive — one page of a hundred
messages measured at roughly 12,000 tokens, most of it stack traces that change no acronym count —
and it is transcription rather than piping, so it can introduce into the corpus the errors you are
measuring the corpus to avoid.

A command fixes both, and it means a source nobody here has thought of works on the day you write
the shell for it.

## Recipes

Each of these emits the contract above. They are starting points, not supported integrations.

**Slack**, via any token you already have:

```sh
#!/bin/sh
# ./export-chat.sh CHANNEL_ID — needs SLACK_TOKEN with channels:history
curl -s "https://slack.com/api/conversations.history?channel=$1&limit=1000" \
     -H "Authorization: Bearer $SLACK_TOKEN" \
  | jq -c '.messages[] | select(.subtype == null)
           | {author: .user, text: .text}'
```

`.user` is a user id, which is stable and is what the destination reports, so no name lookup is
needed for counting.

**A Slack workspace export** (Settings → Import/Export), which is JSON on disk and needs no token:

```sh
jq -c '.[] | {author: .user, text: .text}' export/general/*.json
```

**Microsoft Teams**, via Graph:

```sh
az rest --uri "https://graph.microsoft.com/v1.0/teams/$TEAM/channels/$CHAN/messages" \
  | jq -c '.value[] | {author: .from.user.id, text: .body.content}'
```

Teams returns message bodies as markup rather than plain text. The tags cost nothing here — the
acronym pattern does not match `<div>` — but strip them if you want to read the candidate list
yourself.

**Discord**, via [DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter) in JSON mode:

```sh
jq -c '.messages[] | {author: .author.id, text: .content}' export.json
```

**A mailing list** or any mbox:

```sh
python3 -c '
import mailbox, json, sys
for m in mailbox.mbox(sys.argv[1]):
    body = m.get_payload(decode=True) or b""
    print(json.dumps({"author": m.get("From", ""),
                      "text": body.decode("utf-8", "replace")}))' archive.mbox
```

**A wiki or document store.** Anything with an export API works, but check the author field first:
a page with one editor and forty terms is one author for all forty, which is the correct answer and
a weak signal. Chat and code review are better corpora because they have many authors per term.

## What the count is not

It is breadth, not frequency. A term one person used two hundred times stays unknown; a term four
people used once each is known. The threshold is four distinct authors, and
[thresholds.md](thresholds.md) has the measurement behind that number.

So a corpus needs enough people to be worth scanning. Roughly a hundred messages from five or more
authors is where the counts start to separate; one person's outbox tells you what they write, not
what their readers know.

## Changing when an audience applies

Scanning decides what an audience knows. A separate set of identifiers decides when it applies, and
the two are easy to confuse — `--match-channel` reads like a source and is not one.

```
python3 lib/audiences.py match platform-team channel C054ZDE533R
python3 lib/audiences.py match platform-team repo your-org/infra your-org/tools
python3 lib/audiences.py match platform-team owner your-org
python3 lib/audiences.py match platform-team path 'docs/runbooks/*'
python3 lib/audiences.py match platform-team channel C054ZDE533R --rm
```

`channel` is deliberately not named after any chat product. Whatever produced the message already
knows which product it came from; by the time an audience is being chosen, a channel id is just an
identifier.
