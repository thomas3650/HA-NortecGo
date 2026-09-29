# Tag and publish a release when a merged PR bumps the version — design

Date: 2026-09-29 · Branch: `process/auto-release` · Issue: #64

## Goal

- **What:** once CI has passed on `main` for a commit that bumps the version, a workflow tags that commit
  `v<version>` and publishes the GitHub release, with no manual step. A pull request check makes sure that a
  version change comes with its changelog section.
- **Why:** today the owner tags every release by hand after merging the bump PR (D10). The bump PR already
  holds everything a release needs, so the tag is a step that can be forgotten or put on the wrong commit.
- **Not in this work:** bumping the version automatically (the bump PR stays a deliberate PR the owner
  merges), bumping `pynortecgo` (#49), and changes to GitHub settings (branch protection, required checks).
- **Done when:** a merged PR that bumps the version produces the tag and the GitHub release without a
  manual step, and HACS offers the new version; the gates pass; `docs/releasing.md` and the decision log are
  updated.

## Decisions

Proposed by the team lead, backed by the PO, and escalated to the owner on issue #64 (2026-09-29).

| Topic | Decision |
|---|---|
| Trigger | A new `auto-release.yml`, run by `workflow_run` on each of the five workflows that are required checks on `main` (`lint`, `tests`, `hassfest`, `hacs`, `gitleaks`). It acts only on a successful `push` run on `main` from this repository, and only once all five checks have passed on that commit. The workflows aren't merged into one (§2.1) |
| Release path | `release.yml` gains `workflow_call`, and `auto-release.yml` calls it as a reusable workflow. There is one release code path, and the write permission needed is `contents: write` only: no `actions: write`, no `gh workflow run` |
| What is a bump | The version at the commit is higher (semver) than at its first parent, and the same commit adds the `## [X.Y.Z]` changelog heading, with a non-empty section. Anything else, a revert to an older version included, releases nothing |
| Older versions | The automation never back-fills. A version whose bump commit merged before this work (`0.1.0`) is tagged by hand, as today (§5) |
| Repeats | A run for a commit whose tag already points at it and whose release exists does nothing. A tag of that name on another commit fails the run. No second release is ever created |
| Fallback | `workflow_dispatch` on `auto-release.yml`, with a `sha` and a `dry_run` input (default `true`); the manual tag push stays as the last fallback |
| PR check | A new `version-check.yml` on `pull_request` (never `pull_request_target`), skipped for drafts. It isn't a required check; making it one is the owner's GitHub setting (§6) |
| Lint | `actionlint` and `zizmor` join the gates, as `uv` dev dependencies, a pre-commit hook and a step in `lint.yml` |
| Decision log | D39, which supersedes the manual tag in D10: D10's status becomes `active; the manual tag superseded by D39` |
| Process | Full path (spec, plan, `full-reviewer`); no D25 ruling |

Facts used, public-safe:

- A tag or release created with `GITHUB_TOKEN` doesn't start other workflows (so a tag push from the
  workflow wouldn't run `release.yml`'s `push: tags` trigger). `workflow_dispatch` and `workflow_call` are
  not limited that way.
- A `workflow_dispatch` run uses the workflow file as it is at the ref it runs on, so a tag on a commit from
  before this work can't be dispatched into a `release.yml` that has the new trigger.
- A `workflow_run` run uses the workflow file from the default branch, and in it `GITHUB_SHA` and
  `github.ref` are the default branch's head, not the commit the triggering run tested. That commit is
  `github.event.workflow_run.head_sha`.
- `workflow_run` fires once per completed triggering run; there is no "all of these finished" trigger.
- The repository has no rulesets, so nothing stops the workflow creating a tag. The default workflow
  token is read-only, so each job states its permissions.
- `gh release create <tag> --target <sha>` creates the tag on that commit if it doesn't exist.

## 1. Files

| File | Change |
|---|---|
| `scripts/release_check.py` | New, stdlib only: the version, changelog and check rules (§3) |
| `.github/workflows/auto-release.yml` | New (§2) |
| `.github/workflows/release.yml` | `workflow_call` inputs, checkout at the given commit, no second release (§4) |
| `.github/workflows/version-check.yml` | New (§6) |
| `.github/workflows/lint.yml` | `actionlint` and `zizmor` steps (§7) |
| Other workflows | Only what `zizmor` asks for (§7) |
| `.pre-commit-config.yaml` | An `actionlint` and a `zizmor` hook (§7) |
| `pyproject.toml`, `uv.lock` | `actionlint-py` and `zizmor` in the dev group; `scripts` in mypy's files (§7) |
| `CLAUDE.md` | The lint command in *Commands* gains the two linters (§7) |
| `docs/releasing.md` | §5 |
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
  workflow_dispatch:
    inputs:
      sha: {description: "A commit on main that bumps the version", required: true}
      dry_run: {type: boolean, default: true}
```

Merging the five workflows into one `ci.yml` would give a single trigger, but it restructures CI and the
required checks; triggering on all five and letting the last one to finish do the work keeps CI as it is.

A `workflow_run` run continues only if all of these hold, checked in the job's `if:`:

- `github.event.workflow_run.conclusion == 'success'`;
- `github.event.workflow_run.event == 'push'` (never a PR or scheduled run);
- `github.event.workflow_run.head_branch == 'main'`;
- `github.event.workflow_run.head_repository.full_name == github.repository`.

A `workflow_dispatch` run continues only if `sha` is a commit on `main` (`git merge-base --is-ancestor`).

**The commit.** Every read, checkout and tag target uses the commit the triggering run tested,
`github.event.workflow_run.head_sha`, or the `sha` input for a dispatch; never `GITHUB_SHA` or
`github.ref`. Event values reach `run:` steps through `env:`, never by `${{ }}` inside the script.

**Concurrency:** one group per commit (`auto-release-<commit>`), `cancel-in-progress: false`, so the
runs for one commit follow each other and a later one sees what an earlier one did.

### 2.2 Jobs

1. **`decide`** (`permissions: contents: read`, `actions: read`, `checks: read`):
   - checks out `main` with full history and `persist-credentials: false` (only merged code runs, never a
     PR's);
   - asks `release_check.py bump <commit>` (§3) whether the commit is a bump; if not, logs
     `v<version> unchanged: nothing to release` (or why it isn't a bump) and ends with success;
   - reads the commit's check runs (`gh api repos/<repo>/commits/<commit>/check-runs`, the latest run
     per name) and asks `release_check.py checks-green` (§3) whether all five required checks passed; if
     not, logs which ones are missing or not green, and ends with success (a later run will see them);
   - looks up the tag `v<version>`: missing is fine; present on this commit is fine; present on another
     commit fails the run with both commits in the log. An annotated tag is followed to its commit;
   - outputs `version`, `tag` and `release: true|false`.
   In a dry run it logs what it would do and outputs `release: false`.
2. **`release`** (`needs: decide`, `if: needs.decide.outputs.release == 'true'`,
   `permissions: contents: write`): `uses: ./.github/workflows/release.yml` with `tag` and `sha`.

The token that can write never reaches a job that runs a script from the repository other than
`release.yml`'s own steps (§4), and those run on the merged commit.

## 3. `scripts/release_check.py`

Stdlib only, run with `python3` (no `uv sync` in the workflows that call it). Pure functions, a thin CLI,
and every branch unit tested (§9).

- **Versions:** parses `X.Y.Z` with an optional `-<pre-release>` suffix, and compares them by the semver
  precedence rules (a pre-release is lower than its release; pre-release identifiers compare by number or
  text). An unparseable version is an error.
- **Changelog section:** the text between `## [X.Y.Z]` and the next `## [` heading (the same rule as
  `release.yml`'s `awk`); missing and blank-only are both "no section".
- **Bump:** given the manifest and changelog at a commit and at its first parent, the commit is a bump when
  the version is higher, the changelog has a non-empty section for it, and the parent's changelog doesn't
  have that heading.
- **Checks green:** given the check runs JSON and the required names, all required names are present with
  conclusion `success`. The required names are a constant in the script, `REQUIRED_CHECKS`.
- **CLI:**
  - `bump <commit>`: reads both versions with `git show`, prints the verdict, and writes `version=`,
    `tag=` and `bump=true|false` to `$GITHUB_OUTPUT` when it is set. Exit 0 for "bump" and "not a bump";
    non-zero only for an error (unreadable manifest, bad version).
  - `checks-green`: reads the check runs JSON on stdin; exit 0 when green, 1 when not, listing the
    missing and failed names.
  - `pr-check <base> <head>`: §6.

## 4. `release.yml`

- **Triggers:** `push: tags: ["v*"]` stays (the manual fallback); `workflow_call` adds inputs `tag` and
  `sha` (both required strings).
- **The tag and commit:** from the inputs when called, otherwise `GITHUB_REF_NAME` and `GITHUB_SHA`. They
  reach the steps through `env:`. Checkout is at that commit, with `persist-credentials: false`.
- **Checks:** unchanged (the tag equals `v` plus the manifest version at that commit; the changelog section
  is non-empty).
- **No second release:** if `gh release view <tag>` finds the release, the job logs it and ends with
  success.
- **Create:** `gh release create <tag> --target <sha> --title <tag> --notes-file notes.md`, plus
  `--prerelease` as today. For a pushed tag, `--target` is the commit the tag points at, so nothing changes.
- **Permissions:** `contents: write`, as today. When called, it can't exceed what the caller job gives.

## 5. `docs/releasing.md`

- **The bump PR is the release:** the three bump steps stay; merging the PR releases it. After CI passes on
  `main`, `auto-release.yml` tags the merge commit and publishes the release. What counts as a bump is the
  rule from §3, in words.
- **What to check after a merge:** the `auto-release` run for the merge commit, the tag, the release, and
  that HACS offers it.
- **Fallbacks:** the `workflow_dispatch` run (dry run first), and then the manual tag, which stays the only
  way for a version whose bump merged before this work (v0.1.0, if the owner hasn't tagged it yet) or for a
  commit the rule doesn't count as a bump.
- **What `release.yml` checks:** add the "no second release" rule and the two ways it starts.
- **Required checks:** the list in `auto-release.yml`'s trigger and in `REQUIRED_CHECKS` must follow the
  required checks on `main`; `tests/test_workflows.py` catches a workflow added or renamed in the repo,
  but not a change made only in the GitHub settings.
- The *Tagging (owner only)* heading becomes *Tagging by hand (fallback)*.

## 6. `version-check.yml`

- **On:** `pull_request` with `types: [opened, synchronize, reopened, ready_for_review]`; the job has
  `if: github.event.pull_request.draft == false`. `permissions: contents: read`.
- **Does:** checks out the PR (full history, `persist-credentials: false`) and runs
  `release_check.py pr-check <base sha> <head sha>`:
  - version unchanged: passes, nothing required;
  - version changed: it must be higher than the base's, and the changelog must have a non-empty section for
    it; otherwise it fails and says which.
- **Required check:** not made one here. The owner may add `version-check` to `main`'s required checks
  after the merge; it is a GitHub setting (way of working §6). A check skipped for a draft counts as passed.

## 7. Workflow linting

- **Tools:** `actionlint-py` (the `actionlint` binary) and `zizmor`, in the `uv` dev group.
- **Gate:** `lint.yml` runs `uv run actionlint` and `uv run zizmor --offline .github/workflows`;
  `CLAUDE.md`'s lint command gains the same two, so a local gate run catches what CI would.
- **Pre-commit:** local hooks with the same commands, limited to `^\.github/workflows/`.
- **zizmor findings:** fixed where the fix is small and safe (for example `persist-credentials: false` on a
  checkout that doesn't push). `auto-release.yml`'s `workflow_run` trigger is flagged by design; that
  finding is ignored inline with the reason (only `main` push runs, no PR code, §2.1).
- **mypy:** `scripts` joins `files`, so the script is type-checked under `strict`.

## 8. Decision log

```markdown
### D39: A merged bump PR is the release
- **Date:** 2026-09-29 · **Status:** active
- **Decision:** When CI passes on `main` for a commit that raises the version and adds its changelog
  section, `auto-release.yml` tags that commit and publishes the release through `release.yml`. Tagging by
  hand stays as a fallback, and for versions whose bump merged earlier.
- **Why:** The bump PR already holds everything a release needs; the owner still decides when a release goes
  out by merging it.
- **Source:** [auto-release spec](superpowers/specs/2026-09-29-auto-release-design.md), Decisions and §2
```

D10's status becomes `active; the manual tag superseded by D39`.

## 9. Tests and verification

**Unit tests** (`tests/test_release_check.py`): version parsing and precedence (release, pre-release,
equal, lower, bad input); the changelog section (present, missing, blank, last section in the file); bump
(raised with section, raised without section, heading already in the parent, unchanged, lowered, a revert
to an older version); checks green (all green, one missing, one failed, a scheduled rerun that is newer);
the CLI's outputs and exit codes, with `git` run in a temporary repository.

**Workflow tests** (`tests/test_workflows.py`, PyYAML parse):
- the set of workflows that run on `push` to `main` (excluding `auto-release`), by `name`, equals
  `auto-release.yml`'s `workflow_run.workflows` and `REQUIRED_CHECKS`;
- `auto-release.yml` has no `pull_request` or `pull_request_target` trigger, and the only job with
  `contents: write` is the one that calls `release.yml`;
- `version-check.yml` uses `pull_request`, never `pull_request_target`.

**Lint:** `actionlint` and `zizmor` in the gates (§7).

**Can't be tested before the merge:** the real trigger, the token's permissions and the release. After the
merge the owner checks:
1. This PR's merge isn't a bump, so `auto-release` runs (up to five times) and each run ends with a
   "nothing to release" line. That tests the trigger, the filters and `bump`.
2. Optionally, a dispatch dry run on the merge commit, which logs the same.
3. The next bump PR is the end-to-end test: the tag on the merge commit, the release with the changelog
   section as notes, and HACS offering the version.
