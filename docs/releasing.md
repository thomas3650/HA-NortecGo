# Releasing

## Versioning

This project uses [Semantic Versioning](https://semver.org/). Every release is a full release of an
`X.Y.Z` version; there are no pre-releases. While the major version is 0, a minor release may break
something; its changelog entries say so.

A merged PR is the only way a release happens (D40). Its title decides whether it releases and at which
level, a releasing PR carries its own version bump, and merging it publishes the release. Neither release
workflow can be started by hand, and a pushed tag publishes nothing on its own.

## PR titles

Every PR title is `type(scope)!: text`. The `version-check` check reads it on every PR that isn't a draft.
- `type` is lowercase, and one of the types in the table.
- `(scope)` is optional: one or more characters other than `(`, `)` and whitespace.
- `!` is optional, comes right before the colon, and marks a breaking change.
- Then a colon, one space, and the text. The text may hold `(#n)` references.

| Type | Release |
|---|---|
| `fix`, `perf` | patch |
| `feat` | minor |
| `feat!`, `fix!`, `perf!` (breaking) | minor while the major version is 0, major from 1.0 |
| `refactor`, `docs`, `chore`, `ci`, `test`, `process` | none |

- `!` on a non-releasing type is invalid: a breaking change is a `feat`, `fix` or `perf`.
- A user-visible change is a `feat`, `fix` or `perf`, with a `CHANGELOG.md` entry. A change that isn't
  user-visible has a non-releasing type.
- GitHub's *Revert* button titles a PR `Revert "…"`. Retitle it, for example `fix: revert …`.
- Only `!` marks a breaking change; a `BREAKING CHANGE:` footer isn't read.
- Dependabot's titles are `chore(deps): …`, or `chore(deps-dev): …` for development dependencies. For one
  that users should get, retitle it `feat` or `fix` and run the bump step on its branch. Dependabot then
  stops rebasing it, which is fine for a PR about to merge.
- The title's type is separate from the branch's type (`way-of-working.md` §1 step 2).

## A releasing PR

1. Write the changelog entries under `## [Unreleased]`, as for any user-visible change.
2. **The bump step** comes last, just before the PR is marked ready. In the PO flow it comes before the team
   lead's `branch ready`.

   ```bash
   uv run python scripts/release_check.py release-pr --title="$(gh pr view --json title -q .title)"
   ```

   Before the PR exists (a trivial or D25 PR, opened ready), give the title in single quotes instead, for
   example `--title='fix: …'`. In double quotes, an interactive shell breaks on the `!` of a breaking title.

   The command fetches `origin/main` and sets `version` in `manifest.json` to the next version after
   `main`'s. Then it moves *Unreleased* under `## [X.Y.Z] - <today, UTC>` and prints the version. It commits
   nothing: commit `chore: release X.Y.Z` and push. It refuses a non-releasing title, and a branch that
   `origin/main` isn't merged into.
3. After the bump:
   - **A changelog change:** put it under *Unreleased* and rerun the bump step. It first folds the branch's
     earlier bump back.
   - **A retitle to another releasing type:** rerun the bump step.
   - **A retitle to a non-releasing type:** if `main` has moved, merge `origin/main` in first. Then set
     `version` in `manifest.json` back to `origin/main`'s, changing only that value (a `pynortecgo` bump also
     changes the file). Set `CHANGELOG.md` back to `origin/main`'s too, and commit.

`version-check` compares the PR with its merge base. A releasing PR must have:
- a `version` that is exactly the next one;
- an empty *Unreleased*;
- below it, a `## [X.Y.Z] - YYYY-MM-DD` section with entries. Only the date's format is checked, not its
  value, since the merge may come days after the bump.

A non-releasing PR changes neither `version` nor `CHANGELOG.md`. The rules live in
`scripts/release_check.py`.

## Two releasing PRs at once

`main` requires a PR to be up to date before it merges. This is strict mode, and it binds admins too. Once
one releasing PR merges, the other can't merge until it takes in `main`, and then its bump is stale and
`version-check` fails.

1. Merge `origin/main` into the branch: `git merge origin/main`, or GitHub's *Update branch* with its merge
   option. Never rebase: that needs a force-push.
2. Whether or not git reports a conflict:
   - take `main`'s `CHANGELOG.md`, and put this branch's entries back under its `## [Unreleased]`;
   - take `main`'s `version` in `manifest.json`.
3. Commit the merge, rerun the bump step, commit and push.

In the PO flow the team lead does this after the PO resumes it, and the PO merges one PR at a time
(`way-of-working.md` §8, *Merging*).

## Fixing an old changelog entry

Released sections never change, except in a PR titled `docs(changelog): …`. Such a PR may fix their text.
It may not:
- add or remove a section;
- change a heading;
- change *Unreleased*;
- change `version`.

## What happens on merge

`auto-release.yml` waits until the five required workflows (`lint`, `tests`, `hassfest`, `hacs`,
`gitleaks`) have passed on `main` for the merge commit. Then it checks whether the commit is a bump,
compared with the commit before it:
- the version is higher (semver);
- the same commit adds the `## [X.Y.Z]` heading to `CHANGELOG.md`;
- that section has entries.

If so, it tags the commit `vX.Y.Z` and publishes the release through `release.yml`. Any other merge
releases nothing, and the `auto-release` run says why.

Afterwards, check the `auto-release` runs for the merge commit. There are up to five, one per required
workflow. Some show as cancelled, and the one that runs after the last workflow does the work. When the
last two workflows finish close together, two runs see them all green; they run one at a time, and the
second finds the release made and ends in `decide`. Then check:
- the tag;
- the release, with the changelog section as its notes;
- that HACS offers the version.

In the PO flow the PO checks the runs after every merge, and the tag and the release after the merge of a
releasing PR; the HACS check stays the owner's (`way-of-working.md` §8, *After a merge*).

## When a release fails

Re-running a run can publish, and so can pushing a tag, so every step here is the owner's. The controller
takes one only when the owner says so for that release.

- **A required workflow failed on `main`.**
  - If it's flaky, re-run it: *Re-run failed jobs*, or `gh run rerun <id> --failed`. When it passes,
    `auto-release` runs again.
  - A real break is fixed in a PR. The version it would have released may never be published. Its
    `CHANGELOG.md` section stays as history, and the next releasing PR carries only its own entries.
- **`auto-release` or `release` failed.**
  - A re-run replays the original event with the original commit: it runs that run's `auto-release.yml`
    and the `./.github/workflows/release.yml` from that same commit. A fix to either workflow file merged to
    `main` never reaches a re-run, and merging one makes the releasing commit's workflows differ from
    `main`'s head, which is the HTTP 403 case below. Only `scripts/release_check.py` is picked up, because
    the `decide` job checks out `main`.
  - So re-run the failed `auto-release` run when the cause has passed (a GitHub outage, say), or when it was
    a bug in `scripts/release_check.py`, fixed on `main` in a PR first. Neither a release that already
    exists nor a tag already on that commit gets in the way.
  - A bug in `auto-release.yml` or `release.yml` means that version isn't published. Its `CHANGELOG.md`
    section stays as history, and the next releasing PR carries only its own entries.
- **`HTTP 403: Resource not accessible by integration` when the release is created.**
  - Why: GitHub needs the `workflows` permission to create a release with a new tag on a commit whose
    `.github/workflows/` differ from `main`'s head, and a workflow's `GITHUB_TOKEN` can't have that
    permission
    ([GitHub changelog](https://github.blog/changelog/2023-11-02-github-actions-enforcing-workflow-scope-when-creating-a-release/)).
  - When: a PR that changes the workflows merged after the releasing PR, but before its release was tagged.
    A re-run fails the same way.
  - Fix: the owner pushes the tag on the releasing commit by hand, then re-runs the failed `auto-release`
    run. The re-run finds the tag on that commit and publishes.

  ```bash
  git fetch origin
  git tag vX.Y.Z <releasing commit>
  git push origin vX.Y.Z
  ```

## What `release.yml` checks

`auto-release.yml` calls it with the tag and the commit; it has no other trigger.

- The tag equals `v` followed by the `version` in `manifest.json`. If it doesn't match, the release fails.
- The `CHANGELOG.md` has a `## [X.Y.Z]` section for that version, and it is not empty. If it's missing or
  empty, the release fails.
- A release that exists already means there is nothing to do: the run ends with no second release.
- A tag that exists must point at the commit being released, or the release fails.
- If the checks pass, it runs `gh release create`, using that changelog section as the release notes.

## Required workflows

`auto-release.yml`'s trigger list and `REQUIRED_WORKFLOWS` in `scripts/release_check.py` follow the
required status checks on `main`. Each required workflow has one job with the workflow's name, and those
names are the checks. `tests/test_workflows.py` fails if a workflow that runs on a push to `main` is added
or renamed without them. It doesn't see a change made only in GitHub's settings.

## Bumping `pynortecgo`

`requirements` in `manifest.json` pins the `pynortecgo` client library to an exact version, for example
`pynortecgo==X.Y.Z`, and `pyproject.toml` pins the same version. A new client release gets its own pull
request, or the pull request of the feature that needs it. That pull request bumps both pins, updates the
lock with `uv lock --upgrade-package pynortecgo` (which leaves the other pins alone, apart from what the new
version needs), runs the usual gates, and works through this checklist before merging:

- [ ] Read the new version's exception messages, including errors it wraps from lower layers, and confirm
  they hold no email, password, tokens, device ID or request bodies. The integration passes them into its
  logs (`CLAUDE.md`, hard rule 5).
- [ ] If `test_client_model_fields_are_pinned` in `tests/test_diagnostics.py` fails, the diagnostics show
  a changed `Charger`, `ActiveCharge`, `CompletedCharge` or `Vehicle` field: decide for each new field
  whether it is a secret, add it to `TO_REDACT` in `diagnostics.py` if so, and update the pinned sets (D38).
- [ ] Look for new exception classes the charger, car, price, start and stop calls can raise, and give each
  the right handling. The charger read's catch-all only keeps an unknown error from crashing the read.
- [ ] Read the client's changelog for breaking changes to the models the entities use.

Title such a PR by what it changes for users (*PR titles*). If users see a difference, it's a `feat` or
`fix` with a changelog entry and the bump step. If they don't, it's `chore(deps): …`. A change only in the
shape of the diagnostics download isn't something users see, as long as what the user docs say the file
keeps and leaves out stays true (D46).

## Bumping Home Assistant

A `pytest-homeassistant-custom-component` bump pull request also raises `hacs.json`'s `homeassistant` key
to the Home Assistant version that dependency pins, and updates `requires-python` if that Home Assistant
version needs a newer Python. A `requires-python` change also updates `[tool.mypy] python_version` in
`pyproject.toml` and the `.devcontainer` image tag.

Title such a PR by what it changes for users (*PR titles*). A higher minimum Home Assistant version is
something users see, so that PR is a `feat` or `fix` with a changelog entry and the bump step.
