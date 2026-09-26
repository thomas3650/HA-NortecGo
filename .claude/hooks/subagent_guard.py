r"""PreToolUse hook: refuse subagents' edits to guarded paths, git hook bypasses, whole-tree reverts and
direct .env reads.

Design: docs/superpowers/specs/2026-09-25-ways-of-working-design.md §5 and
docs/superpowers/specs/2026-09-26-guard-hardening-design.md. Best-effort, like the main guard.
Runs on Python >= 3.9 with the stdlib only. Exit 0 allows the call; exit 2 refuses it (stderr is shown).
The main thread (no ``agent_id`` in the input) is never restricted.

Refused for subagents, besides edits of guarded paths: skipping hooks (``--no-verify`` and its prefixes,
``-n``, ``SKIP=``); config that can bypass them (``core.hooksPath``, ``alias.*``, ``include.*``,
``includeIf.*`` via ``-c``/``--config-env``/``git config``; any ``GIT_CONFIG*`` variable); whole-tree
reverts (``git reset --hard/--merge/--keep``, ``git stash``, ``git clean -x/-X``, ``checkout -f``,
``switch -f/--discard-changes``, and ``checkout``/``restore``/``rm`` of the root, globs, ``$``/``~+``
expansions or pathspec magic); a shell reading commands from stdin; and direct .env reads (Bash words
and redirects, ``python -c``/``perl -e`` text, and Read/Grep/Glob). ``sh``/``bash``/``zsh``/``dash``/
``ksh``/``csh``/``tcsh -c`` and ``eval`` strings are checked as commands. ``cp``/``ln`` count only the
destination (and where each source lands in it), except links (``ln``, ``cp -l``/``-s``), which count
the sources too. ``git clean -f``/``-fd`` without a pathspec is allowed: it removes untracked, non-ignored
files only.

Known limits: commands inside quoted ``"$(...)"`` or backticks are not inspected (the quoted heredoc commit
form must stay allowed); a script that opens files itself, a recursive search (``grep -rn X .``), a write
after ``cd`` into a guarded directory, ``git -C <dir>`` path arguments (resolved against the payload cwd),
a whole-tree copy into the root (``cp -R /tmp/x/. .``, or with a trailing slash, ``cp -R /tmp/x/ .``),
switching branches (``git checkout <branch>``, ``git switch <branch>``), whole-tree plumbing
(``git checkout-index -a -f``, ``git read-tree -u --reset``), other writers (``rsync``, ``tar -x``,
``unzip``, ``install``), a relative symlink target (resolved from the link's directory, e.g.
``ln -s ../.pre-commit-config.yaml docs/p``), a global config reached through ``HOME=`` or
``XDG_CONFIG_HOME=``, obfuscated commands (``xargs``, ``timeout``, ``nice``, ``find -exec``), ANSI-C
quoting (``$'.env'``), globs that reach .env only through shell options (zsh ``*(D)`` or ``globdots``,
bash ``dotglob``), assignments made by builtins (``printf -v``), GNU long-option prefixes of ``cp``
(``--li``, ``--targ=``), and reads of ``captures/`` (the hard rule covers them) are not detected.
Read/Grep/Glob are checked only when the hook's matcher includes them. A quoted argument made only of
shell punctuation (``grep ">" file``) is indistinguishable from a redirect after tokenizing and is treated
as one; search with ``grep "[>]" file`` instead. Some harmless commands are refused too:
``git config --get alias.x``, ``git restore --staged .``, commands that mention .env without reading it
(``ls .env``, ``grep -n .env .gitignore``), ``[.]env`` quoted or not (the hook can't see quotes; write
``"\.env"``), and words with more than 4096 brace alternatives. Grep's ``glob`` is
checked only when the search covers the repo root (no ``path``, or the root or an ancestor).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOW_FILE = ROOT / ".git" / "subagent-guard-allow"
GUARDED_PARTS = {".claude", ".git"}
CASE_FOLD = sys.platform == "darwin"
FILE_TOOLS = {"Edit": "file_path", "Write": "file_path", "NotebookEdit": "notebook_path"}
READ_TOOLS = {"Read": ("file_path",), "Grep": ("path", "glob"), "Glob": ("path", "pattern")}
BRACES = re.compile(r"\{([^{}]*)\}")
ENV_TEXT = re.compile(r"(?<![\w.])\.env(?![\w.])")
WRITE_COMMANDS = {"tee", "mv", "rm", "chmod", "truncate", "touch"}
GIT_WRITE_SUBCOMMANDS = {"checkout", "restore", "rm"}
WRAPPERS = {"env", "command", "nohup", "time", "exec", "!"}
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
DANGEROUS_CONFIG = re.compile(r"^(?:core\.hookspath|alias\.|include\.|includeif\.)", re.IGNORECASE)
DECLARE_BUILTINS = {"export", "env", "declare", "typeset", "readonly", "local"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "csh", "tcsh"}
SHELL_VALUE_OPTIONS = {"--rcfile", "--init-file"}
MAX_BRACE_ALTERNATIVES = 4096
GLOB_CHARS = set("*?[")
RESET_MODES = ("--hard", "--merge", "--keep")
PUNCTUATION = set(";&|()<>\n")
OPERATOR = re.compile(r"&>>?|>>|>&|>\||<<<|<<|<&|<>|[<>]|&&|\|\||[;&|()\n]")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
GUARDED_TEXT = re.compile(
    r"(?:^|[^\w.-])\.(?:claude|git)(?:/|$|[^\w.-])|\.pre-commit-config\.yaml", re.IGNORECASE
)
UNPARSEABLE = "unparseable command: rephrase with the Write tool or `git commit -F <file>`"


class Refuse(Exception):
    """The call is refused; the message says why."""


def norm(path: str) -> str:
    real = os.path.realpath(path)
    return real.casefold() if CASE_FOLD else real


def resolve(path: str, cwd: str | None) -> str:
    return norm(os.path.join(cwd or str(ROOT), os.path.expanduser(path)))


def has_git_part(resolved: str) -> bool:
    return ".git" in Path(resolved).parts


def is_guarded(resolved: str) -> bool:
    if GUARDED_PARTS.intersection(Path(resolved).parts):
        return True
    return resolved == norm(str(ROOT / ".pre-commit-config.yaml"))


def expand_braces(word: str) -> list[str]:
    """Expand simple ``{a,b}`` groups, as bash and zsh do, up to MAX_BRACE_ALTERNATIVES words."""
    pending, done = [word], []
    while pending:
        current = pending.pop()
        match = BRACES.search(current)
        if not match or "," not in match.group(1):
            done.append(current)
            continue
        head, tail = current[: match.start()], current[match.end() :]
        pending.extend(head + alt + tail for alt in match.group(1).split(","))
        if len(pending) + len(done) > MAX_BRACE_ALTERNATIVES:
            raise Refuse("too many brace alternatives; rephrase")
    return done


def env_basenames(word: str) -> list[str]:
    """The basenames a word can reach: brace alternatives, the part after the last ``=``."""
    bases = []
    for alt in expand_braces(word):
        base = alt.rpartition("=")[2].rstrip("/").rsplit("/", 1)[-1]
        bases.append(base.casefold() if CASE_FOLD else base)
    return bases


def names_env(word: str) -> bool:
    """The word reaches .env as a shell word: a basename starting with ``.`` or ``[`` (a shell glob
    needs one to match a dotfile) that matches .env."""
    return any(b[:1] in (".", "[") and fnmatch.fnmatchcase(".env", b) for b in env_basenames(word))


def glob_reaches_env(pattern: str) -> bool:
    """ripgrep's --glob overrides hidden and ignore filtering, so any matching glob reaches .env."""
    return any(fnmatch.fnmatchcase(".env", b) for b in env_basenames(pattern))


def allowlist() -> set[str]:
    try:
        lines = ALLOW_FILE.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return set()
    return {resolve(line.strip(), str(ROOT)) for line in lines if line.strip()}


def check_root() -> None:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and norm(env) != norm(str(ROOT)):
        raise Refuse(f"CLAUDE_PROJECT_DIR ({env}) is not the repo this guard belongs to ({ROOT})")


def check_file(tool: str, tool_input: dict, cwd: str | None) -> None:
    raw = tool_input.get(FILE_TOOLS[tool])
    if not isinstance(raw, str) or not raw:
        raise Refuse(f"{tool} call without a {FILE_TOOLS[tool]}")
    target = resolve(raw, cwd)
    if not is_guarded(target):
        return
    if has_git_part(target):
        raise Refuse(f"{raw} is under .git; subagents never edit it")
    if target not in allowlist():
        raise Refuse(f"{raw} is a guarded file and is not in this task's Guarded files")


def check_read(tool: str, tool_input: dict, cwd: str | None) -> None:
    path = tool_input.get("path")
    searches_root = not isinstance(path, str) or is_root_or_ancestor(resolve(path, cwd))
    for field in READ_TOOLS[tool]:
        value = tool_input.get(field)
        if not isinstance(value, str):
            continue
        is_glob = tool == "Grep" and field == "glob"
        candidates = [value, *grep_glob_pieces(value)] if is_glob else [value]
        for candidate in candidates:
            reaches = is_glob and searches_root and glob_reaches_env(candidate)
            if names_env(candidate) or reaches:
                raise Refuse(f"{tool} of .env; subagents never read it directly")


def grep_glob_pieces(value: str) -> list[str]:
    """How Claude Code splits Grep's ``glob`` into ``--glob`` flags: on whitespace, then each piece on
    commas unless it holds both ``{`` and ``}``."""
    pieces: list[str] = []
    for piece in value.split():
        pieces.extend([piece] if "{" in piece and "}" in piece else piece.split(","))
    return [p for p in pieces if p]


def tokenize(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        raise Refuse(UNPARSEABLE) from None


def split_commands(tokens: list[str]) -> list[list[str]]:
    """Split on separators; keep redirect operators (split out of mixed runs like ``)>``) in place."""
    commands: list[list[str]] = [[]]
    for token in tokens:
        if not token or not set(token) <= PUNCTUATION:
            commands[-1].append(token)
            continue
        for op in OPERATOR.findall(token):
            if "<" in op or ">" in op:
                commands[-1].append(op)
            else:
                commands.append([])
    return [c for c in commands if c]


def strip_redirects(tokens: list[str], cwd: str | None) -> list[str]:
    """Return the words of a simple command; refuse a redirect whose target is guarded."""
    words: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not (token and set(token) <= PUNCTUATION):
            words.append(token)
            i += 1
            continue
        target = tokens[i + 1] if i + 1 < len(tokens) else ""
        i += 2
        if names_env(target):
            raise Refuse("reads or writes .env; subagents never touch it directly")
        if token.startswith("<<"):
            raise Refuse(UNPARSEABLE)
        if ">" not in token:
            continue
        if target in {"/dev/null", "-"} or (target.startswith("&") and target[1:].isdigit()):
            continue
        if token.endswith("&") and target.isdigit():
            continue
        if is_guarded(resolve(target, cwd)):
            raise Refuse(f"redirect writes to guarded path {target}")
    return words


def names_guarded_path(words: list[str], cwd: str | None) -> bool:
    return any(not w.startswith("-") and is_guarded(resolve(w, cwd)) for w in words)


def short_group_has(arg: str, letters: str) -> bool:
    """A short-option group (``-fdx``) containing any of ``letters``."""
    return arg.startswith("-") and not arg.startswith("--") and any(c in arg[1:] for c in letters)


def is_long_prefix(arg: str, option: str, minimum: int) -> bool:
    """``arg`` (before any ``=``) is a unique-prefix spelling of ``option``, git style."""
    name = arg.partition("=")[0]
    return len(name) >= minimum and option.startswith(name)


def is_root_or_ancestor(resolved: str) -> bool:
    root = norm(str(ROOT))
    return resolved == root or root.startswith(resolved.rstrip(os.sep) + os.sep)


def names_guarded_pathspec(words: list[str], cwd: str | None) -> bool:
    """Like names_guarded_path, plus the root, its ancestors, globs, shell expansions ($, ~+, ~-) and
    pathspec magic."""
    for word in words:
        if word.startswith("-"):
            continue
        if word.startswith((":", "~+", "~-")) or "$" in word or GLOB_CHARS.intersection(word):
            return True
        target = resolve(word, cwd)
        if is_guarded(target) or is_root_or_ancestor(target):
            return True
    return False


def copy_targets(name: str, args: list[str]) -> list[str]:
    """The paths cp/ln write: the destination (and where each source lands in it), or, for a link
    (hard or symbolic), the destination and the sources."""
    operands: list[str] = []
    target: str | None = None
    # A link makes its source writable through the new name, so the sources count too.
    links = name == "ln"
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            operands.extend(args[i + 1 :])
            break
        if not arg.startswith("-") or arg == "-":
            operands.append(arg)
        elif arg.startswith("--"):
            option, has_value, value = arg.partition("=")
            if option == "--target-directory":
                if has_value:
                    target = value
                else:
                    target = args[i + 1] if i + 1 < len(args) else ""
                    i += 1
            elif option in {"--link", "--symbolic-link"} and name == "cp":
                links = True
        else:
            group = arg[1:]
            if name == "cp" and ("l" in group or "s" in group):
                links = True
            if "t" in group:
                rest = group[group.index("t") + 1 :]
                if rest:
                    target = rest
                else:
                    target = args[i + 1] if i + 1 < len(args) else ""
                    i += 1
        i += 1
    if target is not None:
        dest, sources = target, operands
    else:
        dest, sources = (operands[-1] if operands else ""), operands[:-1]
    if links:
        return [dest, *sources]
    # Into a directory, each source lands at <dest>/<its basename>.
    return [dest] + [os.path.join(dest, os.path.basename(s.rstrip("/"))) for s in sources]


def check_git(args: list[str], cwd: str | None) -> None:
    i = 0
    while i < len(args) and args[i].startswith("-"):
        option, has_value, attached = args[i].partition("=")
        if option in {"-c", "--config-env"}:
            if has_value:
                value = attached
                i += 1
            else:
                value = args[i + 1] if i + 1 < len(args) else ""
                i += 2
            if DANGEROUS_CONFIG.match(value):
                raise Refuse(f"git {option} {value.partition('=')[0]} can bypass the hooks")
        elif option in GIT_VALUE_OPTIONS and not has_value:
            i += 2
        else:
            i += 1
    if i >= len(args):
        return
    sub, rest = args[i], args[i + 1 :]
    if sub in {"commit", "push"}:
        takes_value = set("mFCct") if sub == "commit" else set("o")
        skip_next = False
        for arg in rest:
            if skip_next:
                skip_next = False
                continue
            if arg == "--":
                break
            if arg.startswith("--no-verify") or is_long_prefix(arg, "--no-verify", len("--no-v")):
                raise Refuse(f"git {sub} --no-verify bypasses the hooks")
            if arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
                for pos, flag in enumerate(arg[1:], start=1):
                    if flag == "n":
                        raise Refuse(f"git {sub} -n bypasses the hooks")
                    if flag in takes_value:
                        skip_next = pos == len(arg) - 1
                        break
    elif sub == "config":
        if any(DANGEROUS_CONFIG.match(a) for a in rest):
            raise Refuse("git config of hooksPath, alias or include can bypass the hooks")
    elif sub == "reset":
        for arg in rest:
            if arg == "--":
                break
            if any(is_long_prefix(arg, mode, 3) for mode in RESET_MODES):
                raise Refuse("git reset --hard/--merge/--keep reverts the whole tree")
    elif sub == "stash":
        if not rest or rest[0] not in {"list", "show"}:
            raise Refuse("git stash reverts the whole tree")
    elif sub == "clean":
        if any(short_group_has(a, "xX") for a in rest):
            raise Refuse("git clean -x/-X deletes ignored files")
        if names_guarded_pathspec(rest, cwd):
            raise Refuse("git clean deletes a guarded path or the whole tree")
    elif sub in GIT_WRITE_SUBCOMMANDS:
        if sub in {"checkout", "restore"}:
            for arg in rest:
                if arg == "--":
                    break
                if (
                    short_group_has(arg, "f")
                    or is_long_prefix(arg, "--force", 3)
                    or is_long_prefix(arg, "--pathspec-from-file", 6)
                ):
                    raise Refuse(f"git {sub} --force/--pathspec-from-file reverts the whole tree")
        if names_guarded_pathspec(rest, cwd):
            raise Refuse(f"git {sub} writes a guarded path or the whole tree")
    elif sub == "switch":
        for arg in rest:
            if arg == "--":
                break
            if (
                short_group_has(arg, "f")
                or is_long_prefix(arg, "--force", 3)
                or is_long_prefix(arg, "--discard-changes", 4)
            ):
                raise Refuse("git switch --force/--discard-changes reverts the whole tree")
    elif sub == "apply" and GUARDED_TEXT.search(" ".join(rest)):
        raise Refuse("git apply on a guarded path")


def check_simple(words: list[str], cwd: str | None) -> None:
    i = 0
    while i < len(words) and ASSIGNMENT.match(words[i]):
        if words[i].startswith("SKIP="):
            raise Refuse("SKIP= skips pre-commit hooks")
        if words[i].startswith("GIT_CONFIG"):
            raise Refuse("GIT_CONFIG* can bypass the hooks")
        i += 1
    if i >= len(words):
        return
    name, args = os.path.basename(words[i]), words[i + 1 :]
    if name in DECLARE_BUILTINS:
        for arg in args:
            if arg.startswith("SKIP="):
                raise Refuse("SKIP= skips pre-commit hooks")
            if arg.startswith("GIT_CONFIG"):
                raise Refuse("GIT_CONFIG* can bypass the hooks")
    if name in WRAPPERS:
        rest = args
        while rest and rest[0].startswith("-"):
            takes_value = name == "env" and rest[0] in {"-u", "-C", "--unset", "--chdir"}
            rest = rest[2:] if takes_value else rest[1:]
        check_simple(rest, cwd)
    elif name == "uv" and args[:1] == ["run"]:
        rest = args[1:]
        while rest and rest[0].startswith("-"):
            rest = rest[1:]
        check_simple(rest, cwd)
    elif name in SHELLS:
        for pos, arg in enumerate(args):
            if short_group_has(arg, "c"):
                commands = [a for a in args[pos + 1 :] if not a.startswith("-")]
                if commands:
                    check_bash(commands[0], cwd)
                break
        else:
            # Options start with - or +; an option's value (-o pipefail, -eo pipefail) is not the
            # script: a short group ending in o/O takes the next word.
            options: list[str] = []
            j = 0
            while j < len(args) and args[j][:1] in ("-", "+"):
                arg = args[j]
                short_value = not arg.startswith("--") and len(arg) > 1 and arg[-1] in "oO"
                options.append(arg)
                j += 2 if short_value or arg in SHELL_VALUE_OPTIONS else 1
            if j >= len(args) or any(short_group_has(a, "s") for a in options):
                raise Refuse(f"{name} reading commands from stdin isn't inspected")
    elif name == "eval":
        check_bash(" ".join(args), cwd)
    elif name in {"cp", "ln"}:
        if names_guarded_path(copy_targets(name, args), cwd):
            raise Refuse(f"{name} writes a guarded path")
    elif name == "git":
        check_git(args, cwd)
    elif name == "pre-commit" and "uninstall" in args:
        raise Refuse("pre-commit uninstall removes the hooks")
    elif name in WRITE_COMMANDS:
        if names_guarded_path(args, cwd):
            raise Refuse(f"{name} writes a guarded path")
    elif name == "sed":
        in_place = any(
            a.startswith("--in-place")
            or (a.startswith("-") and not a.startswith("--") and "i" in a)
            for a in args
        )
        if in_place and names_guarded_path(args, cwd):
            raise Refuse("sed -i writes a guarded path")
    elif (
        name == "patch"
        or (name.startswith("python") and any(re.match(r"^-[A-Za-z]*c", a) for a in args))
        or (name == "perl" and any(re.match(r"^-[A-Za-z]*[eEi]", a) for a in args))
    ):
        if GUARDED_TEXT.search(" ".join(args)):
            raise Refuse(f"{name} may write a guarded path")
        if name != "patch" and ENV_TEXT.search(" ".join(args)):
            raise Refuse(f"{name} may read .env; subagents never read it directly")


def check_bash(command: str, cwd: str | None) -> None:
    for tokens in split_commands(tokenize(command)):
        words = strip_redirects(tokens, cwd)
        if any(names_env(w) for w in words):
            raise Refuse("reads .env; subagents never read it directly")
        check_simple(words, cwd)


def refuse(reason: str) -> int:
    suffix = "" if reason == UNPARSEABLE else " Report BLOCKED to the controller."
    print(f"subagent-guard: {reason}.{suffix}", file=sys.stderr)
    return 2


def main() -> int:
    try:
        data = json.loads(sys.stdin.read())
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except ValueError:
        return refuse("hook input is not a JSON object")
    if not data.get("agent_id"):
        return 0
    try:
        check_root()
        tool = data.get("tool_name")
        tool_input = data.get("tool_input") or {}
        cwd = data.get("cwd")
        if tool in FILE_TOOLS:
            check_file(tool, tool_input, cwd)
        elif tool == "Bash":
            check_bash(str(tool_input.get("command", "")), cwd)
        elif tool in READ_TOOLS:
            check_read(tool, tool_input, cwd)
    except Refuse as exc:
        return refuse(str(exc))
    except Exception as exc:
        return refuse(f"guard error ({type(exc).__name__}: {exc})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        print(
            f"subagent-guard: crashed ({exc!r}). Report BLOCKED to the controller.", file=sys.stderr
        )
        sys.exit(2)
