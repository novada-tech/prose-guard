#!/bin/bash
# Say at the start of a session that this install is checking nothing, while that is still true.
# See session_start.py for why it is said here and why it repeats.
#
# Fails quiet, like the other hook: no python3, no message. A machine without python3 cannot run any
# of this, and an error notice every session would be a second thing to fix rather than a clue about
# the first.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || true)"
[ -z "$PY" ] && exit 0
exec "$PY" "$DIR/session_start.py"
