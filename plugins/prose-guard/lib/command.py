"""What a shell command says it will publish, worked out without running anything that can change.

Reading a command is not running one, and this module never blurs that. Three questions, in order of
how much they can cost:

    command_itself   the command minus what it merely CARRIES - a heredoc body is a document, not a command
    flag_values      every (flag, value) the command itself passes, read as words rather than searched for
    resolve          the text behind `$(...)`, where it can be had without risking a side effect

The order matters, because the first two are what make the third safe. A `--body "$(cat ~/.ssh/id_rsa)"`
written INSIDE a heredoc that a command happens to be writing to a file is not that command's flag, and
treating it as one turned "an agent wrote a runbook" into "a private key was read and sent to a model".

Reading a file needs no execution at all. Running a command does, and this cannot know whether the one
it is looking at is read-only: `$(curl -X POST ...)` would fire twice. So execution is limited to git,
and to argument lists where EVERY argument is recognised.

Recognising only the subcommand was not enough, and the way it failed is why this is now a
per-subcommand table. `tag` and `notes` were on the old list of subcommands that "report". `git tag -d`
deletes a tag, `git tag NAME` creates one, and `git notes add -f -m` overwrites a note - and all three
ran on tool calls the caller went on to DENY, so the repository changed before anybody was asked to
approve anything, and the message the person read said nothing had been checked.

No form of diff is allowed, and that is what keeps a repository's own configuration from naming a
command to run: `diff.external` reaches `git log -p --ext-diff`, and `textconv` reaches `cat-file
--textconv`. Neither is reachable if a patch is never asked for.

Chaining is prevented by something stronger than a check: a command is run as a list of arguments, with
no shell, so `;` and `&&` reach git as arguments and git rejects them. CHAINS is redundancy for anything
that later runs this through a shell - removing it changes no behaviour today, which a test cannot show.
"""
import os
import re
import shlex
import stat
import subprocess

# A flag whose value is exactly `-` means "the text arrives on stdin", and for these commands stdin is
# the heredoc sitting in the same tool call. `git commit -F -` is how a long commit message is really
# written, and `gh pr create --body-file -` is the same idea.
STDIN = "-"

# One pattern for both halves of the heredoc question, because they must agree: what `command_itself`
# strips out of the command is exactly what `heredoc_body` may read back, and a form one accepted and
# the other did not would be a body that routes as part of a command while never being read as prose.
#
# The body starts on the NEXT line, whatever else follows the redirect on this one — and what usually
# follows is the rest of a chain, `git commit -F - <<'EOF' && git push`. The terminator may be indented,
# since `<<-` strips tabs and a heredoc inside an `if` is indented whether bash requires it or not.
HEREDOC = re.compile(r"<<-?[ \t]*['\"]?(\w+)['\"]?[^\n]*\r?\n(.*?)^[ \t]*\1[ \t]*$",
                     re.S | re.M)


def heredoc_body(cmd):
    """The body of the heredoc this command feeds itself, or None.

    Only ever the command's OWN heredoc. `command_itself` strips heredocs before routing, because a
    document that quotes a publishing command is not one — and that stays true: this is read only after
    the stripped command has been found to carry a text flag whose value is stdin, which the attack
    shape (`cat > runbook.md <<EOF ... gh pr create ... EOF`) cannot produce, since the command left
    after stripping is `cat` and no destination claims it.
    """
    # The body starts on the NEXT line, whatever else follows the redirect on this one — and what
    # usually follows is the rest of a chain: `git commit -F - <<'EOF' && git push`. Demanding a newline
    # straight after the delimiter missed 22 of 151 real cases, every one of them that shape. The
    # terminator may be indented, since `<<-` strips tabs and a heredoc inside an `if` is indented
    # whether bash requires it or not.
    m = HEREDOC.search(cmd)
    return m.group(2) if m else None


# What a span this tool cannot see is replaced with before the checks read the text. A word, because
# the checks read sentences: an empty string joins the words either side into one, and a symbol makes a
# sentence ungrammatical and draws a complaint about the tool's own placeholder.
UNSEEN = "something"
_SUBSTITUTION = re.compile(r"\$\([^()]*\)|\$\{[^{}]*\}|`[^`]*`")


def visible(value):
    """The literal part of a text argument, with each span this tool cannot see standing in as a word.

    A message is rarely all substitution. Measured across 4,154 local transcripts, the text arguments
    that contain one are 87% literal at the median and never below 64% — so refusing the whole thing
    threw away most of a message to avoid guessing at a fraction of it, and held the call back for a
    defect nobody had looked for.

    Returns (text, how_many_unseen). The caller decides what to do about the count: a finding here is
    about words that will be sent verbatim, so it is worth acting on, but the tool has not read
    everything and should not imply that it has.
    """
    seen = _SUBSTITUTION.sub(UNSEEN, value)
    return seen, len(_SUBSTITUTION.findall(value))


def command_itself(cmd):
    """A command with its heredoc bodies removed, so what it DOES is read and not what it carries.

    Everything about routing keys off the command string, and a heredoc body is not part of the command:
    it is a document being written. Before this, `cat > runbook.md <<EOF ... gh pr create --body "$(cat
    ~/.ssh/id_ed25519)" ... EOF` routed as a pull request, resolved the substitution, and sent the key to
    the checker — from a command that opens no pull request and publishes nothing. An agent writes
    documents like that from web pages and issue comments, so the text inside one is untrusted, and the
    same shape made passive discovery offer `cd somewhere` as a destination on the strength of a docstring.

    The cost, stated rather than hidden: `cat > notes.md <<MD ... MD` writes a prose file and is not
    noticed. The shape that would have recorded is `bash: cat`, which is not worth acting on, and heredocs
    carrying scripts are far more common than heredocs writing documents.
    """
    return HEREDOC.sub(" ", cmd)


# A message is at most this long. Past it the thing being read is not a message, and the checks cannot
# use it: a 300MB file became a 646MB process, and a FIFO held the hook open until the harness killed it.
MOST_BYTES = 400_000


def read_prose_file(path, cwd=None, inside=True):
    """The contents of a file whose prose is about to be published, or None.

    Three conditions, and the first is the one doing the work. `inside` means the path came from text the
    command carried rather than from the command itself, and a hidden path is refused there: prose is
    never a dotfile, while `~/.ssh/id_ed25519`, `.env`, `.aws/credentials` and `.git/config` all are.
    That is a floor, not a wall — `~/secrets/token.txt` would still be read — so it is not what closes
    this. What closes it is that a substitution inside a heredoc or a nested quote is no longer resolved
    at all, so nothing an agent merely writes DOWN can name a file to read. See `_from_bash`.

    Then: a regular file, so a device or a FIFO cannot hang the hook, and a size cap, because a file
    larger than a message is not a message.
    """
    full = os.path.expanduser(path)
    if not os.path.isabs(full):
        full = os.path.join(cwd or os.getcwd(), full)
    if inside and any(part.startswith(".") and part not in (".", "..")
                      for part in os.path.abspath(full).split(os.sep)):
        return None
    try:
        st = os.lstat(full)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_size > MOST_BYTES:
        return None                           # a symlink, a device, a FIFO, or larger than a message
    try:
        with open(full, errors="replace") as fh:
            return fh.read(MOST_BYTES)
    except OSError:
        return None

def flag_values(cmd):
    """Every (flag, value) the command itself passes, or None when it cannot be read as words.

    Token-level, and that is the whole point of it. It is the difference between a command that
    publishes prose and a command that merely mentions one: in `echo 'run: gh pr create --body "$(cat
    …)"' >> log.txt` the flag sits INSIDE a single token belonging to `echo`, so nothing here finds it.
    A regex over the whole string found it, resolved the substitution, read the file and sent it to the
    checker — for a command that appends one line to a log. An agent writes lines like that from web
    pages and issue comments, so what they contain is not the agent's own choice.

    A command that cannot be parsed as words yields nothing rather than falling back to searching the
    string: a command this tool cannot read is one it must not claim to have checked.
    """
    try:
        words = shlex.split(command_itself(cmd))
    except ValueError:
        return
    for i, word in enumerate(words):
        if not word.startswith("-"):
            continue
        if "=" in word:
            yield tuple(word.split("=", 1))
        elif i + 1 < len(words):
            yield word, words[i + 1]

READS_A_FILE = re.compile(r"""^\$\(\s*(?:cat|<)\s+['"]?([^'"\s)]+)['"]?\s*\)$""")
# Subcommand -> the flags whose presence still leaves the invocation a report. A flag that is not listed
# for the subcommand in hand refuses the whole substitution, which is the only version of this that
# survives a future git release adding a flag nobody here has read about.
REPORTS = {"log": ("--format", "--pretty", "--date", "-n", "--max-count", "--skip", "--reverse",
                   "--no-merges", "--first-parent"),
           "show": ("--format", "--pretty", "--date", "-s", "--no-patch"),
           "cat-file": ("-p",),
           "describe": ("--tags", "--always", "--long", "--abbrev"),
           "rev-parse": ("--short", "--abbrev-ref", "--verify"),
           "rev-list": ("-n", "--max-count", "--count", "--reverse", "--no-merges", "--first-parent")}
CHAINS = (";", "&&", "||", "|", "`", "$(", ">", "<")
# Emptied for the one invocation, so no repository can name a command through them.
NO_CONFIGURED_COMMANDS = ("--no-pager", "-c", "diff.external=", "-c", "core.pager=cat")
_FLAG = re.compile(r"^(--?[A-Za-z][-\w]*)(=.*)?$", re.S)
# A revision, a count, or a path: `HEAD~2`, `main..HEAD`, `v1.0`, `5`, `docs/x.md`. Never a flag.
_PLAIN = re.compile(r"^[A-Za-z0-9][\w./^~@{}+-]*$")


def _only_reports(words):
    """Whether every argument of a git invocation is one this tool recognises as reporting."""
    allowed = REPORTS.get(words[1])
    if allowed is None:
        return False
    for word in words[2:]:
        if re.fullmatch(r"-\d+", word) or word == "--":
            continue                          # `git log -1`, and the end-of-flags separator
        flag = _FLAG.match(word)
        if flag:
            if flag.group(1) not in allowed:
                return False
        elif not _PLAIN.match(word):
            return False
    return True


# One tool call resolves a given substitution once. The old shape ran it twice — `extract` resolved it,
# and `unreadable` resolved it again to decide whether the gap was worth mentioning — which doubled every
# side effect the whitelist was there to prevent. Making a second call free is smaller than coordinating
# two call sites, and it holds for a third caller nobody has written yet. The process lives for one tool
# call, so the cache cannot go stale.
_RESOLVED = {}


def resolve(value, cwd=None):
    """The text behind a substitution, where it can be had without risking a side effect.

    Returns None when it cannot, which is the honest answer for `${SUMMARY}` — the hook is a separate
    process and never sees the caller's shell variables — and for any command it declines to run.
    """
    key = (value.strip(), cwd or os.getcwd())
    if key not in _RESOLVED:
        _RESOLVED[key] = _resolve(*key)
    return _RESOLVED[key]


def _resolve(value, cwd):
    m = READS_A_FILE.match(value)
    if m:
        return read_prose_file(m.group(1), cwd)
    if not (value.startswith("$(") and value.endswith(")")):
        return None
    inner = value[2:-1].strip()
    if any(bad in inner[2:] for bad in CHAINS):
        return None
    try:
        words = shlex.split(inner)            # so `--format="%B"` does not reach git with the quotes
    except ValueError:
        return None
    if len(words) < 2 or words[0] != "git" or not _only_reports(words):
        return None
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        got = subprocess.run(words[:1] + list(NO_CONFIGURED_COMMANDS) + words[1:],
                             capture_output=True, text=True, timeout=20, env=env,
                             cwd=cwd or os.getcwd())
    except Exception:
        return None
    return got.stdout if got.returncode == 0 else None


# A text argument whose value the tool call does not contain: `--body "$(git log -1 --format=%b)"`,
# `--body "$(cat notes.md)"`, `--message "${SUMMARY}"`. The prose is real and is about to be published;
# it just is not here. The quotes are gone by the time this is tested, because the value came from
# `flag_values`, which reads the command as words.
SUBSTITUTED = ("$(", "${")
