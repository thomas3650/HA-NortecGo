# Ground structure: layout, tooling, CI, docs and GitHub settings — design

Date: 2026-09-26 · Branch: `chore/ground-structure` · Issue: #1

## Goal

Put the base of the repo in place so features can be built on it:

- **What it is:** the **public** repo of a Home Assistant custom integration for a **Nortec Go** EV charger
  (a white-label Monta app). It talks only to the public API of `pynortecgo`, an async client that lives in
  the separate, **private** `NortecGo` repo. The integration is unofficial and not affiliated with Nortec or
  Monta.
- **Who it is for:** the owner's own Home Assistant, installed via **HACS**. The code and docs aim at Home
  Assistant **core quality**: the Integration Quality Scale, **Silver** as the first target.
- **In this work:** an empty `nortec_go` integration skeleton (no `pynortecgo` dependency yet), dev tooling,
  CI with five required checks, the docs and way of working, the `.claude/` setup adapted from `NortecGo`,
  the GitHub repo settings, and a `v0.0.1` pre-release that proves the release path.
- **Not in this work:** any feature (config flow, entities, the `pynortecgo` dependency). Every quality-scale
  rule stays `todo` or `exempt`, except `brands`, which the local `brand/` folder completes.

## Decisions

| Topic | Decision |
|---|---|
| Domain | `nortec_go` (core's snake_case convention for two-word brands) |
| Quality target | Core quality; Silver first. `quality_scale.yaml` lists every Bronze→Platinum rule so the gap stays visible. Known gap: `dependency-transparency` (Bronze) can't be met while `pynortecgo`'s source repo is private (§1.1) |
| Install route | HACS custom repository; the owner is the only user |
| License | Apache-2.0 (same as HA core) |
| Tooling | `uv` + dev-only `pyproject.toml` + `uv.lock`; ruff (core's rules), `mypy --strict`, pytest with `pytest-homeassistant-custom-component`, pre-commit |
| HA / Python | Current stable HA only; the exact `pytest-homeassistant-custom-component` pin sets it. Python matches the pinned HA's `requires-python` (`>=3.14.2` for HA 2026.9) |
| Devcontainer | Optional, for manual testing only. Never the gate environment: gates run on the host with `uv` |
| Dependency | `manifest.json` has `"requirements": []` until the first feature. Then `pynortecgo==X.Y.Z`, pinned exactly |
| Merging | Squash only; PR title + body as the commit message; head branches deleted on merge |
| Required checks | `lint`, `tests`, `hassfest`, `hacs`, `gitleaks`, and branches up to date before merge |
| Releases | Manual: a bump PR, then the owner pushes tag `vX.Y.Z`, then `release.yml` publishes the GitHub release |
| First release | `v0.0.1` pre-release, tagged by the owner after the merge |
| Way of working | Copied from `NortecGo` and adapted, with a sync note in both repos |
| User docs | `docs/user/nortec_go.md` in home-assistant.io page format; README short and links to it |
| GitHub settings | Applied once by the controller with `gh`, each step after the owner's explicit OK; no settings script |
| Issues | Issues on; interaction limit "collaborators only" (6 months) plus an issue-template note |
| Real data | Anything from a real instance goes in `local/` (gitignored); `.gitignore` patterns are a backstop |
| Brand | A neutral EV-charger icon of our own in `custom_components/nortec_go/brand/` (HA ≥ 2026.3 serves it; HACS accepts it). No Nortec or Monta marks |

## 1. Repository layout

```
HA-NortecGo/
├── custom_components/nortec_go/
│   ├── __init__.py
│   ├── manifest.json
│   ├── const.py
│   ├── strings.json
│   ├── translations/en.json
│   ├── quality_scale.yaml
│   └── brand/{icon.png,icon@2x.png}
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_init.py
├── docs/
│   ├── README.md
│   ├── way-of-working.md
│   ├── decisions.md
│   ├── releasing.md
│   ├── notes.md
│   ├── user/nortec_go.md
│   └── superpowers/{specs,plans}/
├── .claude/
├── .github/
│   ├── workflows/{lint,tests,hassfest,hacs,gitleaks,release}.yml
│   ├── dependabot.yml
│   ├── ISSUE_TEMPLATE/{config.yml,bug.yml,feature.yml}
│   └── pull_request_template.md
├── .devcontainer/devcontainer.json
├── scripts/develop
├── CLAUDE.md, README.md, CHANGELOG.md, LICENSE, SECURITY.md
└── hacs.json, pyproject.toml, uv.lock, .pre-commit-config.yaml, .gitignore
```

### 1.1 The skeleton

- `manifest.json`, with keys in the order hassfest enforces (`domain`, `name`, then alphabetical):
  `domain: nortec_go`, `name: Nortec Go`, `codeowners: ["@thomas3650"]`, `config_flow: false`,
  `dependencies: []`, `documentation` (the GitHub URL of `docs/user/nortec_go.md` on `main`),
  `integration_type: hub`, `iot_class: cloud_polling`, `issue_tracker` (this repo's issues URL),
  `requirements: []`, `version: 0.0.1`. `config_flow` is `false` because there is no UI setup yet; the
  config-flow feature sets it to `true`. (hassfest only errors when the flag is `true` and `config_flow.py` is
  missing.)
- `__init__.py`: `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)` (UI-only; a YAML `nortec_go:`
  key gets HA's standard error) and a typed `async_setup(hass, config) -> bool` that returns `True`. There is no
  config entry setup yet: HA imports `config_flow.py` whenever it sets up a config entry, so entry setup and
  unload come with the config-flow feature. No platforms yet.
- `const.py`: `DOMAIN: Final = "nortec_go"`.
- `strings.json`: a minimal valid file. `translations/en.json` is an exact copy (the core layout; HA loads
  `translations/` for custom integrations). A test asserts the two are identical.
- `quality_scale.yaml`: every rule from Bronze to Platinum, in core's format. Each is `todo`, or `exempt` with
  a `comment` giving the reason. The plan takes the current rule list from the HA developer docs
  (`docs/core/integration-quality-scale/rules/`) at implementation time. `dependency-transparency` is `todo`
  with the comment "The pynortecgo source repo is private; the rule needs an open repo, tags and a public
  publishing pipeline. Tracked in the pynortecgo repo (issue #34)." `brands` is `done`, with the comment
  "Local brand/ folder (HA >= 2026.3), accepted by HACS; moves to home-assistant/brands for a core
  submission."
- `brand/icon.png` (256×256) and `brand/icon@2x.png` (512×512): square PNGs with a transparent background,
  showing a neutral EV-charger pictogram. The source is the Material Design Icons `ev-station` glyph, if its
  license allows reuse in an Apache-2.0 repo (the plan checks and records the license and attribution in
  `brand/README.md`); otherwise a pictogram drawn for this repo. Local brand images are supported from HA
  2026.3, and HACS's `brands` check accepts `brand/icon.png` in the integration folder. If this integration
  ever goes to core, the images move to the `home-assistant/brands` repo instead.
- `tests/conftest.py`: enables custom integrations (`enable_custom_integrations`, autouse).
- `tests/test_init.py`: the smoke test. `await async_setup_component(hass, DOMAIN, {})` returns `True`, and
  `DOMAIN` is in `hass.config.components`. It imports `DOMAIN` from
  `custom_components.nortec_go.const`. The import is needed: `pytest-homeassistant-custom-component` ships
  its own `custom_components` package, and ours is only found if a test imports it first. It also holds the
  `strings.json` = `en.json` test.
- `tests/test_quality_scale.py`: loads `quality_scale.yaml` with `homeassistant.util.yaml.load_yaml_dict`
  (typed, so `mypy --strict` needs no PyYAML stubs) and checks that every rule's status is `done`,
  `todo` or `exempt`, and that every `exempt` has a `comment`. hassfest skips this file for custom
  integrations, so nothing else validates it.

### 1.2 Other root files

- `hacs.json`: `name: Nortec Go`, `homeassistant: <the HA version the test pin uses>`.
- `LICENSE`: Apache-2.0 text, copyright "2026 thomas jørgensen". It reaches `main` first, in its own PR
  (§4 step 2), because HACS's `license` check reads the license GitHub detects on the default branch.
- `SECURITY.md`: report privately via GitHub private vulnerability reporting; don't open public issues for
  security problems.
- `CHANGELOG.md`: Keep a Changelog format, with an empty `## [Unreleased]` and `## [0.0.1] - <date>`
  ("Initial project skeleton; not usable yet"). This PR is the `0.0.1` bump PR. The date is set when the PR is
  marked ready, and the owner tags right after merging.
- `scripts/develop`: creates `config/` with a `configuration.yaml` holding `default_config:` if it's missing,
  symlinks `config/custom_components/nortec_go` to the repo's folder, and runs
  `uv run hass -c config --debug`. On first start HA installs runtime packages for `default_config` into the
  venv; the next `uv sync` (for example from the gates) removes them again, so they are reinstalled after
  each sync. This is expected and noted in the script's header comment. `config/` is gitignored.
- `.devcontainer/devcontainer.json`: plain JSON with no comments (`check-json` rejects JSONC). It uses a Python
  image matching the pinned HA's `requires-python`, runs `uv sync` on create, and forwards port 8123. The
  file's `name` and `docs/way-of-working.md` both say it is for manual testing only.

### 1.3 `.gitignore` additions

The existing entries stay. Added:

```gitignore
# HA diagnostics downloads (real data goes in local/)
config_entry-*.json
*diagnostics*.json
# HA logs and state
*.log
home-assistant_v2.db*
.storage/
```

Snapshot tests use `.ambr` files under `tests/snapshots/`, so the diagnostics pattern doesn't hide them.

## 2. Tooling and CI

### 2.1 `pyproject.toml`

A dev-only file: `[project]` with `name = "ha-nortecgo"`, `version = "0.0.0"` (unused; `manifest.json`
holds the real version), `requires-python` equal to the pinned HA's (`>=3.14.2` for HA 2026.9; `uv lock`
fails with `>=3.14`), no dependencies, and no build system.

- A `dev` dependency group: `pytest-homeassistant-custom-component` (pinned exactly), `pytest-cov`, `ruff`,
  `mypy`, `pre-commit`.
- **ruff:** copied from HA core's `pyproject.toml` at implementation time: `[tool.ruff.lint]` `select`/`ignore`,
  and the `isort` (with `known-first-party = ["custom_components.nortec_go", "tests"]`), `pydocstyle` and
  `flake8-tidy-imports` banned-api sections. Rules that only make sense for the core monorepo are removed,
  and the plan lists each one and why.
- **mypy:** `strict = true`, `files = ["custom_components", "tests"]`, `explicit_package_bases = true`, and an
  override with `ignore_missing_imports` for `pytest_homeassistant_custom_component.*` (it ships no
  `py.typed`).
- **pytest:** `asyncio_mode = "auto"`, `testpaths = ["tests"]`. Coverage isn't in `addopts`, so single-test TDD
  runs aren't failed by it. The coverage gate is its own command, run by CI and by the gates before
  committing (`CLAUDE.md`):
  `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`.

### 2.2 pre-commit

The same as `NortecGo`: `default_install_hook_types: [pre-commit, pre-push]`; `no-commit-to-branch` (main),
`check-yaml`, `check-json`, `check-toml`, `end-of-file-fixer`, `trailing-whitespace`, `detect-private-key`,
`check-added-large-files`; ruff check `--fix` and ruff format; gitleaks; and the local `no-push-to-main`
pre-push hook.

### 2.3 Workflows

The job name is the required check name.

| File | Job | Triggers | Steps |
|---|---|---|---|
| `lint.yml` | `lint` | PR, push to main | `uv sync --locked`; `ruff check`; `ruff format --check`; `mypy` |
| `tests.yml` | `tests` | PR, push to main | `uv sync --locked`; the coverage gate command (§2.1) |
| `hassfest.yml` | `hassfest` | PR, push to main, weekly | `home-assistant/actions/hassfest` |
| `hacs.yml` | `hacs` | PR, push to main, weekly | `hacs/action`, `category: integration`, no ignores |
| `gitleaks.yml` | `gitleaks` | PR, push to main | `gitleaks/gitleaks-action` with `fetch-depth: 0`: on a PR it scans the PR's commits, on push to `main` the pushed range. Needs `pull-requests: read` |
| `release.yml` | `release` | push of tag `v*` | check tag = `v` + `manifest.json` version, else fail; extract that version's `CHANGELOG.md` section, and fail if it's missing or empty; `gh release create` with it as notes, `--prerelease` when the version is `0.0.x` or has a `-` suffix |

- Every action is pinned to a commit SHA with a version comment.
- `permissions: contents: read` at the top of every workflow. `gitleaks.yml` adds `pull-requests: read`, and
  `release.yml` has `contents: write`.
- **HACS checks:** archived, brands, description, hacs.json, information (README), integration manifest,
  issues, license and topics. There is no releases check, so the PR passes before `v0.0.1` exists. Brands
  pass through the local `brand/icon.png`, description and topics through §4 step 1, and license through
  the LICENSE-only PR (§4 step 2).

### 2.4 Dependabot

`github-actions` and `uv`, monthly, each ecosystem's updates grouped into one PR. Dependabot reads its
config only from `main`, so it first runs after the merge (§5). If the `uv` ecosystem doesn't update a
`pyproject.toml` that has only `[dependency-groups]`, that goes in `notes.md` and gets an issue. When
`pytest-homeassistant-custom-component` is bumped, the same PR raises `hacs.json`'s `homeassistant` minimum
to the HA version it pins. The PR template has a checklist line for this.

### 2.5 Templates

- `pull_request_template.md`: `Closes #`, summary, and a checklist:
  - gates pass;
  - CHANGELOG *Unreleased* entry for user-visible changes;
  - `quality_scale.yaml` updated;
  - `docs/user/nortec_go.md` updated;
  - no private data;
  - for a `pytest-homeassistant-custom-component` bump, `hacs.json` minimum raised.
- `ISSUE_TEMPLATE/config.yml`: `blank_issues_enabled: false`, and a contact link explaining the repo doesn't
  accept external issues yet (security goes through `SECURITY.md`).
- `bug.yml` and `feature.yml`: short forms (what happened / expected / HA version / integration version; the
  user story).

## 3. Docs and process

### 3.1 `CLAUDE.md`

- **What this repo is**, with the unofficial note.
- **Layout.**
- **Commands:** `uv sync`, `uv run pytest -q` (fast, no coverage), the coverage gate (§2.1),
  `uv run ruff check && uv run ruff format --check && uv run mypy`, `uv run pre-commit install`,
  `scripts/develop`.
- `@docs/way-of-working.md`.
- **Code and docs rules:**
  - TDD, and the gates pass before committing.
  - A CHANGELOG *Unreleased* entry for user-visible changes.
  - `quality_scale.yaml` and `docs/user/nortec_go.md` are updated in the same PR as the code they describe.
- **Hard rules:**
  1. Every change reaches `main` only through a merged PR. Never commit on or push to `main`.
  2. Never start or stop a real charge without the owner's explicit OK, in dev or manual testing. Tests always
     mock `pynortecgo`.
  3. Nothing private in this public repo: no account, charger or user IDs, tokens, emails, captures, APK
     references, links into the private `NortecGo` repo's docs, or raw API endpoints, headers and response
     shapes. The integration uses only `pynortecgo`'s public API.
  4. Never commit `.env`, `config/`, or anything taken from a real instance.
  5. Diagnostics and logs redact tokens, email, IDs and location (`async_redact_data`), and credentials and
     usernames are never logged, even wrong ones. Anything taken from a real instance (diagnostics
     downloads, logs, dumps) goes in `local/` and is never committed.
  6. Never auto-retry `start_charge`. On `AuthError`, start reauth instead of retrying login (login is
     rate-limited; a start places a card hold).
  7. Test fixtures are built from `pynortecgo` model objects, never from raw API JSON.
  8. What the client needs goes to `NortecGo` as a change request (`docs/way-of-working.md`), never patched or
     vendored here.
  9. Subagents never read `.env` directly, and never read anything under `local/` or `config/`.
- **Context:** the owner's own charger and account.
- `@docs/README.md`.

### 3.2 `docs/way-of-working.md`

Copied from `NortecGo` and adapted.

- **Starts with a sync note:** "A sibling copy lives in the private `NortecGo` repo. A process change in either
  copy gets a follow-up issue in the other repo."
- **Removed:** `api.md`, `api-standard.md`, `reverse-engineering.md`, the `document-endpoint` skill, PyPI
  publishing, and the "no server-side ruleset" caveat. §7 *Learnings* points to this repo's docs instead
  (`notes.md`, `docs/user/nortec_go.md`, `way-of-working.md`).
- **Renumbered:** references to `NortecGo` decisions (D27, D28 and others) are reworded as plain rules, and
  where the origin matters they're cited as "NortecGo D27", with no link. This repo's own D-numbers start at
  D1.
- **`captures/` becomes `local/`:** wherever the copy says "`captures/`", this repo says "`local/`" (and
  `config/`), since that's where real data lives here (D12).
- **Changed:**
  - Gates are this repo's commands; hassfest and HACS run in CI only.
  - `Model: opus` is for tasks that touch auth, tokens or reauth, anything near charge start/stop, or the
    mapping of `pynortecgo` models to entities; and for debugging with an unknown cause.
  - Git guards: `main` is also protected server-side, with the required checks.
- **Added:**
  - **Client change requests:** send them to the `nortecgo-af` session. If it isn't running, the controller
    files the issue with `gh issue create -R thomas3650/nortecgo --label ha-integration`. The issue holds no
    private data from this side.
  - **Quality scale:** a PR that completes a rule sets it to `done` in `quality_scale.yaml`.
  - **Devcontainer:** manual testing only.
- **Controller permissions:** `NortecGo`'s table, adapted. "Tag releases or publish to PyPI" becomes "Tag
  releases", and "Read `.env` or `captures/`" becomes "Read `.env`, `local/` or `config/`". The one-time
  settings in this work (§4) are an explicit exception, each step approved by the owner.

### 3.3 `.claude/`

- **Agents** (`implementer`, `task-reviewer`, `full-reviewer`): "pynortecgo repo" becomes "HA-NortecGo"
  (public HACS integration repo), and the gate commands become this repo's (§3.1). References to
  `check_api_md.py`, `docs/api.md`, `docs/api-standard.md`, `uv build` and the published package are removed.
  "Never read `.env` or anything under `captures/`" becomes "Never read `.env`, or anything under `local/` or
  `config/`". The branch review also checks hard rule 3 across the diff.
- **`hooks/subagent_guard.py`:** its code is unchanged. In the docstring, the design links into `NortecGo`
  (private) are replaced with a pointer to this spec. The known-limits line about `captures/` becomes
  `local/`/`config/` (the hook doesn't enforce them; hard rule 9 does).
- **`settings.json`:** unchanged.
- **`skills/document-endpoint/`:** deleted.

### 3.4 `docs/`

- `README.md`: the documentation map. One table: doc, contents, read it when. A second table, **Useful
  links**, grouped by topic, points to the upstream references:
  - HA developer docs: creating an integration, file structure, tests file structure, manifest, config flow,
    options flow, fetching data (`DataUpdateCoordinator`), setup failures, diagnostics, system health, brand
    images, the development checklist, component and platform checklists, style guidelines, testing (incl.
    snapshot tests), typing, and building a Python library for an API.
  - Integration Quality Scale: the overview, the checklist and the rules list.
  - home-assistant.io: the integration docs template and the documentation standards.
  - HACS: publishing an integration, the `hacs.json` reference and the HACS action.
  - Tools: `pytest-homeassistant-custom-component`, the hassfest action, the brands repo.

  The URLs are checked (HTTP 200) when the doc is written.
- `decisions.md`: the same header and entry format as `NortecGo`, with these entries, each linking to this
  spec:
  - D1 domain `nortec_go`
  - D2 HACS install, core-quality target, Silver first
  - D3 Apache-2.0
  - D4 `uv` tooling; current stable HA only; Python as the pinned HA requires; optional devcontainer, never the
    gate environment
  - D5 squash-only merges
  - D6 five required checks
  - D7 no dependency in the skeleton; `pynortecgo` pinned exactly once it's added; only its public API is used
  - D8 way of working copied with a sync note; client change requests via `nortecgo-af` or `gh issue create`
  - D9 user docs in home-assistant.io format
  - D10 manual releases
  - D11 GitHub settings applied once with `gh`; issues limited to collaborators
  - D12 real data only in `local/`
  - D13 no Claude memory; questions as plain text (inherited)
  - D14 a neutral brand icon of our own, in the local `brand/` folder
  - D15 `dependency-transparency` stays `todo` while `pynortecgo`'s source repo is private; tracked upstream
- `releasing.md`:
  - the bump PR (`manifest.json` version, the CHANGELOG section moved from *Unreleased*);
  - the owner pushes the tag;
  - what `release.yml` checks;
  - pre-release rules;
  - bumping the `pynortecgo` pin.
- `notes.md`: dated small facts. First entry: how to renew the interaction limit
  (`gh api -X PUT repos/thomas3650/HA-NortecGo/interaction-limits -f limit=collaborators_only -f expiry=six_months`)
  and when it expires.
- `user/nortec_go.md` follows home-assistant.io's `_integration_docs_template.markdown`, in its order. It is
  plain GitHub Markdown: the YAML front matter stays (GitHub shows it as a table), and the template's Liquid
  tags (`{% term %}`, `{% configuration_basic %}`, `{% include %}`) become plain text, lists or tables. A
  core submission would convert them back. The sections:
  - the front matter (title, description, `ha_iot_class: Cloud Polling`, `ha_domain: nortec_go`,
    `ha_integration_type: hub`, `ha_codeowners`);
  - the intro with a high-level description, a link to the product, and the unofficial disclaimer;
  - Supported devices;
  - Unsupported devices;
  - Prerequisites;
  - Installation (HACS custom repository; this section isn't in core's template, and is dropped for a core
    submission);
  - Configuration options;
  - Supported functionality;
  - Actions, Conditions and Triggers (covering Bronze's `docs-actions`, `docs-conditions` and
    `docs-triggers`; the template pulls these in through includes after Supported functionality, and this is
    one plain section instead);
  - Automation examples;
  - Data updates;
  - Known limitations;
  - Troubleshooting;
  - Removing the integration.

  Sections with nothing to describe yet say "Not available yet."

### 3.5 `README.md`

What it is, the unofficial disclaimer, a status line ("Skeleton; not usable yet"), install via HACS (custom
repository), and a link to `docs/user/nortec_go.md`. No private data.

### 3.6 Outside this repo

`NortecGo` needs the matching sync note in its `way-of-working.md`. The controller asks `nortecgo-af` to file
that issue, or files it itself with `gh issue create -R thomas3650/nortecgo --label ha-integration`.

## 4. GitHub settings and release sequence

The controller runs these with `gh`. **⏸** marks a step that waits for the owner's explicit OK. After every
settings step, a read-only `gh api` call confirms each value.

1. **⏸ Settings before the PR:**
   - description "Unofficial Home Assistant integration for Nortec Go EV chargers (Monta white-label)";
   - topics `home-assistant`, `hacs`, `homeassistant-integration`, `ev-charging`, `nortec-go`, `monta`;
   - wiki, projects and discussions off; issues on;
   - squash merge only (`allow_squash_merge: true`, `allow_merge_commit: false`, `allow_rebase_merge: false`),
     with `squash_merge_commit_title: PR_TITLE` and `squash_merge_commit_message: PR_BODY`;
   - `delete_branch_on_merge: true`, `allow_auto_merge: false`, `allow_update_branch: true` (the "Update
     branch" button, needed with `strict` required checks);
   - Dependabot alerts and security updates on;
   - secret scanning and push protection on;
   - private vulnerability reporting on;
   - interaction limit `collaborators_only` for `six_months`.
2. **LICENSE-only PR.** Branch `chore/license` off `main`, with only the Apache-2.0 `LICENSE`, as a ready PR
   (a trivial change under `NortecGo`'s way-of-working §4 *Trivial changes*, which this work copies; the
   license was decided in this spec). **The owner
   merges it.** Verify: `gh api repos/thomas3650/HA-NortecGo --jq .license.spdx_id` prints `Apache-2.0`.
   Then rebase `chore/ground-structure` onto `main`.
3. Commit the spec and plan on `chore/ground-structure`, push, and open a **draft PR** with `Closes #1` and
   links to both.
4. Execute the plan (SDD). CI goes green on the PR, so all five check names exist.
5. **⏸ Update the `main` protection** with one full `PUT repos/thomas3650/HA-NortecGo/branches/main/protection`
   (the protection has no `required_status_checks` yet, so a partial PATCH doesn't work). The body repeats the
   current values and adds the checks:
   - `required_status_checks`: `strict: true`, `checks` = `lint`, `tests`, `hassfest`, `hacs`, `gitleaks`, each
     bound to the GitHub Actions app (`app_id: 15368`), with no `contexts` alongside;
   - `required_pull_request_reviews` with `required_approving_review_count: 0`;
   - `enforce_admins: true`, `required_conversation_resolution: true`;
   - `allow_force_pushes: false`, `allow_deletions: false`, `restrictions: null`.

   The body is sent as a JSON file with `gh api --input <file>`.
6. Branch review until Ready, then ready the PR. **The owner merges.**
7. **The owner** tags `v0.0.1` on `main` and pushes the tag. `release.yml` publishes a pre-release.
8. The controller files the issue "Renew interaction limit (expires YYYY-MM-DD)".

## 5. Verification

**Local, on the branch:**
- `uv sync --locked`, the coverage gate command (§2.1), `uv run ruff check`, `uv run ruff format --check`
  and `uv run mypy` all pass.
- `uv run pre-commit run --all-files` passes.
- A commit attempted on `main` is refused by the hook, checked with a throwaway commit that the hook stops.
- `scripts/develop` starts HA. The log has "We found a custom integration nortec_go which has not been
  tested…" (HA's loader logs it for every folder in `custom_components` during the startup scan, with no
  config entry or YAML needed), and no errors mentioning `nortec_go`.
- Private-data scan over tracked files only (never `.venv/`, `config/` or `local/`):
  `git grep -nE 'ory_st_[A-Za-z0-9]{8,}|[A-Za-z0-9._%+-]+@[A-Za-z][A-Za-z0-9-]*\.[A-Za-z]{2,}' | grep -v 'noreply@anthropic\.com'`
  prints nothing.
  The domain part must start with a letter, so `icon@2x.png` doesn't match, and `@pytest.fixture` has no
  local part. Commit messages are checked separately:
  `git fetch origin && git log --format=%B origin/main..HEAD | grep -nE '[A-Za-z0-9._%+-]+@[A-Za-z][A-Za-z0-9-]*\.[A-Za-z]{2,}'` prints
  only the `noreply@anthropic.com` trailer lines.

**CI:** all five checks are green on the PR.

**GitHub, after each ⏸ step:** `gh api repos/thomas3650/HA-NortecGo` and the protection, security and
interaction-limit endpoints match §4.

**After the merge:** trigger Dependabot once (Insights → Dependency graph → Dependabot → "Check for updates",
per ecosystem). Check that it runs for both `github-actions` and `uv`, and that it can open a PR while the
interaction limit is set. The result goes in `notes.md`.

**After the release:**
- `gh release view v0.0.1` shows a pre-release with the CHANGELOG notes.
- `hassfest` and `hacs` pass on `main`.

**Reviews:** `full-reviewer` reviews this spec, then the plan, then the branch, each until Ready.
