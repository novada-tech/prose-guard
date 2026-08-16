#!/usr/bin/env python3
"""Read a cursor-paginated JSON API and print the document contract, without losing half of it.

    export SLACK_AUTH="Authorization: Bearer $SLACK_TOKEN"
    python3 lib/fetch.py --url 'https://slack.com/api/conversations.history?channel=C123&limit=200' \\
        --header-env SLACK_AUTH \\
        --ok ok --error error --items messages --author user --text text --ts ts \\
        --cursor-out response_metadata.next_cursor --cursor-in cursor

Every source needed the same four things and none of them are about the source: retry what is
transient, wait when told to wait, follow the cursor to the end, and fail loudly rather than quietly
returning less. Written by hand for one real read, that came to two bugs found by running it — a
connection reset at 5,564 documents that would have been written up as a complete corpus, and rate
limits met by stopping.

This knows nothing about any particular service. It takes the paths to the fields, so anything that
returns a JSON array of items and a cursor works: chat history, issue trackers, wikis, document
stores. If your source is not that shape, write your own command — `learn.py scan --command` takes
any of them, and docs/sources.md has hand-written recipes.

What it does NOT do, on purpose: authenticate. Pass a header. A tool that collects credentials is a
tool that stores them, and the token belongs in your shell, your keychain or your CI secret store.

Name the variable, do not paste the value: `--header-env` reads the header out of the environment,
which no other process can read. `--header "Authorization: Bearer $TOKEN"` was expanded by the shell
before this process started, so the token was in this process's argv, and `ps` shows argv to anything
running as the same user. `--header` is still there for headers that are not secret.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

TRANSIENT = {408, 425, 429, 500, 502, 503, 504}


def dig(obj: Any, path: str | None) -> Any:
    """A dotted path into nested JSON. Returns None rather than raising: a missing field is a fact to
    report with the rest of the response, not a traceback."""
    if not path:
        return None
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def headers_for(literal: list[str], from_env: list[str]) -> dict[str, str]:
    """The request headers, from arguments and from the environment.

    Two ways in because they are not equivalent. A header read from the environment never appears in
    this process's argv, and argv is world-readable through `ps` to anything running as the same user —
    which includes every other tool an agent starts. So the credential goes in a variable, and only
    its NAME is ever printed here, error messages included.
    """
    pairs = []
    for name in from_env:
        raw = os.environ.get(name)
        if not raw:
            raise SystemExit(f"fetch: ${name} is not set, so --header-env {name} has nothing to send. "
                             f"Set it to a whole header line: "
                             f"export {name}='Authorization: Bearer <your token>'")
        pairs.append((f"${name}", raw))
    pairs += [(repr(value), value) for value in literal]
    out = {}
    for source, raw in pairs:
        if ":" not in raw:
            raise SystemExit(f"fetch: {source} wants 'Name: value'")
        name, value = raw.split(":", 1)
        out[name.strip()] = value.strip()
    return out


def with_cursor(url: str, param: str, cursor: str | None) -> str:
    if not cursor:
        return url
    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k != param]
    query.append((param, cursor))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def get(url: str, headers: dict[str, str], retries: int, base: float,
        note: Callable[[str], None]) -> Any:
    """One request, retried while the failure looks temporary.

    A 429 is not a failure, it is an instruction. Where the service says how long to wait, wait that
    long — backing off by guesswork either hammers it or sleeps far longer than asked.
    """
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code not in TRANSIENT or attempt == retries:
                body = (exc.read() or b"").decode("utf-8", "replace")[:200]
                raise SystemExit(f"fetch: {exc.code} {exc.reason} from {url[:90]}\n{body}")
            wait = exc.headers.get("Retry-After")
            delay = float(wait) if wait and str(wait).isdigit() else base * (2 ** attempt)
            note(f"  {exc.code}; waiting {delay:.0f}s"
                 f"{' as asked' if wait else ''} (attempt {attempt + 1} of {retries})")
        # http.client.IncompleteRead is an HTTPException, NOT an OSError: a response whose body stops
        # short of its Content-Length is exactly the failure this tool exists for, and it would have
        # escaped as a traceback.
        except (urllib.error.URLError, OSError, http.client.HTTPException,
                json.JSONDecodeError) as exc:
            if attempt == retries:
                raise SystemExit(f"fetch: giving up on {url[:90]} after {retries} retries: {exc}")
            delay = base * (2 ** attempt)
            note(f"  {type(exc).__name__}; waiting {delay:.0f}s "
                 f"(attempt {attempt + 1} of {retries})")
        time.sleep(delay * (0.5 + random.random()))
    raise SystemExit("fetch: unreachable")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="first page, query string and all")
    ap.add_argument("--header", action="append", default=[], metavar="K: V",
                    help="repeatable. For headers that are not secret: an argument is visible in `ps` "
                         "to anything running as you")
    ap.add_argument("--header-env", action="append", default=[], metavar="ENVVAR",
                    help="repeatable. Where the credential goes: the name of an environment variable "
                         "holding a whole 'Name: value' header, so the value stays out of argv")
    ap.add_argument("--items", required=True, metavar="PATH",
                    help="dotted path to the array of documents, e.g. messages or value")
    ap.add_argument("--author", required=True, metavar="PATH",
                    help="dotted path within one document, e.g. user or from.user.id")
    ap.add_argument("--text", required=True, metavar="PATH")
    ap.add_argument("--ts", metavar="PATH",
                    help="optional. Reported back by scan so a later read knows where to resume")
    ap.add_argument("--cursor-out", metavar="PATH",
                    help="dotted path to the next cursor. Without it, one page is read")
    ap.add_argument("--cursor-in", default="cursor", metavar="PARAM",
                    help="query parameter to send the cursor as (default: cursor)")
    ap.add_argument("--ok", metavar="PATH",
                    help="a field that must be truthy, e.g. ok. Some services answer 200 with a "
                         "refusal in the body, which otherwise reads as an empty page")
    ap.add_argument("--error", metavar="PATH", help="where the message is when --ok is falsy")
    ap.add_argument("--max-pages", type=int, default=1000)
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--retry-base", type=float, default=2.0, metavar="SECONDS")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    headers = headers_for(a.header, a.header_env)

    def note(line: str) -> None:
        if not a.quiet:
            print(line, file=sys.stderr, flush=True)

    url, pages, written = a.url, 0, 0
    started = time.monotonic()
    while url and pages < a.max_pages:
        payload = get(url, headers, a.retries, a.retry_base, note)
        pages += 1
        if a.ok and not dig(payload, a.ok):
            raise SystemExit(f"fetch: the service refused: "
                             f"{dig(payload, a.error) or json.dumps(payload)[:200]}")
        items = dig(payload, a.items)
        if items is None:
            raise SystemExit(f"fetch: no {a.items!r} in the response. It looks like "
                             f"{json.dumps(payload)[:200]}")
        for item in items:
            who = dig(item, a.author)
            text = dig(item, a.text)
            if who is None or text is None:
                continue
            row = {"author": str(who), "text": str(text)}
            when = dig(item, a.ts) if a.ts else None
            if when is not None:
                row["ts"] = when
            print(json.dumps(row), flush=True)
            written += 1
        cursor = dig(payload, a.cursor_out) if a.cursor_out else None
        url = with_cursor(a.url, a.cursor_in, cursor) if cursor else None
        if pages % 10 == 0:
            note(f"  {pages} pages, {written} documents, {int(time.monotonic() - started)}s")

    # The read either finished or hit a bound. Saying which is the difference between a complete
    # corpus and one that stopped, and nothing downstream can tell them apart from the output alone.
    if url:
        note(f"  stopped at --max-pages {a.max_pages} with more to read: {written} documents so far. "
             f"This corpus is incomplete.")
        return 2
    note(f"  read {written} documents from {pages} page(s) in "
         f"{int(time.monotonic() - started)}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
