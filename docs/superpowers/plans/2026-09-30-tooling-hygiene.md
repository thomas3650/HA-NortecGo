# Tooling hygiene — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** pre-commit's ruff always matches `uv.lock` (#45), the subagent guard's git lookups ignore git's repository-location variables (#54), and the agent files and PR template point at the full gate set (#66).

**Architecture:**
- Task 1 changes the guard hook: a fixed list of variables, a helper that builds the environment, and `env=` on both git calls. It adds tests with a decoy repository.
- Task 2 replaces the remote `ruff-pre-commit` repo with local `uv run ruff` hooks and adds a Dependabot `pre-commit` entry, with tests. It also updates `way-of-working.md` §6 and adds D41.
- Task 3 points the three agent files and the PR template at `CLAUDE.md` → *Commands*.

**Tech Stack:** Python (the hook: stdlib only, Python ≥ 3.9), pytest, PyYAML, pre-commit, uv, Dependabot.

**Spec:** `docs/superpowers/specs/2026-09-30-tooling-hygiene-design.md` (issues #45, #54, #66).

## Global Constraints

- **Nothing private (hard rule 3):** no IDs, tokens or emails, and no real-instance data.
- **Gates before every commit** (`CLAUDE.md` → Commands): `uv run pytest -q`, then `uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`. The coverage gate (`uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`) passes at the end of each task.
- **Every command runs in the task's worktree:** `cd <worktree> && …`, or `git -C <worktree> …`. Edit files by absolute path under the worktree.
- **Commit messages:** write them with the Write tool to `/tmp/tooling-hygiene-task-<n>-msg.txt` and commit with `git commit -F <file>`. No heredocs. End each message with the co-author trailer given in the dispatch. Titles start with `process:`.
- **The hook** (`.claude/hooks/subagent_guard.py`) stays stdlib only and runs on Python ≥ 3.9. It already has `from __future__ import annotations`.
- **Fixed names:**
  - in the hook: `GIT_LOCAL_ENV_VARS` (a `frozenset[str]`) and `git_env() -> dict[str, str]`;
  - in `tests/test_subagent_guard.py`: the keyword argument `extra_env: dict[str, str] | None = None` on `run_write` and `run_bash`;
  - in `.pre-commit-config.yaml`: the hook ids `ruff-check` and `ruff-format`.
- **Decision number:** D41, for the #45 route only. No other entry changes status.
- **PR:** title `process: tooling hygiene (#45, #54, #66)`. It doesn't release, so there is no `CHANGELOG.md` entry and no bump.

## Review Focus

1. **The owner's git config isolation survives.** The tests set `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_NOSYSTEM` on the hook. `git_env()` must keep them: they aren't in `git rev-parse --local-env-vars`. Task 1's `test_git_env_keeps_other_variables` pins this.
2. **A variable that widens access.** With `GIT_DIR` pointing at a decoy repository whose allowlist names the target, the Write is still refused. Task 1's `test_git_location_variables_cannot_widen_the_allowlist` pins this.
3. **A newer git with more location variables.** Task 1's `test_guard_ignores_every_git_local_env_var` checks that the hook's list is a superset of what the installed git prints.
4. **Hook order and Markdown formatting.** ruff still runs after `pre-commit-hooks` and before `gitleaks`, and `ruff-format` still takes `markdown` files, which is how plan and spec code blocks get formatted. Task 2's `test_pre_commit_ruff_is_the_locked_one` and `test_pre_commit_ruff_runs_before_gitleaks` pin both.
5. **Dependabot's new entry is titled `chore`.** The existing `test_dependabot_titles_are_chore` covers every entry, so it covers the new one. Task 2's `test_dependabot_bumps_pre_commit_hooks` checks that the entry exists.

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (guard) | Alone, but in a task worktree (`<HA-NortecGo-wt>/tooling-hygiene-task-1`). The issue worktree's guard is live for every subagent, so it isn't edited in place |
| 2 | Task 2 (pre-commit, Dependabot, D41), Task 3 (agents, PR template) | Disjoint files, in `…-task-2` and `…-task-3`. They start only after the live-guard check below |

**Guarded files:**
- Task 1: `.claude/hooks/subagent_guard.py`.
- Task 2: `.pre-commit-config.yaml`.
- Task 3: `.claude/agents/implementer.md`, `.claude/agents/task-reviewer.md` and `.claude/agents/full-reviewer.md`.

Before each dispatch, the team lead writes the task's paths (absolute, under its worktree) to `$(git -C <task worktree> rev-parse --absolute-git-dir)/subagent-guard-allow`. It empties that file however the task ends.

**Live-guard check (team lead, after Task 1 is cherry-picked onto the feature branch, before wave 2).** The order is: the pick, the gates, this check, then the push. Run every step from the issue worktree `<HA-NortecGo-wt>/tooling-hygiene` (`cd` there first):
1. Run `uv run pytest tests/test_subagent_guard.py -q`. Expect all tests to pass.
2. With the Write tool, create `/tmp/tooling-hygiene-guard-1.json`:
   `{"tool_name": "Write", "tool_input": {"file_path": "<issue worktree>/.claude/settings.json", "content": "x"}, "cwd": "<issue worktree>", "agent_id": "check"}`.
   Run `python3 "$PWD/.claude/hooks/subagent_guard.py" < /tmp/tooling-hygiene-guard-1.json; echo "exit $?"` (by absolute path, as `.claude/settings.json` calls it). Expect exit 2, with stderr that contains `not in this task's Guarded files`. It must not contain `guard error` or `crashed`.
3. Create `/tmp/tooling-hygiene-guard-2.json` the same way, for `<issue worktree>/docs/.pre-commit-config.yaml`, and run the hook on it. Expect exit 0. This path goes through `worktree_of`, so it exercises the new `env=`.
4. If any step fails: revert the pick on the feature branch (`git revert`), don't push, and re-run Task 1 as a fix round.

---

### Task 1: Guard git calls without repository-location variables (#54)

**Model:** opus — the subagent guard itself.
**Wave:** 1
**Guarded files:** `.claude/hooks/subagent_guard.py` — the fix is in the guard itself (#54).

**Files:**
- Modify: `.claude/hooks/subagent_guard.py` (the module docstring's allowlist paragraph; the constants; `worktree_of`; `common_git_dir`)
- Modify: `tests/test_subagent_guard.py`

**Interfaces:**
- Consumes: the existing `worktree_of`, `common_git_dir` and `allowlist` in the hook; the existing `repos` fixture and the `git`, `allow`, `run_write` and `run_bash` helpers in the tests.
- Produces: `GIT_LOCAL_ENV_VARS` and `git_env()` in the hook. Nothing else uses them.

- [ ] **Step 1: Give the test helpers an `extra_env` argument**

In `tests/test_subagent_guard.py`, add `import importlib.util` to the imports, keeping ruff's isort order. Change `run_write` and `run_bash`:
- add `extra_env: dict[str, str] | None = None` as the last parameter of each;
- change each `env={**env, **GIT_ENV},` to `env={**env, **GIT_ENV, **(extra_env or {})},`;
- in each docstring, add: "extra_env is set on the hook's environment only."

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_subagent_guard.py`:

```python
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
```

Add `from typing import Any` to the imports.

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_subagent_guard.py -q -k "git_location or git_local_env or git_env"`

Expected: all four fail.
- `…ignored_for_an_allowlisted_write`: exit 2 instead of 0, because the lookups resolve to the decoy, which has no allowlist.
- `…cannot_widen_the_allowlist`: exit 0 instead of 2, because the decoy's allowlist opens the file.
- `test_guard_ignores_every_git_local_env_var` and `test_git_env_keeps_other_variables`: `AttributeError`, because the hook doesn't have those names yet.

- [ ] **Step 4: Implement the fix in the hook**

In `.claude/hooks/subagent_guard.py`, after `UNPARSEABLE = …`, add:

```python
# git's repository-location variables (`git rev-parse --local-env-vars`). The guard's git lookups run
# without them, so they find the repository from `-C <dir>` only.
GIT_LOCAL_ENV_VARS = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_DIR",
        "GIT_GRAFT_FILE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    }
)
```

After `resolve`, add:

```python
def git_env() -> dict[str, str]:
    """The hook's environment without git's repository-location variables."""
    return {k: v for k, v in os.environ.items() if k not in GIT_LOCAL_ENV_VARS}
```

In both `worktree_of` and `common_git_dir`, add `env=git_env(),` to the `subprocess.run(...)` call, after `check=False,`.

In the module docstring's last paragraph (the one that starts "The allowlist is per worktree"), add a final sentence:
"The git lookups run without git's repository-location variables (``GIT_DIR``, ``GIT_WORK_TREE``,
``GIT_COMMON_DIR`` and the rest of ``git rev-parse --local-env-vars``), so they follow ``-C`` only."

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_subagent_guard.py -q`
Expected: all pass (the 12 existing tests and the 4 new ones).

Then run the gates from *Global Constraints*.

- [ ] **Step 6: Commit**

```bash
git -C <worktree> add .claude/hooks/subagent_guard.py tests/test_subagent_guard.py
git -C <worktree> commit -F /tmp/tooling-hygiene-task-1-msg.txt
```

Message: `process: guard's git lookups ignore GIT_DIR and friends (#54)`, a one-line body, and the trailer.

---

### Task 2: pre-commit ruff from `uv.lock`, Dependabot for the hooks, D41 (#45)

**Model:** opus — it changes the commit hooks every agent runs, and it writes a decision-log entry (a docs task, D33).
**Wave:** 2
**Guarded files:** `.pre-commit-config.yaml`

**Files:**
- Modify: `.pre-commit-config.yaml`
- Modify: `.github/dependabot.yml`
- Modify: `tests/test_workflows.py`
- Modify: `docs/way-of-working.md` (§6 *Git guards*)
- Modify: `docs/decisions.md` (append D41)

**Interfaces:**
- Consumes: `WORKFLOWS` and `yaml` in `tests/test_workflows.py`.
- Produces: the local hook ids `ruff-check` and `ruff-format`. `way-of-working.md` §1 step 5, `notes.md` and `implementer.md` already use these names (`ha-notes.md` says "the pre-commit `ruff format` hook", which stays true).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_workflows.py`:

```python
PRE_COMMIT = WORKFLOWS.parent.parent / ".pre-commit-config.yaml"


def _pre_commit_repos() -> list[dict[str, Any]]:
    data = yaml.safe_load(PRE_COMMIT.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    repos = data["repos"]
    assert isinstance(repos, list)
    return repos


def test_pre_commit_ruff_is_the_locked_one() -> None:
    """pre-commit runs ruff through uv run, so its version is the one in uv.lock (D41)."""
    repos = _pre_commit_repos()
    assert not any("ruff-pre-commit" in repo["repo"] for repo in repos)
    hooks = {
        hook["id"]: hook
        for repo in repos
        if repo["repo"] == "local"
        for hook in repo["hooks"]
    }
    check, fmt = hooks["ruff-check"], hooks["ruff-format"]
    assert check["entry"] == "uv run ruff check --force-exclude"
    assert check["args"] == ["--fix"]
    assert check["types_or"] == ["python", "pyi", "jupyter"]
    assert fmt["entry"] == "uv run ruff format --force-exclude"
    assert fmt["types_or"] == ["python", "pyi", "jupyter", "markdown"]
    for hook in (check, fmt):
        assert hook["language"] == "system"
        assert hook["require_serial"] is True


def test_pre_commit_ruff_runs_before_gitleaks() -> None:
    """The ruff hooks keep their place: after pre-commit-hooks, before gitleaks."""
    repos = _pre_commit_repos()
    ids = [[hook["id"] for hook in repo["hooks"]] for repo in repos]
    ruff = next(i for i, repo_ids in enumerate(ids) if "ruff-check" in repo_ids)
    gitleaks = next(i for i, repo_ids in enumerate(ids) if "gitleaks" in repo_ids)
    hygiene = next(i for i, repo_ids in enumerate(ids) if "check-yaml" in repo_ids)
    assert hygiene < ruff < gitleaks
    assert repos[ruff]["repo"] == "local"
    assert "ruff-format" in ids[ruff]


def test_dependabot_bumps_pre_commit_hooks() -> None:
    """Dependabot bumps the remote pre-commit hooks monthly, in one group."""
    config = yaml.safe_load(
        (WORKFLOWS.parent / "dependabot.yml").read_text(encoding="utf-8")
    )
    updates = {u["package-ecosystem"]: u for u in config["updates"]}
    pre_commit = updates["pre-commit"]
    assert pre_commit["directory"] == "/"
    assert pre_commit["schedule"] == {"interval": "monthly"}
    assert pre_commit["groups"] == {"pre-commit": {"patterns": ["*"]}}
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_workflows.py -q -k "pre_commit"`
Expected: `test_pre_commit_ruff_is_the_locked_one` fails (the `ruff-pre-commit` repo is still there), `test_pre_commit_ruff_runs_before_gitleaks` fails on `repos[ruff]["repo"] == "local"` (the remote repo still holds `ruff-check`), and `test_dependabot_bumps_pre_commit_hooks` fails with `KeyError: 'pre-commit'`.

- [ ] **Step 3: Replace the ruff repo in `.pre-commit-config.yaml`**

Replace the block

```yaml
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.16.9
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
```

with

```yaml
  # ruff runs through uv, so its version is the one in uv.lock, as in CI (D41).
  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check
        entry: uv run ruff check --force-exclude
        args: [--fix]
        language: system
        types_or: [python, pyi, jupyter]
        require_serial: true
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format --force-exclude
        language: system
        types_or: [python, pyi, jupyter, markdown]
        require_serial: true
```

Leave everything else in the file as it is.

- [ ] **Step 4: Add the Dependabot entry**

Append to the `updates:` list in `.github/dependabot.yml`:

```yaml
  - package-ecosystem: pre-commit
    directory: /
    commit-message:
      prefix: chore
      include: scope
    schedule:
      interval: monthly
    groups:
      pre-commit:
        patterns: ["*"]
```

- [ ] **Step 5: Run the tests and check the hooks**

Run: `uv run pytest tests/test_workflows.py -q`
Expected: all pass, `test_dependabot_titles_are_chore` included.

Then run `uv run pre-commit validate-config .pre-commit-config.yaml` (with no filename it checks nothing) and `uv run pre-commit run ruff-check --all-files && uv run pre-commit run ruff-format --all-files`. Expected: both hooks show `Passed` and change no files, because the locked ruff is the same 0.16.9 the old hook used. If a hook changes files, stop and report BLOCKED with the list of files.

- [ ] **Step 6: Update `docs/way-of-working.md` §6**

In the *Git guards* bullet, change `Some hooks run a dev tool with `uv run` (`actionlint`, `zizmor`), so` to `Some hooks run a dev tool with `uv run` (ruff, `actionlint`, `zizmor`), so`. Re-wrap the paragraph to at most 110 characters a line, as the file does.

- [ ] **Step 7: Append D41 to `docs/decisions.md`**

At the end of the file, after D40, add:

```markdown
### D41: pre-commit runs ruff from `uv.lock`
- **Date:** 2026-09-30 · **Status:** active
- **Decision:** pre-commit runs ruff as local hooks through `uv run ruff`, so it uses the version in `uv.lock`,
  as CI does. Dependabot's `pre-commit` ecosystem bumps the remaining remote hooks (`pre-commit-hooks`,
  `gitleaks`) monthly.
- **Why:** a separately pinned `ruff-pre-commit` drifts from `uv.lock` after a Dependabot `uv` bump, so a
  commit that passes the hook can fail CI's `ruff format --check`. Letting Dependabot bump both would still
  bring them in separate PRs.
- **Source:** [tooling hygiene spec](superpowers/specs/2026-09-30-tooling-hygiene-design.md), Decisions
```

Keep one blank line between D40 and D41, as between the other entries.

- [ ] **Step 8: Run the gates and commit**

Run the gates from *Global Constraints*, then:

```bash
git -C <worktree> add .pre-commit-config.yaml .github/dependabot.yml tests/test_workflows.py docs/way-of-working.md docs/decisions.md
git -C <worktree> commit -F /tmp/tooling-hygiene-task-2-msg.txt
```

Message: `process: pre-commit runs ruff from uv.lock; Dependabot bumps the hooks (#45)`, a one-line body, and the trailer. The commit itself runs the new local hooks, which is one more check that they work.

---

### Task 3: Agent files and PR template point at the gates (#66)

**Model:** opus — the agents' rules, and a docs task (D33).
**Wave:** 2
**Guarded files:** `.claude/agents/implementer.md`, `.claude/agents/task-reviewer.md`, `.claude/agents/full-reviewer.md`

**Files:**
- Modify: `.claude/agents/implementer.md` (the *Gates pass before each commit* bullet)
- Modify: `.claude/agents/task-reviewer.md` (the first bullet under *Rules*)
- Modify: `.claude/agents/full-reviewer.md` (the first bullet under *Rules*)
- Modify: `.github/pull_request_template.md` (the *Gates pass* checkbox; not guarded)

**Interfaces:**
- Consumes: the *Commands* section of `CLAUDE.md`, as it stands on the feature branch. Read it first; it has the tests line, the coverage gate line and the lint line (ruff check, ruff format, mypy, `actionlint`, `zizmor`).
- Produces: nothing code uses.

- [ ] **Step 1: Change the implementer's gate bullet**

In `.claude/agents/implementer.md`, replace

```text
- Gates pass before each commit: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`,
  `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`.
```

with

```text
- Gates pass before each commit: the gate lines of `CLAUDE.md` → *Commands*, which are the tests, the
  coverage gate, and the lint line (ruff, ruff format, mypy, `actionlint`, `zizmor`). The rest of that
  section (`uv sync`, `pre-commit install`, the `scripts/`) isn't a gate: don't run `pre-commit install` or
  the scripts.
```

- [ ] **Step 2: Change the reviewers' check lists**

In `.claude/agents/task-reviewer.md`, replace

```text
- Read-only. Never modify files, the index, HEAD or branches. Bash only for inspection (`git show`,
  `git diff`, `git log`, `grep`) and for running checks (`uv sync --locked`, `uv run ruff check`,
  `uv run ruff format --check`, `uv run mypy`,
  `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`,
  `uv run pre-commit run --all-files`), which write only git-ignored caches.
```

with

```text
- Read-only. Never modify files, the index, HEAD or branches. Bash only for inspection (`git show`,
  `git diff`, `git log`, `grep`) and for running checks: `uv sync --locked`, the gate lines of `CLAUDE.md` →
  *Commands* (the tests, the coverage gate, and the lint line, with `actionlint` and `zizmor`), and
  `uv run pre-commit run --all-files`. These write only git-ignored caches.
```

In `.claude/agents/full-reviewer.md`, make the same replacement, but its old bullet ends `which write only git-ignored or temporary files.` Keep that ending: the new bullet ends `These write only git-ignored or temporary files.`

- [ ] **Step 3: Change the PR template's gate checkbox**

In `.github/pull_request_template.md`, replace

```text
- [ ] Gates pass (ruff, ruff format, mypy, pytest with coverage ≥ 95%)
```

with

```text
- [ ] Gates pass (`CLAUDE.md` → *Commands*: the tests, the coverage gate and the lint line)
```

- [ ] **Step 4: Check and commit**

- Run `grep -n 'uv run ruff format --check' .claude/agents/*.md` (single quotes, so zsh expands nothing). Expected: no output.
- Run `grep -n "actionlint" .claude/agents/implementer.md .claude/agents/task-reviewer.md .claude/agents/full-reviewer.md`. Expected: one line each.
- Run the gates from *Global Constraints*, then:

```bash
git -C <worktree> add .claude/agents/implementer.md .claude/agents/task-reviewer.md .claude/agents/full-reviewer.md .github/pull_request_template.md
git -C <worktree> commit -F /tmp/tooling-hygiene-task-3-msg.txt
```

Message: `process: agents and PR template point at the gates in CLAUDE.md (#66)`, a one-line body, and the trailer.
