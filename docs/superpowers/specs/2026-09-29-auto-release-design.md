# Tag and publish a release when a merged PR bumps the version — design

Date: 2026-09-29 · Branch: `process/auto-release` · Issue: #64

## Goal

- **What:** once CI has passed on `main` for a commit that bumps the version, a workflow tags that commit
  `v<version>` and publishes the GitHub release, with no manual step. A pull request check makes sure that a
  version change is a bump the workflow will release.
- **Why:** today the owner tags every release by hand after merging the bump PR (D10). The bump PR already
  holds everything a release needs, so the tag is a step that can be forgotten or put on the wrong commit.
- **Not in this work:** bumping the version automatically (the bump PR stays a deliberate PR the owner
  merges), bumping `pynortecgo` (#49), and changes to GitHub settings (branch protection, required checks).
- **Done when:** a merged PR that bumps the version produces the tag and the GitHub release without a
  manual step, and HACS offers the new version; the gates pass; `docs/releasing.md` and the decision log are
  updated.

## Decisions

Proposed by the team lead and approved by the owner through the PO (issue #64, 2026-09-29).

| Topic | Decision |
|---|---|
| Trigger | A new `auto-release.yml`, run by `workflow_run` on each of the five workflows that are required checks on `main` (`lint`, `tests`, `hassfest`, `hacs`, `gitleaks`). It acts only on a successful `push` run on `main` from this repository, and only once all five workflows have passed for that commit's push. The workflows aren't merged into one (§2.1) |
| Release path | `release.yml` gains `workflow_call`, and `auto-release.yml` calls it as a reusable workflow. There is one release code path, and the only write permission is `contents: write`: no `actions: write`, no `gh workflow run` |
| What is a bump | The version at the commit is higher (semver) than at its first parent, and the same commit adds the `## [X.Y.Z]` changelog heading, with a non-empty section. Anything else, a revert to an older version included, releases nothing |
| Older versions | The automation never back-fills on its own. A bump commit merged before this work is released by the owner's dispatch of the fallback; `0.1.0` (`9441abd`) is released that way, as the first real use (§2.4) |
| Repeats | A run for a commit whose release exists does nothing. A tag of that name on another commit fails the run. No second release is ever created |
| Fallback | `workflow_dispatch` on `auto-release.yml`, from `main` only, with a `sha` and a `dry_run` input (default `true`); the manual tag push stays as the last fallback |
| PR check | A new `version-check.yml` on `pull_request` (never `pull_request_target`), skipped for drafts, applying the same bump rule against the PR's base. The owner makes `version-check` a required check after the merge, as a GitHub setting (§6) |
| Lint | `actionlint` (with ShellCheck) and `zizmor` join the gates, as `uv` dev dependencies, pre-commit hooks and steps in `lint.yml` |
| Decision log | D39, which supersedes the manual tag in D10: D10's status becomes `active; the manual tag superseded by D39` |
| Process | Full path (spec, plan, `full-reviewer`); no D25 ruling |

Facts used, public-safe:

- A tag or release created with `GITHUB_TOKEN` doesn't start other workflows (so a tag made by the
  workflow wouldn't run `release.yml`'s `push: tags` trigger). `workflow_dispatch` and `workflow_call` are
  not limited that way.
- A `workflow_dispatch` run uses the workflow files as they are at the ref it runs on. A local reusable
  workflow (`uses: ./.github/workflows/...`) is read from that same commit, so a dispatch on `main` calls
  `main`'s `release.yml`, whatever commit it releases, and a dispatch from another branch would run that
  branch's files.
- A `workflow_run` run uses the workflow file from the default branch, and in it `GITHUB_SHA` and
  `github.ref` are the default branch's head, not the commit the triggering run tested. That commit is
  `github.event.workflow_run.head_sha`. `workflow_run` fires once per completed triggering run; there is no
  "all of these finished" trigger.
- In a called (reusable) workflow, the `github` context is the caller's: `github.event_name` is the
  caller's event and `github.ref_name` is `main`, never the tag.
- A concurrency group holds at most one running and one pending run; a new run replaces (cancels) the
  pending one.
- The runner's `python3` is 3.12, while the gates format and lint for 3.14 (`ruff format` writes
  `except A, B:`, a syntax error before 3.14). The runner has ShellCheck, which `actionlint` uses when it is
  on the `PATH`.
- PyYAML loads the key `on:` as the boolean `True`.
- The repository has no rulesets, so nothing stops the workflow creating a tag. The default workflow token
  is read-only, so each job states its permissions.
- `gh release create <tag> --target <sha>` creates the tag on that commit if it doesn't exist, and ignores
  `--target` if it does.
- `9441abd` (the `0.1.0` bump) raises the version from `0.0.1` to `0.1.0`, adds the `## [0.1.0]` heading,
  and all five required workflows passed for its push.

## 1. Files

| File | Change |
|---|---|
| `scripts/release_check.py` | New, stdlib only: the version, changelog, bump and run rules (§3) |
| `.github/workflows/auto-release.yml` | New (§2) |
| `.github/workflows/release.yml` | `workflow_call`, the tag and commit from the inputs, the tag's commit checked, no second release (§4) |
| `.github/workflows/version-check.yml` | New (§6) |
| `.github/workflows/lint.yml` | `actionlint` and `zizmor` steps (§7) |
| Other workflows | Only what `actionlint` or `zizmor` asks for (§7) |
| `.pre-commit-config.yaml` | `actionlint` and `zizmor` hooks (§7) |
| `pyproject.toml`, `uv.lock` | Dev group: `actionlint-py`, `shellcheck-py`, `zizmor`, `types-PyYAML`; pytest `pythonpath`, mypy `mypy_path` and `files`, ruff per-file ignores for `scripts/*.py` (§3, §7) |
| `CLAUDE.md` | The lint command in *Commands* gains the two linters (§7) |
| `docs/releasing.md` | §5 |
| `docs/README.md` | The `releasing.md` row mentions the automatic release (§5) |
| `docs/decisions.md` | D39, and D10's status (§8) |
| `tests/test_release_check.py`, `tests/test_workflows.py` | New (§9) |

There is no `CHANGELOG.md` entry: nothing changes for a user of the integration. `quality_scale.yaml` and
`docs/user/nortec_go.md` don't change.

## 2. `auto-release.yml`

### 2.1 Trigger and filters

```yaml
on:
  workflow_run:
    workflows: [lint, tests, hassfest, hacs, gitleaks]
    types: [completed]
    branches: [main]
  workflow_dispatch:
    inputs:
      sha: {description: "A commit on main that bumps the version", required: true}
      dry_run: {type: boolean, default: true}
permissions: {}
```

Merging the five workflows into one `ci.yml` would give a single trigger, but it restructures CI and the
required checks; triggering on all five and letting a run after the last one do the work keeps CI as it is.

A `workflow_run` run goes on only if all of these hold, in the `decide` job's `if:` (`branches: [main]`
only saves the runs for PR pushes; the `if:` is the guard):

- `github.event.workflow_run.conclusion == 'success'`;
- `github.event.workflow_run.event == 'push'` (never a PR or scheduled run);
- `github.event.workflow_run.head_branch == 'main'`;
- `github.event.workflow_run.head_repository.full_name == github.repository`.

A `workflow_dispatch` run goes on only if `github.ref == 'refs/heads/main'` (so only `main`'s files run
with a write token), and `sha` resolves to a commit (`git rev-parse --verify "$sha^{commit}"`, which also
turns a short SHA into the full one used from then on) that is on `main` (`git merge-base --is-ancestor`).

**The commit.** Every read, check and tag target uses the commit the triggering run tested,
`github.event.workflow_run.head_sha`, or the resolved `sha` input for a dispatch; never `GITHUB_SHA` or
`github.ref`. Event and input values reach `run:` steps through `env:`, never by `${{ }}` inside the
script.

### 2.2 Concurrency

At workflow level (so a run's `decide` never overlaps another run's `release`):
`group: auto-release-<event>-<commit>`, where `<event>` is `github.event.workflow_run.event`, or
`dispatch`; `cancel-in-progress: false`.

- For one push, the five triggers land in one group. One run goes at a time; a trigger that arrives while
  another waits cancels the waiting one. The last trigger comes after the last of the five workflows has
  finished, so the run that goes last sees all five, and a release made by an earlier run.
- The event is in the key so that a scheduled `hassfest` or `hacs` run on the same commit (which does
  nothing, §2.1) can't cancel a waiting push run.
- A dispatch and an automatic run on the same commit aren't serialised; `release.yml`'s checks (§4) make
  the second one end without a second release.

### 2.3 Jobs

1. **`decide`** (`permissions: contents: read, actions: read`):
   - checks out `main` with full history and `persist-credentials: false` (only merged code runs, never a
     PR's), and installs Python 3.14 with `astral-sh/setup-uv` (the pinned SHA the other workflows use, with
     `python-version: "3.14"`, which sets `UV_PYTHON`, and `enable-cache: false`); the script runs with
     `uv run --no-project --python 3.14`;
   - runs `release_check.py bump <commit>` (§3); if it isn't a bump, logs why (for example
     `0.1.0 unchanged: nothing to release`) and ends with success;
   - lists the commit's push runs (`gh api "repos/<repo>/actions/runs?head_sha=<commit>&event=push&per_page=100"`)
     and runs `release_check.py runs-green` on them; if not all five passed, logs which are missing or not
     green, and ends with success (a later trigger will see them);
   - looks up the tag `v<version>` with `git ls-remote origin refs/tags/<tag> 'refs/tags/<tag>^{}'` and
     `release_check.py tag-commit` (§3): missing is fine; on this commit is fine; on another commit fails
     the run with both commits in the log;
   - outputs `version`, `tag`, `sha` and `release: true|false`. In a dry run it logs what it would do and
     outputs `release: false`.
2. **`release`** (`needs: decide`, `if: needs.decide.outputs.release == 'true'`,
   `permissions: contents: write`): `uses: ./.github/workflows/release.yml` with `tag` and `sha`.

`actions: read` is for the runs list; nothing else is granted. The write token reaches only
`release.yml`'s own steps (§4), which are shell only and run no script from the checked-out commit.

### 2.4 The first real use: `0.1.0`

`0.1.0` was merged (`9441abd`) before this work and isn't tagged; the owner doesn't tag it by hand. After
this PR merges, the owner dispatches `auto-release.yml` on `main` with `sha=9441abd`, first with
`dry_run=true` and then `false`:

- `decide` runs `bump 9441abd` with `main`'s script: a bump (`0.0.1` to `0.1.0`, heading added); all five
  push runs passed; the tag `v0.1.0` is missing;
- `release` calls `main`'s `release.yml` (which has `workflow_call`, although `9441abd`'s doesn't), which
  checks out `9441abd`, reads the manifest and the `[0.1.0]` section there, and creates `v0.1.0` on
  `9441abd` with that section as the notes. `0.1.0` is a full release, not a pre-release.

## 3. `scripts/release_check.py`

Stdlib only, pure functions and a thin CLI, written for 3.14 like the rest of the repo; the workflows run it
on 3.14 (§2.3, §6). Tests import it through pytest's `pythonpath = ["scripts"]`; mypy checks it under
`strict` (`mypy_path = "scripts"`, and the file in `files`). Ruff ignores `INP001` and `T201` for
`scripts/*.py` (a script, not a package, that prints); the docstring rules apply. The coverage gate stays
on the integration; the unit tests (§9) cover every branch of the script.

- **Versions:** parses `X.Y.Z` with an optional `-<pre-release>` suffix, and compares by semver precedence
  (a pre-release is lower than its release; pre-release identifiers compare numerically or as text). An
  unparseable version is an error.
- **Changelog section:** the text between `## [X.Y.Z]` and the next `## [` heading (the rule of
  `release.yml`'s `awk`); missing and blank-only are both "no section".
- **Bump:** given the manifest and changelog at a commit and at a base (the first parent, or a PR's base),
  it is a bump when the version is higher than the base's, the changelog has a non-empty section for it,
  and the base's changelog doesn't have that heading. The verdict says which condition failed.
- **Runs green:** given the workflow runs JSON, for each name in `REQUIRED_WORKFLOWS` (a constant:
  `lint`, `tests`, `hassfest`, `hacs`, `gitleaks`) the newest run by `created_at` exists and has
  conclusion `success`. A run still going (no conclusion) isn't green. Only push runs are listed, so a
  scheduled run is never counted.
- **Tag commit:** given `git ls-remote` output for a tag, the commit it points at: the `^{}` line for an
  annotated tag, otherwise the plain line; none if the tag is missing.
- **CLI:**
  - `bump <commit>`: reads the manifest and changelog at `<commit>` and `<commit>^1` with `git show`,
    prints the verdict, and writes `version=`, `tag=` and `bump=true|false` to `$GITHUB_OUTPUT` when it is
    set. Exit 0 for a bump and for not a bump; non-zero only for an error (unreadable file, bad version).
  - `pr-check <base> <head>`: the same bump rule with `<base>` as the base. Version unchanged: exit 0.
    Version changed and a bump: exit 0. Version changed and not a bump: exit 1 with the reason.
  - `runs-green`: the runs JSON on stdin; exit 0 when green, 1 when not, listing the missing and failed
    names.
  - `tag-commit <tag>`: `git ls-remote` output on stdin; prints the commit, or nothing if missing. A
    missing tag is empty output (`git ls-remote` exits 0 for it), never judged by the exit code.

## 4. `release.yml`

`release.yml` stays shell only: when called for an older commit (§2.4), the checked-out commit doesn't have
`scripts/release_check.py`.

- **Triggers:** `push: tags: ["v*"]` stays (the manual fallback); `workflow_call` adds the required string
  inputs `tag` and `sha`.
- **Which path:** called when `inputs.tag` is set, never judged by `github.event_name` (a called workflow
  sees the caller's event). Called: `tag = inputs.tag`, checkout at `inputs.sha`. Pushed: `tag =
  github.ref_name`, checkout at `github.ref`, and the commit is `git rev-parse HEAD`. Values reach the steps
  through `env:`; checkout with `persist-credentials: false`.
- **Permissions:** `permissions: {}` at the top, `contents: write` on the job; when called, it can't exceed
  what the caller job gives.
- **Checks:** unchanged (the tag equals `v` plus the manifest version at that commit; the changelog section
  is non-empty); then:
  - **no second release:** if `gh release view <tag>` finds the release, the job logs it and ends with
    success;
  - **the tag's commit:** if the tag exists (`git ls-remote`, the `^{}` line for an annotated tag), it must
    point at the commit, or the job fails; `--target` doesn't move an existing tag.
- **Create:** `gh release create <tag> --target <commit> --title <tag> --notes-file notes.md`, plus
  `--prerelease` for `0.0.x` or a `-` suffix, as today, passed without word-splitting (ShellCheck).
- A tag pushed by hand on the bump commit while the automatic run goes may make both runs try to create
  the release; one fails with "already exists", and one release exists. That is harmless.

## 5. `docs/releasing.md`

- **The bump PR is the release:** the three bump steps stay; merging the PR releases it. After CI passes on
  `main`, `auto-release.yml` tags the merge commit and publishes the release. What counts as a bump is the
  rule from §3, in words, and `version-check` checks it on the PR.
- **What to check after a merge:** the `auto-release` runs for the merge commit (some show as cancelled:
  §2.2), the tag, the release, and that HACS offers it.
- **Fallbacks:** the `workflow_dispatch` run on `main` (dry run first), also for a bump commit merged
  before the automation; then the manual tag, for a commit the rule doesn't count as a bump. A dispatch with
  `dry_run=false` tags a release, so, like the manual tag, it is the owner's action (way of working §6: the
  controller doesn't tag releases).
- **Once, after the auto-release PR merges:** the owner adds `version-check` to `main`'s required status
  checks (§6), then dispatches `auto-release.yml` with `sha=9441abd`, a dry run and then a real one, to
  release `0.1.0` (§2.4), and checks the tag, the release and HACS. The next bump PR removes this step; the
  PR description lists the same steps.
- **What `release.yml` checks:** add the two ways it starts, the "no second release" rule and the tag's
  commit check.
- **Required workflows:** the list in `auto-release.yml`'s trigger and in `REQUIRED_WORKFLOWS` follows
  the required checks on `main`; `tests/test_workflows.py` catches a workflow added or renamed in the repo,
  not a change made only in the GitHub settings.
- The *Tagging (owner only)* heading becomes *Tagging by hand (fallback)*.
- `docs/README.md`'s row for `releasing.md` reads: the bump PR, the automatic release, tagging by hand,
  what `release.yml` checks.

## 6. `version-check.yml`

- **On:** `pull_request` with `types: [opened, synchronize, reopened, ready_for_review, edited]`
  (`edited` covers a change of base branch); the job has
  `if: github.event.pull_request.draft == false`. `permissions: contents: read`.
- **Does:** checks out the PR head (full history, `persist-credentials: false`), installs Python 3.14 as in
  §2.3, and runs `release_check.py pr-check <merge base> <head sha>` (§3). The merge base is
  `git merge-base "$BASE_SHA" "$HEAD_SHA"`, with both SHAs from `github.event.pull_request` through
  `env:`: what the PR itself changes, so a PR behind a newer release on `main` doesn't see a lowered
  version. `main` requires branches to be up to date, so at merge time the merge base is the squash commit's
  first parent, and the check predicts `bump` exactly. A version change that isn't a bump fails with the reason, so a
  PR that passes is released when it merges.
- **Check name:** the job's id is `version-check` and it has no `name:`, so its check is `version-check`.
- **Required check:** after the merge, the owner adds `version-check` to `main`'s required status checks;
  it is a GitHub setting, so it isn't done here (way of working §6). A check skipped for a draft counts as
  passed. It runs only on `pull_request`, so it isn't in `REQUIRED_WORKFLOWS` or `auto-release.yml`'s
  trigger (those are the workflows that run on a push to `main`).

## 7. Workflow linting

- **Tools:** `actionlint-py` (the `actionlint` binary), `shellcheck-py` (ShellCheck, so `actionlint` checks
  `run:` scripts locally as it does in CI) and `zizmor`, in the `uv` dev group.
- **Gate:** `lint.yml` runs `uv run actionlint` and `uv run zizmor --offline .github/workflows`;
  `CLAUDE.md`'s lint command gains the same two.
- **Pre-commit:** local hooks with the same commands, limited to `^\.github/workflows/`.
- **Findings in the existing workflows:** fixed where the fix is small and safe (for example
  `persist-credentials: false` on a checkout that doesn't push, and the unquoted `$flags` in `release.yml`).
  `auto-release.yml`'s `workflow_run` trigger is flagged by design; that finding is ignored inline with the
  reason (only `main` push runs, no PR code, §2.1).
- **Typing:** `types-PyYAML` for `tests/test_workflows.py`.

## 8. Decision log

```markdown
### D39: A merged bump PR is the release
- **Date:** 2026-09-29 · **Status:** active
- **Decision:** When CI passes on `main` for a commit that raises the version and adds its changelog
  section, `auto-release.yml` tags that commit and publishes the release through `release.yml`. A dispatch
  of `auto-release.yml` is the fallback, also for a bump merged before it; tagging by hand is the last one.
- **Why:** The bump PR already holds everything a release needs; the owner still decides when a release goes
  out by merging it.
- **Source:** [auto-release spec](superpowers/specs/2026-09-29-auto-release-design.md), Decisions and §2
```

D10's status becomes `active; the manual tag superseded by D39`.

## 9. Tests and verification

**Unit tests** (`tests/test_release_check.py`):
- versions: parsing and precedence (release, pre-release, equal, lower, bad input);
- the changelog section: present, missing, blank, the last section in the file;
- bump: raised with a section; raised without one; the heading already in the base; unchanged; lowered; a
  revert to an older version;
- runs green: all green; one missing; one failed; one still running; an older failed run and a newer
  successful one (green); an older successful run and a newer failed one (not green);
- tag commit: lightweight, annotated, missing;
- the CLI's outputs and exit codes, with `git` in a temporary repository: `bump` and `pr-check` for each
  verdict, and `$GITHUB_OUTPUT` set and unset;
- the `0.1.0` case (§2.4): a temporary repository whose commit raises `0.0.1` to `0.1.0` and adds its
  section, then a later commit that doesn't change the version: `bump` on the first says bump with
  `version=0.1.0` and `tag=v0.1.0`, and on the later one says not a bump. (Not on this repository's own
  history: CI's checkout is shallow.)

**Workflow tests** (`tests/test_workflows.py`, PyYAML, with `on:` read as `True`):
- the workflows that run on `push` to `main` (whose `push.branches` holds `main`; `release.yml`'s
  `push: tags` doesn't count), by `name`, equal
  `auto-release.yml`'s `workflow_run.workflows` and `REQUIRED_WORKFLOWS`, and each has exactly one job,
  whose id equals the workflow's name (the required check names on `main` are those job names);
- `auto-release.yml` has no `pull_request` or `pull_request_target` trigger, top-level `permissions: {}`,
  and the only job with `contents: write` is the one that uses `release.yml`;
- `release.yml` has top-level `permissions: {}`;
- `version-check.yml` uses `pull_request`, never `pull_request_target`, and its job id is `version-check`.

**Lint:** `actionlint` with ShellCheck, and `zizmor`, in the gates (§7).

**Before the merge** (in the plan's last task, from the worktree, with full history): `release_check.py
bump 9441abd` says bump to `0.1.0`; `bump db53bf7` says not a bump; `runs-green` on the real runs list for
`9441abd` (`gh api`, read-only) says green.

**Can't be tested before the merge:** the real trigger, the token's permissions and the release. After the
merge the owner checks:
1. This PR's merge isn't a bump, so `auto-release` runs up to five times; each run ends with
   "nothing to release" or shows as cancelled (§2.2). That tests the trigger, the filters and `bump`.
2. The `0.1.0` dispatch (§2.4), dry run and then real: the first real test of the release path, on a real
   bump commit: the tag on `9441abd`, the release with the `[0.1.0]` section as notes, and HACS offering
   `0.1.0`.
3. The next bump PR is the end-to-end test of the automatic path: the tag on the merge commit, the release,
   and HACS offering the version.
