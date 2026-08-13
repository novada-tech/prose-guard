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
    assumptions shared_context and reach, where the destination cannot say

Routing is on `matches` alone, deterministically. Prose is a bad router: a mistake there happens
before any check runs and so corrupts all of them. When nothing matches, the audience is
*unresolved* — the tool falls back to a configured baseline and stops being allowed to block,
because it is now guessing about the reader rather than knowing.

Combining several in-scope audiences is one operation per dimension, not one operation:

    vocabulary      intersection  - only what everyone knows is safe
    shared_context  minimum       - assume the least-informed reader
    reach           maximum       - the widest reader decides whether internal links resolve

There is deliberately no subset elimination. Dropping an audience whose members are contained in
another looks like a free simplification and is not sound: measured breadth within the larger group
does not imply every member of it knows the term, and dropping an audience can only widen the
vocabulary, which is the unsafe direction. `overlap()` reports shared membership for a human to
look at instead.
"""
import fnmatch
import glob
import json
import os
import subprocess

import paths
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
BUILTIN_DIR = os.path.join(_HERE, "..", "data", "audiences")

# How many distinct people have to have used a term before an audience is assumed to know it.
# 4 rather than 3 because on the corpus this was calibrated against, a term the team lead said
# plainly needed explaining reached exactly 3.
MIN_AUTHORS = 4

CONTEXT_ORDER = ("low", "medium", "high")
REACH_ORDER = ("internal", "public")


def config_dir():
    return paths.home()


def user_dir():
    return os.path.join(config_dir(), "audiences")


class Audience:
    def __init__(self, data, path, builtin, shared=False):
        self.path = path
        self.builtin = builtin
        # Shared means it came from a directory a team keeps, so it is not yours to delete: it goes
        # away when someone removes it from that repository.
        self.shared = shared
        self.name = data.get("name") or os.path.basename(path)[:-5]
        self.who = data.get("who") or ""
        self.matches_on = data.get("matches") or {}
        self.vocabulary = {str(k).upper(): int(v) for k, v in (data.get("vocabulary") or {}).items()}
        self.inherits = list(data.get("inherits") or [])
        self.members = list(data.get("members") or [])
        self.assumptions = data.get("assumptions") or {}
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
    def origin(self):
        return "built in" if self.builtin else ("shared" if self.shared else "yours")

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

    That order is the useful one. A team can correct a shipped baseline for everybody, and you can
    still override the team's copy locally — to try a change before proposing it, or because your own
    reading of an audience differs. `list` says which you are looking at.
    """
    found = {}
    layers = [(BUILTIN_DIR, True, False)]
    layers += [(d, False, True) for d in paths.shared()]
    layers.append((user_dir(), False, False))
    for directory, builtin, shared in layers:
        for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
            data = _read(path)
            if not data:
                continue
            a = Audience(data, path, builtin, shared)
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
        self.shared_context = min((a.assumptions.get("shared_context", "low") for a in source),
                                  key=lambda v: CONTEXT_ORDER.index(v)
                                  if v in CONTEXT_ORDER else 0) if source else "low"
        self.reach = max((a.assumptions.get("reach", "internal") for a in source),
                         key=lambda v: REACH_ORDER.index(v)
                         if v in REACH_ORDER else 0) if source else "internal"

    @property
    def names(self):
        return [a.name for a in self.audiences]

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
    for i, a in enumerate(named):
        for b in named[i + 1:]:
            hits = []
            for x in a.members:
                kx = _key(x)
                if len(kx) < 4:
                    continue
                for y in b.members:
                    ky = _key(y)
                    if len(ky) >= 4 and (kx.startswith(ky) or ky.startswith(kx)):
                        hits.append((x, y))
                        break
            out.append((a.name, b.name, hits, len(a.members), len(b.members)))
    return out



# ------------------------------------------------------------------------ writing
def path_for(name):
    return os.path.join(user_dir(), name + ".json")


def save(name, data):
    os.makedirs(user_dir(), exist_ok=True)
    path = path_for(name)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=1, sort_keys=False)
        fh.write("\n")
    return path


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
    """Whether the repository holding a directory is public, if that can be established.

    Best effort and clearly labelled as such. Whether names may be shared depends entirely on who can
    read the repository, and a URL does not carry that — a private repository and a public one look
    identical written down.
    """
    try:
        top = subprocess.run(["git", "-C", directory, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10)
        if top.returncode != 0:
            return None, "not a git repository, so nothing is shared by committing it"
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
    data.setdefault("_meta", {})["measured_over_people"] = len(people)
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, name + ".json")
    with open(target, "w") as fh:
        json.dump(data, fh, indent=1, sort_keys=False)
        fh.write("\n")
    return target, len(people)


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
        if a.with_names and public:
            raise SystemExit(
                f"{where}. --with-names would publish {len(ALL[a.name].members)} colleagues' names "
                f"to anyone. Share it without them, or point --to at a directory in a repository only "
                f"your team can read.")
        try:
            target, people = share(a.name, a.to, with_names=a.with_names)
        except (KeyError, PermissionError, ValueError) as exc:
            raise SystemExit(str(exc).strip("'"))
        print(f"{a.name} -> {target}")
        print(f"  measured over {people} people, and the file says so")
        if a.with_names and public is False:
            print(f"  their names are included. {where[0].upper() + where[1:]}, so that is who reads "
                  f"them.")
        elif a.with_names:
            print(f"  their names are included, and {where} — so check who can read it before you "
                  f"push.")
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
            print(f"{name:24s} {kind:9s} {aud.origin:9s} {known:4d} terms  "
                  f"{len(aud.members):3d} people  {where}")
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
        where = accept(a.name, a.term)
        print(f"{a.term.upper()} was already known to {a.name}; nothing to change" if where is None
              else f"updated {where}")
        return

    aud = ALL.get(a.name)
    if aud is None:
        raise SystemExit(f"no audience called {a.name!r}. Try: list")
    print(f"name       {aud.name}")
    print(f"file       {aud.path}  ({aud.origin})")
    print(f"who        {aud.who}")
    print(f"matches    {json.dumps(aud.matches_on)}")
    print(f"inherits   {', '.join(aud.inherits) or 'nothing'}")
    print(f"people     {len(aud.members)}: {', '.join(aud.members[:12])}"
          f"{' …' if len(aud.members) > 12 else ''}")
    print(f"assumes    {json.dumps(aud.assumptions)}")
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
