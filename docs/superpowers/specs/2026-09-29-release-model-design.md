# A merged PR releases itself, by its title — design

Date: 2026-09-29 · Branch: `process/release-model` · Issues: #68, #67

## Goal

- **What:** the PR title's type decides whether a merge is a release, and at which level. A releasing PR
  carries its own version bump and changelog move, made by a script just before the PR is marked ready, and
  `auto-release.yml` (D39) publishes it on merge. A PR check makes sure the title, the version and the
  changelog agree. A merged PR is the only way a release happens: the hand-started `auto-release` run and
  the hand-pushed tag go.
- **Why:** today a release needs a second, hand-made bump PR, and user-visible changes wait under
  *Unreleased* until someone opens one. The owner's client library repo already releases every releasing PR
  this way, and the owner wants the same model here.
- **Not in this work:** pre-releases, and GitHub settings (making `version-check` required stays the
  owner's one-time step in `docs/releasing.md`).
- **Before the merge:** the owner releases `0.1.0` with the one `auto-release` dispatch that
  `docs/releasing.md` describes today (its bump, `9441abd`, merged before the automation). This PR removes
  that dispatch, so it can't be done after.
- **Done when:** a `feat`, `fix` or `perf` PR, bumped with the script, is released on merge with no further
  step; a PR whose title, version and changelog disagree fails `version-check`; the docs, the decision log
  and the flow (§1, §4, §6, §8 of `way-of-working.md`, and the team lead agent) describe this model;
  neither `auto-release.yml` nor `release.yml` can be started by hand or by a tag push; the gates pass. #67
  (make the real dispatch owner only) is closed by this PR, since the dispatch no longer exists.

## Decisions

Approved by the owner in the brainstorm (issue #68, 2026-09-29).

| Topic | Decision |
|---|---|
| Model | Every PR whose title is `feat`, `fix` or `perf` is a release; other PRs release nothing. No separate bump PRs |
| Level | From the title (§2): `fix`, `perf` patch; `feat` minor; `!` minor on 0.x, major from 1.0; `refactor`, `docs`, `chore`, `ci`, `test`, `process` none |
| Changelog | Hand-written under *Unreleased* as today; the bump moves the entries under the new version, dated the bump day (UTC) |
| Who bumps | The controller, as part of §1 step 10, just before `gh pr ready`. In the PO flow, the team lead, as its last step before `branch ready` |
| Two PRs at once | The second merges `origin/main` in (no rebase, no force-push) and reruns the bump |
| Only PRs release | `auto-release.yml` loses `workflow_dispatch` (and its `sha` and `dry_run` inputs); `release.yml` loses `push: tags` and runs only when `auto-release.yml` calls it. No tag is pushed by hand. `0.1.0` is released by the owner's dispatch before this merges |
| A failed release | Re-run the failed run (GitHub's *Re-run failed jobs*, or `gh run rerun <id> --failed`), the owner's action; a flaky required workflow on `main` is re-run the same way, which starts `auto-release` again. A version that is never released stays in `CHANGELOG.md` as history; the next releasing PR carries only its own entries |
| Pre-releases | None. The bump only makes `X.Y.Z` versions, so `release.yml`'s pre-release marking (for `0.0.x` and `-` versions) goes |
| Tooling | New rules and a `release-pr` subcommand in `scripts/release_check.py` (one home for the release rules); `version-check.yml` passes it the title. `auto-release.yml`'s bump rule is unchanged: a bumped PR's merge commit is a bump by it |
| Dependabot | Titles become `chore(deps): …` (non-releasing) |
| Decision log | D40; D39's bump PR and fallbacks superseded by it (§7) |
| Process | Full path (spec, plan, `full-reviewer`) |

Facts used:

- The repo allows squash merges only, with the PR title as the commit subject and `(#n)` appended. The merge commit of a
  bumped PR raises the version and adds its changelog section against its first parent, which is what
  `release_check.py bump` counts as a bump.
- Every past PR title here is `feat:`, `fix:`, `docs:`, `chore:` or `process:`, with an optional
  `(#n)` list before the `(#n)` of the PR.
- `.github/dependabot.yml` sets no commit-message prefix, so Dependabot's titles today start `Bump …`, which
  the title rule would refuse. `commit-message: {prefix: chore, include: scope}` makes them `chore(deps): …`.
- `version-check.yml` already runs on `edited` (a retitle) and skips drafts, and its job and check name is
  `version-check`. It isn't a required check on `main` yet (only `lint`, `tests`, `hassfest`, `hacs`,
  `gitleaks` are, checked 2026-09-29); the owner adds it (D39's follow-up in `docs/releasing.md`).
- There is no `v0.1.0` tag or release yet; `v0.0.1` is the only one.
- Re-running a `workflow_run`-started run replays the same event, so a re-run of `auto-release` acts on the
  same commit; a re-run of a required workflow's `push` run on `main` completes it again and starts
  `auto-release` again.
- A PR title is user-controlled text: it goes to the script through an `env:` variable, never through
  `${{ }}` inside `run:` (zizmor's template-injection rule).
- `CHANGELOG.md` has a preamble, `## [Unreleased]`, and dated `## [X.Y.Z] - YYYY-MM-DD` sections with
  Keep a Changelog `###` groups; it has no link references at the end.
- Two releasing PRs based on the same version always conflict on the `version` line of `manifest.json` once
  the first merges.

## 1. Files

| File | Change |
|---|---|
| `scripts/release_check.py` | Titles, next version, changelog parsing and bump, the widened `pr-check`, the new `release-pr` (§3) |
| `.github/workflows/version-check.yml` | Passes the PR title (§4) |
| `.github/workflows/auto-release.yml` | No `workflow_dispatch` (§4) |
| `.github/workflows/release.yml` | No `push: tags`, no pre-release marking (§4) |
| `.github/dependabot.yml` | `commit-message` for both ecosystems (§5) |
| `docs/releasing.md` | Rewritten around titles and the bump step (§6) |
| `docs/way-of-working.md` | §1 step 10, §4, §6, §8 (§6) |
| `.claude/agents/team-lead.md` | The bump before `branch ready` in PO mode (§6) |
| `CLAUDE.md` | The changelog rule points to the titles (§6) |
| `docs/README.md` | The `releasing.md` row (§6) |
| `docs/decisions.md` | D40, and D39's status (§7) |
| `tests/test_release_check.py`, `tests/test_workflows.py` | §8 |

No `CHANGELOG.md` entry and no version change: this PR is titled `process: …`, so under its own rule it
changes neither.

## 2. The rules

**Titles.** A PR title is `type(scope)!: text`; the scope and `!` are optional. `type` is one of:

| Type | Release |
|---|---|
| `fix`, `perf` | patch |
| `feat` | minor |
| `feat!`, `fix!`, `perf!` (breaking) | minor while the major version is 0, major from 1.0 |
| `refactor`, `docs`, `chore`, `ci`, `test`, `process` | none |

- `!` on a non-releasing type is invalid: a breaking change is a `feat`, `fix` or `perf`.
- A user-visible change is a `feat`, `fix` or `perf`, and has a changelog entry (CLAUDE.md). A change that
  isn't user-visible has a non-releasing type.
- GitHub's *Revert* button titles a PR `Revert "…"`: it is retitled, for example `fix: revert …`.
- Only `!` marks a breaking change; a `BREAKING CHANGE:` footer isn't read.

**A releasing PR**, compared with its merge base:
- `version` in `manifest.json` is exactly the next version after the base's, by the title's level. The
  base's version is `X.Y.Z`; a pre-release base is an error.
- The first changelog section is `## [Unreleased]`, and it is empty.
- The second is `## [<next>] - YYYY-MM-DD`, with entries.
- No other version section is added.

**A non-releasing PR** changes neither `version` nor `CHANGELOG.md`. The one exception is a
`docs(changelog): …` PR, which may fix the text of released sections, but not add or remove a section,
change a heading, or change *Unreleased*.

**Released sections** (the base's version sections) are never removed, and their headings and bodies never
change, apart from that exception.

## 3. `scripts/release_check.py`

Stays stdlib only. The existing `bump`, `runs-green` and `tag-commit` subcommands and their rules are
unchanged. New:

- **Title parsing** into type, scope and breaking, refusing a malformed title, an unknown type, and `!` on a
  non-releasing type, each with a message naming `docs/releasing.md`.
- **Next version** from an `X.Y.Z` base and a title.
- **Changelog parsing** into a preamble and sections (name, date, heading line, body), refusing a heading
  that isn't `## [Unreleased]` or `## [X.Y.Z] - YYYY-MM-DD`, and a section name that appears twice.
  Rendering what it parsed gives back the same text for the current `CHANGELOG.md`.
- **The changelog bump:** the branch's own version sections (those not in `origin/main`'s changelog) and
  *Unreleased* are merged into one body (free text first, then the `###` groups in Keep a Changelog order:
  Added, Changed, Deprecated, Removed, Fixed, Security, then any other; earlier sections first within a
  group), placed under `## [<next>] - <today, UTC>`, and *Unreleased* is left empty above it. An empty body
  is an error.
- **`pr-check --title TITLE BASE HEAD`** (replacing today's `pr-check BASE HEAD`): reads both files at both
  commits with `git show`, prints one line per broken rule of §2, and exits 1 if there is any, 0 if none,
  2 on an error, like the other subcommands.
- **`release-pr --title TITLE`**: refuses a non-releasing title (exit 1, saying there is nothing to bump);
  runs `git fetch origin main`; takes the next version from `origin/main`'s `manifest.json`; writes the new
  `version` into the working tree's `manifest.json` (changing only that value, so the file's formatting
  stays) and the bumped `CHANGELOG.md`; prints the version. It commits nothing. Because it folds the
  branch's own sections back first, rerunning it after a retitle or a merge of `main` gives the right
  result.

## 4. The workflows

**`version-check.yml`.** The job keeps its id and name (`version-check`), the `pull_request` trigger with its types (including
`edited`), the draft skip, the checkout of the head, and the merge-base comparison. The step gets the title
through `env: PR_TITLE: ${{ github.event.pull_request.title }}` and runs
`release_check.py pr-check --title "$PR_TITLE" "$base" "$HEAD_SHA"`. The step's name becomes "Title,
version and changelog agree".

**`auto-release.yml`** drops `workflow_dispatch` and what serves only it: the `workflow_dispatch` half of
the `decide` job's `if:`, the `inputs.sha` branch of *The commit* step (it takes
`github.event.workflow_run.head_sha`, and keeps the check that the commit is on `main`), the dry run in *The
tag* step, and the `'dispatch'` and `inputs.sha` fallbacks in the concurrency group. The trigger, the
filters, the bump and runs checks, the tag check and the call to `release.yml` stay as they are.

**`release.yml`** drops `push: tags`, so it runs only through `workflow_call`: the checkout takes
`inputs.sha`, and the tag is `inputs.tag` (the `github.ref` and `github.ref_name` fallbacks go). The
pre-release marking goes; every release is a full one. The other checks (tag equals the manifest version,
the changelog section, an existing release, the tag's commit) stay.

## 5. Dependabot

Both entries in `.github/dependabot.yml` (`github-actions` and `uv`) get
`commit-message: {prefix: chore, include: scope}`, so their PR titles are `chore(deps): …`. A dependency
bump users should get is retitled `feat` or `fix` and bumped. (`pynortecgo` bumps are hand-made PRs with
their own checklist in `docs/releasing.md`, titled by what they change for users.)

## 6. The flow and the docs

**The bump step** (in `docs/releasing.md`, pointed to from everywhere else): for a releasing title, run
`uv run python scripts/release_check.py release-pr --title "<PR title>"`, commit `chore: release X.Y.Z`,
and push.
- After a changelog change: put it under *Unreleased* and rerun. After a retitle to another releasing type:
  rerun. After a retitle to a non-releasing type: `git revert` the bump commit(s) and remove the
  *Unreleased* entries.
- **Two releasing PRs at once:** after the first merges, merge `origin/main` into the second (no rebase: it
  needs a force-push). Resolve `manifest.json` to `main`'s side; in `CHANGELOG.md` keep `main`'s new
  section as it is and the branch's own section too. Commit the merge, rerun `release-pr` (it folds the
  branch's section back and bumps from `main`'s new version), commit and push.

**`docs/releasing.md`** is rewritten: versioning (no pre-releases), PR titles (§2's table and rules), a
releasing PR and the bump step, two PRs at once, fixing an old changelog entry (`docs(changelog)`), what
happens on merge (the existing `auto-release` text, with "a bump PR" replaced by "a releasing PR"), *When a
release fails* (the re-runs in the Decisions table, the owner's action), and the sections that still hold
(*What `release.yml` checks*, without the tag push and the pre-release marking; *Required workflows*;
*Bumping `pynortecgo`*; *Bumping Home Assistant*). *Fallbacks* and *Tagging by hand* go. *Once, after the
auto-release PR merges* keeps only the steps not done yet when this merges (`uv sync` in every checkout, and
the owner adding `version-check` to the required checks), since `0.1.0` is released before. The
`pynortecgo` and Home Assistant bump sections say how to title such a PR.

**`docs/way-of-working.md`:**
- §1 step 6: the draft PR's title follows `docs/releasing.md`'s title rules.
- §1 step 10: for a releasing title, the bump step runs after `scripts/smoke` passes and before the PR
  description is updated and `gh pr ready`.
- §4: a trivial or D25 PR with a releasing title is bumped before it is opened.
- §6: the controller's *may* column gains "Run the bump step in a releasing PR"; the *may not* column's
  "Tag releases" becomes "Tag releases, or re-run a workflow run on `main`" (a re-run of a required
  workflow or of `auto-release` can publish).
- §8: the team lead runs the bump step (for a releasing title) as its last step before `branch ready`; the
  PO's acceptance check (step 4 of *From branch ready to PR ready*) includes the title's type and level; a
  merge conflict on a ready PR is resolved by the team lead as in *Two releasing PRs at once*.

**`.claude/agents/team-lead.md`:** in PO mode, "step 10 is the PO's" gains "except the bump step, which you
run before `branch ready`".

**`CLAUDE.md`:** the rule "Add a `CHANGELOG.md` entry under *Unreleased* for user-visible changes" gains
"and title the PR `feat`, `fix` or `perf` (`docs/releasing.md`)".

**`docs/README.md`:** the `releasing.md` row reads "PR titles and the bump step, the automatic release,
fallbacks and tagging by hand, what `release.yml` checks".

## 7. Decision log

### D40: A merged PR releases itself, by its title
- **Date:** 2026-09-29 · **Status:** active
- **Decision:** The PR title's type decides the release (`fix`/`perf` patch, `feat` minor, `!` minor on 0.x
  and major from 1.0, other types none). A releasing PR carries its own bump from `release_check.py
  release-pr`, run before it is marked ready; `auto-release.yml` publishes it on merge, as D39 set up. A
  merged PR is the only way to release: no dispatch, no tag by hand; a failed release is re-run.
- **Why:** a separate bump PR was a manual step that left changes waiting under *Unreleased*, and every
  release should come from a reviewed, merged PR; a version conflict between two ready PRs is accepted as
  the price.
- **Source:** [release model spec](superpowers/specs/2026-09-29-release-model-design.md), Decisions

D39's status becomes `active; the bump PR and the fallbacks superseded by D40` (its automatic tag on a
green `main` stays).

## 8. Tests and verification

**Unit tests** (`tests/test_release_check.py`, table-driven where it fits):
- titles: each type, with and without a scope, with `!`, with a `(#n)` suffix; malformed, unknown type,
  `!` on a non-releasing type, `Revert "…"`;
- next version: patch, minor, `!` on 0.x, `!` from 1.0, a pre-release base;
- changelog parsing: the current `CHANGELOG.md` round-trips unchanged; a bad heading; a duplicate section;
- the changelog bump: from *Unreleased*; with the branch's own earlier section folded back (group order and
  entry order); after a merge of `main` (both sections present, `main`'s kept); an empty body;
- `pr-check`: each problem of §2 on its own, and a clean releasing and a clean non-releasing PR, including
  a `docs(changelog)` fix and each thing it may not do;
- `release-pr` end to end in a temporary git repository with an `origin`: the bump, a rerun, a rerun after a
  retitle from `fix` to `feat`, a non-releasing title, and that `manifest.json` changes only in `version`.

**Workflow tests** (`tests/test_workflows.py`): `version-check.yml` passes the title through `env`, and no
`run:` in it contains `github.event.pull_request.title`; `auto-release.yml`'s only trigger is
`workflow_run`, and no workflow uses `inputs.dry_run`; `release.yml`'s only trigger is `workflow_call`, and
it has no `--prerelease`; the existing checks are updated to match (the triggers, and
`inputs.sha || github.ref` becoming `inputs.sha`) and otherwise stay.

**Lint:** the gates, including `actionlint` and `zizmor`.

**Before the merge:** the owner's `0.1.0` dispatch has run, and `v0.1.0` and its release exist on
`9441abd` (the controller checks read-only with `gh release view v0.1.0`). Then, in the plan's last task: `pr-check` on this branch with its own title says it is clean;
`release-pr` with a `fix:` title in a scratch clone of this branch writes `0.1.1` and a dated section, and
the result passes `pr-check` with that title.
