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
CFG_HOME="${PROSE_GUARD_HOME:-${CLAUDE_PLUGIN_DATA:-${XDG_CONFIG_HOME:-$HOME/.config}/prose-guard}}"
if [ -z "${PROSE_GUARD_EFFORT:-}${CLAUDE_PLUGIN_OPTION_EFFORT:-}" ]; then
  [ -f "$CFG_HOME/config.json" ] || exit 0
  grep -Eq '"effort"[[:space:]]*:[[:space:]]*"(low|medium|high)"' "$CFG_HOME/config.json" || exit 0
fi
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || true)"
[ -z "$PY" ] && exit 0
exec "$PY" "$DIR/outgoing_guard.py"
