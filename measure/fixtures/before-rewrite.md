Work out the substitution instead of asking for a file

Denying an unreadable body and asking for `--body-file` closed the coverage hole and made somebody
restructure a command that was already correct. Two of those cases need no execution at all, and one is
safely whitelistable, so the text is had and the check happens with nothing to change:

    --body "$(cat notes.md)"            the file is read, no command runs
    --body "$(git log -1 --format=%B)"  run, and the output is checked
    --body "${SUMMARY}"                 held back: a hook never sees your shell variables
    --body "$(anything-else)"           held back: running it to find out would fire it twice

The whitelist is narrow because "read-only" is not a property of a command name. `git log --output=FILE`
writes a file, which a test now asserts, so a flag that can write is refused. Chaining is prevented by
something stronger than a check: the command runs as a list of arguments with no shell, so `;` and `&&`
reach git as arguments and git rejects them.

It generalises without naming anything. Both halves read the destination's own `text_arg`, so
`git commit -m "$(...)"` and `glab mr note --message "$(...)"` behave the same, and a destination added
later does too — asserted for both.

The test that mattered was neither of those. A substitution that resolves to something too short to judge
leaves no text either, and calling that a substitution problem would send someone to fix a command that
works. It is silent, and removing the guard for it is caught.

One mutation survives and is left alone with the reason written down: dropping the metacharacter check
changes no behaviour today, because the list-form exec is what prevents chaining. It stays as redundancy
for anything that later runs this through a shell.

