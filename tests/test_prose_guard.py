#!/usr/bin/env python3
"""Tests for prose-guard. No dependencies beyond the standard library.

    python3 tests/test_prose_guard.py

Each case pins something a plausible-looking implementation gets wrong. A guard that quietly
stopped checking chat, or started checking source files, or blocked on a vocabulary it had never
measured, would otherwise look exactly like a working one.

Mutation-checked rather than trusted on a green run: see the mutations listed in the README.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(HERE, "..", "plugins", "prose-guard")
LIB = os.path.join(PLUGIN, "lib")
GUARD = os.path.join(PLUGIN, "hooks", "scripts", "guard-outgoing-prose.sh")
sys.path.insert(0, LIB)

# 25 words is the floor, so test text has to clear it to be inspected at all
PAD = (" Anyone still relying on the previous credentials will need to re-run the setup command "
       "before their next deploy actually goes through cleanly today.")
FAILS = []


def check(label, got, want):
    if got != want:
        FAILS.append(f"FAIL {label}: got {got!r}, wanted {want!r}")


def env(home, state, effort="medium"):
    e = {k: v for k, v in os.environ.items() if not k.startswith("PROSE_GUARD")}
    e.pop("CLAUDE_PLUGIN_DATA", None)
    e.pop("CLAUDE_PLUGIN_OPTION_EFFORT", None)
    e.update(PROSE_GUARD_HOME=home, PROSE_GUARD_STATE=state, PROSE_GUARD_EFFORT=effort)
    return e


def run_guard(payload, home, state, effort="medium"):
    r = subprocess.run(["bash", GUARD], input=json.dumps(payload), capture_output=True,
                       text=True, env=env(home, state, effort), timeout=300)
    out = r.stdout.strip()
    if not out:
        return "allow", ""
    h = json.loads(out)["hookSpecificOutput"]
    if h.get("permissionDecision") == "deny":
        return "deny", h["permissionDecisionReason"]
    return "advise", h.get("additionalContext", "")


def measured(home, terms):
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "vocabulary.json"), "w") as fh:
        json.dump({"terms": terms}, fh)


def test_detection():
    """The Schwartz-Hearst expansion detection, which is the deterministic half of the tool."""
    import jargon
    cases = [
        ("expanded in parentheses", "We use Application Default Credentials (ADC) here.", []),
        ("expanded in prose", "Terraform prefers Application Default Credentials. ADC is "
                              "separate.", []),
        ("never expanded", "ADC is a separate grant.", ["ADC"]),
        ("only inside code", "Run `gcloud auth ADC` now.", []),
        # a quoted line is someone else's words. Dropping blockquotes removed zero detections
        # across 301 real messages, whereas skipping any term inside backticks anywhere would
        # have silenced a third of the true positives.
        ("only inside a blockquote", "Someone wrote:\n\n> we should move onto ADC soon\n\nFine.",
         []),
        ("in my own prose", "We should move onto ADC soon.", ["ADC"]),
        # word boundaries mean GOOGLE_OAUTH never matches
        ("screaming snake case", "The script exported GOOGLE_OAUTH_ACCESS_TOKEN on start.", []),
        # a one-letter word must not stand in for an initial: "a docker container" used to make
        # ADC count as explained, passing a message that never explained it
        ("short words are not an expansion", "We ran a docker container, then ADC failed.",
         ["ADC"]),
        ("a real three-word expansion counts", "Terraform reads application default credentials. "
                                               "ADC is separate.", []),
    ]
    for label, text, want in cases:
        check(f"detect/{label}", jargon.unexplained(text + PAD)[0], want)


def test_vocabulary():
    """Shipped general terms pass; anything else is unknown until it has been measured."""
    import vocabulary
    for term, needs in (("CLI", False), ("API", False), ("JSON", False), ("HTTP", False),
                        # capitalised English words and code constants are not acronyms. A
                        # hand-kept exclusion list would grow forever, so the system word list
                        # catches these.
                        ("LOGGER", False), ("NULL", False), ("ERROR", False), ("ASCII", False),
                        # nothing org-specific ships, so these are unknown out of the box
                        ("ADC", True), ("GKE", True), ("CDM", True)):
        check(f"vocab/{term}", vocabulary.needs_explaining(term), needs)
    check("nothing measured ships with the tool", vocabulary.HAVE_MEASURED, False)


def test_confidence_gates_enforcement():
    """Without a measured vocabulary the tool is guessing, so it must advise and not block.

    This is the property that makes zero-setup usable. Blocking on a guess means the first day is
    spent arguing with it about house vocabulary.
    """
    text = "We moved the kubectl configuration onto GKE this week." + PAD
    payload = {"tool_name": "mcp__slack__slack_send_message", "session_id": "s1",
               "tool_input": {"channel_id": "C1", "message": text}}
    with tempfile.TemporaryDirectory() as tmp:
        home, state = os.path.join(tmp, "home"), os.path.join(tmp, "state")
        verdict, why = run_guard(payload, home, state, "low")
        check("unmeasured audience advises", verdict, "advise")
        check("and says it is guessing", "guess" in why, True)

        # measured, and GKE sits below the author cut: now it is evidence, so it blocks
        measured(home, {"KUBECTL": 6, "GKE": 3})
        verdict, _ = run_guard(payload, home, os.path.join(tmp, "s2"), "low")
        check("measured audience denies", verdict, "deny")

        # at or above the cut, there is nothing to say
        measured(home, {"KUBECTL": 6, "GKE": 4})
        verdict, _ = run_guard(payload, home, os.path.join(tmp, "s3"), "low")
        check("a term the audience shares is not flagged", verdict, "allow")

        # accepting a term by hand works without a rerun, and applies immediately
        measured(home, {"KUBECTL": 6, "GKE": 3})
        with open(os.path.join(home, "known-terms.txt"), "w") as fh:
            fh.write("# mine\nGKE\n")
        verdict, _ = run_guard(payload, home, os.path.join(tmp, "s4"), "low")
        check("known-terms.txt is honoured", verdict, "allow")


def test_routing():
    """What counts as outgoing prose is data, and the data has to be right."""
    text = "We moved the kubectl configuration onto GKE this week." + PAD
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        measured(home, {"KUBECTL": 6})            # so terms can deny and routing is observable
        bodyfile = os.path.join(tmp, "body.md")
        with open(bodyfile, "w") as fh:
            fh.write(text)
        cases = [
            ("slack", {"tool_name": "mcp__slack__slack_send_message",
                       "tool_input": {"channel_id": "C1", "message": text}}, "deny"),
            ("github comment", {"tool_name": "mcp__github__add_issue_comment",
                                "tool_input": {"body": text}}, "deny"),
            ("notion page", {"tool_name": "mcp__notion__notion-update-page",
                             "tool_input": {"content": text}}, "deny"),
            ("markdown file", {"tool_name": "Write",
                               "tool_input": {"file_path": "/tmp/design.md",
                                              "content": text}}, "deny"),
            # --body-file is how a long body is really passed. It used to be invisible.
            ("gh pr create --body-file", {"tool_name": "Bash",
                                          "tool_input": {"command": f"gh pr create --title x "
                                                                    f"--body-file {bodyfile}"}},
             "deny"),
            # code is out of scope: this guards writing, not programming
            ("java file", {"tool_name": "Write",
                           "tool_input": {"file_path": "/tmp/Foo.java", "content": text}},
             "allow"),
            ("read-only tool", {"tool_name": "Read",
                                "tool_input": {"file_path": "/tmp/x.md"}}, "allow"),
            ("unrelated bash", {"tool_name": "Bash",
                                "tool_input": {"command": "git status"}}, "allow"),
            # too short to be the failure this catches
            ("short message", {"tool_name": "mcp__slack__slack_send_message",
                               "tool_input": {"channel_id": "C1", "message": "done, thanks"}},
             "allow"),
        ]
        for label, payload, want in cases:
            payload["session_id"] = "r-" + label.replace(" ", "_")
            verdict, _ = run_guard(payload, home, os.path.join(tmp, label.replace(" ", "_")),
                                   "low")
            check(f"routing/{label}", verdict, want)


def test_user_destinations_win():
    """A user file is read before the shipped defaults, so it can override as well as extend."""
    import importlib
    text = "We moved the kubectl configuration onto GKE this week." + PAD
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        measured(home, {"KUBECTL": 6})
        with open(os.path.join(home, "destinations.json"), "w") as fh:
            json.dump({"destinations": [
                {"name": "my own tool", "tool": ["send_briefing"], "text_fields": ["note"],
                 "audience": {"audience": "the operations rota"}},
                # override: stop checking markdown files
                {"name": "markdown off", "file": r"\.md$", "text_fields": []},
            ]}, fh)
        verdict, _ = run_guard({"tool_name": "example__send_briefing", "session_id": "u1",
                                "tool_input": {"note": text}}, home, os.path.join(tmp, "u1"),
                               "low")
        check("a destination the user added is checked", verdict, "deny")
        verdict, _ = run_guard({"tool_name": "Write", "session_id": "u2",
                                "tool_input": {"file_path": "/tmp/x.md", "content": text}},
                               home, os.path.join(tmp, "u2"), "low")
        check("a destination the user overrode is skipped", verdict, "allow")

        os.environ["PROSE_GUARD_HOME"] = home
        import destinations
        importlib.reload(destinations)
        env_ = destinations.envelope(
            {"tool": ["send_briefing"], "audience": {"audience": "the operations rota"}},
            "example__send_briefing", {"note": text})
        check("a declared audience reaches the envelope", env_.get("audience"),
              "the operations rota")
        del os.environ["PROSE_GUARD_HOME"]
        importlib.reload(destinations)


def test_envelope_is_derived():
    """The audience comes from the call, and says so when it cannot."""
    import destinations
    slack = next(d for d in destinations.DESTINATIONS if "slack_send_message" in (d.get("tool") or []))
    dm = destinations.envelope(slack, "slack_send_message", {"channel_id": "D42"})
    ch = destinations.envelope(slack, "slack_send_message", {"channel_id": "C42"})
    check("a direct message is one colleague", "direct message" in dm["audience"], True)
    check("a channel arrives cold", "cold" in ch.get("shared_context", ""), True)
    thread = destinations.envelope(slack, "slack_send_message",
                                   {"channel_id": "C42", "thread_ts": "1.0"})
    check("a thread reply is marked as continuing", "thread" in thread.get("situation", ""), True)
    gh = next(d for d in destinations.DESTINATIONS if "add_issue_comment" in (d.get("tool") or []))
    priv = destinations.envelope(gh, "mcp__github__add_issue_comment", {"owner": "someone"})
    check("an owner not declared public is treated as private",
          "private" in priv.get("reach", ""), True)
    unknown = destinations.envelope({}, "whatever", {})
    check("an unconfigured destination admits it", "unknown" in unknown["audience"], True)


def test_session_ledger_bounds_the_argument():
    """Ten different drafts, each still carrying an unexplained term, must not block forever."""
    with tempfile.TemporaryDirectory() as tmp:
        home, state = os.path.join(tmp, "home"), os.path.join(tmp, "state")
        measured(home, {"KUBECTL": 6})
        seq = []
        for n in range(10):
            payload = {"tool_name": "mcp__github__add_issue_comment", "session_id": "ledger",
                       "tool_input": {"body": f"Draft {n} still talks about GKE clusters." + PAD}}
            seq.append(run_guard(payload, home, state, "low")[0] == "deny")
        check("a session is blocked at most MAX_DENIALS times", sum(seq), 6)
        check("and stops blocking once the ledger is spent", any(seq[-2:]), False)
        fresh = run_guard({"tool_name": "mcp__github__add_issue_comment", "session_id": "other",
                           "tool_input": {"body": "Another note about GKE." + PAD}},
                          home, state, "low")[0]
        check("a new session gets its own ledger", fresh, "deny")


def test_levels():
    """Which checks each level runs, and that low never reaches a model."""
    import importlib
    import checks
    for level, names in (("disabled", []),
                         ("low", ["terms"]),
                         ("medium", ["terms", "judgement"]),
                         ("high", ["terms", "relevance", "structure", "sentence", "reference"])):
        got = [c.NAME for c in checks.for_effort(level)]
        check(f"level/{level}", got, names)
    check("low spends no model call",
          [c.COSTS_A_CALL for c in checks.for_effort("low")], [False])
    from checks import config
    for bad in ("", "nonsense", "LOW "):
        os.environ["PROSE_GUARD_EFFORT"] = bad
        importlib.reload(config)
        check(f"an unrecognised level falls back to disabled ({bad!r})", config.effort(),
              "disabled")
    del os.environ["PROSE_GUARD_EFFORT"]
    importlib.reload(config)


def test_state_stays_out_of_the_plugin():
    """An earlier version fell back to the plugin directory and put state under version control."""
    text = "We moved the kubectl configuration onto GKE this week." + PAD
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        measured(home, {"KUBECTL": 6})
        e = env(home, os.path.join(tmp, "state"), "low")
        subprocess.run(["bash", GUARD], input=json.dumps(
            {"tool_name": "mcp__github__add_issue_comment", "session_id": "st",
             "tool_input": {"body": text}}), capture_output=True, text=True, env=e, timeout=300)
        check("state written where it was told",
              os.path.isfile(os.path.join(tmp, "state", "sessions", "st.json")), True)

        # and with nowhere told, the fallback must still land outside the plugin. Pointing HOME at
        # a temporary directory makes ~/.cache land there, so this asserts the fallback itself
        # rather than only asserting that an explicit path is honoured.
        e2 = {k: v for k, v in e.items() if k != "PROSE_GUARD_STATE"}
        e2["HOME"] = os.path.join(tmp, "fakehome")
        e2["PROSE_GUARD_HOME"] = home
        subprocess.run(["bash", GUARD], input=json.dumps(
            {"tool_name": "mcp__github__add_issue_comment", "session_id": "fb",
             "tool_input": {"body": text}}), capture_output=True, text=True, env=e2, timeout=300)
        check("the fallback lands under the user's cache",
              os.path.isfile(os.path.join(tmp, "fakehome", ".cache", "prose-guard",
                                          "sessions", "fb.json")), True)
        for junk in ("sessions", "outgoing-guard-state"):
            check(f"no {junk} inside the plugin",
                  os.path.isdir(os.path.join(PLUGIN, junk)), False)


def main():
    for fn in (test_detection, test_vocabulary, test_confidence_gates_enforcement,
               test_routing, test_user_destinations_win, test_envelope_is_derived,
               test_session_ledger_bounds_the_argument, test_levels,
               test_state_stays_out_of_the_plugin):
        fn()
    for line in FAILS:
        print(line)
    if FAILS:
        print(f"\n{len(FAILS)} failure(s)")
        return 1
    print("prose-guard: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
