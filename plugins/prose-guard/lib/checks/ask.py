"""The one model call every judgement-style check makes. Shared so the checks differ only in
their prompt file, not in how they are asked.

A minimal system prompt instead of the full coding-agent one: the same verdicts as far as we
could measure, for about a third of the output tokens and 35% less cache-read.
"""
import json
import os
import subprocess

MODEL = os.environ.get("CHECKER_MODEL", "claude-sonnet-5")
EFFORT = os.environ.get("CHECKER_EFFORT", "medium")
SYSTEM = ("You are a text checker. You read a message and answer with exactly one line, either "
          "PASS or FAIL followed by a reason. You never use tools.")


def envelope_text(env):
    if not env:
        return ""
    lines = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in (env or {}).items())
    return f"\n\nWhat you know about the situation:\n{lines}\n"


def _log_usage(name, usage, seconds):
    """Record what a check cost, when asked to. Lets anyone re-measure the real per-message
    price on their own traffic instead of trusting a number from someone else's run."""
    path = os.environ.get("CHECKER_COST_LOG")
    if not path:
        return
    try:
        with open(path, "a") as fh:
            fh.write(json.dumps({"check": name, "seconds": round(seconds, 2), **usage}) + "\n")
    except OSError:
        pass


def read_prompt(path):
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return None


def ask(name, prompt, text, envelope=None):
    """(ok, message). Any failure to reach the checker is a pass: it must not block work."""
    import time
    if not prompt:
        return True, ""
    t0 = time.time()
    try:
        r = subprocess.run(
            ["claude", "-p", f"{prompt}{envelope_text(envelope)}"
             f"\n===== MESSAGE =====\n{text}\n",
             "--model", MODEL, "--effort", EFFORT,
             "--system-prompt", SYSTEM,
             "--output-format", "json", "--setting-sources", "project"],
            capture_output=True, text=True, timeout=180)
        blob = json.loads(r.stdout)
        out = (blob.get("result") or "").strip()
    except Exception:
        return True, ""
    _log_usage(name, blob.get("usage") or {}, time.time() - t0)
    if out.upper().startswith("PASS") or "FAIL" not in out.upper():
        return True, ""
    return False, out.split(":", 1)[-1].strip()[:700]
