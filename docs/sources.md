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

## Writing a command that reads a live service

Two things go wrong here, and both produce a corpus that looks fine.

**Say which credential, and where it comes from.** "A token with `channels:history`" was not enough:
someone reached for the token they had, a Slack CLI app-configuration token, which authenticated
successfully and then failed on the first data call. Every recipe below names the kind of credential
and links to the page that creates it, and a recipe you write for your own source should do the same.
The exact scope matters less than the kind — a token of the wrong kind fails in a way that reads as
your command being broken.

**Read the whole thing, or say you did not.** A file either opens or it does not; an API call fails
part way through and leaves you holding two-thirds of a channel. One real read died at 5,564 messages
on a connection reset and would have been written up as complete. So retry transient errors with a
backoff, honour rate limits (`429`, and `Retry-After` where the service sends one), and let one
unreadable page cost that page rather than the rest of the run.

`scan` catches what it can see: a source that yields no usable lines is named as a warning, a corpus of
nothing refuses outright, and rebuilding an audience over a smaller corpus than last time says so. What
it cannot see is a source that quietly stopped at two-thirds and exited 0. That one is yours.

## The fetcher, for anything cursor-paginated

Most of the work in a live source is not about the source: retry what is transient, wait when told to
wait, follow the cursor to the end, and fail loudly rather than quietly returning less. `fetch.py` does
those four things and knows nothing about any particular service — you give it the paths to the fields.

```
export SLACK_AUTH="Authorization: Bearer $SLACK_TOKEN"
python3 lib/fetch.py --url 'https://slack.com/api/conversations.history?channel=C123&limit=200' \
    --header-env SLACK_AUTH \
    --ok ok --error error --items messages --author user --text text --ts ts \
    --cursor-out response_metadata.next_cursor --cursor-in cursor
```

**Name the variable, do not paste the value.** `--header-env` takes the NAME of an environment
variable holding the whole header line; `--header "Authorization: Bearer $SLACK_TOKEN"` would have the
shell expand the token before the process starts, and `ps` shows one process's arguments to every
other process running as you — an agent, an `npm` postinstall, a colleague on a shared box. The token
was read out of a process table that way while this was being reviewed. `--header` is still the flag
for headers that are not secret.

That prints the contract on stdout, so it goes straight into a scan:

```
python3 lib/learn.py scan --command './read-chat.sh' --keep corpus.jsonl
```

`--ok` is the one flag worth explaining. Some services answer `200` with a refusal in the body, which
otherwise reads as an empty page — name the field that has to be truthy and a refusal becomes a failure.
It honours `Retry-After` rather than guessing, retries a body that stops short of its own
`Content-Length`, and exits `2` with "this corpus is incomplete" if it hits `--max-pages` with more to
read. It does not authenticate: pass `--header-env`, and keep the credential in your shell or keychain.

If your source is not a JSON array plus a cursor, write your own command. The recipes below are all a
few lines of shell.

## Recipes

Each of these emits the contract above. They are starting points, not supported integrations.

**Slack**, via a bot token:

```sh
#!/bin/sh
# ./export-chat.sh CHANNEL_ID
# SLACK_TOKEN must be a BOT token — it starts `xoxb-`, and comes from
#   https://api.slack.com/apps -> your app -> OAuth & Permissions -> Bot User OAuth Token
# with the `channels:history` scope, and the bot invited to the channel.
# A `xoxe.xoxp-` token from the Slack CLI is an app-configuration token: it authenticates and then
# returns `missing_scope` on any data call.
printf 'header = "Authorization: Bearer %s"\n' "$SLACK_TOKEN" \
  | curl -s -K - "https://slack.com/api/conversations.history?channel=$1&limit=1000" \
  | jq -c 'if .ok then .messages[] | select(.subtype == null)
                       | {author: .user, text: .text}
           else "slack: " + .error | halt_error(1) end'
```

`-K -` reads the header from curl's stdin rather than from its arguments, and `printf` is a shell
builtin, so no process on the machine has the token in its argument list. `curl -H "Authorization:
Bearer $SLACK_TOKEN"` puts it in one that `ps` prints.

`.user` is a user id, which is stable and is what the destination reports, so no name lookup is needed
for counting. The `if .ok` is the point of that `jq`: without it a rejected token prints one error
object and the pipeline exits 0.

Paging past the first 1,000 messages, retrying and rate-limit handling are left out to keep the recipe
readable — see the section above for why a real read needs them.

**A Slack workspace export** (Settings → Import/Export), which is JSON on disk and needs no token:

```sh
jq -c '.[] | {author: .user, text: .text}' export/general/*.json
```

**Microsoft Teams**, via Graph. `az login` first; reading another team's messages needs the
`ChannelMessage.Read.All` application permission, granted by an administrator at
https://portal.azure.com -> App registrations -> your app -> API permissions:

```sh
az rest --uri "https://graph.microsoft.com/v1.0/teams/$TEAM/channels/$CHAN/messages" \
  | jq -c '.value[] | {author: .from.user.id, text: .body.content}'
```

Teams returns message bodies as markup rather than plain text. The tags cost nothing here — the
acronym pattern does not match `<div>` — but strip them if you want to read the candidate list
yourself.

**Discord**, via [DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter) in JSON mode. It
takes a bot token from https://discord.com/developers/applications -> your app -> Bot -> Token, with
the Message Content intent enabled — without that intent every `content` field comes back empty, which
looks like a channel of blank messages rather than a permission problem:

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
