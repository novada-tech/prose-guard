"""Who reads this, and what they can be assumed to know.

An audience is a named set of people, a prose description of them, the identifiers that say a
message is going to them, and a measured vocabulary. Audiences overlap: one channel can hold two
of them, and then only what BOTH know is safe to leave unexplained.

    name        what to call it
    who         prose for the checks to read. NEVER used to decide which audience applies.
    matches     identifiers that decide which audience applies: channels, repos, owners, paths.
    vocabulary  {TERM: how many distinct people used it}
    inherits    built-in baselines, e.g. "engineers"
    members     who they are, from the learn step. Local only, never published.
    assumptions shared_context, where the destination cannot say

Routing is on `matches` alone, deterministically. Prose is a bad router: a mistake there happens
before any check runs and so corrupts all of them. When nothing matches, the audience is
*unresolved* — the tool falls back to a configured baseline and stops being allowed to block,
because it is now guessing about the reader rather than knowing.

Combining several in-scope audiences is one operation per dimension, not one operation:

    vocabulary      intersection  - only what everyone knows is safe
    shared_context  minimum       - assume the least-informed reader

There was a third dimension, `reach`, meant to say whether readers outside the company can see this.
Nothing ever read it: no prompt named it and no check asked for it, so two audiences differing only
in `reach` produced identical prompts. Public reach reaches a check through
`destinations.situation()`, which reads the destination's owner and is live. The audience dimension
is gone rather than left looking load-bearing.

There is deliberately no subset elimination. Dropping an audience whose members are contained in
another looks like a free simplification and is not sound: measured breadth within the larger group
does not imply every member of it knows the term, and dropping an audience can only widen the
vocabulary, which is the unsafe direction. `overlap()` reports shared membership for a human to
look at instead.
"""
import fnmatch
import itertools
import json
import os
import subprocess

import paths
import re

# How many distinct people have to have used a term before an audience is assumed to know it.
# 4 rather than 3 because on the corpus this was calibrated against, a term the team lead said
# plainly needed explaining reached exactly 3.
MIN_AUTHORS = 4

CONTEXT_ORDER = ("low", "medium", "high")

# What a name may be, because a name becomes a filename. Not only typed by a person: it comes out of
# the audience file itself, and an audience file can arrive in a repository somebody pulled, so
# `../../.claude/settings` is a name a file can claim.
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


def user_dir():
    return paths.mine().audiences


def usable_name(name):
    """The name if it can become a filename, else None. The one gate between a name and a path.

    Every write goes through `path_for`, `path_for` goes through here, and `load` drops a file whose
    name does not survive it — so nothing downstream has to wonder where a name came from.

    Refused on the whole name, and `basename` taken afterwards rather than instead: taking the
    basename first turns `../../CLOBBERED` into the perfectly good name `CLOBBERED`, which writes
    somewhere harmless under a name nobody typed. Two ways to be wrong, and only one of them is loud.
    """
    text = str(name or "")
    return os.path.basename(text) if SAFE_NAME.fullmatch(text) else None


class Audience:
    def __init__(self, data, path, origin):
        self.path = path
        # Which layer it came from, in the words `list` prints: yours, shared, built in. One label,
        # from paths.layers(), so this and destinations.py cannot describe the same layer differently.
        self.origin = origin
        # The origin of the audience of the same name that this one displaced, or "". A file that
        # replaces a shipped baseline replaces a measured 227-term vocabulary that gains terms every
        # release, and nothing said so — while destinations printed `(shadowed by yours)` for exactly
        # this event. Set by `load`, which is the only thing in a position to see it happen.
        self.replaces = ""
        # The file's own name wins over the name inside it, if the inside one could not be a filename.
        # A hostile file must not even be listed under a name that traverses, because everything a
        # person then types that name at writes somewhere.
        self.name = usable_name(data.get("name")) or usable_name(os.path.basename(path)[:-5]) or ""
        self.who = data.get("who") or ""
        self.matches_on = data.get("matches") or {}
        self.vocabulary = {str(k).upper(): int(v) for k, v in (data.get("vocabulary") or {}).items()}
        # {TERM: {"Long Form": how many people wrote it out that way}}. Two entries for one term means
        # this audience uses that abbreviation for two different things.
        #
        # Required, not optional. A file without it was measured before expansions existed, and treating
        # that as "no ambiguity anywhere" is wrong in the one direction that matters: it reports an
        # overloaded abbreviation as safe. There is no compatibility shim, because there is no user base
        # to be compatible with — the audience is marked as needing a rescan and says so.
        self.stale = "expansions" not in data
        self.expansions = {str(k).upper(): dict(v)
                           for k, v in (data.get("expansions") or {}).items()}
        self.inherits = list(data.get("inherits") or [])
        self.members = list(data.get("members") or [])
        self.assumptions = data.get("assumptions") or {}
        # One place a level becomes a level. Anything that is not one ranks as the least-informed
        # reader, which is the safe end — and, more to the point, is no longer handed to the model as
        # itself: `"shared_context": "sideways"` in a hand-edited file used to reach a prompt verbatim,
        # as "how much they already know of this: sideways". `show` still prints the file's own words.
        level = self.assumptions.get("shared_context")
        self.shared_context = level if level in CONTEXT_ORDER else CONTEXT_ORDER[0]
        self.meta = data.get("_meta") or {}

    # ---------------------------------------------------------------- matching
    def matches(self, ctx):
        """ctx carries whatever the tool call revealed: channel, repo, owner, path, cwd_repo."""
        m = self.matches_on
        # `channels` is generic on purpose: any chat destination yields a channel id, and whatever
        # produced the message already knows which product it came from.
        if ctx.get("channel") and ctx["channel"] in (m.get("channels") or []):
            return True
        for key in ("repo", "cwd_repo"):
            if ctx.get(key) and ctx[key] in (m.get("repos") or []):
                return True
        if ctx.get("owner") and ctx["owner"] in (m.get("github_owners") or []):
            return True
        path = ctx.get("path")
        if path:
            for pattern in m.get("paths") or []:
                if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(os.path.basename(path),
                                                                     pattern):
                    return True
        return False

    def known(self, baselines):
        """Terms this audience can be assumed to know: measured, plus any baseline it inherits."""
        terms = {t for t, n in self.vocabulary.items() if n >= MIN_AUTHORS}
        for name in self.inherits:
            terms |= baselines.get(name, set())
        return terms

    @property
    def builtin(self):
        return self.origin == "built in"

    @property
    def shared(self):
        """It came from a directory a team keeps, so it is not yours to delete: it goes away when
        somebody removes it from that repository."""
        return self.origin == "shared"

    @property
    def rescan_note(self):
        """Why this audience cannot tell an overloaded abbreviation apart, or "" if it can.

        Two different reasons, and telling someone to rescan a file they did not measure is worse than
        saying nothing: a shared audience arrives without expansions on purpose, because each one is a
        phrase copied out of somebody's private writing.
        """
        if not (self.stale and self.matches_on):
            return ""
        if self.shared:
            return "no expansions: a shared audience travels without them"
        return "rescan: no expansions recorded"

    def __repr__(self):
        return f"<Audience {self.name} {len(self.vocabulary)} terms, {self.origin}>"


def _read(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None


def load():
    """Built-ins, then your team's, then yours. Later replaces earlier by name.

    That order is the useful one, and it is `paths.layers()` read backwards — nearest last, because an
    audience is a measured whole and the nearest one has to be the one that survives. A team can
    correct a shipped baseline for everybody, and you can still override the team's copy locally, to
    try a change before proposing it or because your own reading of an audience differs.

    Replacing is not free and is now visible: what a file displaced is recorded on it, so `list` can
    say that the 227-term shipped baseline is not what is being used.
    """
    found = {}
    for layer in reversed(paths.layers()):
        for path in layer.audience_files():
            data = _read(path)
            if not data:
                continue
            a = Audience(data, path, layer.origin)
            if not a.name:
                continue                      # neither its name nor its filename could be a filename
            if a.name in found:
                a.replaces = found[a.name].origin
            found[a.name] = a
    return found


ALL = load()
# A baseline is an audience with no `matches` of its own: it exists to be inherited.
BASELINES = {name: a.known({}) for name, a in ALL.items() if not a.matches_on}


class Resolved:
    """What one outgoing message is being judged against."""

    def __init__(self, audiences, unresolved_default=None):
        self.audiences = audiences
        self.resolved = bool(audiences)
        self.fallback = unresolved_default if not audiences else None
        source = audiences or ([ALL[unresolved_default]] if unresolved_default in ALL else [])
        sets = [a.known(BASELINES) for a in source]
        self.known = set.intersection(*sets) if sets else set()
        # The least-informed reader in scope. Every value is already one of CONTEXT_ORDER, because
        # Audience clamped it on the way in, so this is a ranking and nothing else.
        self.shared_context = min((a.shared_context for a in source),
                                  key=CONTEXT_ORDER.index) if source else CONTEXT_ORDER[0]

    @property
    def names(self):
        return [a.name for a in self.audiences]

    def meanings(self, term):
        """What this term has been written out as, by how many people, across the audiences in scope."""
        out = {}
        for a in self.audiences:
            for long, count in (a.expansions.get(term.upper()) or {}).items():
                out[long] = out.get(long, 0) + count
        return out

    def is_known(self, term):
        return term.upper() in self.known

    def describe(self):
        """The prose the model-based checks are given. Only ever descriptive."""
        if not self.resolved:
            who = (ALL[self.fallback].who if self.fallback in ALL else "")
            return (f"unknown: no audience is configured for this destination, so the "
                    f"'{self.fallback}' baseline is assumed. {who}").strip()
        if len(self.audiences) == 1:
            return self.audiences[0].who or self.audiences[0].name
        joined = "; ".join(f"{a.name}: {a.who}" for a in self.audiences)
        return ("several groups at once, so assume only what all of them share — " + joined)


def resolve(ctx, unresolved_default="engineers"):
    scope = [a for a in ALL.values() if a.matches_on and a.matches(ctx)]
    return Resolved(scope, unresolved_default)


def _key(name):
    """A person's name reduced to something two sources might agree on."""
    return re.sub(r"[^a-z]", "", name.lower())


def _might_be(x, y):
    """Whether two names from different sources might be one person. A prefix match on at least four
    letters: shorter than that, initials collide with everybody."""
    kx, ky = _key(x), _key(y)
    return min(len(kx), len(ky)) >= 4 and (kx.startswith(ky) or ky.startswith(kx))


def possible_overlap():
    """People who MIGHT be in two audiences at once. A hint for a person, never a fact.

    Exact overlap is not computable and the tool does not pretend otherwise. Sources name people
    differently — a chat export gives display names, a repository gives logins — so "Sam" and
    "sam-t" are one person that no comparison here can join with confidence, and a plain set
    intersection reports zero while several people are in both.

    So this matches on a normalised prefix and is labelled as a guess. Nothing depends on it:
    audiences are never merged or dropped on the strength of it, because a wrong guess would widen
    a vocabulary, which is the unsafe direction.
    """
    named = [a for a in ALL.values() if a.members]
    out = []
    for a, b in itertools.combinations(named, 2):
        # One hit per left-hand name: two people on the right whose names both prefix-match would be
        # one guess reported twice.
        hits = [(x, y) for x in a.members
                if (y := next((y for y in b.members if _might_be(x, y)), None))]
        out.append((a.name, b.name, hits, len(a.members), len(b.members)))
    return out



# ------------------------------------------------------------------------ writing
def path_for(name, directory=None):
    """Where an audience file goes. The only place a name turns into a path.

    Refuses rather than sanitising quietly, because a name that is not a usable name means the file it
    came from is not what it says it is. `save` writes the dict it read, keys it knows nothing about
    included, so an unchecked name here wrote attacker-chosen JSON to an attacker-chosen path with
    `.json` appended — `../../.claude/settings` being the one that then gets executed.
    """
    safe = usable_name(name)
    if not safe:
        raise ValueError(f"{name!r} is not a usable audience name: a letter or digit first, then "
                         f"letters, digits, dot, dash or underscore, up to 64 characters")
    return os.path.join(directory or user_dir(), safe + ".json")


def _write(path, data):
    """One writer, so every audience file on disk has the same shape whoever wrote it — the file a
    `share` puts in a team repository has to be readable by `load` on someone else's machine."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=1, sort_keys=False)
        fh.write("\n")
    return path


def save(name, data):
    return _write(path_for(name), data)


def remove(name):
    a = ALL.get(name)
    if a is None:
        raise KeyError(name)
    if a.builtin:
        raise PermissionError(f"{name} ships with the tool. Write your own {path_for(name)} to "
                              f"replace it instead of deleting it.")
    if a.shared:
        raise PermissionError(
            f"{name} is shared with your team, from {a.path}. Deleting the file here would take it "
            f"from everyone on your next push, and it would come back on the next pull. To stop using "
            f"it yourself, write your own {path_for(name)} — that wins locally. To retire it for "
            f"everybody, remove it from that repository and say why.")
    os.remove(a.path)
    return a.path


def accept(name, term):
    """Mark a term known for one audience, at full confidence, without re-measuring.

    What to reach for when a single flag is wrong. It edits the audience file, so it is visible in
    the same place as everything the learn step wrote.
    """
    a = ALL.get(name)
    if a is None or a.builtin:
        raise KeyError(f"{name} is not an audience you can edit")
    data = _read(a.path) or {}
    vocab = data.setdefault("vocabulary", {})
    t = term.upper()
    if int(vocab.get(t, 0)) >= MIN_AUTHORS:
        return None                           # already known: say so rather than claim a change
    vocab[t] = MIN_AUTHORS
    hand = data.setdefault("_meta", {}).setdefault("accepted_by_hand", [])
    if t not in hand:
        hand.append(t)
    return save(a.name, data)


# The dimensions an audience can be routed on. `channels` is generic on purpose: a channel id is a
# channel id whether it came from Slack, Teams or Discord, and the destination that produced it
# already knows which product it is. Nothing below this line is Slack-specific.
DIMENSIONS = {
    "channel": "channels",
    "repo": "repos",
    "owner": "github_owners",
    "path": "paths",
}


def route(name, dimension, values, drop=False):
    """Add or remove the identifiers that decide when an audience applies.

    Without this the only way to widen an audience was to hand-edit its JSON, which someone did —
    and hand-editing is where a typo silently stops an audience from ever matching again.
    """
    a = ALL.get(name)
    if a is None or a.builtin:
        raise KeyError(f"{name} is not an audience you can edit")
    key = DIMENSIONS[dimension]
    data = _read(a.path) or {}
    matches = data.setdefault("matches", {})
    have = list(matches.get(key) or [])
    if drop:
        after = [v for v in have if v not in values]
    else:
        after = have + [v for v in values if v not in have]
    if after == have:
        return None, have                     # say nothing changed rather than claim it did
    if after:
        matches[key] = after
    else:
        matches.pop(key, None)
    return save(a.name, data), after


# `members` is the list of colleagues whose writing was counted — logins and display names. Within a
# team it is unremarkable and useful: it is who the audience is, it makes `overlap` work, and the
# measurer is usually in it. Published, it is a list of named people, and some of those names come
# from sources wider than the team, like a public repository's contributors or a channel shared with
# clients. So it is a choice rather than a rule, and the default is the one that cannot go wrong.
#
# The COUNT travels either way, because that is the provenance a reader actually needs: an audience
# measured over 94 people deserves more trust than one measured over 5, and neither answer requires a
# name.
def visibility(directory):
    """Whether the repository holding a directory is public: True, False, or None for cannot tell.

    Best effort and clearly labelled as such. Whether names may be shared depends entirely on who can
    read the repository, and a URL does not carry that — a private repository and a public one look
    identical written down.

    Only `False` is a permission to publish names. `None` — no repository yet, no `gh`, `gh` not
    logged in, a remote GitHub cannot describe — is how a first-time user arrives, and it used to be
    falsy enough to publish them.
    """
    try:
        top = subprocess.run(["git", "-C", directory, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        if top.returncode != 0:
            return None, "that directory is not in a git repository, so nobody can say who will read it"
        seen = subprocess.run(["gh", "repo", "view", "--json", "visibility,nameWithOwner"],
                              capture_output=True, text=True, timeout=20,
                              cwd=top.stdout.strip())
        if seen.returncode != 0:
            return None, "could not ask GitHub what this repository is"
        found = json.loads(seen.stdout)
        public = str(found.get("visibility", "")).upper() == "PUBLIC"
        return public, f"{found.get('nameWithOwner')} is {str(found.get('visibility')).lower()}"
    except Exception:
        return None, "could not tell who can read this repository"


def share(name, directory, with_names=False):
    """Copy one audience into a directory a team keeps.

    Sharing is a separate verb on purpose. This shares exactly the one you name — audiences are
    measured from real conversations, and publishing the lot because it was convenient is not a thing
    to make easy.
    """
    a = ALL.get(name)
    if a is None:
        raise KeyError(f"no audience called {name}")
    if a.builtin:
        raise PermissionError(f"{name} ships with the tool — everyone already has it")
    data = _read(a.path) or {}
    if not (data.get("matches") or {}):
        raise ValueError(f"{name} has no identifiers, so it would never apply on anyone else's "
                         f"machine. Add some with `match` first")
    people = list(data.get("members") or [])
    if not with_names:
        data.pop("members", None)
    # Expansions never travel. Each one is a phrase copied verbatim out of writing the team did in
    # private — "BSP: Big Secret Project" — so it is where an unreleased project name or a client name
    # appears in full, and a share can land in a public repository. The receiving side is told what it
    # is missing rather than left to assume nothing here is ambiguous: `rescan_note` says so, and
    # dropping the key rather than writing an empty one is what makes it say so.
    data.pop("expansions", None)
    data.setdefault("_meta", {})["measured_over_people"] = len(people)
    return _write(path_for(name, directory), data), len(people)


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="Inspect and manage audiences.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="every audience, where it came from, and what it covers")
    p = sub.add_parser("show", help="one audience in full")
    p.add_argument("name")
    p = sub.add_parser("rm", help="delete an audience you created")
    p.add_argument("name")
    p = sub.add_parser("accept", help="mark one term known for one audience")
    p.add_argument("name")
    p.add_argument("term")
    p = sub.add_parser("share", help="copy one audience into a directory your team keeps")
    p.add_argument("name")
    p.add_argument("--to", required=True, metavar="DIR",
                   help="a directory in a repository your colleagues already clone")
    p.add_argument("--with-names", action="store_true",
                   help="include who was counted. Fine inside a team, and a published list of named "
                        "people if that repository is public. The count travels either way")
    p = sub.add_parser("match", help="change when an audience applies")
    p.add_argument("name")
    p.add_argument("dimension", choices=sorted(DIMENSIONS),
                   help="channel: a chat channel id | repo: owner/repo | owner: every repo under "
                        "an owner | path: a file glob")
    p.add_argument("values", nargs="+", metavar="VALUE")
    p.add_argument("--rm", action="store_true", help="remove these instead of adding them")
    sub.add_parser("overlap", help="people who may be in two audiences at once (a guess)")
    a = ap.parse_args()

    if a.cmd == "share":
        public, where = visibility(a.to)
        # Proved private, or the names stay here. Anything else — public, no repository, no `gh`, `gh`
        # not logged in, a host `gh` cannot describe — is a question nobody answered, and a list of
        # colleagues' names is not the thing to guess about.
        if a.with_names and public is not False:
            raise SystemExit(
                f"--with-names refused: {where}. Names travel only where GitHub says the repository is "
                f"private. Share it without them — the count travels either way and is the provenance "
                f"a colleague needs — or point --to at a directory in a private repository your team "
                f"already clones.")
        try:
            target, people = share(a.name, a.to, with_names=a.with_names)
        except (KeyError, PermissionError, ValueError) as exc:
            raise SystemExit(str(exc).strip("'"))
        print(f"{a.name} -> {target}")
        print(f"  measured over {people} people, and the file says so")
        if ALL[a.name].replaces == "built in":
            print(f"  it has the shipped {a.name} baseline's name, so everyone who pulls it stops "
                  f"reading the shipped one — including the terms later releases add to it")
        print(f"  written-out forms are not included: each is a phrase from private writing, so an "
              f"abbreviation this audience uses for two things is not told apart by whoever pulls it")
        if a.with_names:
            print(f"  their names are included, and {where} — so that is who reads them.")
        elif people:
            print(f"  their names are not, so `overlap` will not work for whoever pulls this. "
                  f"--with-names includes them.")
        print("\nNothing is shared until you commit it. Then anyone whose config lists that "
              "directory\ngets this audience by pulling — no scan, no setup:")
        print(f"  git -C {os.path.dirname(os.path.abspath(target))} add {os.path.basename(target)} "
              f"&& git commit -m 'Share the {a.name} audience'")
        return

    if a.cmd == "match":
        try:
            path, now = route(a.name, a.dimension, a.values, drop=a.rm)
        except KeyError as exc:
            raise SystemExit(str(exc).strip("\'"))
        verb = "no longer" if a.rm else "now"
        if path is None:
            print(f"{a.name} already reads exactly that — nothing changed")
        else:
            print(f"{a.name} {verb} covers {a.dimension} " + ", ".join(a.values))
            print(f"  {a.dimension}s: " + (", ".join(now) or "none"))
            print(f"  {path}")
        return

    if a.cmd == "list":
        if not ALL:
            print("no audiences")
            return
        for name, aud in sorted(ALL.items()):
            kind = "baseline" if not aud.matches_on else "audience"
            known = len(aud.known(BASELINES))
            where = ", ".join(f"{k}={len(v)}" for k, v in aud.matches_on.items()) or "inherit only"
            # A file of the same name in a nearer layer wins outright — an audience is a measured
            # whole, so there is no merging — and the one it displaced may be a shipped baseline that
            # gains terms every release. Silence about that is how a 227-term vocabulary becomes a
            # 1-term one without anybody deciding to.
            notes = [f"replaces the {aud.replaces} one" if aud.replaces else "", aud.rescan_note]
            print(f"{name:24s} {kind:9s} {aud.origin:9s} {known:4d} terms  "
                  f"{len(aud.members):3d} people  {where}"
                  + (f"   [{'; '.join(n for n in notes if n)}]" if any(notes) else ""))
        print(f"\nyours:  {user_dir()}")
        for directory in paths.shared():
            print(f"shared: {directory}")
        if not paths.shared():
            print("shared: none configured. `python3 lib/share_dir.py --add DIR` reads a directory "
                  "your team keeps")
        return

    if a.cmd == "overlap":
        rows = possible_overlap()
        if not rows:
            print("fewer than two audiences record who is in them")
            return
        print("Names that may be the same person in two audiences. A GUESS: sources name people")
        print("differently, so this cannot be exact, and nothing in the tool depends on it.\n")
        for x, y, hits, nx, ny in rows:
            print(f"{x} ({nx} people) and {y} ({ny} people): {len(hits)} possible matches")
            for left, right in hits[:8]:
                print(f"    {left}  ~  {right}")
            if len(hits) > 8:
                print(f"    … and {len(hits) - 8} more")
        return

    if a.cmd == "rm":
        try:
            print("deleted", remove(a.name))
        except KeyError:
            raise SystemExit(f"no audience called {a.name!r}. Try: list")
        except PermissionError as exc:
            raise SystemExit(str(exc))
        return

    if a.cmd == "accept":
        try:
            where = accept(a.name, a.term)
        except (KeyError, ValueError) as exc:
            raise SystemExit(str(exc).strip("'"))
        print(f"{a.term.upper()} was already known to {a.name}; nothing to change" if where is None
              else f"updated {where}")
        return

    aud = ALL.get(a.name)
    if aud is None:
        raise SystemExit(f"no audience called {a.name!r}. Try: list")
    print(f"name       {aud.name}")
    print(f"file       {aud.path}  ({aud.origin})"
          + (f", replacing the {aud.replaces} audience of the same name" if aud.replaces else ""))
    print(f"who        {aud.who}")
    print(f"matches    {json.dumps(aud.matches_on)}")
    print(f"inherits   {', '.join(aud.inherits) or 'nothing'}")
    print(f"people     {len(aud.members)}: {', '.join(aud.members[:12])}"
          f"{' …' if len(aud.members) > 12 else ''}")
    print(f"assumes    {json.dumps(aud.assumptions)}")
    if aud.expansions:
        for term, seen in sorted(aud.expansions.items()):
            if len(seen) > 1:
                print(f"ambiguous  {term}: " + ", ".join(f"{long} ({n})"
                                                         for long, n in sorted(seen.items(),
                                                                               key=lambda kv: -kv[1])))
    elif aud.rescan_note:
        print(f"rescan     {aud.rescan_note}, so an abbreviation used here for two things cannot be "
              f"told apart."
              + ("" if aud.shared else " Re-run /prose-guard:audiences to measure them."))
    known = sorted(t for t, n in aud.vocabulary.items() if n >= MIN_AUTHORS)
    below = sorted(t for t, n in aud.vocabulary.items() if n < MIN_AUTHORS)
    print(f"knows      {len(known)} measured + {len(aud.known(BASELINES)) - len(known)} inherited")
    print(f"           {', '.join(known[:25])}{' …' if len(known) > 25 else ''}")
    if below:
        print(f"too few    {', '.join(below[:25])}{' …' if len(below) > 25 else ''}"
              f"   (fewer than {MIN_AUTHORS} people used these, so they still need explaining)")
    if aud.meta:
        print(f"provenance {json.dumps(aud.meta)[:300]}")


if __name__ == "__main__":
    _cli()
