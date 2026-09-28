# Agent orchestration: a PO agent with team leads and workers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** A PO agent session runs the backlog through up to 2 background team-lead sessions, each running the existing flow with up to 3 workers; the owner answers escalations and merges.

**Architecture:** Two new session agents (`po`, `team-lead`) that point to a new *PO flow* section in `way-of-working.md`, which holds the process. The guard hook learns per-worktree allowlists, so team leads (and their task worktrees) can run guarded tasks. Task 1 first confirms the CLI and tool behaviours the design relies on; if one fails, the plan stops.

**Tech Stack:** Claude Code CLI (`claude --bg`, `--agent`, `--resume`, `claude agents`), `SendMessage`/`ListAgents`, Claude in Chrome, Python 3.14 stdlib (the hook), pytest, `gh`.

**Spec:** the comment https://github.com/thomas3650/HA-NortecGo/issues/50#issuecomment-5877369877 on #50 (revision 4, approved by the owner on 2026-09-28; the owner ruled that this one spec lives on the issue). Read it with `gh api repos/thomas3650/HA-NortecGo/issues/comments/5877369877 --jq .body`.

## Global Constraints

- Hard rules 1 to 9 in `CLAUDE.md` are unchanged. Nothing private (hard rule 3) in any file, commit message, PR text or issue comment.
- Roles: 1 PO (Opus / high), at most **2** team leads (Opus / medium), at most **3** workers active per team lead. The PO never merges; the owner merges.
- The PO escalates below 90% certainty, and always for the 5 cases in spec §5.
- Screenshots go in `local/screenshots/<topic>/` (hard rule 5 as it stands); agents write them there and never read them back.
- New decision entry: **D35** (D34 is taken by the unmerged `feat/pynortecgo-0.5.0` branch; the controller re-checks `origin/main` and open PR branches before Task 4 and adjusts the number if needed).
- Subagents write commit messages with the Write tool to a file outside the repo and commit with `git commit -F <file>` (no heredocs). End each message with the co-author trailer given in the dispatch.
- Gates before every commit (`CLAUDE.md` → Commands). `CHANGELOG.md` is not changed: nothing here is user-visible.
- The owner's spec choices are fixed; a task that finds one can't work reports BLOCKED rather than redesigning.

## Review Focus

1. A guarded edit in a linked worktree with that worktree's allowlist must be allowed, and without it refused with the normal "not in this task's Guarded files" text, never a "guard error" (Task 2 tests `test_worktree_edit_allowed_by_its_own_allowlist`, `test_worktree_edit_refused_without_allowlist`).
2. The main checkout's allowlist must not open files in another worktree (Task 2 test `test_main_allowlist_does_not_cover_a_worktree`).
3. `.pre-commit-config.yaml` must stay guarded at a worktree's top level, and a file with that name deeper down must not be (Task 2 tests `test_pre_commit_config_guarded_in_a_worktree`, `test_pre_commit_config_guarded_in_another_worktree`, `test_pre_commit_config_name_elsewhere_not_guarded`).
4. A Write that creates a new directory under `.claude/` must be judged by its nearest existing ancestor, not fail as a guard error (Task 2 test `test_new_directory_under_claude_judged_by_ancestor`).
5. The agent files and the new section must never tell an agent to merge, click a charge control, type credentials, or read `local/`, `config/` or `.env` (Task 3 and Task 4 self-checks, grep steps).

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (confirm CLI and tool behaviours) | Run by the controller, in the main checkout, with the owner. Stop point if a check fails |
| 2 | Task 2 (guard hook, per-worktree allowlist) | Guarded: its own wave, in the main checkout (today's rule, which this task retires) |
| 3 | Task 3 (agent files `po.md`, `team-lead.md`, `full-reviewer.md`) | Guarded: its own wave, in the main checkout |
| 4 | Task 4 (way-of-working, decisions, CLAUDE.md) | Written against the findings of Task 1 and the names Tasks 2 and 3 fix |

Rulings for the PR description (way-of-working §3): Task 1 is run by the controller with the owner, with no
implementer or task-reviewer; Task 2's tests run the hook as a subprocess instead of the spec's `importlib`.

After the merge, the rollout (spec §11) is the owner's: 1 PO and 1 team lead on a small `v3` issue, then 2.

---

### Task 1: Confirm the CLI and tool behaviours (spec §12)

**Model:** none — the controller runs it, with the owner, because it starts Claude sessions, uses Chrome and needs the owner's OK on the permission approach. No implementer, no task-reviewer (a ruling for the PR description).
**Wave:** 1

**Files:**
- Findings go in one comment on #50, and in the PR description.
- Only if the owner approves allow rules as the permission approach (Step 5): `.claude/settings.json`, edited by the controller with the owner's OK (way-of-working §6), in its own commit `process: permissions for background team leads (#50)`, which the branch review sees. Otherwise no repo file changes.

**Interfaces:**
- Produces, for Tasks 3 and 4 (the controller passes them in the dispatch as rulings):
  - `START_COMMAND`: the exact command the PO uses to start a team lead, including the permission approach the owner approved;
  - `RESUME_COMMAND`, `STOP_COMMAND`, `LOGS_COMMAND`, `LIST_COMMAND`: the exact forms that worked;
  - `PO_RESTART`: that a fresh `claude --agent po` receives messages sent while no PO ran (or the owner's ruling, Step 7);
  - `HA_RUN`: how the PO keeps HA running during the visual check and stops it, or `owner-fallback` (spec §12.7);
  - `SCREENSHOT_SAVE`: how a screenshot is saved to disk;
  - any owner ruling from Step 7 that changes Task 3 or Task 4.

The `po` and `team-lead` agents are only created in Task 3, so this task uses throwaway **stand-ins** with those names, defined inline with the CLI's `--agents` option, never as files in the repo. The JSON object lives in `<scratchpad>/standins.json`; `--agents` takes the JSON itself for interactive and `--bg` sessions (a file path only with `--print`), so it is passed as `--agents "$(cat <scratchpad>/standins.json)"`. Each stand-in has a one-line `description`, the `prompt` "Probe stand-in: follow the prompt you are given; change nothing in the repo", `model` and `effort` (`po`: opus, high; `team-lead`: opus, medium) and no `tools` restriction (so they have the Agent tool). Step 2 records whether the inline `effort` field is accepted; if it isn't, the stand-ins still serve every other check. If `claude --help` shows no way to define agents inline, ask the owner before using user-level agent files instead.

Throwaway material goes in the scratchpad or a temporary directory, never in the repo. No step starts or stops a charge; no step reads `.env`, `local/` or `config/`. Findings use `<id>` for session ids, never the real ones.

- [ ] **Step 1: Background session with an agent (§12.1, §12.2).** Create a throwaway worktree `../HA-NortecGo-wt/probe` on a throwaway branch `wt/probe` from `origin/main`. From there, start `claude --bg --agent implementer "Report your model, your cwd and the value of CLAUDE_PROJECT_DIR, then stop. Change nothing."` (`implementer` is Sonnet / medium, unlike the Opus default, so the model shows whether the agent's frontmatter applies). Expected: an id is printed; `claude agents` lists it; `claude logs <id>` shows Sonnet, and cwd and `CLAUDE_PROJECT_DIR` both the probe worktree. Effort: record it from `claude agents` or `claude logs` if either shows it; if neither does, record "effort unverified". Record the exact commands.
- [ ] **Step 2: Messages and listing (§12.3, §12.4).** Start a probe `--bg` session in the probe worktree whose prompt is "Wait for a message, reply `pong` to its sender, then wait again. Change nothing." From the controller: `ListAgents` shows it; `SendMessage` "ping"; a `pong` arrives. Then ask the owner to open `claude --agent team-lead --agents "$(cat <scratchpad>/standins.json)"` in the foreground **in the main checkout**, with the prompt "Probe only: do nothing until told." Check that the controller's `ListAgents` shows it. Record the names `ListAgents` prints. The owner closes it afterwards.
- [ ] **Step 3: Stop and resume (§12.5, §12.6).** Stop the probe with the stop command from `claude --help` / `claude agents --help`; `claude agents` no longer lists it as running. Remove the probe worktree, re-create it at the same path, and resume with `claude --bg --resume <id>`; ask it what its last reply was. Expected: `pong`. Record the commands.
- [ ] **Step 4: Messages to a PO that is down (§12.3).** Ask the owner to open `claude --agent po --agents "$(cat <scratchpad>/standins.json)"` in the main checkout with the prompt "Probe only: don't start the loop; report any message you receive." Have the probe `SendMessage` it once; the owner closes it before it answers; the probe sends a second message while no PO runs; the owner starts a **fresh** `claude --agent po --agents "$(cat <scratchpad>/standins.json)"` with the same prompt. Record which messages the fresh session receives (`PO_RESTART`).
- [ ] **Step 5: Permissions (§12.9).** Propose to the owner, as a question, a permission approach for background team leads (a `--permission-mode` value from `claude --help`, and/or allow rules in `.claude/settings.json`). With the owner's OK (and, for allow rules, the controller's edit in its own commit), start a probe as `claude --bg --agent team-lead --agents "$(cat <scratchpad>/standins.json)"` plus the approach, in the probe worktree, and have it, with no prompt at any point:
  - commit on `wt/probe` (the pre-commit hooks must run);
  - `git push --dry-run origin HEAD:main` (must be denied);
  - `git commit --no-verify` (must be denied);
  - write a line to `$(git rev-parse --absolute-git-dir)/subagent-guard-allow` (outside its project dir);
  - `git worktree add <HA-NortecGo-wt>/probe-task-1 -b wt/probe-task-1 wt/probe` (a sibling of its worktree);
  - dispatch an `implementer` subagent that tries a Write to `<HA-NortecGo-wt>/probe-task-1/.claude/x.md` with no allowlist line for it (must be refused by the guard hook: this shows a `--bg --agent` session can dispatch subagents, and that they carry `agent_id`), and a Write to `<HA-NortecGo-wt>/probe-task-1/docs/probe.md` (must succeed without a prompt).
  Record the approach and each result. Before Task 2 lands, the refusal reads `guard error (NotADirectoryError ...)`: that still counts as refused, and shows the hook ran for the subagent (so it carries `agent_id`).
- [ ] **Step 6: HA and Chrome (§12.7, §12.8).** Stop any dev HA first. Try `scripts/develop` with the Bash tool's `run_in_background`; check that `http://localhost:8123` answers and that HA doesn't crash within 2 minutes; open it in a new Chrome tab (owner's existing login); save one screenshot of the Settings page (no charger page) to `local/screenshots/probe/` if a Chrome tool can; confirm it exists without reading it (`test -s local/screenshots/probe/<file> && echo saved`); stop HA (`pkill -f "hass -c config"`). Record `HA_RUN` and `SCREENSHOT_SAVE`.
- [ ] **Step 7: Clean up and decide.** Stop all probe sessions; remove the probe worktrees, the `wt/probe*` branches and the stand-in definitions. Post the findings (commands and results only, `<id>` for ids; no real-instance data, spec §5) as a comment on #50. If any §12 item other than §12.7 failed, **stop**: the design goes back to the owner, who rules (the controller may propose a fallback; for example, team leads re-send an unanswered message when a restarted PO says `hello`). A failed §12.7 uses the spec's fallback: `HA_RUN` = `owner-fallback`. A ruling that changes `po.md` or `team-lead.md` goes into Task 3's dispatch; one that changes §8 into Task 4's.

---

### Task 2: Per-worktree allowlist in the guard hook

**Model:** sonnet
**Wave:** 2
**Guarded files:** `.claude/hooks/subagent_guard.py` — the hook itself is what this task fixes.

**Files:**
- Modify: `.claude/hooks/subagent_guard.py` (docstring, constants, `is_guarded`, `allowlist`, `check_file`; two new helpers)
- Create: `tests/test_subagent_guard.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the allowlist of a guarded target is `<absolute git dir of the worktree holding the target>/subagent-guard-allow`; relative lines resolve against that worktree's top level. Helpers `nearest_existing_dir(resolved: str) -> str` and `worktree_of(resolved: str) -> tuple[str, Path] | None`; `allowlist(target: str) -> set[str]`. `ALLOW_FILE` is replaced by `ALLOW_NAME = "subagent-guard-allow"`.

Notes:
- The spec says the tests load the hook with `importlib`. This plan runs the hook as a subprocess instead, the way Claude Code runs it: it tests the real entry point, and avoids typing a module loaded from a non-package under mypy strict (a ruling for the PR description).
- The tests copy the hook into the test worktree and run that copy, so the hook's `ROOT` is a linked worktree, as it is for a team lead. That shows today's bug (`NotADirectoryError` → "guard error") failing first, and keeps the tests independent of this repo's own allowlist.
- **The hook you edit judges your own edits** (it is this repo's PreToolUse hook), so every intermediate state must keep working. Make the edits in the order of Step 3; don't reorder them.
- Known limit, unchanged: on a case-sensitive volume the casefolded paths (macOS) may miss; the repo lives on the default case-insensitive APFS.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_subagent_guard.py`:

```python
"""Tests for the subagent guard hook's per-worktree allowlist."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

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
    hook: Path, target: Path, cwd: Path, agent: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run the hook on a Write of target, as a subagent unless agent is False."""
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
        env={**env, **GIT_ENV},
    )


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
```

Run `uv run ruff format tests/test_subagent_guard.py` once after writing it; the formatter may rewrap a few lines.

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_subagent_guard.py -v`
Expected: 8 FAIL — `test_pre_commit_config_guarded_in_another_worktree` (exit 0: today only the hook's own `ROOT` guards the file), and `test_worktree_edit_allowed_by_its_own_allowlist`, `test_worktree_edit_refused_without_allowlist`, `test_main_allowlist_does_not_cover_a_worktree`, `test_relative_line_resolves_against_the_worktree`, `test_main_checkout_uses_its_own_allowlist`, `test_pre_commit_config_guarded_in_a_worktree`, `test_new_directory_under_claude_judged_by_ancestor`, each with `guard error (NotADirectoryError ...)` in stderr (the copied hook's `ROOT` is the linked worktree, whose `.git` is a file). 2 PASS: `test_pre_commit_config_name_elsewhere_not_guarded`, `test_main_thread_is_not_restricted`.

- [ ] **Step 3: Implement, in this order (each edit leaves the hook working)**

In `.claude/hooks/subagent_guard.py`:

a) In the module docstring, add to the end of the paragraph that starts `Design: copied from the NortecGo repo`:

```text
The allowlist is per worktree: ``<git dir>/subagent-guard-allow`` of the worktree the target file is in
(``git rev-parse --absolute-git-dir``); relative lines resolve against that worktree's top level.
```

b) Add `import subprocess` after `import shlex`. After the line `ALLOW_FILE = ROOT / ".git" / "subagent-guard-allow"` (keep that line for now), add:

```python
ALLOW_NAME = "subagent-guard-allow"
PRE_COMMIT_CONFIG = ".pre-commit-config.yaml"
```

c) Replace `is_guarded` with these three functions (where `is_guarded` is now):

```python
def nearest_existing_dir(resolved: str) -> str:
    """The target's directory, or its nearest ancestor that exists (a Write may create directories)."""
    path = Path(resolved)
    candidate = path if path.is_dir() else path.parent
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return str(candidate)


def worktree_of(resolved: str) -> tuple[str, Path] | None:
    """The top level (normalized) and absolute git dir of the worktree holding the target, or None."""
    result = subprocess.run(
        [
            "git",
            "-C",
            nearest_existing_dir(resolved),
            "rev-parse",
            "--show-toplevel",
            "--absolute-git-dir",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    lines = result.stdout.splitlines()
    if result.returncode != 0 or len(lines) != 2:
        return None
    return norm(lines[0]), Path(lines[1])


def is_guarded(resolved: str) -> bool:
    if GUARDED_PARTS.intersection(Path(resolved).parts):
        return True
    if Path(resolved).name != PRE_COMMIT_CONFIG:
        return False
    if resolved == norm(str(ROOT / PRE_COMMIT_CONFIG)):
        return True
    worktree = worktree_of(resolved)
    return worktree is not None and norm(str(Path(resolved).parent)) == worktree[0]
```

d) In **one Edit** that spans from `def allowlist() -> set[str]:` through the line `    if target not in allowlist():` in `check_file` (so `check_root` and the start of `check_file` are inside the edited text, unchanged), replace `allowlist` with the version below and change that last line to `    if target not in allowlist(target):`:

```python
def allowlist(target: str) -> set[str]:
    """The Guarded files of the task running in the worktree that holds the target."""
    worktree = worktree_of(target)
    if worktree is None:
        return set()
    top, git_dir = worktree
    try:
        lines = (git_dir / ALLOW_NAME).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return set()
    return {resolve(line.strip(), top) for line in lines if line.strip()}
```

e) Last, delete the line `ALLOW_FILE = ROOT / ".git" / "subagent-guard-allow"`, and run `grep -n ALLOW_FILE .claude/hooks/subagent_guard.py` (expected: no hits).

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_subagent_guard.py -v`
Expected: all 10 PASS.

- [ ] **Step 5: Check the hook still works on this repo**

Run: `printf '%s' '{"agent_id":"a","tool_name":"Write","tool_input":{"file_path":"'"$PWD"'/.claude/agents/x.md"},"cwd":"'"$PWD"'"}' | python3 .claude/hooks/subagent_guard.py; echo "exit $?"`
Expected: `subagent-guard: .../.claude/agents/x.md is a guarded file and is not in this task's Guarded files. Report BLOCKED to the controller.` and `exit 2`. (While this task runs, the allowlist holds only `.claude/hooks/subagent_guard.py`.)

- [ ] **Step 6: Gates and commit**

Run: `uv run pytest -q`, `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`, `uv run ruff check && uv run ruff format --check && uv run mypy`. All pass.

Commit `.claude/hooks/subagent_guard.py` and `tests/test_subagent_guard.py` with the message `process: per-worktree allowlist in the subagent guard (#50)` plus the trailer.

---

### Task 3: The `po` and `team-lead` agent files

**Model:** opus — a docs task (D33), and it sets the safety rules for two autonomous roles.
**Wave:** 3
**Guarded files:** `.claude/agents/po.md`, `.claude/agents/team-lead.md`, `.claude/agents/full-reviewer.md`

**Files:**
- Create: `.claude/agents/po.md`
- Create: `.claude/agents/team-lead.md`
- Modify: `.claude/agents/full-reviewer.md` (the plan check's guarded-task rule)

**Interfaces:**
- Consumes: Task 1's `LIST_COMMAND` and any owner ruling from Task 1 Step 7 that changes these files (in the dispatch, as rulings); Task 2's allowlist location.
- Produces: the agent names `po` and `team-lead`; they point to `docs/way-of-working.md` §8 *PO flow* (written in Task 4) and to its message names `hello`, `question`, `spec ready`, `plan ready`, `need D-number`, `blocked`, `branch ready`.

The files are short: the process lives in `way-of-working.md` §8 (no duplication, §7). They hold the role, the start steps, and the "never" list. No `tools:` line, so both sessions have every tool.

- [ ] **Step 1: Write `.claude/agents/po.md`**

```markdown
---
name: po
description: The PO session for PO mode, started by the owner with `claude --agent po` in the main checkout. Picks issues, runs up to 2 team leads, approves their specs and plans, and makes PRs ready; the owner merges.
model: opus
effort: high
---

You are the PO (product owner) of the HA-NortecGo repo (the public Home Assistant custom integration for
Nortec Go, installed via HACS). You run the backlog through team leads, and the owner merges. The process is
`docs/way-of-working.md` §8 *PO flow*: read it at the start of every session and follow it. The project rules
in `CLAUDE.md` apply and are already in your context.

## At the start of a session
1. Read `docs/way-of-working.md` §8, and `.git/po-sessions.json` if it exists.
2. Run `ListAgents`. If a `team-lead` session runs whose name isn't in `.git/po-sessions.json`, the owner is
   in team lead mode: say so and do nothing else.
3. Rebuild the picture: <LIST_COMMAND>, `gh issue list --label active`, `gh pr list`.
4. Start the loop with `/loop` (self-paced, 10 to 20 minutes between checks).

## Never
- Merge a PR, force-push, tag a release, or change GitHub settings.
- Bypass hooks (`--no-verify`, `-n`, `SKIP=`).
- Read `.env`, or anything under `local/` or `config/`. You write screenshots to `local/screenshots/<topic>/`
  and never open them again.
- In Home Assistant: click the Charge switch, a start or stop button, or anything else that calls an action
  on the charger; type credentials; run the config flow or reauth.
- Edit `.claude/settings.json` without the owner's OK each time.
- Post real-instance data on GitHub or in a commit message (§8 *Public text*).
- Start or stop a real charge.
- Start or resume a team lead while the main checkout is detached.
- Run more than 2 team leads.
```

Replace `<LIST_COMMAND>` with the exact command from Task 1 before writing the file, and apply any Task 1 ruling for this file. If Task 1 gave `HA_RUN` = `owner-fallback`, nothing in this file changes (§8 holds the fallback).

- [ ] **Step 2: Write `.claude/agents/team-lead.md`**

```markdown
---
name: team-lead
description: A team lead for one issue. Runs the way-of-working §1 flow from brainstorm to branch review. Started by the PO in the background (PO mode), or by the owner in the foreground (team lead mode).
model: opus
effort: medium
---

You are a team lead in the HA-NortecGo repo (the public Home Assistant custom integration for Nortec Go,
installed via HACS). You take one issue from brainstorm to branch review with the flow in
`docs/way-of-working.md` §1 and §2, as the controller. The project rules in `CLAUDE.md` apply and are already
in your context.

## Your mode
- **PO mode:** your start prompt names a PO session, an issue, a branch and a worktree. Work only in that
  worktree. Your first message to the PO is `hello` with the issue number. From then on you talk only to the
  PO, with `SendMessage` and the message names in `docs/way-of-working.md` §8: `question`, `spec ready`,
  `plan ready`, `need D-number`, `blocked`, `branch ready`. The PO takes the owner's place in §1 steps 3 to 8;
  step 10 is the PO's.
- **Team lead mode:** your start prompt names no PO. You run in the main checkout; the owner is the PO and you
  ask the owner in the terminal. Step 10 is yours, as it is the controller's today.

## Workers
At most 3 workers (subagents) active at once; split a wider wave. For a task with a `Guarded files:` line,
write the paths to `$(git -C <the task's worktree> rev-parse --absolute-git-dir)/subagent-guard-allow`, and
empty it however the task ends.

## Never
- Merge a PR, force-push, tag a release, or change GitHub settings.
- Bypass hooks (`--no-verify`, `-n`, `SKIP=`).
- Read `.env`, or anything under `local/` or `config/`.
- Edit `.claude/settings.json`.
- Start or stop a real charge.
- In PO mode: run `gh pr ready`, `scripts/smoke` or `scripts/develop`; take a D-number without asking the PO;
  ask the owner directly.
```

- [ ] **Step 3: `full-reviewer.md`**

In `.claude/agents/full-reviewer.md`, the plan check says "a task with `Guarded files:` sits alone in its wave (`docs/way-of-working.md` → Parallel waves)". Replace that clause (it wraps over two lines) with: "a task with `Guarded files:` follows `docs/way-of-working.md` §1 step 7 (the allowlist of the worktree it runs in)". Keep the line wrap under 110 characters.

- [ ] **Step 4: Self-check**

Run: `grep -n "<[A-Z_]*>" .claude/agents/po.md .claude/agents/team-lead.md` — expected: no hits.
Run: `grep -n -i "merge\|local/\|config/\|\.env\|credential\|charge" .claude/agents/po.md .claude/agents/team-lead.md`
Expected: every hit is in a "Never" line, or is `local/screenshots/` (written, never read), or is the description's "the owner merges". No line tells an agent to do any of these.

- [ ] **Step 5: Gates and commit**

Run the gates (`CLAUDE.md` → Commands). Commit the three files with the message `process: po and team-lead agents (#50)` plus the trailer.

---

### Task 4: The PO flow in the docs

**Model:** opus — a docs task (D33).
**Wave:** 4

**Files:**
- Modify: `docs/way-of-working.md` (§1 step 7, §1 *Parallel waves*, §5 table, §6 three lines, new §8)
- Modify: `docs/decisions.md` (new D35, D16 status)
- Modify: `CLAUDE.md` (*Layout* `.claude/` line, *Commands*)

**Interfaces:**
- Consumes: Task 1's findings (commands, `HA_RUN`, `SCREENSHOT_SAVE`, whether a message to a down PO is delivered, whether `ListAgents` shows foreground sessions) as rulings in the dispatch; Task 2's allowlist location; Task 3's agent names and message names.
- Produces: `docs/way-of-working.md` §8 *PO flow*, which the agent files point to.

- [ ] **Step 1: `way-of-working.md` §1 step 7**

Replace the bullet `- write the task's \`Guarded files:\` paths, if any, to \`.git/subagent-guard-allow\`;` with:

```text
   - write the task's `Guarded files:` paths, if any, to the allowlist of the worktree the task runs in:
     `$(git -C <worktree> rev-parse --absolute-git-dir)/subagent-guard-allow` (in the main checkout, that is
     `.git/subagent-guard-allow`);
```

And in step 7's last bullet, `empty \`.git/subagent-guard-allow\`` becomes `empty that allowlist`.

- [ ] **Step 2: `way-of-working.md` §1 *Parallel waves***

Replace the bullet that starts `- A task with a \`Guarded files:\` line gets a wave of its own` (and ends `(a known limit of the guard hook).`) with:

```text
- A task with a `Guarded files:` line may run in any worktree: the guard hook reads the allowlist of the
  worktree the edited file is in (§1 step 7). One known limit stays: the hook's whole-tree revert check
  compares against the main checkout only, so a revert of a task worktree isn't caught.
```

Leave the *Starting ahead of inputs* bullet "never has a `Guarded files:` line" as it is. In the bullet "The controller runs the SDD scripts … from the main checkout", add at the end: `For a team lead in the PO flow (§8), "the main checkout" here is its issue worktree.` After the sentence "A subagent's shell starts in the main checkout." add: `(For a team lead in the PO flow, its issue worktree.)`

- [ ] **Step 3: `way-of-working.md` §5 table**

Add two rows after the `Controller (main session)` row:

```text
| PO (PO flow, §8) | Opus / high |
| Team lead (PO flow, §8) | Opus / medium |
```

- [ ] **Step 4: `way-of-working.md` §6**

- Replace `- **Merging and pushing:** the owner merges. Only the controller pushes or marks a PR ready.` with `- **Merging and pushing:** the owner merges. Only the controller pushes or marks a PR ready; in the PO flow (§8) the team lead pushes and the PO marks ready.`
- Replace `- **Questions to the owner:** plain terminal text, one at a time.` with `- **Questions to the owner:** plain terminal text, one at a time. In the PO flow, the PO also posts them on the issue (§8).`
- Replace `- **Delegated plan approval:** the owner may let the controller approve a plan once \`full-reviewer\` rates it Ready; the spec always needs the owner's approval.` with `- **Delegated plan approval:** the owner may let the controller approve a plan once \`full-reviewer\` rates it Ready; the spec always needs the owner's approval, except in the PO flow, where the PO approves both (D35).`

- [ ] **Step 5: `way-of-working.md` new §8**

Append after §7:

```markdown
## 8. PO flow

An alternative to running the flow yourself: a PO session runs the backlog through team leads, and the owner
answers escalations and merges (D35). The agent files `.claude/agents/po.md` and `team-lead.md` point here.

### Roles and start modes

- **PO:** `claude --agent po`, interactive, in the main checkout. Picks issues, starts and resumes team leads,
  answers their questions or escalates, approves specs and plans, hands out D-numbers, runs step 10's checks
  and marks PRs ready. Never merges.
- **Team lead:** a background session per issue, in its own issue worktree, started by the PO; at most 2.
  Runs §1 steps 3 to 9 as the controller, with the PO in the owner's place.
- **Workers:** the team lead's subagents, as in §2; at most 3 active per team lead.
- **Team lead mode**, for hard problems: the owner runs `claude --agent team-lead` in the foreground in the
  main checkout, with no PO named, and is the PO. **PO mode and team lead mode never run at the same time.**
- Owner only: merging, anything that starts or stops a real charge, the permission setup for team leads, and
  `.claude/settings.json`.

### Picking and starting an issue

When fewer than 2 team leads run, the PO picks an open issue without `active`: all `v1` first, then `v2`,
then `v3`, the most important first within a label. It skips issues without an urgency label, issues in the
same area as one in progress, and issues that depend on an unfinished one. Then it:
1. runs `git fetch`, labels the issue `active`, creates `<type>/<topic>` from `origin/main` and the issue
   worktree `../HA-NortecGo-wt/<topic>`, and runs `uv sync` there (never `pre-commit install`);
2. starts the team lead there with <START_COMMAND>, naming itself, the issue, the branch and the worktree;
3. records the session id, issue, branch and worktree in `.git/po-sessions.json`, and comments on the issue
   that a team lead has picked it up.

A team lead's task worktrees go next to its issue worktree: `<HA-NortecGo-wt>/<topic>-task-<n>`.

### Messages

The team lead talks only to the PO, with `SendMessage`:

| Message | The PO |
|---|---|
| `hello` (first message, with the issue number) | Records its `ListAgents` name in `.git/po-sessions.json`. |
| `question` | Answers, or escalates; the team lead waits for the answer. |
| `spec ready` / `plan ready`, with the `full-reviewer` verdict | Approves or sends back with points; records the approval as an issue comment. |
| `need D-number` | Gives the next number not used on `origin/main`, on an open PR's branch, or already handed out (kept in `.git/po-sessions.json`). |
| `blocked` | Decides, or escalates. |
| `branch ready`, with `visible: yes/no` (proposed; the PO decides) | Runs *From branch ready to PR ready*. |

### Escalation

The PO escalates when it is less than 90% sure, and always for: anything near starting or stopping a charge,
or auth, tokens and reauth; a new decision or a change to a hard rule; changes to `.claude/`,
`.pre-commit-config.yaml` or `.github/workflows/`; a ruling after 5 review rounds (§3); anything that would
file an issue on the client repo.

It posts the question as an issue comment starting with `**PO question:**`, and asks the same in the terminal,
one at a time (the rest wait in a queue; on the issues they can all be up). The first answer counts; an
answer given in the terminal is copied to the issue. If the two places give different answers, the PO asks
again.

**Public text:** issue comments, PR descriptions, review comments and commit messages follow hard rule 3 and
hold no real-instance data: no smoke log lines, no values or states seen in HA, no screenshots. The visual
check is reported by what it covered, not what it saw; a defect is described in the code's terms.

### From branch ready to PR ready

One branch at a time, in the main checkout (only the PO works there, and only one Home Assistant runs):
1. The main checkout must be clean; if not, escalate. `git fetch`, `git switch --detach origin/<branch>`,
   `uv sync`. While detached, the PO starts and resumes no team leads.
2. `scripts/smoke`. A failure that comes from the shared `config/` (for example a store version another
   branch left) is escalated, not sent back.
3. **Visual check**, when the change is visible in HA (entities, names, icons, units, the options flow,
   translations, the device page): <HA_RUN>, a new Chrome tab on `http://localhost:8123` with the owner's
   existing login, checked against the spec, screenshots to `local/screenshots/<topic>/` (<SCREENSHOT_SAVE>),
   then HA stopped. Never the config flow or reauth, never credentials, never anything that calls an action on
   the charger. The screenshots are for the owner, who also cleans them up.
4. **Acceptance check:** the PR against the issue's user story and the approved spec, and the PR description
   (rulings, learnings, smoke result, which parts the visual check covered, and that the screenshots are in
   `local/screenshots/<topic>/`). Not a second code review.
5. Switch back to the branch the main checkout was on, and `uv sync`.
6. On a failure: back to the team lead with the finding. Otherwise: update the PR description, `gh pr ready`,
   tell the owner, stop the team lead (<STOP_COMMAND>), and remove its worktrees (`git worktree remove
   --force`: they hold `.venv` and `.superpowers/sdd/`) and `wt/` branches. The SDD workspace goes with them;
   the rulings are in the PR description.

### After ready, the loop, and failures

- A ready PR takes no slot. On changes requested or a merge conflict, the PO re-creates the issue worktree at
  the same path and resumes the team lead (<RESUME_COMMAND>) when a slot is free. Conflicts are fixed by
  merging `origin/main` in, never by a force-push. A resumed team lead starts without its old SDD ledger.
- The PO's `/loop` (every 10 to 20 minutes) checks GitHub for merged PRs (remove `active` if still there, pick
  the next issue), answers to open `PO question`s, and review comments or conflicts on ready PRs.
- **State:** GitHub is the source of truth; `.git/po-sessions.json` maps each team lead's session id and
  `ListAgents` name to its issue, branch and worktree, and holds the D-numbers handed out. <LIST_COMMAND>
  shows the background sessions; `ListAgents` the names to message.
- A team lead that is gone is resumed once; if that fails, the PO escalates and leaves the issue `active`.
  One with nothing new in <LOGS_COMMAND> for 2 loops is asked for its status, then escalated.
- If the PO session ends, team leads keep running and their messages wait; the next
  `claude --agent po` rebuilds its state from the above and carries on.
```

Before writing, replace each `<...>` with Task 1's finding: `<START_COMMAND>`, `<RESUME_COMMAND>`, `<STOP_COMMAND>`, `<LOGS_COMMAND>`, `<LIST_COMMAND>` with the exact commands in backticks; `<HA_RUN>` with how HA was run, or, for `owner-fallback`, rewrite step 3 so the PO lists what to look at as a `PO question` and the owner checks; `<SCREENSHOT_SAVE>` with how. Apply every owner ruling from Task 1 Step 7 that the dispatch gives for §8 (for example on messages to a PO that is down, or on seeing a foreground team lead); make no other change to the design.

- [ ] **Step 6: `decisions.md`**

In D16, change `**Status:** active` to `**Status:** active; the spec approval superseded by D35 for the PO flow`.

Append:

```markdown
### D35: The PO flow
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** Besides the direct flow (§1), the owner can start a PO session that runs up to 2 team
  leads (each with up to 3 workers). In that flow the PO answers brainstorm questions and approves specs and
  plans in the owner's place, escalating below 90% certainty and always for a fixed list; the owner still
  merges.
- **Why:** Several issues move forward in parallel while the owner only answers escalations and merges.
- **Source:** spec comment on #50 (https://github.com/thomas3650/HA-NortecGo/issues/50#issuecomment-5877369877)
```

Use the D-number the controller gives in the dispatch if it isn't D35, everywhere in this task (steps 4 and 6).

- [ ] **Step 7: `CLAUDE.md`**

- In *Layout*, change `agents (\`implementer\`, \`task-reviewer\`, \`full-reviewer\`)` to `agents (\`implementer\`, \`task-reviewer\`, \`full-reviewer\`, and the session agents \`po\` and \`team-lead\`)`.
- In *Commands*, add after the `scripts/smoke` line:

```text
claude --agent po                # PO mode: the PO runs the backlog through team leads (docs/way-of-working.md §8)
claude --agent team-lead         # team lead mode, for hard problems; never while a PO runs
```

- [ ] **Step 8: Self-check**

Run: `grep -n "<[A-Z_]*>" docs/way-of-working.md` — expected: no hits (every placeholder replaced).
Run: `grep -n "subagent-guard-allow" docs/way-of-working.md` — expected: only the step 7 lines from Step 1.
Read §8 once against the spec (sections 2 to 8): every rule there has a line here, and nothing contradicts §1 to §7.

- [ ] **Step 9: Gates and commit**

Run the gates (`CLAUDE.md` → Commands; `pre-commit` reformats Python blocks in Markdown, and there are none here). Commit the three files with the message `docs: the PO flow (#50)` plus the trailer.
