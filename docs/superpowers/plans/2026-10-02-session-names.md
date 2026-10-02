# Session names that collide across projects — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, the `Model:` tag, waves).

**Goal:** the PO flow tells this repo's sessions from another project's by the directory a session runs in, so another project's `po` or `team-lead` neither blocks a start nor receives a team lead's message (#53).

**Architecture:** a new read-only script, `scripts/sessions.py`, is the one place that decides whether a running session belongs to this repo: its `cwd` and the script's own directory have the same git common directory. The two start scripts call it for their refusal check. `docs/way-of-working.md` §8 and the two agent files tell the PO and the team lead when to call it. The session names don't change.

**Tech Stack:** Python 3.14 (standard library only), bash, pytest, git. Markdown for the docs task.

**Spec:** `docs/superpowers/specs/2026-10-02-session-names-design.md` (issue #53).

## Global Constraints

- **Nothing private (hard rule 3):** no IDs, tokens or emails, no real-instance data, no real session name
  of another project, and no local absolute path: not in the code, the tests, the docs, the commit message,
  or the report's quoted output. The session names, ids and paths in the tests are invented or come from
  `tmp_path`.
- **Never the real `claude`:** no test and no step runs `claude`, and nobody starts, stops, resumes or
  renames a session. Every test puts the stub `claude` first on `PATH` or passes the rows in. Don't run
  `scripts/po`, `scripts/team-lead` or `scripts/sessions.py` from the worktree by hand: the tests run
  copies.
- **`scripts/sessions.py` is read-only and standard library only:** it runs `claude agents --json` and
  `git rev-parse`, and writes nothing. It never prints a `cwd` or a session id, on stdout or stderr; the
  stderr of `git` and `claude` is captured and never passed through.
- **The session names stay** `po`, `team-lead` and `tl-<topic>`.
- **The texts are fixed:** the code and the texts in the tasks' blocks land as written there, line breaks
  included. (A hook may reformat Python; its result wins.)
- **Only the listed files change.** Never `.claude/settings.json`, `.claude/hooks/`,
  `.pre-commit-config.yaml`, `.github/workflows/`, `CLAUDE.md` or `CHANGELOG.md`.
- **Docs principles (`way-of-working.md` §7):** each fact lives in one place. The rule for "this repo's
  session" is stated in the new **Sessions of this repo** bullet; the re-send rule in the "If the PO session
  ends" bullet; the other places point there.
- **Gates before the commit** (`CLAUDE.md` → Commands): `uv run pytest -q`, then `uv run ruff check && uv
  run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`,
  and the coverage gate (`uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing
  --cov-fail-under=95`).
- **Every command runs in the issue worktree:** `cd <worktree> && …`, or `git -C <worktree> …`. The dispatch
  gives the worktree's absolute path. Edit files by absolute path under it.
- **Commit message:** write it with the Write tool to `/tmp/session-names-task-<n>-msg.txt` and commit with
  `git commit -F <file>`. No heredocs. End the message with the co-author trailer given in the dispatch.
  The title starts with `process:`.
- **Never push.** The team lead pushes.
- **Stop instead of widening:** if the work turns out to need `.claude/settings.json`, the guard hook,
  `.pre-commit-config.yaml`, `.github/workflows/` or a hard rule in `CLAUDE.md`, stop and report it; the
  team lead sends it to the PO as `blocked`.
- **PR:** title `process: the PO flow tells its sessions from other projects' (#53)`. It doesn't release,
  so there is no `CHANGELOG.md` entry and no bump.

## Review Focus

Each line names the test or check that pins it.

1. **A path prefix is taken for the rule.** The issue worktrees are next to the main checkout, and their
   directory's name starts with the main checkout's. Pinned by Task 1's fixture: the worktree is `repo-wt`
   next to `repo`, and the other repository is its sibling too
   (`test_ours_in_the_main_checkout_…`, `test_not_ours_elsewhere`).
2. **`git` prints a missing directory's path, and it reaches the terminal.** Pinned by
   `test_no_directory_or_session_id_is_printed`, which runs the script as a program with a session in a
   directory that doesn't exist.
3. **An inherited `GIT_DIR` makes every directory look like this repo.** Pinned by
   `test_an_inherited_git_dir_does_not_make_a_directory_ours`.
4. **`claude agents --json` fails or changes shape, and a start goes through anyway.** Pinned by
   `test_exit_2_…` (three tests) and `test_start_script_refuses_when_the_sessions_cannot_be_listed`.
5. **Both `po` and `team-lead` run, and the refusal message breaks over two lines.** Pinned by
   `test_start_script_refuses_for_a_session_of_this_repo`, which compares the whole of stderr.
6. **The docs state a rule twice, or cite the new bullet as a section.** No test reads the docs; pinned by
   Task 2, Step 6's searches and by the task review.

---

### Task 1: `scripts/sessions.py`, its tests, and the start scripts

**Model:** sonnet
**Wave:** 1

**Files:**
- Create: `scripts/sessions.py`
- Create: `tests/test_sessions.py`
- Modify: `scripts/po` (lines 3 and 13–17)
- Modify: `scripts/team-lead` (lines 3 and 13–17)
- Modify: `pyproject.toml` (mypy's `files`, ruff's `known-first-party`, the comment on the `scripts/*.py`
  per-file ignores)

**Interfaces:**
- Consumes: nothing from another task.
- Produces, for Task 2's texts (the commands the docs name):
  - `uv run python scripts/sessions.py running [NAME…]`: prints the names of this repo's running sessions,
    one per line, sorted, each once; with names given, only those of them that run. Exit 0.
  - `uv run python scripts/sessions.py reachable NAME`: exit 0 when exactly one running session on the
    machine has the name and it is this repo's; exit 1 otherwise, with one line on stderr.
  - Exit 2, with one line on stderr, when the sessions can't be listed.

- [ ] **Step 1: Register the new module in `pyproject.toml`**

Three one-line edits. In `[tool.mypy]`:

```toml
files = ["custom_components", "tests", "scripts/release_check.py", "scripts/sessions.py"]
```

In `[tool.ruff.lint.isort]`:

```toml
known-first-party = ["custom_components.nortec_go", "tests", "release_check", "sessions"]
```

In `[tool.ruff.lint.per-file-ignores]`, the comment above `"scripts/*.py"` becomes:

```toml
# Scripts run by the workflows or by hand, not a package; they print their results.
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_sessions.py` with exactly this content:

```python
"""Tests for scripts/sessions.py and the start scripts that use it. Nothing here calls the real `claude`."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest
import sessions

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
STUB = """#!/bin/sh
if [ "$1" = "agents" ] && [ "$2" = "--json" ]; then
  if [ -n "${STUB_FAIL:-}" ]; then
    echo "claude: cannot read $STUB_FAIL" >&2
    exit 1
  fi
  cat "$STUB_JSON"
  exit 0
fi
printf '%s\\n' "$@" > "$STUB_CALLS"
"""


def git(cwd: Path, *args: str) -> None:
    """Run git in cwd, without the git variables a hook may have set."""
    env = {key: value for key, value in os.environ.items() if key not in GIT_ENV_VARS}
    subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, env=env
    )


def make_repo(path: Path) -> Path:
    """Make a repository with one commit at path."""
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(
        path,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "init",
    )
    return path


class World:
    """Two repositories, a linked worktree of the first, a plain directory, and a stub `claude`."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Build the directories and put the stub first on PATH."""
        self.ours = make_repo(tmp_path / "repo")
        self.worktree = tmp_path / "repo-wt"
        git(self.ours, "worktree", "add", "-q", str(self.worktree), "-b", "topic")
        self.other = make_repo(tmp_path / "other")
        self.plain = tmp_path / "plain"
        self.plain.mkdir()
        self.gone = tmp_path / "gone"
        self.link = tmp_path / "link"
        self.link.symlink_to(self.ours, target_is_directory=True)
        self.json = tmp_path / "agents.json"
        self.calls = tmp_path / "calls.txt"
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "claude"
        stub.write_text(STUB)
        stub.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("STUB_JSON", str(self.json))
        monkeypatch.setenv("STUB_CALLS", str(self.calls))
        monkeypatch.delenv("STUB_FAIL", raising=False)
        for name in GIT_ENV_VARS:
            monkeypatch.delenv(name, raising=False)

    def sessions(self, *rows: dict[str, Any]) -> list[dict[str, Any]]:
        """Write the rows as the stub's `agents --json` output, and return them."""
        self.json.write_text(json.dumps(list(rows)))
        return list(rows)

    def install(self, checkout: Path) -> Path:
        """Copy the three scripts into checkout/scripts and return that directory."""
        target = checkout / "scripts"
        target.mkdir()
        for name in ("sessions.py", "po", "team-lead"):
            shutil.copy(SCRIPTS / name, target / name)
        return target


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    """The directories and the stub `claude` of one test."""
    return World(tmp_path, monkeypatch)


def row(name: str | None, cwd: Path | None, number: int = 1) -> dict[str, Any]:
    """One row of `claude agents --json`, with an invented session id."""
    result: dict[str, Any] = {
        "kind": "interactive",
        "pid": 1000 + number,
        "sessionId": f"00000000-0000-4000-8000-{number:012d}",
        "status": "idle",
    }
    if name is not None:
        result["name"] = name
    if cwd is not None:
        result["cwd"] = str(cwd)
    return result


def test_ours_in_the_main_checkout_a_worktree_a_subdirectory_and_through_a_symlink(
    world: World,
) -> None:
    """A session is ours wherever in a checkout of the repository it runs."""
    sub = world.worktree / "docs"
    sub.mkdir()
    rows = [
        row("in-main", world.ours, 1),
        row("in-worktree", world.worktree, 2),
        row("in-subdirectory", sub, 3),
        row("through-symlink", world.link, 4),
    ]
    assert sessions.running(rows, anchor=world.ours) == [
        "in-main",
        "in-subdirectory",
        "in-worktree",
        "through-symlink",
    ]
    assert sessions.running(rows, anchor=world.worktree) == sessions.running(
        rows, anchor=world.ours
    )


def test_not_ours_elsewhere(world: World) -> None:
    """Another repository, a plain directory, a missing directory and no cwd are not ours."""
    rows = [
        row("other-repo", world.other, 1),
        row("plain-dir", world.plain, 2),
        row("gone-dir", world.gone, 3),
        row("no-cwd", None, 4),
        {**row("empty-cwd", None, 5), "cwd": ""},
        {**row("odd-cwd", None, 6), "cwd": 7},
    ]
    assert sessions.running(rows, anchor=world.ours) == []


def test_running_filters_sorts_and_skips(world: World) -> None:
    """Names are sorted and printed once; a row without a name is skipped; names filter."""
    rows = [
        row("tl-b", world.worktree, 1),
        row("po", world.ours, 2),
        row("po", world.ours, 3),
        row(None, world.ours, 4),
        {**row("done", world.ours, 5), "status": "busy", "kind": "background"},
        row("team-lead", world.other, 6),
    ]
    assert sessions.running(rows, anchor=world.ours) == ["done", "po", "tl-b"]
    assert sessions.running(rows, ["po", "team-lead"], anchor=world.ours) == ["po"]
    assert sessions.running(rows, ["team-lead"], anchor=world.ours) == []


def test_an_inherited_git_dir_does_not_make_a_directory_ours(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With GIT_DIR set to our repository, a session in a plain directory is still not ours."""
    monkeypatch.setenv("GIT_DIR", str(world.ours / ".git"))
    rows = [row("plain-dir", world.plain), row("in-main", world.ours, 2)]
    assert sessions.running(rows, anchor=world.ours) == ["in-main"]


def test_reachable_reasons(world: World) -> None:
    """Only a name that exactly one session has, and that one ours, is reachable."""
    rows = [
        row("po", world.ours, 1),
        row("elsewhere", world.other, 2),
        row("twice", world.ours, 3),
        row("twice", world.other, 4),
    ]
    assert sessions.unreachable_reason(rows, "po", anchor=world.ours) is None
    assert (
        sessions.unreachable_reason(rows, "nobody", anchor=world.ours)
        == "sessions: no running session is named nobody."
    )
    assert (
        sessions.unreachable_reason(rows, "elsewhere", anchor=world.ours)
        == "sessions: the session named elsewhere belongs to another project."
    )
    assert (
        sessions.unreachable_reason(rows, "twice", anchor=world.ours)
        == "sessions: 2 running sessions are named twice."
    )


@pytest.mark.parametrize(
    ("argv", "code", "out", "err"),
    [
        (["running"], 0, "po\ntl-a\n", ""),
        (["running", "po", "team-lead"], 0, "po\n", ""),
        (["reachable", "po"], 0, "", ""),
        (
            ["reachable", "nobody"],
            1,
            "",
            "sessions: no running session is named nobody.\n",
        ),
    ],
)
def test_main(
    world: World,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    code: int,
    out: str,
    err: str,
) -> None:
    """The commands print and exit as the table in the spec says."""
    world.sessions(row("tl-a", world.worktree, 1), row("po", world.ours, 2))
    assert sessions.main(argv, anchor=world.ours) == code
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == (out, err)


@pytest.mark.parametrize(
    ("output", "message"),
    [
        ("not json", "sessions: `claude agents --json` did not print JSON.\n"),
        (
            '{"name": "po"}',
            "sessions: `claude agents --json` did not print an array of objects.\n",
        ),
        (
            '["po"]',
            "sessions: `claude agents --json` did not print an array of objects.\n",
        ),
    ],
)
def test_exit_2_on_output_that_is_not_an_array_of_objects(
    world: World, capsys: pytest.CaptureFixture[str], output: str, message: str
) -> None:
    """Output of another shape is an error, for both commands."""
    world.json.write_text(output)
    assert sessions.main(["running"], anchor=world.ours) == 2
    assert sessions.main(["reachable", "po"], anchor=world.ours) == 2
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", message * 2)


def test_exit_2_when_claude_fails_and_its_stderr_is_not_passed_on(
    world: World, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """A failing `claude` gives exit 2 and the script's own line, not claude's stderr."""
    monkeypatch.setenv("STUB_FAIL", str(world.gone))
    assert sessions.main(["running"], anchor=world.ours) == 2
    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == "sessions: `claude agents --json` failed.\n"


def test_exit_2_when_claude_is_missing(
    world: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without a `claude` on PATH the script says so and exits 2."""
    monkeypatch.setenv("PATH", str(world.plain))
    assert sessions.main(["running"], anchor=world.ours) == 2
    assert (
        capsys.readouterr().err
        == "sessions: `claude agents --json` could not be run.\n"
    )


def test_exit_2_when_the_anchor_is_not_in_a_repository(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    """The script must sit in a git repository to know which one is ours."""
    world.sessions(row("po", world.ours))
    assert sessions.main(["running"], anchor=world.plain) == 2
    assert sessions.main(["reachable", "po"], anchor=world.plain) == 2
    assert (
        capsys.readouterr().err
        == "sessions: this script is not in a git repository.\n" * 2
    )


def run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a script copy as a program, with the test's environment."""
    return subprocess.run(
        [str(script), *args], capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize(
    "command", [["running"], ["reachable", "gone-dir"], ["reachable", "other-repo"]]
)
def test_no_directory_or_session_id_is_printed(
    world: World, command: list[str]
) -> None:
    """Neither stdout nor stderr holds a cwd or a session id, also for a missing directory."""
    scripts = world.install(world.ours)
    rows = world.sessions(
        row("gone-dir", world.gone, 1),
        row("other-repo", world.other, 2),
        row("po", world.ours, 3),
    )
    result = subprocess.run(
        [sys.executable, str(scripts / "sessions.py"), *command],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1)
    printed = result.stdout + result.stderr
    for session in rows:
        assert session["cwd"] not in printed
        assert session["sessionId"] not in printed
    assert str(world.gone.parent) not in printed


@pytest.mark.parametrize("script", ["po", "team-lead"])
@pytest.mark.parametrize(
    ("names", "listed"),
    [
        (["po"], "po"),
        (["team-lead"], "team-lead"),
        (["team-lead", "po"], "po team-lead"),
    ],
)
def test_start_script_refuses_for_a_session_of_this_repo(
    world: World, script: str, names: list[str], listed: str
) -> None:
    """A po or team-lead session of this repository stops the start; both are named on one line."""
    scripts = world.install(world.ours)
    world.sessions(*(row(name, world.worktree, i) for i, name in enumerate(names)))
    result = run_script(scripts / script)
    assert result.returncode == 2
    assert result.stderr == (
        f"{script}: a session of this repo named {listed} is already running;"
        " PO mode and team lead mode never run at once.\n"
    )
    assert not world.calls.exists()


@pytest.mark.parametrize(
    ("script", "agent"), [("po", "po"), ("team-lead", "team-lead")]
)
def test_start_script_ignores_another_projects_sessions(
    world: World, script: str, agent: str
) -> None:
    """The same names in another repository don't stop the start."""
    scripts = world.install(world.ours)
    world.sessions(
        row("po", world.other, 1),
        row("team-lead", world.other, 2),
        row("tl-a", world.worktree, 3),
    )
    result = run_script(scripts / script, "--model", "x")
    assert result.returncode == 0, result.stderr
    assert world.calls.read_text().splitlines() == [
        "--agent",
        agent,
        "-n",
        agent,
        "--model",
        "x",
    ]


@pytest.mark.parametrize("script", ["po", "team-lead"])
def test_start_script_refuses_in_a_linked_worktree(world: World, script: str) -> None:
    """In a linked worktree the script refuses before it looks at the sessions."""
    scripts = world.install(world.worktree)
    world.sessions()
    result = run_script(scripts / script)
    assert result.returncode == 2
    assert (
        result.stderr
        == f"{script}: run this in the main checkout, not in a worktree.\n"
    )
    assert not world.calls.exists()


@pytest.mark.parametrize("script", ["po", "team-lead"])
def test_start_script_refuses_when_the_sessions_cannot_be_listed(
    world: World, monkeypatch: pytest.MonkeyPatch, script: str
) -> None:
    """If `claude agents --json` fails, the script doesn't start a session."""
    scripts = world.install(world.ours)
    monkeypatch.setenv("STUB_FAIL", "x")
    result = run_script(scripts / script)
    assert result.returncode == 2
    assert result.stderr == "sessions: `claude agents --json` failed.\n"
    assert not world.calls.exists()
```

How the tests work, for the reader:
- `World` builds two repositories (`repo` and `other`), a linked worktree `repo-wt` of the first, a plain
  directory, the path of a directory that doesn't exist, and a symlink to `repo`. It writes the stub
  `claude` and puts it first on `PATH`.
- The stub prints the file named by `STUB_JSON` for `agents --json`, fails when `STUB_FAIL` is set (and
  writes that value to its stderr), and records any other call's arguments, one per line, in the file
  named by `STUB_CALLS`.
- The start scripts are tested as copies in `repo/scripts/`: in the real checkout a test may itself run in
  a linked worktree, which the scripts refuse. The copies run `uv run python scripts/sessions.py`; under
  `uv run pytest` the inner `uv run` uses the same environment (`VIRTUAL_ENV`), also in a directory without
  a project.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest -q tests/test_sessions.py`
Expected: an error at collection, `ModuleNotFoundError: No module named 'sessions'`.

- [ ] **Step 4: Write `scripts/sessions.py`**

Create `scripts/sessions.py` with exactly this content:

```python
"""Tell this repository's running Claude sessions from other projects' (docs/way-of-working.md §8, D49).

Read-only: it runs `claude agents --json` and `git rev-parse`, and writes nothing. It never prints a
session's directory or id, on stdout or stderr.
"""

import argparse
from collections.abc import Sequence
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
DROPPED_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")


class SessionsError(Exception):
    """The sessions can't be listed. The message is the script's own text and safe to print."""


def common_dir(directory: Path) -> Path | None:
    """Return the git common directory of the repository `directory` is in, or None if it is in none."""
    env = {
        key: value for key, value in os.environ.items() if key not in DROPPED_GIT_ENV
    }
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(directory),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except OSError:
        return None
    path = result.stdout.strip()
    if result.returncode != 0 or not path:
        return None
    return Path(path).resolve()


def repo_of(anchor: Path) -> Path:
    """Return the git common directory that stands for this repository."""
    repo = common_dir(anchor)
    if repo is None:
        raise SessionsError("sessions: this script is not in a git repository.")
    return repo


def parse_sessions(text: str) -> list[dict[str, Any]]:
    """Parse the output of `claude agents --json`."""
    try:
        rows = json.loads(text)
    except ValueError as err:
        raise SessionsError(
            "sessions: `claude agents --json` did not print JSON."
        ) from err
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise SessionsError(
            "sessions: `claude agents --json` did not print an array of objects."
        )
    return rows


def load_sessions() -> list[dict[str, Any]]:
    """Run `claude agents --json` and return its rows. Its stderr is captured and never passed on."""
    try:
        result = subprocess.run(
            ["claude", "agents", "--json"], capture_output=True, text=True, check=False
        )
    except OSError as err:
        raise SessionsError(
            "sessions: `claude agents --json` could not be run."
        ) from err
    if result.returncode != 0:
        raise SessionsError("sessions: `claude agents --json` failed.")
    return parse_sessions(result.stdout)


def is_ours(row: dict[str, Any], repo: Path) -> bool:
    """Say whether the session in `row` runs in a checkout of the repository `repo` stands for."""
    cwd = row.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return False
    return common_dir(Path(cwd)) == repo


def running(
    rows: Sequence[dict[str, Any]], names: Sequence[str] = (), anchor: Path = HERE
) -> list[str]:
    """Return the names of this repository's sessions, sorted, each once; only `names` if any are given."""
    repo = repo_of(anchor)
    ours = {
        row["name"]
        for row in rows
        if isinstance(row.get("name"), str) and is_ours(row, repo)
    }
    if names:
        ours &= set(names)
    return sorted(ours)


def unreachable_reason(
    rows: Sequence[dict[str, Any]], name: str, anchor: Path = HERE
) -> str | None:
    """Return why `name` can't be messaged safely, or None when exactly one session has it and it is ours."""
    repo = repo_of(anchor)
    named = [row for row in rows if row.get("name") == name]
    if not named:
        return f"sessions: no running session is named {name}."
    if len(named) > 1:
        return f"sessions: {len(named)} running sessions are named {name}."
    if not is_ours(named[0], repo):
        return f"sessions: the session named {name} belongs to another project."
    return None


def main(argv: Sequence[str] | None = None, anchor: Path = HERE) -> int:
    """Run a command; return 0, 1 (`reachable` says no) or 2 (the sessions can't be listed)."""
    parser = argparse.ArgumentParser(prog="sessions", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    running_parser = commands.add_parser(
        "running", help="print the names of this repo's running sessions"
    )
    running_parser.add_argument(
        "names", nargs="*", help="print only these names, if they run"
    )
    reachable_parser = commands.add_parser(
        "reachable", help="exit 0 if exactly one session has the name and it is ours"
    )
    reachable_parser.add_argument("name")
    args = parser.parse_args(argv)
    try:
        rows = load_sessions()
        if args.command == "running":
            for name in running(rows, args.names, anchor):
                print(name)
            return 0
        reason = unreachable_reason(rows, args.name, anchor)
    except SessionsError as err:
        print(err, file=sys.stderr)
        return 2
    if reason is not None:
        print(reason, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests of the script itself**

Run: `uv run pytest -q tests/test_sessions.py -k "not start_script"`
Expected: 18 passed, 12 deselected.

Run: `uv run pytest -q tests/test_sessions.py -k start_script`
Expected: the `refuses_for_a_session_of_this_repo`, `ignores_another_projects_sessions` and
`cannot_be_listed` tests FAIL (the start scripts still hold the inline Python, which counts every project's
sessions and has the old message); `refuses_in_a_linked_worktree` passes.

- [ ] **Step 6: Change `scripts/po`**

The file becomes exactly this (line 3's comment, the `running=` line and the message change; the rest
stays):

```bash
#!/usr/bin/env bash
# Start Claude in PO mode (docs/way-of-working.md §8): the PO session, named po, in the main checkout.
# Refuses in a linked worktree, and while a session of this repo named po or team-lead runs (the two modes never run at once).
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "$(git rev-parse --absolute-git-dir)" != "$(git rev-parse --path-format=absolute --git-common-dir)" ]; then
  echo "po: run this in the main checkout, not in a worktree." >&2
  exit 2
fi

running=$(uv run python scripts/sessions.py running po team-lead | paste -sd ' ' -)
if [ -n "$running" ]; then
  echo "po: a session of this repo named $running is already running; PO mode and team lead mode never run at once." >&2
  exit 2
fi

exec claude --agent po -n po "$@"
```

`paste -sd ' ' -` joins the names with one space. With `set -euo pipefail`, an exit 2 of `sessions.py`
stops the script with that exit code, and the script's one line is on stderr.

- [ ] **Step 7: Change `scripts/team-lead`**

The file becomes exactly this:

```bash
#!/usr/bin/env bash
# Start Claude in team lead mode (docs/way-of-working.md §8), for hard problems: the owner is the PO.
# Refuses in a linked worktree, and while a session of this repo named po or team-lead runs (the two modes never run at once).
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "$(git rev-parse --absolute-git-dir)" != "$(git rev-parse --path-format=absolute --git-common-dir)" ]; then
  echo "team-lead: run this in the main checkout, not in a worktree." >&2
  exit 2
fi

running=$(uv run python scripts/sessions.py running po team-lead | paste -sd ' ' -)
if [ -n "$running" ]; then
  echo "team-lead: a session of this repo named $running is already running; PO mode and team lead mode never run at once." >&2
  exit 2
fi

exec claude --agent team-lead -n team-lead "$@"
```

Both files stay executable (`git diff --summary` shows no mode change).

- [ ] **Step 8: Run the tests and the gates**

Run: `uv run pytest -q tests/test_sessions.py`
Expected: 30 passed.

Run the gates from *Global Constraints*.
Expected: all pass; the coverage gate stays at or above 95% (it measures `custom_components.nortec_go`
only, which this task doesn't touch).

- [ ] **Step 9: Check that nothing else changed**

Run: `git status --short`
Expected: exactly `scripts/sessions.py` and `tests/test_sessions.py` as new, and `scripts/po`,
`scripts/team-lead` and `pyproject.toml` as modified.

Run: `git diff --summary`
Expected: no `mode change` line.

- [ ] **Step 10: Commit**

Write the message to `/tmp/session-names-task-1-msg.txt` with the Write tool:

```text
process: scripts/sessions.py tells this repo's sessions from other projects' (#53)

The start scripts refuse only for a po or team-lead session of this repo.

<the co-author trailer from the dispatch>
```

```bash
git add scripts/sessions.py tests/test_sessions.py scripts/po scripts/team-lead pyproject.toml
git commit -F /tmp/session-names-task-1-msg.txt
```

---

### Task 2: §8, D49 and the two agent files

**Model:** opus (a docs task, D33)
**Wave:** 2
**Guarded files:** `.claude/agents/po.md`, `.claude/agents/team-lead.md`

**Files:**
- Modify: `docs/way-of-working.md` (§8 only: *Roles and start modes*, *Messages*, *After ready, the loop,
  and failures*)
- Modify: `docs/decisions.md` (D49, appended at the end)
- Modify: `.claude/agents/po.md` (start steps 2 and 3, one line of *Never*)
- Modify: `.claude/agents/team-lead.md` (*Your mode*, **PO mode**)

**Interfaces:**
- Consumes: the two commands Task 1 produces, by the names in its *Interfaces* block. Check them against
  `scripts/sessions.py` on the branch before editing.
- Produces: nothing for another task.

Each step below gives the text that is there now and the text that replaces it. Lines not shown stay as
they are.

- [ ] **Step 1: `docs/way-of-working.md`, *Roles and start modes***

The **Team lead mode** bullet's last four lines now read:

```text
  the same time:** `scripts/po` and `scripts/team-lead` refuse to start while a session named `po` or
  `team-lead` runs, or in a linked worktree, and the PO also checks at start that no session named
  `team-lead` runs. Team leads (`tl-*`) still running while the PO is down count as PO mode: the owner
  doesn't start `scripts/team-lead` then.
```

They become the following, with the new bullet right after them, before the "Owner only" bullet:

```text
  the same time:** `scripts/po` and `scripts/team-lead` refuse to start while a session of this repo named
  `po` or `team-lead` runs, or in a linked worktree, and the PO also checks at start that no session of this
  repo named `team-lead` runs. Team leads (`tl-*`) still running while the PO is down count as PO mode: the
  owner doesn't start `scripts/team-lead` then.
- **Sessions of this repo:** the session names are not unique on the machine: `claude agents --json` and
  `ListAgents` list the sessions of every project. A session is this repo's when it runs in the main
  checkout or one of its worktrees; `scripts/sessions.py` is the one place that decides it (D49). The
  start scripts count only this repo's sessions. A team lead sends to `po` only when
  `scripts/sessions.py reachable po` passes (exactly one running session is named `po`, and it is this
  repo's); otherwise the message counts as failed. So while another project's session named `po` runs,
  team leads hold their messages: two projects can't both run a PO flow with these names at once. The
  PO runs the same check at its start and in every round of its loop. When it starts to fail, the PO
  tells the owner; while it fails, the PO starts and resumes no team lead; when it passes again, the PO
  sends `hello` to its team leads as at its start (*After ready, the loop, and failures* has the
  re-sending).
```

- [ ] **Step 2: `docs/way-of-working.md`, *Messages***

The sentence under the table now reads:

```text
The PO also sends `hello` to its team leads when it starts (see *After ready, the loop, and failures*).
```

It becomes:

```text
The PO also sends `hello` to its team leads when it starts (see *After ready, the loop, and failures*), and
when its own name can be messaged again (*Roles and start modes*, **Sessions of this repo**).
```

- [ ] **Step 3: `docs/way-of-working.md`, *After ready, the loop, and failures***

Three bullets change. The loop bullet's last line, `  ready PRs.`, becomes:

```text
  ready PRs. Each round it also runs the check in *Roles and start modes*, **Sessions of this repo**.
```

The **State** bullet's last two lines now read:

```text
  record (*Merging*, **What the PO records**). `claude agents --json` shows the running sessions, interactive
  and background; `ListAgents` the names to message.
```

They become:

```text
  record (*Merging*, **What the PO records**). `claude agents --json` shows the running sessions of every
  project, interactive and background (`scripts/sessions.py running` those of this repo); `ListAgents` the
  names to message.
```

The bullet that starts "If the PO session ends" now reads:

```text
- If the PO session ends, team leads keep running. A `SendMessage` to a PO that is down fails at once; it
  isn't queued. The team lead keeps every message whose `SendMessage` to `po` failed, and waits (it doesn't
  poll for the PO). The next `scripts/po` rebuilds its state from the above, sends `hello` to every team lead
  in `.git/po-sessions.json`, and carries on; on that `hello`, each team lead re-sends the messages that
  failed, in order.
```

It becomes:

```text
- If the PO session ends, team leads keep running. A `SendMessage` to a PO that is down fails at once; it
  isn't queued. One that the check in *Roles and start modes*, **Sessions of this repo** stops counts as
  failed too. The team lead keeps every message whose `SendMessage` to `po` failed, and waits (it doesn't
  poll for the PO). The next `scripts/po` rebuilds its state from the above, sends `hello` to every team lead
  in `.git/po-sessions.json`, and carries on; on that `hello`, or on any later message from the PO, each
  team lead re-sends the messages that failed, in order.
```

Don't add "with the check" to this bullet: the **Sessions of this repo** bullet already says a team lead
sends to `po` only when the check passes.

- [ ] **Step 4: `docs/decisions.md`**

Append at the end of the file, after the last entry, with one blank line before it:

```markdown
### D49: The PO flow's sessions are told apart by their directory
- **Date:** 2026-10-02 · **Status:** active
- **Decision:** The session names stay `po`, `team-lead` and `tl-<topic>`, and a session belongs to this
  repo when its `cwd` is in the main checkout or one of its worktrees (`scripts/sessions.py` decides it).
  The start scripts count only this repo's sessions, a team lead sends to `po` only when exactly one
  running session has that name and it is this repo's, and the PO runs that check in every round of its
  loop and sends `hello` again once it passes.
- **Why:** The names are not unique on the machine (#53). Filtering by directory changes no name, so
  running sessions keep working; a repo prefix needs a transition and is the next step if two projects
  ever run a PO flow at once.
- **Source:** [session names spec](superpowers/specs/2026-10-02-session-names-design.md), Decisions
```

D48 is not in the file on this branch: it belongs to PR #103. Don't add it and don't renumber.

- [ ] **Step 5: The two agent files**

`.claude/agents/team-lead.md`, in *Your mode*, **PO mode**. The last three lines of the bullet now read:

```text
  step (`docs/releasing.md`), which you run before `branch ready`. If a `SendMessage` to `po` fails, keep
  that message and wait (don't poll for the PO); when the PO's `hello` arrives, re-send every message that
  failed, in order.
```

They become:

```text
  step (`docs/releasing.md`), which you run before `branch ready`. Before each `SendMessage` to `po`, run
  `uv run python scripts/sessions.py reachable po` in your issue worktree's root; if it fails, don't send:
  the message counts as failed. If a `SendMessage` to `po` fails, keep that message and wait (don't poll for
  the PO); when a message from the PO arrives (its `hello`, or any other), re-send every message that
  failed, in order, with the same check.
```

`.claude/agents/po.md`, *At the start of a session*. Steps 2 and 3 now read:

```text
2. Run `ListAgents`. If a session named `team-lead` runs, the owner is in team lead mode: say so and do
   nothing else.
3. Rebuild the picture: `claude agents --json`, `gh issue list --label active`, `gh pr list`.
```

They become:

```text
2. Run `uv run python scripts/sessions.py running team-lead`. If it prints `team-lead`, the owner is in
   team lead mode: say so and do nothing else. Then run `uv run python scripts/sessions.py reachable po`,
   and again in every round of the loop (§8 *Roles and start modes*, **Sessions of this repo**).
3. Rebuild the picture: `uv run python scripts/sessions.py running` and `claude agents --json` (which also
   lists other projects' sessions), `gh issue list --label active`, `gh pr list`.
```

`.claude/agents/po.md`, *Never*. The line

```text
- Start or resume a team lead while the main checkout is detached.
```

becomes

```text
- Start or resume a team lead while the main checkout is detached, or while `reachable po` fails.
```

Use the Edit tool on both files (they are on the allowlist for this task). Don't move, delete or rename
them.

- [ ] **Step 6: Check the texts**

```bash
git grep -c -F 'Sessions of this repo' -- docs/way-of-working.md .claude/agents
```

Expected: `docs/way-of-working.md:4` (the bullet itself, and the pointers in *Messages*, the loop bullet
and the "If the PO session ends" bullet) and `.claude/agents/po.md:1`.

```bash
git grep -n -F '*Sessions of this repo*' -- docs/way-of-working.md .claude/agents
```

Expected: no hit (the bullet is cited in bold, after its section in italics).

```bash
git grep -n -e 'session named `po` or' -e 'session named `team-lead` runs' -e 'Run `ListAgents`' -- docs/way-of-working.md .claude/agents
```

Expected: no hit (the old wordings are gone).

```bash
git grep -c -F 'any later message from the PO' -- docs/way-of-working.md
```

Expected: `docs/way-of-working.md:1` (the re-send rule has one home in §8).

```bash
git grep -n -e '^### D4[89]' -- docs/decisions.md
```

Expected: one hit, D49, and `tail -8 docs/decisions.md` shows it as the last entry.

```bash
git grep -n -e 'sessions.py running' -e 'sessions.py reachable' -- docs/way-of-working.md .claude/agents
```

Expected: every hit names a command from Task 1's *Interfaces* block, spelled as there.

Then run the gates from *Global Constraints*. Expected: all pass.

- [ ] **Step 7: Check that nothing else changed**

Run: `git status --short`
Expected: exactly `docs/way-of-working.md`, `docs/decisions.md`, `.claude/agents/po.md` and
`.claude/agents/team-lead.md` as modified.

- [ ] **Step 8: Commit**

Write the message to `/tmp/session-names-task-2-msg.txt` with the Write tool:

```text
process: the PO flow tells its sessions from other projects' (#53)

§8 and the agent files say when the PO and a team lead run scripts/sessions.py; D49 records the decision.

<the co-author trailer from the dispatch>
```

```bash
git add docs/way-of-working.md docs/decisions.md .claude/agents/po.md .claude/agents/team-lead.md
git commit -F /tmp/session-names-task-2-msg.txt
```

---

## After the tasks (the team lead, not a task)

- **The script, once for real, read-only:** from the issue worktree's root,
  `uv run python scripts/sessions.py running` and `uv run python scripts/sessions.py reachable po`. What
  they print is not copied into the PR (hard rule 3, §8 *Public text*); the PR says only that they ran and
  whether they agreed with the sessions the team lead knew of.
- **Learnings (§1 step 8):** the three deferred points (new names with a repo prefix, the PO's sends to
  `tl-<topic>`, the messages the PO receives) are proposed to the PO as one follow-up issue.
- **PR description:** a section "Proposed decisions, for the owner's review", with one row per choice, its
  alternatives and why: option A against B and C; and, each with the alternative "leave it out": the PO's
  `reachable po` check at its start and in each loop round, the new clause in `po.md`'s *Never* list, the
  re-send on any message from the PO, and the script printing no `cwd` or session id.
- **The merge of `origin/main`** (PR #103): conflicts are expected at the end of `docs/decisions.md` (D48
  before D49) and in §8's *After ready, the loop, and failures* (keep both texts).
- `visible: no`.
