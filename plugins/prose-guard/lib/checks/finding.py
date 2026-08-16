"""What a check returns, and how it runs. A leaf module: it imports nothing, not even its own package.

Every check used to import `Finding` from the package `checks` from inside its `run()`, because the
package imports the checks at module level and hoisting the import to the top of a check raised
`ImportError: cannot import name 'ADVISE' from 'checks'`. That is load-order avoidance rather than
style, and it was copied into every check that was added. The type and the severities live here so a
check and the package can both import them at the top of the file, where an import belongs.
"""
import collections

Finding = collections.namedtuple("Finding", "severity message")

# Severity belongs to the finding rather than to the check, because the same check is sometimes exact
# enough to hold a message back and sometimes only guessing — the term check knows the difference and
# nothing else can.
#
#     block   the complaint is specific, small and evidenced. Hold the message.
#     advise  hand it over and let the message go.
BLOCK = "block"
ADVISE = "advise"

# How a check runs, and therefore what one run of it costs. One attribute rather than the two booleans
# this used to be: COSTS_A_CALL and POOLS describe four states and only three exist, so
# `COSTS_A_CALL=False, POOLS=True` meant nothing — and POOLS was read as `getattr(check, "POOLS",
# True)`, so a new combined-verdict check that forgot to declare it silently paid up to
# `ceiling_for(text)` calls instead of one. A check now names its mode and cannot leave it implied.
EXACT = "exact"          # no model call. One run is the whole answer, so it is never asked twice.
VERDICT = "verdict"      # one model call, one combined verdict. Asking again restates it.
POOLED = "pooled"        # one model call a run, until the runs stop surfacing anything new.
MODES = (EXACT, VERDICT, POOLED)
