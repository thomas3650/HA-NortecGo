"""Tests for the subagent guard hook's per-worktree allowlist."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "subagent_guard.py"
# Keep the owner's git config out of the test repos.
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(cwd: Path, *args: str) -> str:
    """Run git in cwd and return its output."""
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **GIT_ENV},
    )
    return result.stdout.strip()


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A main checkout with one commit, a linked worktree next to it, and a copy of the hook in the worktree."""
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    git(
        main,
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
    worktree = tmp_path / "wt"
    git(main, "worktree", "add", "-q", str(worktree), "-b", "topic")
    hook = worktree / ".claude" / "hooks" / "subagent_guard.py"
    hook.parent.mkdir(parents=True)
    shutil.copy(HOOK, hook)
    return main, worktree, hook


def allow(checkout: Path, *lines: str) -> None:
    """Write the allowlist of the worktree at checkout."""
    git_dir = Path(git(checkout, "rev-parse", "--absolute-git-dir"))
    (git_dir / "subagent-guard-allow").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def run_write(
    hook: Path,
    target: Path,
    cwd: Path,
    agent: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the hook on a Write of target, as a subagent unless agent is False.

    extra_env is set on the hook's environment only.
    """
    payload: dict[str, object] = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(target), "content": "x"},
        "cwd": str(cwd),
    }
    if agent:
        payload["agent_id"] = "agent-1"
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    return subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env={**env, **GIT_ENV, **(extra_env or {})},
    )


def run_bash(
    hook: Path, command: str, cwd: Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the hook on a subagent Bash call of command.

    extra_env is set on the hook's environment only.
    """
    payload: dict[str, object] = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
        "agent_id": "agent-1",
    }
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    return subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env={**env, **GIT_ENV, **(extra_env or {})},
    )


def test_nested_repo_allowlist_is_ignored(
    repos: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    """An allowlist in a nested repo that isn't this repository opens nothing."""
    main, _, hook = repos
    git_dir = tmp_path / "gd"
    subprocess.run(
        [
            "git",
            "init",
            "-q",
            "--separate-git-dir",
            str(git_dir),
            str(main / ".claude"),
        ],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **GIT_ENV},
    )
    target = main / ".claude" / "settings.json"
    (git_dir / "subagent-guard-allow").write_text(f"{target}\n", encoding="utf-8")
    result = run_write(hook, target, main)
    assert result.returncode == 2
    assert "not in this task's Guarded files" in result.stderr


def test_pre_commit_config_redirect_in_a_worktree(
    repos: tuple[Path, Path, Path],
) -> None:
    """A redirect onto a worktree's .pre-commit-config.yaml is refused."""
    _, worktree, hook = repos
    result = run_bash(
        hook, f"echo x > {worktree / '.pre-commit-config.yaml'}", worktree
    )
    assert result.returncode == 2
    assert "redirect writes to guarded path" in result.stderr


def test_worktree_edit_allowed_by_its_own_allowlist(
    repos: tuple[Path, Path, Path],
) -> None:
    """A guarded file in a worktree is allowed by that worktree's allowlist."""
    _, worktree, hook = repos
    target = worktree / ".claude" / "agents" / "po.md"
    target.parent.mkdir(parents=True)
    allow(worktree, str(target))
    result = run_write(hook, target, worktree)
    assert result.returncode == 0, result.stderr


def test_worktree_edit_refused_without_allowlist(
    repos: tuple[Path, Path, Path],
) -> None:
    """Without an allowlist the edit is refused as a guarded file, not as a guard error."""
    _, worktree, hook = repos
    target = worktree / ".claude" / "agents" / "po.md"
    target.parent.mkdir(parents=True)
    result = run_write(hook, target, worktree)
    assert result.returncode == 2
    assert "not in this task's Guarded files" in result.stderr


def test_main_allowlist_does_not_cover_a_worktree(
    repos: tuple[Path, Path, Path],
) -> None:
    """The main checkout's allowlist doesn't open files in another worktree."""
    main, worktree, hook = repos
    target = worktree / ".claude" / "agents" / "po.md"
    target.parent.mkdir(parents=True)
    allow(main, str(target))
    result = run_write(hook, target, worktree)
    assert result.returncode == 2
    assert "not in this task's Guarded files" in result.stderr


def test_relative_line_resolves_against_the_worktree(
    repos: tuple[Path, Path, Path],
) -> None:
    """A relative allowlist line is read from the worktree's top level, whatever the cwd."""
    main, worktree, hook = repos
    target = worktree / ".claude" / "agents" / "po.md"
    target.parent.mkdir(parents=True)
    allow(worktree, ".claude/agents/po.md")
    result = run_write(hook, target, main)
    assert result.returncode == 0, result.stderr


def test_main_checkout_uses_its_own_allowlist(repos: tuple[Path, Path, Path]) -> None:
    """The main checkout keeps working with .git/subagent-guard-allow."""
    main, _, hook = repos
    target = main / ".claude" / "settings.json"
    target.parent.mkdir(parents=True)
    allow(main, str(target))
    result = run_write(hook, target, main)
    assert result.returncode == 0, result.stderr


def test_pre_commit_config_guarded_in_a_worktree(
    repos: tuple[Path, Path, Path],
) -> None:
    """.pre-commit-config.yaml is guarded at a worktree's top level."""
    _, worktree, hook = repos
    result = run_write(hook, worktree / ".pre-commit-config.yaml", worktree)
    assert result.returncode == 2
    assert "not in this task's Guarded files" in result.stderr


def test_pre_commit_config_guarded_in_another_worktree(
    repos: tuple[Path, Path, Path],
) -> None:
    """.pre-commit-config.yaml is guarded at the top level of a worktree other than the hook's own."""
    main, _, hook = repos
    result = run_write(hook, main / ".pre-commit-config.yaml", main)
    assert result.returncode == 2
    assert "not in this task's Guarded files" in result.stderr


def test_pre_commit_config_name_elsewhere_not_guarded(
    repos: tuple[Path, Path, Path],
) -> None:
    """A file with that name below the top level is not guarded."""
    _, worktree, hook = repos
    (worktree / "docs").mkdir()
    result = run_write(hook, worktree / "docs" / ".pre-commit-config.yaml", worktree)
    assert result.returncode == 0, result.stderr


def test_new_directory_under_claude_judged_by_ancestor(
    repos: tuple[Path, Path, Path],
) -> None:
    """A Write that creates new directories is checked from its nearest existing ancestor."""
    _, worktree, hook = repos
    target = worktree / ".claude" / "new" / "deeper" / "file.md"
    allow(worktree, str(target))
    result = run_write(hook, target, worktree)
    assert result.returncode == 0, result.stderr


def test_main_thread_is_not_restricted(repos: tuple[Path, Path, Path]) -> None:
    """A call without agent_id (the main thread) is always allowed."""
    _, worktree, hook = repos
    result = run_write(
        hook, worktree / ".claude" / "settings.json", worktree, agent=False
    )
    assert result.returncode == 0, result.stderr


def load_hook() -> Any:
    """Import the hook as a module, for its constants and helpers."""
    spec = importlib.util.spec_from_file_location("subagent_guard", HOOK)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def decoy(tmp_path: Path) -> dict[str, str]:
    """Git location variables that point at a separate repository."""
    repo = tmp_path / "decoy"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git_dir = repo / ".git"
    return {
        "GIT_DIR": str(git_dir),
        "GIT_WORK_TREE": str(repo),
        "GIT_COMMON_DIR": str(git_dir),
    }


def test_git_location_variables_ignored_for_an_allowlisted_write(
    repos: tuple[Path, Path, Path], decoy: dict[str, str]
) -> None:
    """An allowlisted Write passes although GIT_DIR and friends point at another repository."""
    _, worktree, hook = repos
    target = worktree / ".claude" / "settings.json"
    allow(worktree, str(target))
    result = run_write(hook, target, worktree, extra_env=decoy)
    assert result.returncode == 0, result.stderr


def test_git_location_variables_cannot_widen_the_allowlist(
    repos: tuple[Path, Path, Path], decoy: dict[str, str]
) -> None:
    """Another repository's allowlist, reached through GIT_DIR, opens nothing."""
    _, worktree, hook = repos
    allow(worktree, str(worktree / ".claude" / "settings.json"))
    target = worktree / ".claude" / "other.md"
    # An absolute line: a relative one would resolve against the decoy's top level.
    Path(decoy["GIT_DIR"], "subagent-guard-allow").write_text(
        f"{target}\n", encoding="utf-8"
    )
    result = run_write(hook, target, worktree, extra_env=decoy)
    assert result.returncode == 2
    assert "not in this task's Guarded files" in result.stderr


def test_guard_ignores_every_git_local_env_var() -> None:
    """The hook's list covers every repository-location variable the installed git knows."""
    printed = subprocess.run(
        ["git", "rev-parse", "--local-env-vars"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert printed
    assert set(printed) <= load_hook().GIT_LOCAL_ENV_VARS


def test_git_env_keeps_other_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    """git_env() drops the location variables and keeps the rest, the config switches included."""
    monkeypatch.setenv("GIT_DIR", "/nowhere")
    monkeypatch.setenv("GIT_WORK_TREE", "/nowhere")
    monkeypatch.setenv("GIT_COMMON_DIR", "/nowhere")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    env = load_hook().git_env()
    assert "GIT_DIR" not in env
    assert "GIT_WORK_TREE" not in env
    assert "GIT_COMMON_DIR" not in env
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
