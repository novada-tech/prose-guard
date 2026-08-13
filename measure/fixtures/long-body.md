Read the body behind `$(...)` instead of asking for a file

A command whose text comes from a substitution is checked now, with nothing to rewrite:

    --body "$(cat notes.md)"            the file is read; no command runs
    --body "$(git log -1 --format=%B)"  run, and the output is checked
    --body "${SUMMARY}"                 refused, so nothing is sent
    --body "$(anything-else)"           refused, so nothing is sent

All four used to pass unchecked. The previous commit blocked all four and asked for `--body-file`
instead. That worked. It also meant rewriting commands that were already correct.

The last two are refused for different reasons. A hook is a separate process, so shell variables
are not visible to it and `${SUMMARY}` cannot be resolved by anything. An arbitrary command could
be resolved by running it, and running it is the objection — `$(curl -X POST ...)` would then
execute once during the check and again when the shell runs the command.

A flag that can write is refused even on a whitelisted subcommand: `git log --output=FILE` writes
a file. Only git subcommands that report are on the list at all, because read-only is not a
property of a command name.

Chaining a second command onto one of the substitutions above is prevented separately. The command
runs as a list of arguments with no shell, so `;` and `&&` reach git as arguments and git rejects
them.

Every command-line destination gets this. Extraction and the complaint both read the destination's
own list of text-carrying flags, rather than a list hard-coded in one place. `git commit -m
"$(...)"` and `glab mr note --message "$(...)"` behave the same, and so will one added later.

Look hardest at `--body "$(git log -1 --format=%s)"`. It resolves fine, and gives back a subject
shorter than the 25 words the check needs. There is no text to judge, and the reason is length
rather than the substitution. Saying "substitution" there would send someone to fix a command that
works, so it stays silent.

If you refactor the resolver, keep the metacharacter check even though no test fails when you
remove it. Running the command as a list of arguments is what prevents chaining today; the check
is there for whoever later runs this through a shell.
