#!/usr/bin/env python3
"""Tests for prose-guard. Standard library only.

    python3 tests/test_prose_guard.py

Each case pins a design decision, not an implementation detail. The ones worth reading are the
severity tests — they are where the tool decides whether it knows enough to hold a message back —
and `test_no_subset_elimination`, which pins a simplification that was proposed, looks free, and is
not sound.

Mutation-checked rather than trusted on a green run; the mutations are listed in the README.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.abspath(os.path.join(HERE, "..", "plugins", "prose-guard"))
LIB = os.path.join(PLUGIN, "lib")
GUARD = os.path.join(PLUGIN, "hooks", "scripts", "guard-outgoing-prose.sh")
sys.path.insert(0, LIB)

PAD = (" Anyone still relying on the previous credentials will need to re-run the setup command "
       "before their next deploy actually goes through cleanly today.")
FAILS = []


def check(label, got, want):
    if got != want:
        FAILS.append(f"FAIL {label}: got {got!r}, wanted {want!r}")


def fresh(home):
    """Reload the modules that cache files at import time, pointed at a temporary home."""
    import importlib
    os.environ["PROSE_GUARD_HOME"] = home
    import audiences
    import destinations
    importlib.reload(audiences)
    importlib.reload(destinations)
    return audiences, destinations


def write_audience(home, name, **kw):
    d = os.path.join(home, "audiences")
    os.makedirs(d, exist_ok=True)
    data = {"name": name, "who": kw.pop("who", f"the {name}"),
            "matches": kw.pop("matches", {}), "inherits": kw.pop("inherits", []),
            "members": kw.pop("members", []), "vocabulary": kw.pop("vocabulary", {}),
            "assumptions": kw.pop("assumptions", {})}
    data.update(kw)
    with open(os.path.join(d, name + ".json"), "w") as fh:
        json.dump(data, fh)


class Ctx:
    def __init__(self, audience, situation=None):
        self.audience = audience
        self.situation = situation or {}


# --------------------------------------------------------------------- detection
def test_detection():
    import jargon
    known = {"CLI", "API"}

    def is_known(t):
        return t.upper() in known

    cases = [
        ("expanded in parentheses", "We use Application Default Credentials (ADC) here.", []),
        ("expanded in prose", "Terraform prefers Application Default Credentials. ADC is next.",
         []),
        ("never expanded", "ADC is a separate grant.", ["ADC"]),
        ("only inside code", "Run `gcloud auth ADC` now.", []),
        # someone else's words are not yours to answer for. Dropping blockquotes removed zero
        # detections across 301 real messages, whereas skipping any term inside backticks anywhere
        # would have silenced a third of the true positives.
        ("only in a blockquote", "They wrote:\n\n> move onto ADC soon\n\nNothing for me.", []),
        ("in my own prose", "We should move onto ADC soon.", ["ADC"]),
        ("screaming snake case", "The script exported GOOGLE_OAUTH_ACCESS_TOKEN on start.", []),
        # a one-letter word must not stand in for an initial: "a docker container" once made ADC
        # count as explained, passing a message that never explained it
        ("short words are not an expansion", "We ran a docker container, then ADC failed.",
         ["ADC"]),
        ("a real three-word expansion", "It reads application default credentials. ADC is next.",
         []),
        ("known terms pass", "The CLI calls the API twice.", []),
        # An acronym is by definition not a word. These all lowercase to real words and were being
        # reported as jargon nobody had explained — a regression the rebuild reintroduced, which
        # only showed up because the audiences skill printed its "needs explaining" pile.
        ("capitalised English words are not acronyms",
         "THE build WAS broken WITH a NULL logger and an ERROR in ASCII output.", []),
        # LOGGER lowercases to a real word. DEBUG does not, and is covered by the engineers
        # baseline instead — two different mechanisms, and it matters which one is doing the work.
        ("nor is a code identifier that happens to be a word",
         "The LOGGER never wrote anything at all.", []),
        # the word list holds base forms, so inflections need the suffix strip
        ("nor an inflected one", "It FAILS and nobody HAS COINED a name for that yet.", []),
    ]
    for label, text, want in cases:
        check(f"detect/{label}", jargon.scan(text + PAD, is_known)[0], want)
    # The denominator: every acronym-shaped term the reader met, known or not. A known term counts
    # even where the local dictionary happens to contain it — otherwise this number, and the share
    # threshold computed from it, differ between Linux and macOS.
    check("considered counts known terms too",
          jargon.scan("The CLI hit the API and then ADC failed." + PAD, is_known)[1],
          ["ADC", "API", "CLI"])
    check("and excludes things that are not acronyms at all",
          jargon.scan("THE ERROR was in the CLI." + PAD, is_known)[1], ["CLI"])
    # ZZQ is in no dictionary on any platform, so this case cannot drift with the word list
    check("an unknown non-word always counts",
          jargon.scan("The ZZQ pipeline broke." + PAD, is_known)[1], ["ZZQ"])


# --------------------------------------------------------------------- audiences
def test_it_survives_a_machine_with_no_dictionary():
    """Many Linux containers have no /usr/share/dict/words, and the filter that tells an acronym from
    a capitalised English word depends on it. Without a floor, THE, WAS and WITH are reported as
    unexplained jargon and the tool is noise — silently, which is the worst part.
    """
    import audiences
    import jargon
    real, jargon.WORDS = jargon.WORDS, jargon.SHIPPED_WORDS
    try:
        check("a floor ships with the tool", len(jargon.SHIPPED_WORDS) > 300, True)
        resolved = audiences.Resolved([], "engineers")
        bad, _ = jargon.scan(
            "THE build WAS broken WITH a NULL logger and an ERROR in ASCII output today, so nobody "
            "could tell what the GKE cluster did.", resolved.is_known)
        check("without a system dictionary only the real term is flagged", bad, ["GKE"])
    finally:
        jargon.WORDS = real


def test_modern_technical_words_are_not_jargon():
    """The system word list is the 1913 web2 dictionary and knows none of this.

    Someone ran the checker on a draft and the only thing it flagged was INLINE, from their own
    scaffolding header. INLINE is not an acronym, is not in the word list, and was not in the
    baseline — a whole class: KUBECTL, TERRAFORM, CIDR and 80 others were in the same position.
    """
    import audiences
    import jargon
    # Assert the OUTCOME, not which mechanism produces it. Two do: the word list catches anything
    # that lowercases to English (KAFKA is in it, for the author), and the baseline carries the rest.
    # A test on baseline membership would fail for a term the word list already handles.
    resolved = audiences.Resolved([], "engineers")
    def flagged(term):
        return jargon.is_acronym(term) and not resolved.is_known(term)

    for term in ("INLINE", "ASYNC", "ENUM", "REGEX", "KUBECTL", "TERRAFORM", "CIDR", "SUBNET",
                 "GRPC", "WEBHOOK", "MONOREPO", "CRON", "ZSH", "TMUX", "REDIS", "KAFKA", "TOML",
                 "SEMVER", "OTEL", "P99"):
        check(f"a developer knows {term}", flagged(term), False)
    # and nothing that genuinely needs explaining was swallowed to get there
    for term in ("ADC", "GKE", "SFTR", "MSCI", "FTSE", "CDM", "DRR", "FQN", "GAV", "ISDA"):
        check(f"{term} still needs explaining", flagged(term), True)


def test_everyday_abbreviations_are_not_jargon():
    """ASAP is not an engineer's term, and it is not an English word either.

    Real traffic flagged it six times in three thousand messages. Asking someone to expand ASAP is
    noise, and it is noise for every audience, so it belongs with the word list rather than in a
    baseline anyone could be missing.
    """
    import audiences
    import jargon
    resolved = audiences.Resolved([], "engineers")

    def flagged(term):
        return jargon.is_acronym(term) and not resolved.is_known(term)

    for term in ("ASAP", "FYI", "ETA", "AKA", "TLDR", "IIRC", "KPI", "PTO", "EOD"):
        check(f"any reader knows {term}", flagged(term), False)
    for term in ("HTML", "CSS", "GPU", "SMTP", "ACL", "TTY", "OOM"):
        check(f"any developer knows {term}", flagged(term), False)
    # LF lowercases to nothing and looks like line feed, so it is tempting to ship as known. In the
    # corpus it meant Linux Foundation in five of seven appearances, to readers who were not told.
    # Two letters rarely carry one meaning; an audience that does share it can learn it.
    check("LF stays flagged, being ambiguous", flagged("LF"), True)


def test_matching():
    with tempfile.TemporaryDirectory() as home:
        write_audience(home, "chat", matches={"slack_channels": ["C1"]})
        write_audience(home, "byrepo", matches={"repos": ["your-org/infra"]})
        write_audience(home, "byowner", matches={"github_owners": ["your-org"]})
        write_audience(home, "bypath", matches={"paths": ["docs/runbooks/*"]})
        A, _ = fresh(home)
        for label, ctx, want in (
                ("channel", {"channel": "C1"}, ["chat"]),
                ("repo", {"repo": "your-org/infra"}, ["byrepo"]),
                ("cwd repo", {"cwd_repo": "your-org/infra"}, ["byrepo"]),
                ("owner", {"owner": "your-org"}, ["byowner"]),
                ("path glob", {"path": "docs/runbooks/deploy.md"}, ["bypath"]),
                ("nothing", {"channel": "C9"}, []),
        ):
            check(f"match/{label}", sorted(A.resolve(ctx).names), want)
        # a baseline has no identifiers, so it can never be selected on its own
        check("a baseline never matches by itself",
              "engineers" in A.resolve({"channel": "C1"}).names, False)


def test_combination():
    """Three dimensions, three different combinators. Getting reach wrong is the expensive one."""
    with tempfile.TemporaryDirectory() as home:
        write_audience(home, "eng", matches={"slack_channels": ["C1"]},
                       vocabulary={"JVM": 9, "SHARED": 9},
                       assumptions={"shared_context": "high", "reach": "internal"})
        write_audience(home, "clients", matches={"slack_channels": ["C1"]},
                       vocabulary={"SHARED": 9, "SWAP": 9},
                       assumptions={"shared_context": "low", "reach": "public"})
        A, _ = fresh(home)
        r = A.resolve({"channel": "C1"})
        check("both audiences are in scope", sorted(r.names), ["clients", "eng"])
        check("vocabulary intersects", sorted(r.known), ["SHARED"])
        check("shared context takes the minimum", r.shared_context, "low")
        check("reach takes the maximum", r.reach, "public")
        check("the description names both", "several groups" in r.describe(), True)


def test_no_subset_elimination():
    """Dropping an audience contained in another looks free and is not sound.

    Measured breadth inside the larger group does not imply every member of it knows the term, and
    dropping an audience can only WIDEN the vocabulary, which is the unsafe direction. So a contained
    audience must keep constraining.
    """
    with tempfile.TemporaryDirectory() as home:
        write_audience(home, "big", matches={"slack_channels": ["C1"]},
                       members=["alice", "bobby", "carol", "dave"],
                       vocabulary={"WIDE": 9, "NARROW": 9})
        write_audience(home, "small", matches={"slack_channels": ["C1"]},
                       members=["alice", "bobby"], vocabulary={"WIDE": 9})
        A, _ = fresh(home)
        r = A.resolve({"channel": "C1"})
        check("the contained audience still constrains", sorted(r.known), ["WIDE"])
        # overlap is a HINT, not a fact: sources name people differently, so it is reported for a
        # person to confirm and nothing depends on it
        rows = A.possible_overlap()
        check("possible overlap is reported for a human instead",
              [(x, y, len(h)) for x, y, h, _, _ in rows], [("big", "small", 2)])


# --------------------------------------------------------------------- severity
def test_severity():
    """When the tool may hold a message back, and when it must only advise."""
    from checks import ADVISE, BLOCK, terms
    with tempfile.TemporaryDirectory() as home:
        write_audience(home, "team", matches={"slack_channels": ["C1"]},
                       vocabulary={f"T{i}": 9 for i in range(20)})
        A, _ = fresh(home)
        import importlib

        import checks.terms
        importlib.reload(checks.terms)
        terms = checks.terms

        unresolved = Ctx(A.resolve({"channel": "C9"}))
        resolved = Ctx(A.resolve({"channel": "C1"}))

        # no audience for this destination: the finding is a guess, so it cannot block
        f = terms.run("The ZZQ pipeline broke." + PAD, unresolved)
        check("unresolved advises", f.severity, ADVISE)
        check("and says it is guessing", "guess" in f.message, True)

        # a small, specific complaint against a known audience is actionable
        known_terms = " ".join(f"T{i}" for i in range(12))
        f = terms.run(f"Touching {known_terms} and also ZZQ today." + PAD, resolved)
        check("few unknown terms block", f.severity, BLOCK)

        # most of the terms unknown means the audience is wrong, not the message
        f = terms.run("ZZQ WQX YYT RRP MMN and LLK all changed today." + PAD, resolved)
        check("mostly unknown advises instead", f.severity, ADVISE)
        check("and says the audience is the likely problem", "audience is wrong" in f.message, True)

        # a share is meaningless when almost nothing is in play: 1 of 1 is 100% and still fixable
        f = terms.run("The ZZQ pipeline broke this morning." + PAD, resolved)
        check("one unknown term of one still blocks", f.severity, BLOCK)

        check("nothing to say when everything is known",
              terms.run(f"Touching {known_terms} today." + PAD, resolved), None)


# ------------------------------------------------------------------ destinations
def test_routing():
    with tempfile.TemporaryDirectory() as tmp:
        _, D = fresh(os.path.join(tmp, "home"))
        long = ("Removed the exporter line because nothing on a laptop reads that variable, and it "
                "broke terraform after an hour of shell uptime by shadowing the fallback "
                "credential entirely.")
        bodyfile = os.path.join(tmp, "body.md")
        with open(bodyfile, "w") as fh:
            fh.write(long)
        cases = [
            ("chat", "mcp__slack__slack_send_message", {"channel_id": "C1", "message": long},
             "chat message"),
            ("github comment", "mcp__github__add_issue_comment", {"body": long},
             "code review or issue comment"),
            ("commit -m", "Bash", {"command": f'git commit -m "{long}"'}, "commit message"),
            ("commit --message=", "Bash", {"command": f'git commit --message="{long}"'},
             "commit message"),
            ("commit -F", "Bash", {"command": f"git commit -F {bodyfile}"}, "commit message"),
            ("amend -m", "Bash", {"command": f'git commit --amend -m "{long}"'},
             "commit message"),
            ("tag -a -m", "Bash", {"command": f'git tag -a v1 -m "{long}"'}, "commit message"),
            ("gh comment", "Bash", {"command": f'gh pr comment 5 --body "{long}"'}, "github cli"),
            ("gh body-file", "Bash",
             {"command": f"gh pr create --title x --body-file {bodyfile}"}, "github cli"),
            ("git status", "Bash", {"command": "git status"}, None),
            ("read", "Read", {"file_path": "/tmp/x.md"}, None),
        ]
        for label, tool, ti, want in cases:
            dest = D.match(tool, ti)
            check(f"route/{label}", (dest or {}).get("name"), want)
            if want:
                check(f"extract/{label}", bool(D.extract(dest, tool, ti)), True)
        # the editor form carries no text, so it is claimed but nothing can be judged
        dest = D.match("Bash", {"command": "git commit"})
        check("commit with an editor has no text", D.extract(dest, "Bash", {"command": "git commit"}),
              None)
        # two -m flags are one message
        dest = D.match("Bash", {"command": f'git commit -m "Subject line here" -m "{long}"'})
        got = D.extract(dest, "Bash", {"command": f'git commit -m "Subject line here" -m "{long}"'})
        check("both -m parts are joined", got.startswith("Subject line here"), True)


def test_prose_files_must_be_tracked():
    """The line between a document colleagues will read and a scratch file is whether it gets
    committed. Extension alone would check the agent's own notes."""
    with tempfile.TemporaryDirectory() as tmp:
        _, D = fresh(os.path.join(tmp, "home"))
        long = "word " * 40
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        subprocess.run(["git", "-C", repo, "init", "-q"], capture_output=True)
        with open(os.path.join(repo, ".gitignore"), "w") as fh:
            fh.write("ignored.md\n")
        for label, path, want in (
                ("tracked markdown", os.path.join(repo, "README.md"), "prose file someone will read"),
                ("ignored markdown", os.path.join(repo, "ignored.md"), None),
                ("outside any repo", os.path.join(tmp, "loose.md"), None),
                ("source file", os.path.join(repo, "Main.java"), None),
        ):
            dest = D.match("Write", {"file_path": path, "content": long})
            check(f"prose file/{label}", (dest or {}).get("name"), want)


def test_user_destinations_win():
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        with open(os.path.join(home, "destinations.json"), "w") as fh:
            json.dump({"destinations": [
                {"name": "our briefing tool", "tool": ["send_briefing"], "text_fields": ["note"]},
                {"name": "stop checking commits", "bash": r"\bgit\s+commit\b", "text_arg": []},
            ]}, fh)
        _, D = fresh(home)
        long = "word " * 40
        check("a destination the user added is claimed",
              (D.match("example__send_briefing", {"note": long}) or {}).get("name"),
              "our briefing tool")
        # the override is listed first, so it wins and extracts nothing
        dest = D.match("Bash", {"command": f'git commit -m "{long}"'})
        check("a shipped destination can be overridden", dest.get("name"), "stop checking commits")
        check("and then nothing is extracted",
              D.extract(dest, "Bash", {"command": f'git commit -m "{long}"'}), None)


def test_passive_discovery():
    """It must speak up once, and never again — declining has to be permanent.

    The failure to avoid is: tool used, suggestion made, user declines, tool used again, same
    suggestion. That is what makes people turn a tool off.
    """
    with tempfile.TemporaryDirectory() as home:
        _, D = fresh(home)
        secret = "swordfish " * 40
        bash = ("Bash", {"command": f'my-cli notify --text "{secret}"'})
        mcp = ("mcp__example__post_update", {"body": secret})

        notes = [D.record_candidate(*mcp) for _ in range(6)]
        check("silent until it has been used enough to matter", notes[:2], [None, None])
        check("speaks up on the third use", notes[2] is not None, True)
        check("and never again", notes[3:], [None, None, None])

        raw = open(os.path.join(home, "unclaimed-destinations.json")).read()
        seen = json.loads(raw)
        check("no message text is ever written down", "swordfish" in raw, False)
        check("an mcp shape is the tool and the field",
              "tool: mcp__example__post_update [body]" in seen, True)
        D.record_candidate(*bash)
        check("a bash shape is binary, subcommand and flag",
              "bash: my-cli notify --text" in json.loads(
                  open(os.path.join(home, "unclaimed-destinations.json")).read()), True)

        # declining is permanent, and stops the counting
        D.decline("bash: my-cli notify --text")
        after = [D.record_candidate(*bash) for _ in range(5)]
        check("a declined shape is never mentioned", after, [None] * 5)
        entry = json.loads(open(os.path.join(home,
                                             "unclaimed-destinations.json")).read())[
            "bash: my-cli notify --text"]
        check("and stops being counted", entry["uses"], 1)

        # and the tracked set is bounded
        for i in range(80):
            D.record_candidate(f"mcp__example__tool{i}", {"body": secret})
        check("the tracked set is bounded",
              len(json.loads(open(os.path.join(home,
                                               "unclaimed-destinations.json")).read()))
              <= D.MAX_TRACKED, True)


def test_the_hook_surfaces_a_candidate_once():
    with tempfile.TemporaryDirectory() as tmp:
        home, state = os.path.join(tmp, "home"), os.path.join(tmp, "state")
        long = "word " * 40
        payload = {"tool_name": "mcp__example__post_update", "session_id": "pd", "cwd": tmp,
                   "tool_input": {"body": long}}
        verdicts = [run_guard(payload, home, state)[0] for _ in range(5)]
        check("the hook mentions an unclaimed destination exactly once",
              verdicts, ["allow", "allow", "advise", "allow", "allow"])


# ------------------------------------------------------------------- the hook
def env(home, state, effort="low"):
    e = {k: v for k, v in os.environ.items() if not k.startswith("PROSE_GUARD")}
    e.pop("CLAUDE_PLUGIN_DATA", None)
    e.pop("CLAUDE_PLUGIN_OPTION_EFFORT", None)
    e.update(PROSE_GUARD_HOME=home, PROSE_GUARD_STATE=state, PROSE_GUARD_EFFORT=effort)
    return e


def run_guard(payload, home, state, effort="low"):
    r = subprocess.run(["bash", GUARD], input=json.dumps(payload), capture_output=True,
                       text=True, env=env(home, state, effort), timeout=300)
    out = r.stdout.strip()
    if not out:
        return "allow", ""
    h = json.loads(out)["hookSpecificOutput"]
    if h.get("permissionDecision") == "deny":
        return "deny", h["permissionDecisionReason"]
    return "advise", h.get("additionalContext", "")


def test_hook_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write_audience(home, "team", matches={"slack_channels": ["C1"]}, inherits=["engineers"],
                       vocabulary={"GKE": 9})
        text = "We moved the kubectl configuration onto GKE this week." + PAD
        send = {"tool_name": "mcp__slack__slack_send_message", "session_id": "h1", "cwd": tmp,
                "tool_input": {"channel_id": "C1", "message": text}}
        check("a resolved audience that knows the term allows",
              run_guard(send, home, os.path.join(tmp, "s1"))[0], "allow")
        elsewhere = dict(send, session_id="h2",
                         tool_input={"channel_id": "C9", "message": text})
        verdict, why = run_guard(elsewhere, home, os.path.join(tmp, "s2"))
        check("an unknown destination advises", verdict, "advise")
        check("and names the term", "GKE" in why, True)
        check("disabled does nothing",
              run_guard(elsewhere, home, os.path.join(tmp, "s3"), "disabled")[0], "allow")


def test_session_ledger_bounds_the_argument():
    with tempfile.TemporaryDirectory() as tmp:
        home, state = os.path.join(tmp, "home"), os.path.join(tmp, "state")
        write_audience(home, "team", matches={"slack_channels": ["C1"]}, inherits=["engineers"],
                       vocabulary={"KUBECTL": 9})
        seq = []
        for n in range(10):
            payload = {"tool_name": "mcp__slack__slack_send_message", "session_id": "ledger",
                       "cwd": tmp,
                       "tool_input": {"channel_id": "C1",
                                      "message": f"Draft {n} still talks about GKE." + PAD}}
            seq.append(run_guard(payload, home, state)[0] == "deny")
        check("a session is blocked at most MAX_DENIALS times", sum(seq), 6)
        check("and stops blocking once the ledger is spent", any(seq[-2:]), False)


def test_state_stays_out_of_the_plugin():
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write_audience(home, "team", matches={"slack_channels": ["C1"]}, inherits=["engineers"])
        payload = {"tool_name": "mcp__slack__slack_send_message", "session_id": "fb", "cwd": tmp,
                   "tool_input": {"channel_id": "C1", "message": "GKE broke again." + PAD}}
        e = env(home, os.path.join(tmp, "state"))
        subprocess.run(["bash", GUARD], input=json.dumps(payload), capture_output=True, text=True,
                       env=e, timeout=300)
        check("state written where it was told",
              os.path.isfile(os.path.join(tmp, "state", "sessions", "fb.json")), True)
        # and with nowhere told, it lands beside everything else the tool remembers
        e2 = {k: v for k, v in e.items() if k != "PROSE_GUARD_STATE"}
        subprocess.run(["bash", GUARD], input=json.dumps(dict(payload, session_id="fb2")),
                       capture_output=True, text=True, env=e2, timeout=300)
        check("the fallback lands under the one config home",
              os.path.isfile(os.path.join(home, "sessions", "fb2.json")), True)
        check("no session state inside the plugin",
              os.path.isdir(os.path.join(PLUGIN, "sessions")), False)


# ------------------------------------------------------------------- the rest
def test_one_config_location():
    """The hook, the shell wrapper and a skill's plain shell must resolve the same directory.

    They did not. CLAUDE_PLUGIN_DATA is exported into a hook's environment but not into a skill's
    shell, so setup wrote ~/.config/prose-guard/config.json while the hook read
    ~/.claude/plugins/data/.../config.json. Setup looked like it worked and the guard stayed off.
    """
    import importlib

    import paths
    from checks import config
    with tempfile.TemporaryDirectory() as tmp:
        env_hookish = {**os.environ, "CLAUDE_PLUGIN_DATA": os.path.join(tmp, "plugindata"),
                       "HOME": tmp}
        env_hookish.pop("PROSE_GUARD_HOME", None)
        env_hookish.pop("XDG_CONFIG_HOME", None)
        got = subprocess.run(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, {LIB!r}); import paths; print(paths.home())"],
            capture_output=True, text=True, env=env_hookish, timeout=60).stdout.strip()
        check("CLAUDE_PLUGIN_DATA does not move the config",
              got, os.path.join(tmp, ".config", "prose-guard"))

        # and the shell wrapper agrees with paths.py
        wrapper = open(GUARD).read()
        check("the wrapper resolves the same directory",
              'CFG_HOME="${PROSE_GUARD_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/prose-guard}"'
              in wrapper, True)

        os.environ["PROSE_GUARD_HOME"] = tmp
        importlib.reload(paths)
        importlib.reload(config)
        check("config lands under the one home", config.CONFIG_PATH,
              os.path.join(tmp, "config.json"))
        del os.environ["PROSE_GUARD_HOME"]
        importlib.reload(paths)
        importlib.reload(config)


def test_verdict_parsing():
    """A checker that argues with itself and then agrees must count as agreeing.

    Running the checks on this repository's own README produced a reply that opened "FAIL:", worked
    through the objection, and ended "PASS". Reporting a retracted objection is worse than missing one.
    """
    from checks.ask import read_verdict
    cases = [
        ("PASS", True),
        ("PASS.", True),
        ('FAIL: "the silent row" is a coined label', False),
        # opened with a complaint, talked itself out of it, ended on the verdict
        ('FAIL: "x" might be unclear — actually re-examine: this is fine. PASS', True),
        ("", True),
        ("I have no opinion", True),
    ]
    for out, want_ok in cases:
        check(f"verdict/{out[:34]!r}", read_verdict(out)[0], want_ok)
    check("the reason survives a real failure",
          "coined label" in read_verdict('FAIL: "the silent row" is a coined label')[1], True)


def test_the_two_check_prose_flags_do_different_jobs():
    """--for sets the vocabulary, --who describes the reader. Neither may be silently ignored.

    Someone passed --who and the output said "none named, assuming engineers", which reads as though
    their sentence had been thrown away. It had not — the model-based checks were given it — but
    nothing said so, and they could not tell.
    """
    script = os.path.join(LIB, "check_prose.py")
    with tempfile.TemporaryDirectory() as tmp:
        draft = os.path.join(tmp, "d.md")
        with open(draft, "w") as fh:
            fh.write("The ZZQ reporting path now runs against the new cluster and anyone still "
                     "pointing at the old endpoint should switch before the end of the week.")
        env = {**os.environ, "PROSE_GUARD_HOME": os.path.join(tmp, "home")}
        env.pop("PROSE_GUARD_EFFORT", None)

        def run(*args):
            return subprocess.run([sys.executable, script, draft, "--effort", "low", *args],
                                  capture_output=True, text=True, env=env, timeout=300).stdout

        plain = run()
        check("with no --for, nothing is enforced", "nothing is held back" in plain, True)
        check("and it says how to enforce", "--for engineers" in plain, True)

        described = run("--who", "the ops rota, arriving cold")
        check("a --who is echoed back so it is visibly used",
              "the ops rota, arriving cold" in described, True)
        check("and is marked as not reaching the term check",
              "not by terms" in described, True)

        named = run("--for", "engineers")
        check("--for accepts a shipped baseline", "terms judged against: engineers" in named, True)
        check("and says it is a baseline rather than measured", "not measured" in named, True)
        check("naming it explicitly enforces", "must fix" in named, True)


def test_levels():
    """Which checks each level runs, and that low never reaches a model.

    Isolated from the developer's own config on purpose: an earlier version read
    ~/.config/prose-guard/config.json, so it passed or failed depending on whether the person
    running the tests happened to have the tool switched on.
    """
    import importlib

    import checks
    import paths
    from checks import config
    for level, names in (("disabled", []),
                         ("low", ["terms"]),
                         ("medium", ["terms", "judgement"]),
                         ("high", ["terms", "relevance", "structure", "sentence", "reference",
                                   "address"])):
        check(f"level/{level}", [c.NAME for c in checks.for_effort(level)], names)
    check("only the judgement checks cost a call",
          [c.COSTS_A_CALL for c in checks.for_effort("low")], [False])
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PROSE_GUARD_HOME"] = tmp
        importlib.reload(paths)
        importlib.reload(config)
        for bad in ("", "nonsense", "LOW "):
            os.environ["PROSE_GUARD_EFFORT"] = bad
            check(f"an unrecognised level is disabled ({bad!r})", config.effort(), "disabled")
        del os.environ["PROSE_GUARD_EFFORT"]
    del os.environ["PROSE_GUARD_HOME"]
    importlib.reload(paths)
    importlib.reload(config)


def test_audience_editing():
    import audiences
    with tempfile.TemporaryDirectory() as home:
        write_audience(home, "team", matches={"slack_channels": ["C1"]}, vocabulary={"AAA": 9})
        A, _ = fresh(home)
        check("accept adds a term", bool(A.accept("team", "bbb")), True)
        A, _ = fresh(home)
        check("and it is known afterwards", A.resolve({"channel": "C1"}).is_known("BBB"), True)
        check("accepting a known term changes nothing", A.accept("team", "AAA"), None)
        A.remove("team")
        A, _ = fresh(home)
        check("removed audiences are gone", "team" in A.ALL, False)
        try:
            A.remove("engineers")
            check("a built-in cannot be deleted", "no error", "PermissionError")
        except PermissionError:
            pass


def test_rule_installer():
    with tempfile.TemporaryDirectory() as tmp:
        e = {**os.environ, "HOME": tmp}
        script = os.path.join(LIB, "install_rule.py")

        def run(*args):
            return subprocess.run([sys.executable, script, *args], capture_output=True, text=True,
                                  env=e, timeout=60).stdout.strip()

        check("absent before installing", run().startswith("absent"), True)
        run("--install")
        target = os.path.join(tmp, ".claude", "rules", "prose-guard-communication.md")
        check("installed as a real file, not a link",
              os.path.isfile(target) and not os.path.islink(target), True)
        check("current after installing", run().startswith("current"), True)
        with open(target, "a") as fh:
            fh.write("\nedited\n")
        check("an edited copy is reported as stale", run().startswith("stale"), True)
        check("and is not silently overwritten", run("--install").startswith("stale"), True)
        run("--remove")
        check("removable", os.path.exists(target), False)

def teardown_function(_fn):
    """Make pytest as honest as running this file directly.

    `check` records rather than raises, so one test reports every one of its failures instead of
    stopping at the first. That also means a test function returns normally when it has failed, so
    under pytest all of these passed unconditionally — including three that were mutation-tested
    against broken code and never noticed. pytest calls this after each test.
    """
    if FAILS:
        recorded, FAILS[:] = list(FAILS), []
        raise AssertionError("\n" + "\n".join(recorded))


def main():
    # Discovered, not listed. A hand-maintained list silently skipped three tests that had been
    # written, committed and were passing locally.
    tests = sorted((fn for name, fn in globals().items()
                    if name.startswith("test_") and callable(fn)),
                   key=lambda fn: fn.__code__.co_firstlineno)
    # Every test this file defines has to be one that ran. Three were written, committed and green
    # locally while the runner skipped them, and "all checks passed" is a worse outcome than a red
    # build: it is the same words as a real pass.
    import re
    defined = set(re.findall(r"^def (test_\w+)", open(__file__).read(), re.M))
    missed = defined - {fn.__name__ for fn in tests}
    if missed:
        print(f"FAIL these tests are defined but were not run: {', '.join(sorted(missed))}")
        return 1
    for fn in tests:
        try:
            fn()
        except Exception as exc:                # a test that cannot run is a failure, not a pass
            FAILS.append(f"ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
    for line in FAILS:
        print(line)
    if FAILS:
        print(f"\n{len(FAILS)} failure(s) in {len(tests)} tests")
        return 1
    print(f"prose-guard: all checks passed ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
