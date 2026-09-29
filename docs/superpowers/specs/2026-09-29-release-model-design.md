# A merged PR releases itself, by its title — design

Date: 2026-09-29 · Branch: `process/release-model` · Issues: #68, #67

## Goal

- **What:** the PR title's type decides whether a merge is a release, and at which level. A releasing PR
  carries its own version bump and changelog move, made by a script just before the PR is marked ready, and
  `auto-release.yml` (D39) publishes it on merge. A PR check makes sure the title, the version and the
  changelog agree. A merged PR is the only way a release happens: the hand-started `auto-release` run goes,
  and a tag pushed by hand no longer publishes anything on its own.
- **Why:** today a release needs a second, hand-made bump PR, and user-visible changes wait under
  *Unreleased* until someone opens one. The owner's client library repo already releases every releasing PR
  this way, and the owner wants the same model here.
- **Not in this work:** pre-releases, and GitHub settings (making `version-check` required stays the
  owner's one-time step in `docs/releasing.md`).
- **Done before this work:** `0.1.0` (bump `9441abd`, merged before the automation) is released, on
  2026-09-29, with the owner's OK. The `auto-release` dispatch hit the workflow-scope limit (Facts), so the
  tag was pushed by hand and `release.yml`'s `push: tags` trigger published it. Nothing older is left to
  release, so the dispatch and the tag trigger can go.
- **Done when:** a `feat`, `fix` or `perf` PR, bumped with the script, is released on merge with no further
  step; a PR whose title, version and changelog disagree fails `version-check`; the docs, the decision log,
  the PR template and the flow (§1, §4, §6, §8 of `way-of-working.md`, and the PO and team lead agents)
  describe this model; neither `auto-release.yml` nor `release.yml` can be started by hand or by a tag push;
  the gates pass. #67 (make the real dispatch owner only) is closed by this PR, since the dispatch no longer
  exists.

## Decisions

Approved by the owner in the brainstorm (issue #68, 2026-09-29).

| Topic | Decision |
|---|---|
| Model | Every PR whose title is `feat`, `fix` or `perf` is a release; other PRs release nothing. No separate bump PRs |
| Level | From the title (§2): `fix`, `perf` patch; `feat` minor; `!` minor on 0.x, major from 1.0; `refactor`, `docs`, `chore`, `ci`, `test`, `process` none |
| Changelog | Hand-written under *Unreleased* as today; the bump moves the entries under the new version, dated the bump day (UTC) |
| Who bumps | The controller, as part of §1 step 10, just before `gh pr ready`. In the PO flow, the team lead, as its last step before `branch ready` |
| Two PRs at once | The second merges `origin/main` in (no rebase, no force-push), puts its entries back under *Unreleased*, and reruns the bump (§6) |
| Only PRs release | `auto-release.yml` loses `workflow_dispatch` (and its `sha` and `dry_run` inputs); `release.yml` loses `push: tags` and runs only when `auto-release.yml` calls it, so a pushed tag publishes nothing on its own |
| A failed release | Re-run the failed run (GitHub's *Re-run failed jobs*, or `gh run rerun <id> --failed`), the owner's action; a flaky required workflow on `main` is re-run the same way, which starts `auto-release` again. A version that is never released stays in `CHANGELOG.md` as history; the next releasing PR carries only its own entries |
| The workflow-scope limit | If `main` has moved on to a commit with other workflow files before the releasing commit is tagged (a PR that changes `.github/workflows/` merged within the few minutes of CI), the release fails with HTTP 403 and a re-run fails the same way. The recovery, the owner's action: push the tag on the releasing commit by hand (`git tag vX.Y.Z <sha>`, `git push origin vX.Y.Z`), then re-run the failed `auto-release` run, which finds the tag on that commit and publishes. No GitHub App token or secret for this rare case |
| Re-runs and tags | Owner only (or the controller when the owner says so for that release, as for `0.1.0`): re-running a workflow run on `main` and pushing a tag, since either can publish. The PO and team leads never do either |
| Pre-releases | None. The bump only makes `X.Y.Z` versions, so `release.yml`'s pre-release marking (for `0.0.x` and `-` versions) goes |
| Tooling | New rules and a `release-pr` subcommand in `scripts/release_check.py` (one home for the release rules); `version-check.yml` passes it the title. `auto-release.yml`'s bump rule is unchanged: a bumped PR's merge commit is a bump by it |
| Dependabot | Titles become `chore(deps): …` (non-releasing) |
| Decision log | D40; D39's bump PR and fallbacks, and what was left of D10, superseded by it (§7) |
| Process | Full path (spec, plan, `full-reviewer`) |

Facts used:

- The repo allows squash merges only, with the PR title as the commit subject and `(#n)` appended. The
  merge commit of a bumped PR raises the version and adds its changelog section against its first parent,
  which is what `release_check.py bump` counts as a bump.
- Every past PR title here is `feat:`, `fix:`, `docs:`, `chore:` or `process:`, with an optional
  `(#n)` list before the `(#n)` of the PR.
- `.github/dependabot.yml` sets no commit-message prefix, so Dependabot's titles today start `Bump …`, which
  the title rule would refuse. `commit-message: {prefix: chore, include: scope}` makes them `chore(deps): …`.
- `version-check.yml` already runs on `edited` (a retitle) and skips drafts, and its job and check name is
  `version-check`. It isn't a required check on `main` yet (only `lint`, `tests`, `hassfest`, `hacs`,
  `gitleaks` are, checked 2026-09-29); the owner adds it (D39's follow-up in `docs/releasing.md`).
- `main`'s branch protection has `strict: true`: a PR must be up to date with `main` before it merges, so a
  second releasing PR always takes in the first one's merge before its own can merge.
- Two releasing PRs from the same version both insert a different version section at the same place in
  `CHANGELOG.md`, so merging `main` into the second conflicts there. Their `version` lines don't conflict
  when both PRs have the same level (identical edits merge cleanly); the check (§2) catches the stale
  version.
- GitHub's *Update branch* button offers a merge and a rebase; the rebase rewrites the branch (a
  force-push).
- Creating a release whose tag doesn't exist yet, on a commit whose `.github/workflows/` differ from the
  default branch's head, needs the `workflows` permission, which a workflow's `GITHUB_TOKEN` can't have: the
  call fails with `HTTP 403: Resource not accessible by integration`, whatever `permissions:` says
  ([GitHub changelog, 2023-11-02](https://github.blog/changelog/2023-11-02-github-actions-enforcing-workflow-scope-when-creating-a-release/)).
  Seen here on 2026-09-29, when the `0.1.0` dispatch targeted `9441abd`, which is older than PR #65's
  workflow changes. Creating a release on a tag that already exists on the commit doesn't need it: the tag
  push by hand, then `release.yml`, published `0.1.0` that way.
- A releasing PR's merge commit is normally `main`'s head when `auto-release` runs, so the limit applies
  only when a later merge changed the workflows first.
- Re-running a `workflow_run`-started run replays the same event, so a re-run of `auto-release` acts on the
  same commit; a re-run of a required workflow's `push` run on `main` completes it again and starts
  `auto-release` again.
- A PR title is user-controlled text: it goes to the script through an `env:` variable, never through
  `${{ }}` inside `run:` (zizmor's template-injection rule).
- In an interactive zsh or bash, `!` inside double quotes starts a history expansion, so `--title "feat!: …"`
  typed by hand fails.
- `CHANGELOG.md` has a preamble, `## [Unreleased]`, and dated `## [X.Y.Z] - YYYY-MM-DD` sections with
  Keep a Changelog `###` groups; it has no link references at the end.
- There are no open PRs (2026-09-29).

## 1. Files

| File | Change |
|---|---|
| `scripts/release_check.py` | Titles, next version, changelog parsing and bump, the widened `pr-check`, the new `release-pr` (§3) |
| `.github/workflows/version-check.yml` | Passes the PR title (§4) |
| `.github/workflows/auto-release.yml` | No `workflow_dispatch` (§4) |
| `.github/workflows/release.yml` | No `push: tags`, no pre-release marking (§4) |
| `.github/dependabot.yml` | `commit-message` for both ecosystems (§5) |
| `.github/pull_request_template.md` | The title and bump items (§6) |
| `docs/releasing.md` | Rewritten around titles and the bump step (§6) |
| `docs/way-of-working.md` | §1 steps 2, 6 and 10, §4, §6, §8 (§6) |
| `.claude/agents/team-lead.md`, `.claude/agents/po.md` | The bump before `branch ready`; no re-runs or tags (§6) |
| `CLAUDE.md` | The changelog rule and the `scripts/` layout line (§6) |
| `docs/README.md` | The `releasing.md` row (§6) |
| `docs/decisions.md` | D40, and D39's and D10's status (§7) |
| `tests/test_release_check.py`, `tests/test_workflows.py` | §8 |

No `CHANGELOG.md` entry and no version change: this PR is titled `process: …`, so under its own rule it
changes neither.

## 2. The rules

**Titles.** A PR title matches `type(scope)!: text`:
- `type` is lowercase letters only, and one of the types in the table below;
- `(scope)` is optional, and is one or more characters other than `(`, `)` and whitespace;
- `!` is optional, and comes right before the colon;
- then exactly `: ` (a colon and one space) and a text that starts with a non-space character. The text may
  hold anything, including `(#n)` references.

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
- The title types are independent of the branch types in way-of-working §1 step 2: a `feat/…` branch may
  carry a `fix:` title if that's what it turns out to be.

**A releasing PR**, compared with its merge base with `main`:
- `version` in `manifest.json` is exactly the next version after the base's, by the title's level. The
  base's version is `X.Y.Z`; a pre-release base is an error.
- The first changelog section is `## [Unreleased]`, and it is empty.
- The second is `## [<next>] - YYYY-MM-DD`, with entries. Only the date's format is checked, not its value:
  the owner may merge days after the bump.
- No other version section is added.

**A non-releasing PR** changes neither `version` nor `CHANGELOG.md`. The one exception is a
`docs(changelog): …` PR, which may fix the text of released sections, but not add or remove a section,
change a heading, or change *Unreleased*.

**Released sections** (the base's version sections) are never removed, and their headings and bodies never
change, apart from that exception.

## 3. `scripts/release_check.py`

Stays stdlib only. The existing `bump`, `runs-green` and `tag-commit` subcommands and their rules are
unchanged. New:

- **Title parsing** into type, scope and breaking, by §2's grammar, refusing a malformed title, an unknown
  type, and `!` on a non-releasing type, each with a message naming `docs/releasing.md`.
- **Next version** from an `X.Y.Z` base and a title.
- **Changelog parsing** into a preamble and sections (name, date, heading line, body), refusing a heading
  that isn't `## [Unreleased]` or `## [X.Y.Z] - YYYY-MM-DD`, and a section name that appears twice (the
  message names *Two releasing PRs at once* in `docs/releasing.md`). Rendering what it parsed gives back the
  same text for the current `CHANGELOG.md`.
- **The changelog bump:** the branch's own version sections (those whose name isn't in `origin/main`'s
  changelog) and *Unreleased* are merged into one body: free text first, then the `###` groups in Keep a
  Changelog order (Added, Changed, Deprecated, Removed, Fixed, Security, then any other in the order first
  seen). Within the free text and within each group, the branch's own sections come first, oldest first
  (bottom of the file first), then *Unreleased*: the entries keep the order in which they were written. The
  body goes under `## [<next>] - <today, UTC>`, and *Unreleased* is left empty above it. An empty body is an
  error.
- **`pr-check --title=TITLE BASE HEAD`** (replacing today's `pr-check BASE HEAD`): reads both files at both
  commits with `git show`, prints one line per broken rule of §2, and exits 1 if there is any, 0 if none,
  2 on an error, like the other subcommands.
- **`release-pr --title=TITLE`**, in this order:
  1. refuses a non-releasing title (exit 1: nothing to bump);
  2. runs `git fetch origin main`, and refuses (exit 1: "merge origin/main into this branch first", naming
     *Two releasing PRs at once*) unless `origin/main` is an ancestor of `HEAD`, so the version it writes is
     the one `pr-check` expects against the merge base;
  3. takes the next version from `origin/main`'s `manifest.json`;
  4. writes the new `version` into the working tree's `manifest.json` (changing only that value, so the
     file's formatting and other keys stay) and the bumped `CHANGELOG.md`;
  5. prints the version.

  It commits nothing. Because it folds the branch's own sections back first, rerunning it after a retitle
  or a changelog change gives the right result.

## 4. The workflows

**`version-check.yml`.** The job keeps its id and name (`version-check`), the `pull_request` trigger with
its types (including `edited`), the draft skip, the checkout of the head, and the merge-base comparison.
The step gets the title through `env: PR_TITLE: ${{ github.event.pull_request.title }}` and runs
`release_check.py pr-check --title="$PR_TITLE" "$base" "$HEAD_SHA"` (with `=`, so a title that starts with
`-` isn't read as an option). The step's name becomes "Title, version and changelog agree".

**`auto-release.yml`** drops `workflow_dispatch` and what serves only it: the `workflow_dispatch` half of
the `decide` job's `if:`, the `inputs.sha` branch of *The commit* step (it takes
`github.event.workflow_run.head_sha`, and keeps the check that the commit is on `main`), the dry run in *The
tag* step, and the `'dispatch'` and `inputs.sha` fallbacks in the concurrency group. The trigger, the
`workflow_run` guard in the `if:`, the bump and runs checks, the tag check and the call to `release.yml`
stay as they are.

**`release.yml`** drops `push: tags`, so it runs only through `workflow_call`: the checkout takes
`inputs.sha`, and the tag is `inputs.tag` (the `github.ref` and `github.ref_name` fallbacks go). The
pre-release marking goes; every release is a full one. The other checks (tag equals the manifest version,
the changelog section, an existing release, the tag's commit) stay.

## 5. Dependabot

Both entries in `.github/dependabot.yml` (`github-actions` and `uv`) get
`commit-message: {prefix: chore, include: scope}`, so their PR titles are `chore(deps): …`. A dependency
bump users should get is retitled `feat` or `fix`, and the controller runs the bump step on its branch
(Dependabot then stops rebasing it, which is fine for a PR about to merge). (`pynortecgo` bumps are
hand-made PRs with their own checklist in `docs/releasing.md`, titled by what they change for users.)

## 6. The flow and the docs

**The bump step** (in `docs/releasing.md`, pointed to from everywhere else): for a releasing title, run

```bash
uv run python scripts/release_check.py release-pr --title="$(gh pr view --json title -q .title)"
```

(before the PR exists, for a trivial or D25 PR: the title in single quotes), commit `chore: release X.Y.Z`,
and push.
- After a changelog change: put it under *Unreleased* and rerun. After a retitle to another releasing type:
  rerun. After a retitle to a non-releasing type: make `version` in `manifest.json` and `CHANGELOG.md` equal
  `origin/main`'s again (only the `version` value, not the whole `manifest.json`, which a `pynortecgo` bump
  also changes), and commit.
- **Two releasing PRs at once:** once the first merges, the second is behind `main` (strict mode) and its
  bump is stale.
  1. Merge `origin/main` into the branch (`git merge origin/main`, or GitHub's *Update branch* with its
     merge option; never rebase, which needs a force-push).
  2. Whether or not git reports a conflict: take `main`'s `CHANGELOG.md`, and put this branch's entries
     back under its `## [Unreleased]`; take `main`'s `version` in `manifest.json`.
  3. Commit the merge, rerun `release-pr`, commit and push.

  `pr-check` fails on the stale bump until this is done, so the PR can't merge with the wrong version once
  `version-check` is required.

**`docs/releasing.md`** is rewritten:
- versioning (no pre-releases); PR titles (§2's grammar, table and rules); a releasing PR and the bump step;
  two PRs at once; fixing an old changelog entry (`docs(changelog)`);
- what happens on merge (the existing `auto-release` text, with "a bump PR" replaced by "a releasing PR");
- *When a release fails*: the re-runs and the workflow-scope limit with its recovery (the Decisions table),
  with the 403 message so it can be found by searching, all the owner's actions;
- the sections that still hold: *What `release.yml` checks* (without the tag push and the pre-release
  marking), *Required workflows*, *Bumping `pynortecgo`*, *Bumping Home Assistant*; the last two say how to
  title such a PR;
- *Fallbacks* and *Tagging by hand* go;
- *Once, after the auto-release PR merges* becomes *Once, after the release model PR merges*: `uv sync` in
  every checkout, the owner adding `version-check` to the required checks, and any PR still open then gets a
  title by the new rules and, if releasing, the bump step. `0.1.0`'s steps go, since it is released.

**`.github/pull_request_template.md`:** the item "`CHANGELOG.md` updated under *Unreleased* (user-visible
changes)" becomes two items: "Title type per `docs/releasing.md` (user-visible → `feat`, `fix` or `perf`,
with a `CHANGELOG.md` entry)" and "Releasing title → the bump step run last (`docs/releasing.md`)".

**`docs/way-of-working.md`:**
- §1 step 2: the branch type is independent of the PR title's type (§2 of this spec).
- §1 step 6: the draft PR's title follows `docs/releasing.md`'s title rules.
- §1 step 10: for a releasing title, the bump step runs after `scripts/smoke` passes and before the PR
  description is updated and `gh pr ready`.
- §4: a trivial or D25 PR with a releasing title is bumped before it is opened.
- §6: the controller's *may* column gains "Run the bump step in a releasing PR"; the *may not* column's
  "Tag releases" becomes "Push a tag, or re-run a workflow run on `main`" (either can publish), unless the
  owner says so for that release.
- §8: the team lead runs the bump step (for a releasing title) as its last step before `branch ready`; the
  PO's acceptance check (step 4 of *From branch ready to PR ready*) includes the title's type and level; a
  stale bump or conflict on a ready PR is handled by the team lead as in *Two releasing PRs at once* (the
  existing re-create-and-resume path); the *Owner only* list gains "pushing a tag, and re-running a workflow
  run on `main`".

**`.claude/agents/team-lead.md`:** in PO mode, "step 10 is the PO's" gains "except the bump step, which you
run before `branch ready`". Its *Never* list's "tag a release" becomes "push a tag, re-run a workflow run on
`main`".

**`.claude/agents/po.md`:** its *Never* list's "tag a release" becomes "push a tag, re-run a workflow run
on `main`".

Both agent files are guarded files for the plan (way-of-working §5).

**`CLAUDE.md`:** the rule "Add a `CHANGELOG.md` entry under *Unreleased* for user-visible changes" gains
"and title the PR `feat`, `fix` or `perf` (`docs/releasing.md`)". The layout line's "`release_check.py`,
the release rules the workflows run" becomes "`release_check.py`, the release rules and the bump step".

**`docs/README.md`:** the `releasing.md` row reads "PR titles, the bump step, the automatic release, when a
release fails, what `release.yml` checks".

## 7. Decision log

### D40: A merged PR releases itself, by its title
- **Date:** 2026-09-29 · **Status:** active
- **Decision:** The PR title's type decides the release (`fix`/`perf` patch, `feat` minor, `!` minor on 0.x
  and major from 1.0, other types none). A releasing PR carries its own bump from `release_check.py
  release-pr`, run before it is marked ready; `auto-release.yml` publishes it on merge, as D39 set up. A
  merged PR is the only way to release: no dispatch, and a pushed tag publishes nothing on its own. A failed
  release is re-run by the owner; when the workflow-scope limit blocks the tag, the owner pushes it by hand
  first.
- **Why:** a separate bump PR was a manual step that left changes waiting under *Unreleased*, and every
  release should come from a reviewed, merged PR; a stale bump between two ready PRs is accepted as the
  price.
- **Source:** [release model spec](superpowers/specs/2026-09-29-release-model-design.md), Decisions

D39's status becomes `active; the bump PR and the fallbacks superseded by D40` (its automatic tag on a
green `main` stays). D10's status becomes `superseded by D39 and D40` (the manual tag by D39, the bump PR by
D40).

## 8. Tests and verification

**Unit tests** (`tests/test_release_check.py`, table-driven where it fits):
- titles: each type, with and without a scope, with `!`, with `(#n)` in the text; malformed (uppercase
  type, no space after the colon, two spaces, empty text, an empty or spaced scope, `!` before the scope),
  unknown type, `!` on a non-releasing type, `Revert "…"`;
- next version: patch, minor, `!` on 0.x, `!` from 1.0, a pre-release base;
- changelog parsing: the current `CHANGELOG.md` round-trips unchanged; a bad heading; a duplicate section;
- the changelog bump: from *Unreleased*; with the branch's own earlier section folded back, checking group
  order and that the own section's entries come before *Unreleased*'s within a group; an empty body;
- `pr-check`: each problem of §2 on its own (including a stale version after `main` moved on, and a date
  in a bad format), and a clean releasing and a clean non-releasing PR, including a `docs(changelog)` fix
  and each thing it may not do;
- `release-pr` end to end in a temporary git repository with an `origin`: the bump; a rerun; a rerun after
  a retitle from `fix` to `feat`; a non-releasing title; the refusal when `origin/main` isn't an ancestor of
  `HEAD`; *Two releasing PRs at once* (main gains a release, the branch merges it with step 2 of the recipe,
  the rerun bumps from main's new version); and that `manifest.json` changes only in `version`.

**Workflow tests** (`tests/test_workflows.py`):
- `version-check.yml` passes the title through `env`, and no `run:` in it contains
  `github.event.pull_request.title`;
- `auto-release.yml`'s only trigger is `workflow_run`, no workflow uses `inputs.dry_run`, and the `decide`
  job's `if:` holds the guard: `conclusion == 'success'`, `event == 'push'`, `head_branch == 'main'` and
  `head_repository.full_name == github.repository`;
- `release.yml`'s only trigger is `workflow_call`, and it has no `--prerelease`;
- the existing checks are updated to match (the triggers, and `inputs.sha || github.ref` becoming
  `inputs.sha`) and otherwise stay.

**Lint:** the gates, including `actionlint` and `zizmor`.

**Before the merge**, in the plan's last task:
- `v0.1.0` and its release still exist on `9441abd` (read-only: `gh release view v0.1.0`,
  `git ls-remote origin refs/tags/v0.1.0`);
- `pr-check` with this PR's title, against the merge base with a freshly fetched `origin/main`, says it is
  clean;
- in a scratch clone of this branch from GitHub (so its `origin/main` is GitHub's), `release-pr
  --title='fix: test'` writes `0.1.1` and a dated section; after committing that, `pr-check
  --title='fix: test'` against the merge base with `origin/main` says it is clean. The scratch clone is
  deleted and nothing from it is pushed.
