#!/bin/bash
# Check prose on its way out: a chat message, a review comment, a documentation page, a document.
# See lib/checks/config.py for what each effort level costs.
#
# Fails open by design. Any missing interpreter, missing dependency or unexpected input exits 0 and
# the tool call proceeds: a broken writing check must never be able to block outbound work.
set -u
# The hook has no matcher, so it is offered every tool call in every session. Deciding here rather
# than in Python keeps ~25ms of interpreter startup off anyone who has not turned it on. This is a
# cheap pre-filter only; lib/checks/config.py makes the real decision.
# Must match lib/paths.py exactly. Anything else and the guard reads a different config
# from the one the setup skill wrote, which is silent and looks like the tool not working.
CFG_HOME="${PROSE_GUARD_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/prose-guard}"
if [ -z "${PROSE_GUARD_EFFORT:-}${CLAUDE_PLUGIN_OPTION_EFFORT:-}" ]; then
  if [ ! -f "$CFG_HOME/config.json" ]; then
    # Installed, restarted, setup never run. Nothing can run, and being silent about it made working
    # correctly and doing nothing identical: somebody installs this, sends a message, sees nothing and
    # concludes it is broken — with no wrong output to report, which is why nobody would file it.
    #
    # Said here rather than in Python so the empty state still costs nobody the ~25ms this pre-filter
    # exists to save. Said ONCE, marked by a file, because a notice nobody can dismiss is its own
    # defect — the same bargain destinations.record_candidate strikes for an unclaimed tool. If the
    # marker cannot be written, say nothing: repeating it every call is worse than never saying it.
    #
    # To the person AND to the model, like every other note about what this tool should check in
    # future: the person decides, and the model needs to know enough to offer to do it.
    SAID="$CFG_HOME/setup-mentioned"
    [ -f "$SAID" ] && exit 0
    mkdir -p "$CFG_HOME" 2>/dev/null && : > "$SAID" 2>/dev/null || exit 0
    NOTE='prose-guard is installed but has never been set up, so it is checking nothing. Run /prose-guard:setup to choose a level — medium is the one the measurements support. This is the only time it will be mentioned.'
    printf '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "systemMessage": "%s", "additionalContext": "%s"}}\n' "$NOTE" "$NOTE"
    exit 0
  fi
  # A level set to something that is not a level has to reach the Python, which says so where the person
  # can see it. Exiting here on anything but a known level made a typo indistinguishable from "off".
  if ! grep -Eq '"effort"[[:space:]]*:[[:space:]]*"(low|medium|high)"' "$CFG_HOME/config.json"; then
    grep -Eq '"effort"[[:space:]]*:[[:space:]]*"[^"]+"' "$CFG_HOME/config.json" || exit 0
  fi
fi
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || true)"
[ -z "$PY" ] && exit 0
exec "$PY" "$DIR/outgoing_guard.py"
