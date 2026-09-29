# Releasing

## Versioning

This project uses [Semantic Versioning](https://semver.org/). Versions `0.0.x` and any version with a `-`
suffix (for example `1.0.0-beta.1`) are published as pre-releases. HACS installs from the default branch,
not a pre-release, when a repository has no full release, so the first release a user should install is a
full one.

## The bump PR

1. Set `version` in `custom_components/nortec_go/manifest.json` to the new version.
2. In `CHANGELOG.md`, move the relevant entries from `## [Unreleased]` under a new
   `## [X.Y.Z] - YYYY-MM-DD` section.
3. Open a pull request with these changes and merge it once the gates pass.

Merging it is the release, and nothing else is needed. Once the five required workflows (`lint`, `tests`,
`hassfest`, `hacs`, `gitleaks`) have passed on `main` for the merge commit, `auto-release.yml` tags that
commit `vX.Y.Z` and publishes the release through `release.yml`. The `version-check` check on the PR fails
if the version changes in a way that wouldn't be released.

## What counts as a bump

A commit is a bump when, compared with the commit before it:

- the version is higher (semver);
- the same commit adds the `## [X.Y.Z]` heading to `CHANGELOG.md`;
- that section has entries.

Anything else, a revert to an older version included, releases nothing, and the `auto-release` run says
why. The rule lives in `scripts/release_check.py`.

## After a merge

Check the `auto-release` runs for the merge commit. There are up to five, one per required workflow. Some
show as cancelled, and the one that runs after the last workflow does the work. Then check the tag, the
release with the changelog section as its notes, and that HACS offers the version.

## Once, after the auto-release PR merges

1. Every checkout and worktree runs `uv sync`: the new `actionlint` and `zizmor` pre-commit hooks need the
   tools.
2. The owner adds `version-check` to `main`'s required status checks (a GitHub setting).
3. Then, to release `0.1.0`, whose bump (`9441abd`) merged before the automation, the owner runs
   `auto-release` from the Actions tab on `main` with `sha` `9441abd` and `dry_run` on, reads the log, then
   runs it again with `dry_run` off.
4. Last, the owner checks the tag `v0.1.0` on `9441abd`, the release, and HACS.

The next bump PR removes this section.

## Fallbacks

Run `auto-release` from the Actions tab on `main`, with the commit's `sha`, `dry_run` on first. It takes
any bump commit on `main` whose required workflows passed, also one merged before the automation. Without
the dry run it tags a release, so it is the owner's action, like a tag by hand.

### Tagging by hand

For a commit the rule doesn't count as a bump. The pushed tag starts `release.yml`.

```bash
git switch main
git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

## What `release.yml` checks

It starts in two ways: a pushed `v*` tag, or a call from `auto-release.yml` with the tag and the commit.

- The tag equals `v` followed by the `version` in `manifest.json`. If it doesn't match, the release fails.
- The `CHANGELOG.md` has a `## [X.Y.Z]` section for that version, and it is not empty. If it's missing or
  empty, the release fails.
- A release that exists already means there is nothing to do: the run ends with no second release.
- A tag that exists must point at the commit being released, or the release fails.
- If the checks pass, it runs `gh release create`, using that changelog section as the release notes, and
  marks the release as a pre-release when the version is `0.0.x` or has a `-` suffix.

## Required workflows

`auto-release.yml`'s trigger list and `REQUIRED_WORKFLOWS` in `scripts/release_check.py` follow the
required status checks on `main`. Each required workflow has one job with the workflow's name, and those
names are the checks. `tests/test_workflows.py` fails if a workflow that runs on a push to `main` is added
or renamed without them. It doesn't see a change made only in GitHub's settings.

## Bumping `pynortecgo`

`requirements` in `manifest.json` pins the `pynortecgo` client library to an exact version, for example
`pynortecgo==X.Y.Z`, and `pyproject.toml` pins the same version. A new client release gets its own pull
request that bumps both pins, updates the lock with `uv lock --upgrade-package pynortecgo` (which leaves
the other pins alone, apart from what the new version needs), runs the usual gates, and works through this
checklist before merging:

- [ ] Read the new version's exception messages, including errors it wraps from lower layers, and confirm
  they hold no email, password, tokens, device ID or request bodies. The integration passes them into its
  logs (`CLAUDE.md`, hard rule 5).
- [ ] If `test_client_model_fields_are_pinned` in `tests/test_diagnostics.py` fails, the diagnostics show
  a changed `Charger` or `Vehicle` field: decide for each new field whether it is a secret, add it to
  `TO_REDACT` in `diagnostics.py` if so, and update the pinned sets (D38).
- [ ] Look for new exception classes the charger, car, price, start and stop calls can raise, and give each
  the right handling. The charger read's catch-all only keeps an unknown error from crashing the read.
- [ ] Read the client's changelog for breaking changes to the models the entities use.

## Bumping Home Assistant

A `pytest-homeassistant-custom-component` bump pull request also raises `hacs.json`'s `homeassistant` key
to the Home Assistant version that dependency pins, and updates `requires-python` if that Home Assistant
version needs a newer Python. A `requires-python` change also updates `[tool.mypy] python_version` in
`pyproject.toml` and the `.devcontainer` image tag.
