"""Checks that did not run, said once rather than never. A leaf module: it imports nothing.

Every failure path here allows the call, which is right — a broken writing check must never block
outbound work — and it is also indistinguishable from prose with nothing wrong with it. A missing
prompt file, no `claude` on PATH and an unreadable phases directory all read as "clean". The last of
those turns `high` into `low` and charges nothing, which is the worst shape a failure can take in a
tool somebody is trusting to check their writing.

`checks/config.misspelt()` exists for exactly this on the other setting: a level set to `medim` meant
disabled with nothing said. This is the same failure, so it gets the same treatment — recorded rather
than raised, and read by whoever can reach the person. The hook has a channel that tells them once a
session; check_prose.py prints.
"""
_NOTED = []


def note(what):
    """Record something that did not run. Deduplicated: five phases with no prompt directory is one
    thing to say, not five."""
    if what and what not in _NOTED:
        _NOTED.append(what)


def noted():
    """Everything recorded since this process started, in the order it happened."""
    return list(_NOTED)


def forget():
    """Start again. For a test, and for a caller that reports between two runs."""
    _NOTED.clear()
