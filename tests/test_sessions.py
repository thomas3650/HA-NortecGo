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
        self.other = make_repo(tmp_path / "repo-other")
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
    main_sub = world.ours / "docs"
    main_sub.mkdir()
    worktree_sub = world.worktree / "docs"
    worktree_sub.mkdir()
    rows = [
        row("in-main", world.ours, 1),
        row("in-worktree", world.worktree, 2),
        row("in-main-subdirectory", main_sub, 3),
        row("in-worktree-subdirectory", worktree_sub, 4),
        row("through-symlink", world.link, 5),
    ]
    assert sessions.running(rows, anchor=world.ours) == [
        "in-main",
        "in-main-subdirectory",
        "in-worktree",
        "in-worktree-subdirectory",
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
