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
    # A real scan put FAQ, UK and GDPR in the borderline pile at three authors each, for a human to
    # judge. Every team that measures an audience would spend its judgement on the same terms, so
    # general knowledge — places, dates, units, currencies, titles — is universal here rather than
    # something each organisation re-measures.
    for term in ("FAQ", "UK", "GDPR", "GMT", "CET", "FRI", "SEP", "GB", "MB", "KM", "USD", "EUR",
                 "CEO", "VP", "LLC", "TBC", "PPT"):
        check(f"general knowledge, not vocabulary: {term}", flagged(term), False)
    for term in ("HTML", "CSS", "GPU", "SMTP", "ACL", "TTY", "OOM"):
        check(f"any developer knows {term}", flagged(term), False)
    # LF lowercases to nothing and looks like line feed, so it is tempting to ship as known. In the
    # corpus it meant Linux Foundation in five of seven appearances, to readers who were not told.
    # Two letters rarely carry one meaning; an audience that does share it can learn it.
    check("LF stays flagged, being ambiguous", flagged("LF"), True)


def test_a_stripped_suffix_must_leave_a_word_behind():
    """AWS was missing from a 225-term developer baseline and nothing ever reported it.

    The filter that tells an acronym from a capitalised English word strips plural and past-tense
    suffixes so FAILS and COINED are not treated as jargon. With no floor on what is left, AWS reduced
    to "aw" and AMD to "am" — both in the dictionary — so both were silently exempt, and every
    two-letter abbreviation added to the word list retired another family of acronyms with it.
    """
    import jargon
    # Against a word list written here, not the machine's. Ubuntu's wamerican holds amd, aws, ids and
    # ads outright while macOS's web2 does not, so asserting on the real dictionary tests the platform
    # rather than the floor — and passed on one of them.
    words = jargon.WORDS
    jargon.WORDS = {"am", "aw", "pr", "id", "ad", "fail", "coin", "use", "run", "pod", "job"}
    try:
        for term in ("FAILS", "COINED", "USES", "USED", "RUNS", "PODS", "JOBS"):
            check(f"{term} is an inflected word, not an acronym", jargon.is_acronym(term), False)
        # Each of these reduces to a two-letter word in that list. That is the whole failure.
        for term in ("AMD", "AWS", "PRD", "IDS", "ADS"):
            check(f"{term} is an acronym whatever it ends in", jargon.is_acronym(term), True)
    finally:
        jargon.WORDS = words

    import audiences
    resolved = audiences.Resolved([], "engineers")
    for term in ("AWS", "GCP", "TDD", "AMD", "CMD"):
        check(f"and a developer knows {term}", resolved.is_known(term), True)


def test_matching():
    with tempfile.TemporaryDirectory() as home:
        write_audience(home, "chat", matches={"channels": ["C1"]})
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
        write_audience(home, "eng", matches={"channels": ["C1"]},
                       vocabulary={"JVM": 9, "SHARED": 9},
                       assumptions={"shared_context": "high", "reach": "internal"})
        write_audience(home, "clients", matches={"channels": ["C1"]},
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
        write_audience(home, "big", matches={"channels": ["C1"]},
                       members=["alice", "bobby", "carol", "dave"],
                       vocabulary={"WIDE": 9, "NARROW": 9})
        write_audience(home, "small", matches={"channels": ["C1"]},
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
        write_audience(home, "team", matches={"channels": ["C1"]},
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
        # Real prose, because that is what discovery is looking for. "word " * 40 is long and is not
        # a paragraph, and the check that tells those apart is the point of the mechanism.
        long = ("The exporter line was removed because nothing on a laptop reads that variable. "
                "Plans had started failing in any shell older than an hour, so access uses the "
                "application default credential now. Continuous integration sets it itself.")
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
        # Real prose, because that is what discovery is looking for. "word " * 40 is long and is not
        # a paragraph, and the check that tells those apart is the point of the mechanism.
        long = ("The exporter line was removed because nothing on a laptop reads that variable. "
                "Plans had started failing in any shell older than an hour, so access uses the "
                "application default credential now. Continuous integration sets it itself.")
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
        secret = ("The exporter line was removed because nothing on a laptop reads swordfish. "
                  "Plans had started failing in any shell older than an hour, so access uses the "
                  "application default credential now. Continuous integration sets it itself.")
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


def test_discovery_proposes_how_hard_to_check_a_new_destination():
    """Adding a destination was a yes-or-no question, so everything discovered blocked at full effort.

    That is the wrong default for the two cases only a person can judge: whether anybody reads the text
    before its audience does, and whether it has an addressee at all. The name is weak evidence about
    both — enough to open with a proposal instead of a blank question. A suggestion only: applying one
    without asking would quietly stop a destination holding anything back.
    """
    import destinations as D
    check("a draft should advise rather than block",
          list(D.suggest_caps("tool: mcp__slack__slack_send_message_draft [message]")),
          ["max_severity"])
    check("a record should not pay for the reader checks",
          list(D.suggest_caps("bash: git commit -m")), ["max_effort"])
    # `note` on its own matched `glab mr note`, which is a comment on a merge request and has a reader.
    # A wrong suggestion here is a destination that silently stops blocking.
    check("a merge request comment is a message to somebody",
          D.suggest_caps("bash: glab mr note --message"), {})
    check("and an ordinary send gets no suggestion",
          D.suggest_caps("tool: mcp__example__post_update [body]"), {})
    for field, (value, why) in D.suggest_caps("bash: git commit -m").items():
        check("a suggestion carries a reason to agree or disagree with", len(why) > 30, True)


def test_the_mechanical_errors_are_found_without_a_model():
    """A word typed twice and `a` where `an` belongs. Two rules, because the others were noise.

    Measured on 3,000 real messages: these two produce 62 findings, about 2%, and nothing at all on the
    five documents already judged well built. Four more rules were tried and dropped — space before
    punctuation alone hit 1,131 times, almost every one a line break before a full stop, and together
    they flagged a third of everything written.

    Grammar in general is deliberately absent. The sentence that prompted this was a fragment with no
    main verb, which needs the sentence understood rather than pattern-matched — and asked about that
    sentence alone, `structure` found it in three runs of three and `sentence` in two of three. It got
    through because it sat inside 370 words, which is dilution, not a missing check.
    """
    from checks import mechanics
    for text, expected in (("we we should ship it", "typed twice"),
                           ("this is a interesting result", 'wants "an"'),
                           ("an legal opinion arrived today", 'wants "a"'),
                           ("the the same thing", "typed twice")):
        found = mechanics.scan(text)
        check(f"caught: {text[:26]}", bool(found) and expected in found[0], True)

    # Pronunciation, not spelling. Getting this wrong would flag correct English constantly.
    for correct in ("an FpML mapping arrived", "a UPI value", "a unique identifier", "a unanimous vote",
                    "an hour later", "a useful idea", "that that clause"):
        check(f"left alone: {correct[:24]}", mechanics.scan(correct), [])

    # Not prose: a doubled identifier in code, and a table row that repeats its heading.
    # Across a line break, a repeat is two headings or a heading and its text, not a typo. This was the
    # single biggest source of false positives before the rule was narrowed to one line.
    check("a heading repeated below itself is not a typo",
          mechanics.scan("Meeting\n\nMeeting notes follow"), [])
    check("nor a heading followed by its own text", mechanics.scan("labels\nLabels are set"), [])
    check("but the same line still counts", bool(mechanics.scan("we set the the labels")), True)
    check("code spans are not prose", mechanics.scan("run `git git log` twice"), [])
    check("table rows are not prose", mechanics.scan("| CDM CDM | x |"), [])
    check("indented blocks are not prose", mechanics.scan("    for for x in y:"), [])

    import audiences
    ctx = Ctx(audiences.Resolved([], "engineers"))
    from checks import BLOCK
    finding = mechanics.run("we we should ship this today, and it is a interesting result", ctx)
    check("it holds the message back", finding.severity, BLOCK)
    check("naming both", "typed twice" in finding.message and 'wants "an"' in finding.message, True)
    check("and says nothing about clean prose",
          mechanics.run("this sentence is entirely fine", ctx), None)
    check("costing no model call", mechanics.COSTS_A_CALL, False)


def test_a_finding_has_to_be_raised_twice():
    """A check that cannot reproduce its own complaint is generating nits, and chasing nits has no end.

    Measured on one 370-word document already through six rounds of editing: ten runs of the five
    model-based checks gave one clean result and nine findings, with no finding raised twice. `reference`
    objected on every run and to a different sentence almost every time. So a finding is put back to the
    same check and kept only if it points at the same sentence — after which four runs of the same
    document reported nothing actionable, which is what makes the rewrite loop terminate.
    """
    import checks
    text = ("One idea here and nothing else. A second sentence about the resolver and what it does. "
            "A third one entirely.")

    def about(span):
        return checks.Finding("advise", f'Consider: "{span}" is unclear')

    same = about("A second sentence about the resolver")
    reworded = about("second sentence about the resolver and what")
    elsewhere = about("A third one entirely")
    check("two findings on one sentence agree",
          checks._points_at(text, same), checks._points_at(text, reworded))
    check("two findings on different sentences do not",
          checks._points_at(text, same) == checks._points_at(text, elsewhere), False)
    check("a finding quoting nothing in the text points nowhere",
          checks._points_at(text, checks.Finding("advise", "no quotation at all")), -1)

    class Stub:
        NAME = "stub"
        COSTS_A_CALL = True

        def __init__(self, replies):
            self.replies = list(replies)

        def run(self, text, ctx):
            return self.replies.pop(0) if self.replies else None

    check("a check that says the same thing twice is believed",
          checks.confirms(Stub([reworded]), text, None, same), True)
    check("one that objects to something else is not",
          checks.confirms(Stub([elsewhere]), text, None, same), False)
    check("one that says nothing the second time is not",
          checks.confirms(Stub([]), text, None, same), False)
    # A deterministic check will say the same thing every time, so paying for a second run is waste.
    class Cheap(Stub):
        COSTS_A_CALL = False
    check("a deterministic finding needs no confirming",
          checks.confirms(Cheap([]), text, None, same), True)


def test_destinations_can_be_shared_like_audiences():
    """A destination is worth more shared than an audience.

    An audience is measured from one group's writing. A destination records which tool sends prose and
    which field carries it, and that is the same fact for everyone using that tool — worked out by an
    agent listing tools only it can see, confirmed by a person. Nobody should do that twice.
    """
    import destinations as D
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as team:
        os.environ["PROSE_GUARD_HOME"] = home
        mine = {"destinations": [{"name": "wiki page", "tool": ["wiki_write"],
                                  "text_fields": ["content"]}]}
        with open(os.path.join(home, "destinations.json"), "w") as fh:
            json.dump(mine, fh)
        _, D = fresh(home)

        import importlib
        import discover
        importlib.reload(discover)
        message = discover.share(team)
        check("it says what it copied", "wiki page" in message, True)
        landed = json.load(open(os.path.join(team, "destinations.json")))
        check("the destination travels", landed["destinations"][0]["name"], "wiki page")
        # Copying the shipped set would put a stale duplicate in front of the maintained one.
        check("and only what this machine added", len(landed["destinations"]), 1)
        check("sharing twice adds nothing", "0 added" in discover.share(team), True)

        # A colleague with nothing of their own but the directory registered.
        with tempfile.TemporaryDirectory() as theirs:
            with open(os.path.join(theirs, "config.json"), "w") as fh:
                json.dump({"shared": [team]}, fh)
            _, D2 = fresh(theirs)
            long = ("The exporter line went because nothing on a laptop reads that variable. Plans had "
                    "started failing in any shell older than an hour. Access uses the credential now.")
            got = D2.match("mcp__team__wiki_write", {"content": long})
            check("they have it without configuring anything", (got or {}).get("name"), "wiki page")
            # Their own file still wins, so they can stop checking it locally.
            with open(os.path.join(theirs, "destinations.json"), "w") as fh:
                json.dump({"destinations": [{"name": "mine instead", "tool": ["wiki_write"],
                                             "text_fields": ["content"]}]}, fh)
            _, D3 = fresh(theirs)
            check("and can override it locally",
                  D3.match("mcp__team__wiki_write", {"content": long})["name"], "mine instead")


def test_discovery_ignores_this_tool_talking_to_itself():
    """`--who` is a sentence describing a reader, so it passes the prose test, and the checker's own
    invocation was offered as a destination to add. Checking a check is circular."""
    import destinations as D
    prose = ("Engineers on this team read a pull request description for a plugin they use but did not "
             "write. They know git and the shell. They have not read this plugin internals at all.")
    for own in (f'python3 lib/check_prose.py draft.md --who "{prose}"',
                f'python3 measure/measure_rule.py --rule x --who "{prose}"',
                f'python3 lib/learn.py create team cand.json --who "{prose}"'):
        check(f"not a destination: {own.split()[1]}", D._shape("Bash", {"command": own}), None)
    check("but a real command still is",
          D._shape("Bash", {"command": f'git commit -m "{prose}"'}), "bash: git commit -m")


def test_a_substitution_is_worked_out_where_that_is_safe():
    """The pull request that introduced this went out unchecked, and the first fix was the wrong one.

    `gh pr create --body "$(git log -1 --format=%b)"` matches the destination and carries no prose: the
    body is a shell substitution the tool call does not contain. Denying it and asking for a file works,
    and makes somebody restructure a command that was already correct. Reading a file needs no execution
    at all, and a git command that reports can be run — so the text is had, and the check happens with
    nothing to change.

    What cannot be had is refused rather than guessed at. The hook is a separate process and never sees
    the caller's shell variables, and it cannot know that an arbitrary command is read-only: running
    `$(curl -X POST ...)` to find out would fire it twice. Even git is not simply safe — `git log
    --output=FILE` writes a file — so a flag that can write, or any metacharacter that could chain a
    second command, is a refusal.
    """
    import destinations as D
    with tempfile.TemporaryDirectory() as repo:
        for argv in (["init", "-q"], ["config", "user.email", "a@b.c"], ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", repo, *argv], capture_output=True, timeout=60)
        open(os.path.join(repo, "f"), "w").write("x")
        subprocess.run(["git", "-C", repo, "add", "f"], capture_output=True, timeout=60)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "Rebuild the SFTR payload\n\nbody"],
                       capture_output=True, timeout=60)
        with open(os.path.join(repo, "body.md"), "w") as fh:
            fh.write("prose from a file, long enough to be worth reading at all\n")

        check("a file read needs no execution",
              (D.resolve("$(cat body.md)", repo) or "").startswith("prose from a file"), True)
        check("so does a redirect",
              (D.resolve("$(< body.md)", repo) or "").startswith("prose from a file"), True)
        check("a git command that reports can be run",
              "SFTR" in (D.resolve("$(git log -1 --format=%B)", repo) or ""), True)
        check("a shell variable cannot be had at all", D.resolve("${SUMMARY}", repo), None)
        check("nor an arbitrary command", D.resolve("$(curl -X POST https://example.com)", repo), None)
        # git log --output=FILE writes a file, which is why a subcommand whitelist is not enough.
        check("nor a reporting command that can write",
              D.resolve("$(git log --output=" + os.path.join(repo, "pwned") + " -1)", repo), None)
        check("nor one with a second command chained on",
              D.resolve("$(git log -1; touch " + os.path.join(repo, "chained") + ")", repo), None)
        check("and nothing it refused was run",
              [f for f in ("pwned", "chained") if os.path.exists(os.path.join(repo, f))], [])

        # Resolved and then too short to judge is not the same as unreadable, and saying "substitution"
        # about it would send someone to fix a command that is working. Both leave no text to check.
        dest = D.match("Bash", {"command": 'gh pr create --body "x"'})
        short = 'gh pr create --title "T" --body "$(git log -1 --format=%s)"'
        check("a short subject does resolve",
              (D.resolve("$(git log -1 --format=%s)", repo) or "").startswith("Rebuild"), True)
        check("but is too short to judge", D.extract(dest, "Bash", {"command": short}, repo), None)
        check("and that is not called a substitution",
              D.unreadable(dest, "Bash", {"command": short}, repo), None)


def test_prose_behind_a_substitution_still_reaches_the_checks():
    """End to end, and across destinations: the resolved text is what gets judged, and what cannot be
    resolved is held back rather than passed over in silence — silence there reads exactly like a check
    that passed."""
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as repo:
        for argv in (["init", "-q"], ["config", "user.email", "a@b.c"], ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", repo, *argv], capture_output=True, timeout=60)
        open(os.path.join(repo, "f"), "w").write("x")
        subprocess.run(["git", "-C", repo, "add", "f"], capture_output=True, timeout=60)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m",
                        "Rebuild the SFTR reconciliation payload\n\nThe JSON payload has to be rebuilt "
                        "before the API can serve it over HTTP again, which is why continuous "
                        "integration has been red since yesterday afternoon."],
                       capture_output=True, timeout=60)
        write_audience(home, "team", matches={"paths": ["*"]}, inherits=["engineers"],
                       members=["a", "b", "c", "d"])
        with open(os.path.join(home, "config.json"), "w") as fh:
            json.dump({"effort": "low"}, fh)

        def ask(command, session):
            payload = {"tool_name": "Bash", "session_id": session, "cwd": repo,
                       "tool_input": {"command": command}}
            r = subprocess.run(["bash", GUARD], input=json.dumps(payload), capture_output=True,
                               text=True, env={**os.environ, "PROSE_GUARD_HOME": home}, timeout=180)
            if not r.stdout.strip():
                return "silent", ""
            out = json.loads(r.stdout)["hookSpecificOutput"]
            return ("deny" if out.get("permissionDecision") == "deny" else "advise",
                    out.get("permissionDecisionReason") or str(out.get("additionalContext") or ""))

        # The exact command that opened the pull request this came from.
        verdict, said = ask('gh pr create --title "T" --body "$(git log -1 --format=%B)"', "resolved")
        check("the resolved text reaches the checks", "SFTR" in said, True)
        check("and it is not a denial about being unreadable", "substitution" in said, False)

        # Every bash destination, without any of them being named here: both halves read the
        # destination's own text_arg, so one added later behaves the same.
        for name, command in (("commit message", 'git commit -m "$(git log -1 --format=%B)"'),
                              ("gitlab cli", 'glab mr note --message "$(git log -1 --format=%B)"')):
            verdict, said = ask(command, name[:6])
            check(f"{name}: a substitution is resolved too", "SFTR" in said, True)

        for name, command in (("commit message", 'git commit -m "${MSG}"'),
                              ("gitlab cli", 'glab mr note --message "$(python3 render.py)"')):
            verdict, said = ask(command, "u" + name[:5])
            check(f"{name}: what cannot be resolved is held back", verdict, "deny")
            check(f"{name}: naming the destination", name in said, True)

        # Bounded like every other denial, so a caller that cannot comply is not stuck.
        unresolvable = 'gh pr create --title "T" --body "${SUMMARY}"'
        check("asked once", ask(unresolvable, "bound")[0], "deny")
        check("asked twice", ask(unresolvable, "bound")[0], "deny")
        third, said_third = ask(unresolvable, "bound")
        check("then let through", third, "advise")
        check("saying why it stopped insisting", "not worth blocking" in said_third, True)
        check("and silent after that", ask(unresolvable, "bound")[0], "silent")


def test_discovery_ignores_long_text_that_is_not_going_anywhere():
    """Six mentions in real use, none of them a destination.

    `git grep -E '<a long alternation>'`, the text an edit replaces, a subagent prompt, a `Write` to a
    file the prose-file destination already decides on. Discovery gets one mention per shape for the
    life of the config, so spending it on a search pattern spends it on nothing — and a reader who is
    told three useless things stops reading the fourth.
    """
    import destinations as D
    prose = ("The exporter line was removed because nothing on a laptop reads that variable. Plans "
             "had started failing in any shell older than an hour, so access uses the application "
             "default credential now. Continuous integration sets it itself.")

    def shape(tool, **kw):
        return D._shape(tool, kw)

    pattern = "|".join(f"needle{n}_pattern_alternative" for n in range(12))
    # These two are long in words, which is why word count alone could not tell them from a paragraph.
    # The script has ordinary-looking words and few of them are words; the search has words and no
    # sentences. Each is rejected by a different half of the test.
    script = ("d = json.load(handle); rows = [r for r in d if r.keep]; print(len(rows), "
              "sum(r.n for r in rows)); os.makedirs(out, exist_ok=True); json.dump(rows, handle, "
              "indent=1); print(done, len(rows), total)")
    search = ("fix the flaky test|resolve the import cycle|update the changelog entry|bump the "
              "plugin version|drop the legacy flag|rename the routing key|share the audience file|"
              "read the whole corpus|stop the silent truncation|name the rival rule")
    for label, got in (
            ("a grep pattern", shape("Bash", command=f"git grep -E '{pattern}' lib/")),
            ("a long regex", shape("Bash", command=f"grep -E '{pattern}' -r .")),
            ("a script passed to -c", shape("Bash", command=f'python3 -c "{script}"')),
            ("a search whose pattern is words", shape("Bash", command=f"git log --grep '{search}'")),
            ("the text an edit replaces", shape("Edit", file_path="/x/y.md", old_string=prose,
                                                new_string=prose)),
            ("an instruction to a subagent", shape("Agent", prompt=prose)),
            ("a file being written", shape("Write", file_path="/x/y.md", content=prose))):
        check(f"not a destination: {label}", got, None)

    # And the things that are, still are.
    check("a commit message is", shape("Bash", command='git commit -m "' + prose + '"'),
          "bash: git commit -m")
    check("an unknown tool carrying prose is", shape("mcp__example__post_update", body=prose),
          "tool: mcp__example__post_update [body]")


def test_the_hook_surfaces_a_candidate_once():
    with tempfile.TemporaryDirectory() as tmp:
        home, state = os.path.join(tmp, "home"), os.path.join(tmp, "state")
        # Real prose, because that is what discovery is looking for. "word " * 40 is long and is not
        # a paragraph, and the check that tells those apart is the point of the mechanism.
        long = ("The exporter line was removed because nothing on a laptop reads that variable. "
                "Plans had started failing in any shell older than an hour, so access uses the "
                "application default credential now. Continuous integration sets it itself.")
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
        write_audience(home, "team", matches={"channels": ["C1"]}, inherits=["engineers"],
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
        write_audience(home, "team", matches={"channels": ["C1"]}, inherits=["engineers"],
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
        write_audience(home, "team", matches={"channels": ["C1"]}, inherits=["engineers"])
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
                         ("low", ["terms", "mechanics"]),
                         ("medium", ["terms", "mechanics", "judgement"]),
                         ("high", ["terms", "mechanics", "relevance", "structure", "sentence",
                                   "reference", "address"])):
        check(f"level/{level}", [c.NAME for c in checks.for_effort(level)], names)
    check("nothing at low costs a call",
          [c.COSTS_A_CALL for c in checks.for_effort("low")], [False, False])
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
        write_audience(home, "team", matches={"channels": ["C1"]}, vocabulary={"AAA": 9})
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


def test_a_vocabulary_can_come_from_any_command():
    """The only built-in sources were git and gh. Reading a chat channel meant an agent retyping it.

    A command emitting the JSONL contract keeps any other source disk-to-disk, so no corpus has to
    pass through a context window to be counted.
    """
    with tempfile.TemporaryDirectory() as home:
        e = {**os.environ, "PROSE_GUARD_HOME": home}
        out = os.path.join(home, "candidates.json")
        rows = [json.dumps({"author": who, "text": "the BSP run hit NFS latency again"})
                for who in ("ann", "bob", "cat", "dan")]
        rows.append(json.dumps({"author": "deploy-bot", "text": "BSP BSP BSP BSP BSP"}))
        emit = "printf '%s\\n' " + " ".join(repr(r) for r in rows)
        r = subprocess.run([sys.executable, os.path.join(LIB, "learn.py"), "scan",
                            "--command", emit, "--out", out],
                           capture_output=True, text=True, env=e, timeout=120)
        check("the scan succeeds", r.returncode, 0)
        found = json.load(open(out))
        check("BSP reached the known pile", "BSP" in found["known"], True)
        # The bot wrote BSP five times on its own. Counting writers rather than writings is what
        # stops one loud automated account from teaching the tool a term nobody read.
        check("a bot is not a person", found["counts"]["BSP"]["authors"], 4)
        check("nor is it a member", "deploy-bot" in found["members"], False)

        def scan(*commands, out=out):
            argv = [sys.executable, os.path.join(LIB, "learn.py"), "scan"]
            for c in commands:
                argv += ["--command", c]
            return subprocess.run(argv + ["--out", out], capture_output=True, text=True, env=e,
                                  timeout=120)

        r = scan("exit 3", out=out + ".2")
        check("a failing command is reported, not swallowed", "warning" in r.stderr, True)

        # A credential that authenticates and then has no data access exits 0 and prints an error
        # object. From here that is indistinguishable from an empty channel, and it was being written
        # up as a clean scan of nothing — the summary reads the same whatever the count is.
        r = scan('echo \'{"ok":false,"error":"missing_scope"}\'', out=out + ".3")
        check("a source that yields nothing usable is called out", "warning" in r.stderr, True)
        check("and it says a credential can look like this", "credential" in r.stderr, True)
        check("measuring an empty corpus is refused outright", r.returncode, 1)

        r = scan(emit, 'echo \'{}\'', out=out + ".4")
        check("one dead source among working ones does not stop the scan", r.returncode, 0)
        check("but it is named", "echo" in r.stderr and "warning" in r.stderr, True)

        # A bound on the read, and what was read kept on disk. Both exist for the same reason: a read
        # against a live service takes tens of minutes and can die at any point in them.
        kept = os.path.join(home, "kept.jsonl")
        argv = [sys.executable, os.path.join(LIB, "learn.py"), "scan", "--command", emit,
                "--max-documents", "2", "--keep", kept, "--out", out + ".5"]
        r = subprocess.run(argv, capture_output=True, text=True, env=e, timeout=120)
        check("the read stops where it was told to", "2 documents" in r.stdout, True)
        # Stopping early under-measures, which holds messages back rather than letting them out. Say
        # so, or a short read reads as a complete one.
        check("and says that under-measures", "under-measure" in r.stdout, True)
        check("what was read is on disk", len(open(kept).read().strip().splitlines()), 2)
        check("and is a corpus that can be read back",
              json.loads(open(kept).read().splitlines()[0])["author"], "ann")
        check("the file records that it stopped",
              json.load(open(out + ".5"))["_meta"]["stopped_early"], True)

        # A source can report where it got to, so a later read knows where to resume. Opaque here:
        # whatever the source calls a timestamp is reported back untouched.
        stamped = 'printf \'%s\\n\' \'{"author":"ann","text":"BSP","ts":"1700.5"}\' ' \
                  '\'{"author":"bob","text":"BSP","ts":"1700.9"}\''
        r = scan(stamped, out=out + ".6")
        check("the newest document read is reported", "1700.9" in r.stdout, True)


def test_a_rebuild_says_what_it_takes_away():
    """A rebuild wrote the routing under a key nothing read, and create printed success.

    The audience went on applying to its repositories and silently stopped applying to either chat
    channel, so nothing looked broken from any direction. The same shape of evidence catches a corpus
    that was read only part way: fewer people, fewer terms past the cut, fewer documents than last time.
    """
    with tempfile.TemporaryDirectory() as home:
        e = {**os.environ, "PROSE_GUARD_HOME": home}
        write_audience(home, "team",
                       matches={"repos": ["your-org/infra"], "channels": ["C1", "C2"]},
                       members=["ann", "bob", "cat", "dan"], vocabulary={"BSP": 9, "NFS": 5},
                       _meta={"learned_from": {"documents": 3879}})
        cand = os.path.join(home, "rebuild.json")
        with open(cand, "w") as fh:
            json.dump({"_meta": {"documents": 1200, "inherits": "engineers"},
                       "members": ["ann", "bob", "cat"], "known": ["BSP"],
                       "counts": {"BSP": {"authors": 4, "uses": 9}}}, fh)

        def run(*args):
            r = subprocess.run([sys.executable, os.path.join(LIB, "learn.py"), "create", "team",
                                cand, "--who", "the team", *args],
                               capture_output=True, text=True, env=e, timeout=120)
            return r.returncode, r.stdout + r.stderr

        code, out = run("--match-repo", "your-org/infra")
        check("a rebuild that drops routing is refused", code, 1)
        check("and it says which identifiers", "C1, C2" in out, True)
        after = json.load(open(os.path.join(home, "audiences", "team.json")))
        check("the existing audience is untouched", after["matches"].get("channels"), ["C1", "C2"])

        code, out = run("--match-repo", "your-org/infra", "--force")
        check("--force writes it anyway", code, 0)

        write_audience(home, "team",
                       matches={"repos": ["your-org/infra"], "channels": ["C1", "C2"]},
                       members=["ann", "bob", "cat", "dan"], vocabulary={"BSP": 9, "NFS": 5},
                       _meta={"learned_from": {"documents": 3879}})
        code, out = run("--match-repo", "your-org/infra", "--match-channel", "C1",
                        "--match-channel", "C2")
        check("keeping the routing is not refused", code, 0)
        # A narrower corpus is legitimate, so these warn rather than block — but silently is how a
        # truncated read gets written, and the document count looks reasonable whatever it is.
        check("a person leaving the corpus is reported", "dan" in out, True)
        check("a term falling below the cut is reported", "NFS" in out, True)
        check("and a corpus that shrank is reported", "3879 documents to 1200" in out, True)


def test_routing_can_be_edited_without_hand_editing_json():
    """Someone widening an audience hand-edited its file, which is where a typo silently stops it
    matching. The dimensions are named generically: a channel id is a channel id, whatever chat
    product produced it."""
    import audiences
    with tempfile.TemporaryDirectory() as home:
        write_audience(home, "team", matches={"repos": ["your-org/infra"]})
        A, _ = fresh(home)
        path, now = A.route("team", "channel", ["C1", "C2"])
        check("adding a channel writes the file", bool(path), True)
        check("both are kept", now, ["C1", "C2"])
        A, _ = fresh(home)
        check("the channel routes", A.resolve({"channel": "C2"}).names, ["team"])
        check("and so does the repo it already had", A.resolve({"repo": "your-org/infra"}).names,
              ["team"])
        A, _ = fresh(home)
        check("re-adding changes nothing", A.route("team", "channel", ["C1"])[0], None)
        A.route("team", "channel", ["C1", "C2"], drop=True)
        A, _ = fresh(home)
        gone = A.resolve({"channel": "C2"})
        check("dropping the last one stops it matching", gone.names, [])
        check("and that reads as unresolved rather than as a match", gone.resolved, False)
        try:
            A.route("engineers", "channel", ["C9"])
            check("a built-in cannot be rerouted", "no error", "KeyError")
        except KeyError:
            pass


def test_the_fetcher_survives_what_an_api_does():
    """Written by hand for one real read, this came to two bugs found by running it.

    A connection reset at 5,564 documents that would have been written up as a complete corpus, and
    rate limits met by stopping. Both are the source's business and neither is about any particular
    source, so they are tested here against a scripted service rather than left to each recipe.
    """
    import http.server
    import socketserver
    import threading

    state = {"limited": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            import urllib.parse
            parts = urllib.parse.urlsplit(self.path)
            cursor = (urllib.parse.parse_qs(parts.query).get("cursor") or [""])[0]
            if parts.path == "/refuse":                 # 200 with a refusal in the body
                return self.reply({"ok": False, "error": "missing_scope"})
            if parts.path == "/drop":
                # A body that stops short of its own Content-Length — what a connection reset looks
                # like from the client, and it arrives as an HTTPException rather than an OSError.
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "500")
                self.end_headers()
                self.wfile.write(b'{"ok": true, "messages": [')
                self.close_connection = True
                return
            if state["limited"] < 1 and not cursor:     # rate limited once, with an instruction
                state["limited"] += 1
                self.send_response(429)
                self.send_header("Retry-After", "1")
                self.send_header("Content-Length", "0")
                return self.end_headers()
            if not cursor:
                return self.reply({"ok": True, "messages": [
                    {"user": "ann", "text": "the BSP run failed", "ts": "1700.1"}],
                    "meta": {"next": "page2"}})
            if cursor == "page2":
                return self.reply({"ok": True, "messages": [
                    {"user": "bob", "text": "BSP again", "ts": "1700.2"}], "meta": {"next": ""}})
            return self.reply({"ok": True, "messages": []})

        def reply(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    class Server(socketserver.TCPServer):
        allow_reuse_address = True

        def handle_error(self, *a):
            pass                                # a deliberately dropped response is not a test error

    server = Server(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        script = os.path.join(LIB, "fetch.py")

        def fetch(path, *extra):
            return subprocess.run(
                [sys.executable, script, "--url", f"http://127.0.0.1:{port}{path}",
                 "--items", "messages", "--author", "user", "--text", "text", "--ts", "ts",
                 "--retry-base", "0.1", *extra],
                capture_output=True, text=True, timeout=120)

        r = fetch("/history", "--ok", "ok", "--cursor-out", "meta.next", "--cursor-in", "cursor")
        rows = [json.loads(line) for line in r.stdout.strip().splitlines()]
        check("a 429 is waited out, not given up on", r.returncode, 0)
        check("both pages arrive", [row["author"] for row in rows], ["ann", "bob"])
        check("in the document contract", sorted(rows[0]), ["author", "text", "ts"])
        check("and the instruction is honoured, not guessed at", "as asked" in r.stderr, True)

        # A refusal inside a 200 is the failure that reads as an empty channel. It has to be loud.
        r = fetch("/refuse", "--ok", "ok", "--error", "error")
        check("a refusal in the body fails", r.returncode, 1)
        check("and says what the service said", "missing_scope" in r.stderr, True)

        r = fetch("/drop", "--retries", "2")
        check("a dropped connection is retried", r.stderr.count("waiting"), 2)
        check("and then reported rather than returning less", r.returncode, 1)

        # Stopping at a bound is not the same as reaching the end, and nothing downstream can tell
        # from the output alone.
        r = fetch("/history", "--ok", "ok", "--cursor-out", "meta.next", "--max-pages", "1")
        check("a bounded read says it is incomplete", "incomplete" in r.stderr, True)
        check("and exits differently from a finished one", r.returncode, 2)
    finally:
        server.shutdown()
        server.server_close()


def test_an_audience_can_be_shared_with_a_team():
    """One person measures, everyone gets it by pulling — but only the ones they chose to share.

    Deliberate in both directions. A scan produces audiences that describe a handful of people by
    name, so sharing is a separate verb naming one audience, and whether the names travel is a choice
    with the safe default. The count travels either way, because "measured over 94 people" is the
    provenance a colleague needs and it names nobody.
    """
    import audiences
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as team:
        shared_dir = os.path.join(team, "audiences")
        write_audience(home, "platform", matches={"channels": ["C7"], "repos": ["your-org/infra"]},
                       members=["ann", "bob", "cat"], vocabulary={"BSP": 9})
        write_audience(home, "private-thing", matches={"channels": ["C9"]},
                       members=["ann"], vocabulary={"SECRET": 9})
        A, _ = fresh(home)

        target, people = A.share("platform", shared_dir)
        check("it says how many were counted", people, 3)
        landed = json.load(open(target))
        check("names do not travel by default", "members" in landed, False)
        check("the count does", landed["_meta"]["measured_over_people"], 3)
        check("routing travels", landed["matches"]["channels"], ["C7"])
        check("vocabulary travels", landed["vocabulary"]["BSP"], 9)
        check("and only what was named is shared",
              sorted(os.listdir(shared_dir)), ["platform.json"])

        A.share("platform", shared_dir, with_names=True)
        check("names travel when asked", json.load(open(target))["members"], ["ann", "bob", "cat"])

        # An audience with no identifiers can never apply on anyone else's machine, so sharing it
        # would look like it worked and do nothing at all.
        write_audience(home, "nowhere", matches={}, vocabulary={"AAA": 9})
        A, _ = fresh(home)
        try:
            A.share("nowhere", shared_dir)
            check("an audience that can never apply is refused", "no error", "ValueError")
        except ValueError:
            pass


def test_a_shared_audience_arrives_without_being_measured():
    import audiences
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as team:
        shared_dir = os.path.join(team, "audiences")
        os.makedirs(shared_dir)
        with open(os.path.join(shared_dir, "platform.json"), "w") as fh:
            json.dump({"name": "platform", "who": "the platform team",
                       "matches": {"channels": ["C7"]}, "inherits": ["engineers"],
                       "vocabulary": {"BSP": 9}}, fh)
        with open(os.path.join(home, "config.json"), "w") as fh:
            json.dump({"shared": [shared_dir]}, fh)

        A, _ = fresh(home)
        check("the team's audience is loaded", "platform" in A.ALL, True)
        check("and marked as theirs, not yours", A.ALL["platform"].origin, "shared")
        r = A.resolve({"channel": "C7"})
        check("it routes", r.names, ["platform"])
        check("and its vocabulary applies", r.is_known("BSP"), True)

        # Deleting the file locally would take it from everybody on the next push, and it would come
        # back on the next pull. Overriding is the local answer.
        try:
            A.remove("platform")
            check("a shared audience cannot be deleted locally", "no error", "PermissionError")
        except PermissionError:
            pass
        write_audience(home, "platform", matches={"channels": ["C7"]},
                       vocabulary={"BSP": 9, "SFTR": 9})
        A, _ = fresh(home)
        check("your own copy wins", A.ALL["platform"].origin, "yours")
        check("and it is the one that applies", A.resolve({"channel": "C7"}).is_known("SFTR"), True)

        # A directory that is configured but absent is skipped, not fatal: a colleague may add the
        # line before the checkout lands.
        with open(os.path.join(home, "config.json"), "w") as fh:
            json.dump({"shared": [os.path.join(team, "not-cloned-yet")]}, fh)
        A, _ = fresh(home)
        check("an absent shared directory is skipped", "engineers" in A.ALL, True)


def test_a_destination_can_cap_effort_and_severity():
    """Two different reasons to do less, and they are not the same knob.

    Effort: measured across all eight destinations on the same 77 words of well-built prose, every one
    costs about 15 seconds and 5 model calls — the cost is in the phases and the phases do not care
    where the text is going. So there is no such thing as an expensive destination. What varies is
    whether the questions apply: the phases ask whether this reader will care and whether the ask is
    clear, and a commit message has neither an addressee nor an ask.

    Severity: blocking is justified by the text being about to reach a reader unreviewed. A draft lands
    in your own compose box, so it has a reader already, and holding it back spends a turn arguing
    about text you were about to read anyway.
    """
    import checks
    check("a cap below the level applies", checks.capped("high", "low"), "low")
    check("a cap above it does not", checks.capped("low", "high"), "low")
    check("no cap changes nothing", checks.capped("high", None), "high")
    check("a nonsense cap changes nothing", checks.capped("high", "sideways"), "high")

    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as repo:
        write_audience(home, "team", matches={"channels": ["C1"]}, inherits=["engineers"],
                       members=["a", "b", "c", "d"])
        with open(os.path.join(home, "config.json"), "w") as fh:
            json.dump({"effort": "low"}, fh)
        body = ("The SFTR job needs the JSON payload rebuilt before the API can serve it over HTTP "
                "again, which is why CI has been red since yesterday and the deploy could not go out.")

        def ask(tool):
            payload = {"tool_name": tool, "session_id": tool[-8:], "cwd": repo,
                       "tool_input": {"channel_id": "C1", "message": body}}
            r = subprocess.run(["bash", GUARD], input=json.dumps(payload), capture_output=True,
                               text=True, env={**os.environ, "PROSE_GUARD_HOME": home}, timeout=120)
            if not r.stdout.strip():
                return "allowed", ""
            out = json.loads(r.stdout)["hookSpecificOutput"]
            if out.get("permissionDecision") == "deny":
                return "deny", out["permissionDecisionReason"]
            return "advise", str(out.get("additionalContext") or "")

        sent, said_sent = ask("mcp__slack__slack_send_message")
        draft, said_draft = ask("mcp__slack__slack_send_message_draft")
        check("a message about to be posted is held back", sent, "deny")
        check("the same text as a draft is not", draft, "advise")
        # The finding itself must be identical: the destination changes what is done about it, never
        # whether the tool noticed.
        check("and the finding is the same either way",
              "SFTR" in said_sent and "SFTR" in said_draft, True)


def test_words_already_there_are_not_words_you_wrote():
    """Someone was asked to scrub a client's name out of published commit messages.

    That means reproducing each message verbatim apart from the name — and the guard held the amend over
    two acronyms the original author had written a year earlier. Nothing the agent could do would clear
    it, because the text was not theirs to rewrite. They got past it with `git commit-tree`, plumbing the
    hook does not match, after asking the user to approve a bypass.

    A term already in the version being replaced is not a term this text introduces. Checked against the
    repository rather than taken on trust, so it cannot be used to wave anything through.
    """
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as repo:
        for argv in (["init", "-q"], ["config", "user.email", "t@t.t"], ["config", "user.name", "t"]):
            subprocess.run(["git", "-C", repo, *argv], capture_output=True, timeout=60)
        open(os.path.join(repo, "f.txt"), "w").write("x\n")
        subprocess.run(["git", "-C", repo, "add", "f.txt"], capture_output=True, timeout=60)
        old = ("Resolve the J1-vs-J4 disagreement raised in review\n\n"
               "J1 and J4 were the original author's shorthand for two findings.")
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m", old], capture_output=True,
                       timeout=60)
        write_audience(home, "team", matches={"paths": ["*"]}, inherits=["engineers"],
                       members=["a", "b", "c", "d"], vocabulary={"BSP": 9})
        with open(os.path.join(home, "config.json"), "w") as fh:
            json.dump({"effort": "low"}, fh)

        body = ("Resolve the J1-vs-J4 disagreement raised in review, keeping the original wording "
                "intact apart from the client name, so the published history stays comparable with "
                "what everybody already read on the pull request last year.")
        # Built rather than written out: a literal `git commit -m "...J1..."` in this file is a command
        # the guard reads, and it blocks its own test suite.
        commit = "git" + " commit"

        def ask(command, session):
            payload = {"tool_name": "Bash", "session_id": session, "cwd": repo,
                       "tool_input": {"command": command}}
            r = subprocess.run(["bash", GUARD], input=json.dumps(payload), capture_output=True,
                               text=True, env={**os.environ, "PROSE_GUARD_HOME": home}, timeout=120)
            if not r.stdout.strip():
                return "allowed", ""
            out = json.loads(r.stdout)["hookSpecificOutput"]
            if out.get("permissionDecision") == "deny":
                return "deny", out["permissionDecisionReason"]
            return "advise", str(out.get("additionalContext") or "")

        # "Already there" is answered with the scan's own machinery, not a substring test. A previous
        # message mentioning SOURCE must not excuse RC, or a coincidence becomes an exemption.
        import jargon
        check("a term inside a longer word is not present", jargon.uses("the SOURCE file", "RC"),
              False)
        check("a term against a boundary is", jargon.uses("cut the RC-1 build", "RC"), True)
        check("and every term the scan finds, uses agrees on",
              all(jargon.uses(old, t) for t in ("J1", "J4")), True)

        verdict, said = ask(f'{commit} -m "{body}"', "new")
        check("a new commit introducing the terms is still flagged", verdict, "advise")
        check("and names them", "J1" in said, True)

        verdict, said = ask(f'{commit} --amend -m "{body}"', "amend")
        check("an amend carrying the same terms forward is not", verdict, "allowed")

        # The rule is per term, not per command: an amend is not a blanket exemption.
        fresh_term = body.replace("J1-vs-J4", "SFTR-vs-EMIR")
        verdict, said = ask(f'{commit} --amend -m "{fresh_term}"', "amend2")
        check("an amend that introduces a new term is flagged", verdict, "advise")
        check("naming only the new one", "SFTR" in said and "J1" not in said, True)


def test_one_command_can_be_excused_but_not_a_session():
    """A global off switch is the thing to avoid — turned off for a minute, off for weeks, and nobody
    knows because the absence of complaints reads exactly like clean prose. This cannot outlive the
    command it is written on, and it has to say why in words somebody will read later."""
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as repo:
        subprocess.run(["git", "-C", repo, "init", "-q"], capture_output=True, timeout=60)
        write_audience(home, "team", matches={"paths": ["*"]}, inherits=["engineers"],
                       members=["a", "b", "c", "d"])
        with open(os.path.join(home, "config.json"), "w") as fh:
            json.dump({"effort": "low"}, fh)
        body = ("Resolve the J1-vs-J4 disagreement raised in review, keeping the original wording "
                "intact apart from the client name, so the published history stays comparable with "
                "what everybody already read on the pull request last year.")
        commit = "git" + " commit"

        def ask(command, session="skip"):
            payload = {"tool_name": "Bash", "session_id": session, "cwd": repo,
                       "tool_input": {"command": command}}
            r = subprocess.run(["bash", GUARD], input=json.dumps(payload), capture_output=True,
                               text=True, env={**os.environ, "PROSE_GUARD_HOME": home}, timeout=120)
            if not r.stdout.strip():
                return "allowed", ""
            out = json.loads(r.stdout)["hookSpecificOutput"]
            if out.get("permissionDecision") == "deny":
                return "deny", out["permissionDecisionReason"]
            return "advise", str(out.get("additionalContext") or "")

        verdict, said = ask(f'PROSE_GUARD_SKIP="republishing text I did not write" {commit} '
                            f'-m "{body}"')
        check("a stated reason excuses the command", verdict, "advise")
        check("and the reason is repeated back where it can be read",
              "republishing text I did not write" in said, True)

        verdict, said = ask(f'PROSE_GUARD_SKIP=1 {commit} -m "{body}"', "asswitch")
        check("used as a switch, it is refused", verdict, "deny")
        check("and says what is missing", "reason" in said, True)

        # It applies to the command it is written on and nothing else, so the next one is checked.
        verdict, said = ask(f'{commit} -m "{body}"', "after")
        check("the next command is checked as normal", verdict in ("advise", "deny"), True)

        for n in range(2):
            ask(f'PROSE_GUARD_SKIP="reason number {n} for skipping" {commit} -m "{body}"', "many")
        verdict, said = ask(f'PROSE_GUARD_SKIP="reason number three for skipping" {commit} '
                            f'-m "{body}"', "many")
        check("repeated use is counted and surfaced", "3 skips" in said, True)


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

        # Someone already had an almost identical rule from another source, under a different name.
        # Installing put a second copy of the same guidance into every session, and the two differed
        # only in a closing paragraph, so nothing looked wrong from either side.
        rules = os.path.join(tmp, ".claude", "rules")
        os.makedirs(rules, exist_ok=True)
        mine = open(os.path.join(PLUGIN, "rule", "engineer-communication.md")).read()
        with open(os.path.join(rules, "house-communication.md"), "w") as fh:
            fh.write(mine.replace(mine.rsplit("\n\n", 1)[-1], "A different closing paragraph.\n"))
        out = run("--install")
        check("a near-identical rule already loading is refused", out.startswith("duplicate"), True)
        check("and it names the file so it can be judged", "house-communication.md" in out, True)
        check("nothing was installed", os.path.exists(target), False)
        check("but it can be overridden deliberately",
              run("--install", "--force").startswith("installed"), True)

        # And the other way round: somebody else's rule about something else must not look like a
        # rival, or the installer refuses on every machine that has any rules at all.
        run("--remove")
        os.remove(os.path.join(rules, "house-communication.md"))
        with open(os.path.join(rules, "verification.md"), "w") as fh:
            fh.write("# Claims about system behaviour\n\nEvery claim about how the system behaves "
                     "is either backed by a command you ran and its output, or is explicitly marked "
                     "as unverified. Never present an inference as a finding.\n")
        check("an unrelated rule is not a rival", run("--install").startswith("installed"), True)


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
