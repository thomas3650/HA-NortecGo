# Tooling hygiene — design

Date: 2026-09-30 · Branch: `process/tooling-hygiene` · Issues: #45, #54, #66

## Goal

- **What:** three small tooling fixes in one PR:
  - pre-commit's ruff always runs the version in `uv.lock` (#45);
  - the subagent guard's git lookups ignore git's repository-location environment variables (#54);
  - the agent files name the full gate set, workflow linters included (#66).
- **Why:**
  - #45: `.pre-commit-config.yaml` pins `ruff-pre-commit` separately from the ruff in `uv.lock`. Dependabot
    bumps only the `uv.lock` one, so after a ruff bump the hook and CI can format differently.
  - #54: the guard's `git -C <dir> rev-parse` calls inherit the hook's environment, so a `GIT_DIR`,
    `GIT_WORK_TREE` or `GIT_COMMON_DIR` set there would override the `-C` lookup.
  - #66: the gate lists in `implementer.md`, `task-reviewer.md` and `full-reviewer.md` predate `actionlint`
    and `zizmor` (#64). A subagent's own gate run can miss a workflow finding until the hook or CI catches it.
- **Not in this work:** renaming the session names (#53), other guard limits listed in its docstring, and
  CI changes (`lint.yml` already runs `uv run ruff`).
- **Done when:** the ruff version can't drift between pre-commit and CI; gitleaks and `pre-commit-hooks` get
  Dependabot bumps; the guard finds the right worktree with those variables set; the three agent files point
  at the full gate set. The gates pass, and D41 is in the decision log.

## Decisions

Proposed by the team lead and approved by the owner through the PO (issue #45, 2026-09-30).

| Topic | Decision |
|---|---|
| #45 route | ruff runs as `local` hooks through `uv run`. Dependabot's `pre-commit` ecosystem bumps the remaining remote hooks (`pre-commit-hooks`, `gitleaks`) |
| Rejected for #45 | Keeping `ruff-pre-commit` and letting Dependabot bump it: the `uv` and `pre-commit` bumps come in separate PRs, so the two versions can still drift between them |
| #54 variables | The guard's git calls drop the variables that `git rev-parse --local-env-vars` lists, a fixed list in the hook |
| Rejected for #54 | Only the three variables the issue names (git has more that redirect a lookup: `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`, …); every `GIT_*` (drops `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_NOSYSTEM`, which the guard tests set to keep the owner's config out) |
| #66 form | The agent files point at `CLAUDE.md` → *Commands* and name its gate lines: the tests, the coverage gate and the lint line. Not "every command there": that section also holds `pre-commit install` (which breaks commits when run in a task worktree) and the dev scripts |
| Decision log | D41, for the #45 route (a lasting tooling rule). #54 and #66 need no entry |
| Title | `process: tooling hygiene (#45, #54, #66)`; non-releasing, so no `CHANGELOG.md` entry and no bump |

Facts used:

- `ruff-pre-commit` `v0.16.9` defines `ruff-check` as `ruff check --force-exclude` with
  `types_or: [python, pyi, jupyter]`, and `ruff-format` as `ruff format --force-exclude` with
  `types_or: [python, pyi, jupyter, markdown]`, both `require_serial: true`. The markdown type is why the
  hook formats Python blocks in specs and plans (`way-of-working.md` §1 step 5, `notes.md`).
- `uv.lock` pins ruff `0.16.9`, the same as today's hook. So the switch changes no formatting.
- Dependabot supports `package-ecosystem: "pre-commit"` for version updates (GitHub's supported-ecosystems
  page, 2026-09-30), with no beta flag.
- `git rev-parse --local-env-vars` (git 2.x) lists: `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_CONFIG`,
  `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`, `GIT_OBJECT_DIRECTORY`, `GIT_DIR`, `GIT_WORK_TREE`,
  `GIT_IMPLICIT_WORK_TREE`, `GIT_GRAFT_FILE`, `GIT_INDEX_FILE`, `GIT_NO_REPLACE_OBJECTS`,
  `GIT_REPLACE_REF_BASE`, `GIT_PREFIX`, `GIT_SHALLOW_FILE`, `GIT_COMMON_DIR`. `GIT_CONFIG_GLOBAL` and
  `GIT_CONFIG_NOSYSTEM` aren't in it.
- The hook runs from `$CLAUDE_PROJECT_DIR/.claude/hooks/subagent_guard.py` (`.claude/settings.json`). In the
  PO flow that is the issue worktree, so this branch's guard and agent files are live for its own subagents
  as soon as they're on the feature branch.

## Design

### 1. pre-commit ruff from `uv.lock` (#45)

`.pre-commit-config.yaml`:
- Remove the `ruff-pre-commit` repo.
- In the `local` repo, add two hooks:
  - `ruff-check`: `entry: uv run ruff check --force-exclude`, `args: [--fix]`,
    `types_or: [python, pyi, jupyter]`;
  - `ruff-format`: `entry: uv run ruff format --force-exclude`, `types_or: [python, pyi, jupyter, markdown]`.
- Both hooks get `language: system` and `require_serial: true`, and each gets a `name` like the other local
  hooks have.
- They keep the upstream ids, so the docs and `implementer.md` that name `ruff-format` stay true.
- The hooks stay in the same order: ruff before `gitleaks`, as today.

`.github/dependabot.yml`: add an update for `package-ecosystem: pre-commit`, `directory: /`, monthly, one
group of all hooks. Its commit message is prefix `chore` with scope included, like the other two.

Docs:
- `way-of-working.md` §6 *Git guards*: the hooks that run through `uv run` are now ruff, `actionlint` and
  `zizmor`.
- `decisions.md`: D41.

Tests:
- `tests/test_workflows.py` already checks that every Dependabot entry is titled `chore`, so it covers the new
  entry.
- A new test in the same file checks two things: no repo in `.pre-commit-config.yaml` is `ruff-pre-commit`,
  and the `ruff-check` and `ruff-format` hooks are local, with entries starting `uv run ruff`.
- Another new test checks that Dependabot has a `pre-commit` entry.

### 2. Guard git calls without repo-location variables (#54)

`.claude/hooks/subagent_guard.py`:
- Add a constant: the variables from `git rev-parse --local-env-vars` (see *Facts used*).
- Add a helper that returns `os.environ` without them.
- Both `subprocess.run` calls (`worktree_of`, `common_git_dir`) pass that as `env=`.
- The module docstring gets one line: the git lookups ignore those variables.
- It stays stdlib-only and Python 3.9-compatible.

`tests/test_subagent_guard.py`, a new test, red before the fix:
- Set up an allowlisted guarded Write in the linked worktree.
- Run the hook with `GIT_DIR`, `GIT_WORK_TREE` and `GIT_COMMON_DIR` pointing at a separate tmp repo. Set them
  on the hook's environment only, never in the `git()` setup helper.
- The Write passes (exit 0).
- A second case in the same setup: a guarded Write that isn't allowlisted is still refused (exit 2).

### 3. Agent gate lists (#66)

- `implementer.md`: the *Gates pass before each commit* bullet points at `CLAUDE.md` → *Commands* and names
  its gate lines: the tests, the coverage gate, and the lint line (ruff, mypy, `actionlint`, `zizmor`). It
  also says the rest of that section (`pre-commit install` and the scripts) isn't for implementers.
- `task-reviewer.md` and `full-reviewer.md`: their *Rules* bullet lists the checks they may run, and that list
  is also their Bash scope. It becomes:
  - `uv sync --locked`;
  - the gate lines of `CLAUDE.md` → *Commands* (tests, coverage gate, lint line);
  - `uv run pre-commit run --all-files`.

  The rest of the bullet (read-only, and what those checks write) is unchanged.

## Execution shape

- **Wave 1:** #54 alone, in a task worktree even as a single-task wave. The issue worktree's guard is the live
  one, so an implementer editing it there could break its own tool calls.
  - After the cherry-pick, the team lead checks the live hook before dispatching anything else:
    `uv run pytest tests/test_subagent_guard.py`, a subagent Write payload for a guarded path piped into
    `python3 .claude/hooks/subagent_guard.py` (exit 2), and one for a `docs/` path (exit 0).
- **Wave 2:** #45 and #66 in parallel, on disjoint files, each in its own task worktree.
  - D41 goes with #45.
- **Guarded files:**
  - #54: `.claude/hooks/subagent_guard.py`. Reason: the fix is in the guard itself (#54).
  - #45: `.pre-commit-config.yaml`.
  - #66: `.claude/agents/implementer.md`, `.claude/agents/task-reviewer.md`, `.claude/agents/full-reviewer.md`.
- Every task is `Model: opus`: each touches the guard or the agents' rules, and #66 is a docs task (D33).

## Risks

- **A local hook needs the dev environment.** `uv run ruff` needs `uv sync` in the checkout, as `actionlint`
  and `zizmor` already do. §6 already requires a `uv sync` after such a merge.
- **Markdown formatting.** It keeps working only while the `ruff` in `uv.lock` formats Markdown, which the
  pinned version does today. The upstream hook had the same dependency.
- **The live guard.** A broken guard refuses every subagent call (exit 2). Wave 1's check catches that before
  wave 2. If it's found later, the team lead, who isn't restricted by the guard, reverts the pick.
