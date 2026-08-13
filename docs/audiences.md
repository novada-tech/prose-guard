# Managing audiences, and sharing them with a team

An audience is a file. Everything below reads or writes one, and you can do all of it by hand instead.

## Yours

```
python3 lib/audiences.py list                                   # every audience, and where it came from
python3 lib/audiences.py show platform                          # one in full
python3 lib/audiences.py accept platform GKE                    # one term is wrong; applies immediately
python3 lib/audiences.py match platform channel C054ZDE533R     # change when it applies
python3 lib/audiences.py match platform repo your-org/infra --rm
python3 lib/audiences.py rm platform
python3 lib/audiences.py overlap                                # people who may be in two at once
```

Three layers are read, and later replaces earlier by name:

| layer | where | what it is for |
|---|---|---|
| built in | inside the plugin | baselines like `engineers`, inherited rather than matched |
| shared | directories your team keeps | audiences somebody measured once, for everybody |
| yours | `$XDG_CONFIG_HOME/prose-guard/audiences` | what you measured, and any local override |

So a team can correct a shipped baseline for everyone, and you can still override the team's copy on
your own machine — to try a change before proposing it, or because your reading of an audience differs.
`list` says which one you are looking at.

## Sharing one with your team

Measuring an audience is the expensive part: a corpus, a scan, and a conversation about the borderline
terms. It only has to happen once. Share the result and a colleague gets it by pulling — no scan, no
setup, no decisions.

**One person, once:**

```
python3 lib/audiences.py share platform --to ~/work/team-scripts/claude/audiences
git -C ~/work/team-scripts add claude/audiences/platform.json
git -C ~/work/team-scripts commit -m 'Share the platform audience'
```

**Everyone else:** nothing, if your team's setup script registers the directory. Otherwise once:

```
python3 lib/share_dir.py --add '$TEAM_REPO/claude/audiences'
```

Paths keep their `$VARS` and `~` unexpanded in the config file and are expanded when read, so one line
works on machines that keep their checkouts in different places. A directory that does not exist yet is
skipped rather than fatal, so the line can be added before the checkout lands.

### Why sharing is its own command

Because you have audiences you do not want to share. A scan is run against whatever corpus was to hand,
and some audiences describe a handful of people, or a client, or a channel that was never meant to be a
subject. `share` takes one name and copies one file. There is no "share everything", and adding one
would be the wrong kind of convenient.

### Names

An audience records who was counted — logins and display names, from the corpus. Whether those travel
is a choice, and the default is the one that cannot go wrong:

```
python3 lib/audiences.py share platform --to DIR                # names stay on your machine
python3 lib/audiences.py share platform --to DIR --with-names   # names travel too
```

The **count** travels either way, in `_meta.measured_over_people`. That is the provenance a colleague
actually needs — an audience measured over 94 people deserves more trust than one measured over 5 —
and it names nobody.

Inside a team the names are unremarkable and useful: they are who the audience *is*, they make
`overlap` work, and the person who measured it is usually among them. Published, they are a list of
named people, and some of those names come from sources wider than the team — a public repository's
contributors, a channel shared with clients. So `share` asks GitHub whether the target repository is
public, reports what it found, and refuses `--with-names` when the answer is yes. Where it cannot tell,
it says so and leaves the decision with you.

### Retiring a shared audience

`rm` refuses one that came from a shared directory: deleting the file would take it from everybody on
your next push, and it would come back on your next pull. To stop using it yourself, write your own
file of the same name — yours wins. To retire it for everybody, remove it from the repository, in a
commit that says why.

## What a shared audience does not carry

Nothing about your machine. Routing identifiers, the measured vocabulary, the prose description of the
people, what it inherits, and the assumptions. A colleague who pulls it gets the same verdicts you get,
because those are the whole input.

The corpus it was measured from is not included either — it was never in the audience file. If you want
someone else to be able to re-measure rather than trust the result, share the export command, which is
a few lines of shell. [sources.md](sources.md) is about writing those.
