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
  # Nothing to run, and nothing to say about that here. Saying it is the SessionStart hook's job:
  # hooks/scripts/session_start.py records why it moved, and the short version is that this test —
  # "is there a config.json" — is not the same question as "has anybody chosen a level". Registering
  # a team's shared audiences writes a config.json with no effort key, which used to silence the
  # notice permanently while the guard checked nothing.
  [ -f "$CFG_HOME/config.json" ] || exit 0
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
