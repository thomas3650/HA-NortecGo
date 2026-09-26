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
  rule stays `todo` or `exempt`.

## Decisions

| Topic | Decision |
|---|---|
| Domain | `nortec_go` (core's snake_case convention for two-word brands) |
| Quality target | Core quality; Silver first. `quality_scale.yaml` lists every Bronze→Platinum rule so the gap stays visible |
| Install route | HACS custom repository; the owner is the only user |
| License | Apache-2.0 (same as HA core) |
| Tooling | `uv` + dev-only `pyproject.toml` + `uv.lock`; ruff (core's rules), `mypy --strict`, pytest with `pytest-homeassistant-custom-component`, pre-commit |
| HA / Python | Current stable HA only; the exact `pytest-homeassistant-custom-component` pin sets it. Python ≥ 3.14 |
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

## 1. Repository layout

```
HA-NortecGo/
├── custom_components/nortec_go/
│   ├── __init__.py
│   ├── manifest.json
│   ├── const.py
│   ├── strings.json
│   ├── translations/en.json
│   └── quality_scale.yaml
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

- `manifest.json`: `domain: nortec_go`, `name: Nortec Go`, `version: 0.0.1`, `requirements: []`,
  `dependencies: []`, `codeowners: ["@thomas3650"]`, `config_flow: false`, `iot_class: cloud_polling`,
  `integration_type: hub`, and `documentation` and `issue_tracker` pointing to this repo. `config_flow` stays
  `false` until the config-flow feature adds one, because hassfest checks that the flag matches a
  `config_flow.py`.
- `__init__.py`: only `async_setup_entry` (returns `True`) and `async_unload_entry` (returns `True`), typed.
  No platforms yet.
- `const.py`: `DOMAIN: Final = "nortec_go"`.
- `strings.json`: a minimal valid file. `translations/en.json` is an exact copy (the core layout; HA loads
  `translations/` for custom integrations). A test asserts the two are identical.
- `quality_scale.yaml`: every rule from Bronze to Platinum, in core's format. Each is `todo`, or `exempt` with
  a `comment` giving the reason. The plan looks up the current rule list from HA core at implementation time.
- `tests/conftest.py`: enables custom integrations (`enable_custom_integrations`, autouse).
- `tests/test_init.py`: sets up a `MockConfigEntry` for `nortec_go`, asserts it reaches `LOADED`, unloads it
  and asserts `NOT_LOADED`; plus the `strings.json` = `en.json` test.

### 1.2 Other root files

- `hacs.json`: `name: Nortec Go`, `homeassistant: <current stable version>`, `render_readme: true`.
- `LICENSE`: Apache-2.0 text, copyright "2026 thomas jørgensen".
- `SECURITY.md`: report privately via GitHub private vulnerability reporting; don't open public issues for
  security problems.
- `CHANGELOG.md`: Keep a Changelog format, with `## [Unreleased]` and `## [0.0.1] - <release date>` ("Initial
  project skeleton; not usable yet").
- `scripts/develop`: creates `config/` if missing, and runs `uv run hass -c config --debug` with
  `PYTHONPATH` set so HA finds `custom_components/`. `config/` is gitignored.
- `.devcontainer/devcontainer.json`: a Python 3.14 image, runs `uv sync` on create, forwards port 8123. The
  file and `docs/way-of-working.md` both say it is for manual testing only.

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
holds the real version), `requires-python = ">=3.14"`, no dependencies, and no build system.

- A `dev` dependency group: `pytest-homeassistant-custom-component` (pinned exactly), `pytest-cov`, `ruff`,
  `mypy`, `pre-commit`.
- **ruff:** HA core's `select`/`ignore` lists, copied from core's `pyproject.toml` at implementation time, with
  rules that only make sense for the core monorepo removed (the plan lists what it removed and why).
- **mypy:** `strict = true` for `custom_components` and `tests`.
- **pytest:** `asyncio_mode = "auto"`, `testpaths = ["tests"]`,
  `addopts = "--cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95"`.

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
| `tests.yml` | `tests` | PR, push to main | `uv sync --locked`; `pytest` (coverage ≥ 95%) |
| `hassfest.yml` | `hassfest` | PR, push to main, weekly | `home-assistant/actions/hassfest` |
| `hacs.yml` | `hacs` | PR, push to main, weekly | `hacs/action`, `category: integration`, `ignore: brands` (see below) |
| `gitleaks.yml` | `gitleaks` | PR, push to main | gitleaks over the full history (`fetch-depth: 0`) |
| `release.yml` | `release` | push of tag `v*` | check tag = `v` + `manifest.json` version, else fail; extract that version's `CHANGELOG.md` section; `gh release create` with it as notes, `--prerelease` when the version is `0.0.x` or has a `-` suffix |

- Every action is pinned to a commit SHA with a version comment.
- `permissions: contents: read` at the top of every workflow; `release.yml` has `contents: write`.
- **HACS ignores:**
  - `brands` is ignored because the integration isn't in `home-assistant/brands` yet. Adding the brand is a
    follow-up issue.
  - If the HACS `releases` check fails on the PR because no release exists yet, `releases` is ignored too, and
    a trivial PR removes that ignore after `v0.0.1` (§4 step 7).
  - The reason for each ignore is written as a comment in `hacs.yml`.

### 2.4 Dependabot

`github-actions` and `uv`, monthly, each ecosystem's updates grouped into one PR. When
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
- **Commands:** `uv sync`, `uv run pytest -q`, `uv run ruff check && uv run ruff format --check && uv run
  mypy`, `uv run pre-commit install`, `scripts/develop`.
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
  5. Diagnostics and logs redact tokens, email, IDs and location (`async_redact_data`), and credentials are
     never logged. Anything taken from a real instance (diagnostics downloads, logs, dumps) goes in `local/`
     and is never committed.
  6. Never auto-retry `start_charge`. On `AuthError`, start reauth instead of retrying login (login is
     rate-limited; a start places a card hold).
  7. Test fixtures are built from `pynortecgo` model objects, never from raw API JSON.
  8. What the client needs goes to `NortecGo` as a change request (`docs/way-of-working.md`), never patched or
     vendored here.
  9. Subagents never read `.env` directly.
- **Context:** the owner's own charger and account.
- `@docs/README.md`.

### 3.2 `docs/way-of-working.md`

Copied from `NortecGo` and adapted.

- **Starts with a sync note:** "A sibling copy lives in the private `NortecGo` repo. A process change in either
  copy gets a follow-up issue in the other repo."
- **Removed:** `api.md`, `api-standard.md`, the `document-endpoint` skill, `captures/`, PyPI, and the
  "no server-side ruleset" caveat.
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
- **Controller permissions:** the same table as `NortecGo`. The one-time settings in this work (§4) are an
  explicit exception, each step approved by the owner.

### 3.3 `.claude/`

- **Agents** (`implementer`, `task-reviewer`, `full-reviewer`): "pynortecgo repo" becomes "HA-NortecGo"
  (public HACS integration repo), and the gate commands become this repo's (§3.1). References to
  `check_api_md.py`, `captures/`, `docs/api.md`, `docs/api-standard.md`, `uv build` and the published package
  are removed. The branch review also checks hard rule 3 across the diff.
- **`hooks/subagent_guard.py`:** unchanged. Its docstring's design links point into `NortecGo`, which is
  private, so they are replaced with a pointer to this spec.
- **`settings.json`:** unchanged.
- **`skills/document-endpoint/`:** deleted.

### 3.4 `docs/`

- `README.md`: the documentation map. One table: doc, contents, read it when.
- `decisions.md`: the same header and entry format as `NortecGo`, with these entries, each linking to this
  spec:
  - D1 domain `nortec_go`
  - D2 HACS install, core-quality target, Silver first
  - D3 Apache-2.0
  - D4 `uv` tooling; current stable HA only; Python ≥ 3.14; optional devcontainer, never the gate environment
  - D5 squash-only merges
  - D6 five required checks
  - D7 no dependency in the skeleton; `pynortecgo` pinned exactly once it's added; only its public API is used
  - D8 way of working copied with a sync note; client change requests via `nortecgo-af` or `gh issue create`
  - D9 user docs in home-assistant.io format
  - D10 manual releases
  - D11 GitHub settings applied once with `gh`; issues limited to collaborators
  - D12 real data only in `local/`
  - D13 no Claude memory; questions as plain text (inherited)
- `releasing.md`:
  - the bump PR (`manifest.json` version, the CHANGELOG section moved from *Unreleased*);
  - the owner pushes the tag;
  - what `release.yml` checks;
  - pre-release rules;
  - bumping the `pynortecgo` pin.
- `notes.md`: dated small facts. First entry: how to renew the interaction limit
  (`gh api -X PUT repos/thomas3650/HA-NortecGo/interaction-limits -f limit=collaborators_only -f expiry=six_months`)
  and when it expires.
- `user/nortec_go.md`: home-assistant.io page sections:
  - front matter-style title and intro;
  - the unofficial disclaimer;
  - prerequisites;
  - installation (HACS custom repository);
  - configuration;
  - removal;
  - troubleshooting.

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
   - squash merge only (`allow_merge_commit: false`, `allow_rebase_merge: false`), with
     `squash_merge_commit_title: PR_TITLE` and `squash_merge_commit_message: PR_BODY`;
   - `delete_branch_on_merge: true`, `allow_auto_merge: false`;
   - Dependabot alerts and security updates on;
   - secret scanning and push protection on;
   - private vulnerability reporting on;
   - interaction limit `collaborators_only` for `six_months`.
2. Commit the spec and plan on `chore/ground-structure`, push, and open a **draft PR** with `Closes #1` and
   links to both.
3. Execute the plan (SDD). CI goes green on the PR, so all five check names exist.
4. **⏸ Update the `main` protection:**
   - required status checks `lint`, `tests`, `hassfest`, `hacs`, `gitleaks`, with `strict: true`;
   - everything already set stays: PR required with 0 approvals, conversation resolution, admins included,
     no force pushes, no deletions.
5. Branch review until Ready, then ready the PR. **The owner merges.**
6. **The owner** tags `v0.0.1` on `main` and pushes the tag. `release.yml` publishes a pre-release.
7. If `hacs.yml` ignores `releases`, a trivial PR removes that ignore, and `hacs` must pass without it.
8. The controller files these issues:
   - "Renew interaction limit (expires YYYY-MM-DD)";
   - "Add Nortec Go to home-assistant/brands, then drop the HACS `brands` ignore".

## 5. Verification

**Local, on the branch:**
- `uv sync --locked`, `uv run pytest -q` (coverage ≥ 95%), `uv run ruff check`, `uv run ruff format --check`
  and `uv run mypy` all pass.
- `uv run pre-commit run --all-files` passes.
- A commit attempted on `main` is refused by the hook, checked with a throwaway commit that the hook stops.
- `scripts/develop` starts HA, and the log shows no errors from `nortec_go`. The integration isn't configured
  yet, so the check is that HA starts cleanly with the custom component present.
- `grep -rnE "ory_st_[A-Za-z0-9]{8,}|@[a-z0-9.-]+\.[a-z]{2,}" --exclude-dir=.git .` prints only allowed hits:
  the `noreply` trailer and the GitHub handle.

**CI:** all five checks are green on the PR.

**GitHub, after each ⏸ step:** `gh api repos/thomas3650/HA-NortecGo` and the protection, security and
interaction-limit endpoints match §4. After the interaction limit is set, check that a Dependabot PR can still
be opened (Dependabot is an app, so the limit isn't expected to affect it).

**After the release:**
- `gh release view v0.0.1` shows a pre-release with the CHANGELOG notes.
- `hassfest` and `hacs` pass on `main`.

**Reviews:** `full-reviewer` reviews this spec, then the plan, then the branch, each until Ready.
