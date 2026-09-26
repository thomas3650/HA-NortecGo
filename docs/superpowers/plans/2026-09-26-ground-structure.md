# Ground structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Put the base of the public HA-NortecGo repo in place: an empty `nortec_go` integration skeleton,
tooling, CI, docs, the adapted `.claude/` setup, GitHub settings and a `v0.0.1` pre-release.

**Architecture:** A HACS custom integration under `custom_components/nortec_go/`, developed with a dev-only
`uv` project (`pyproject.toml` + `uv.lock`) and tested with `pytest-homeassistant-custom-component`. The
skeleton has only `async_setup` plus a UI-only config schema; there is no config entry and no `pynortecgo`
dependency yet. GitHub settings and the release are controller/owner steps outside the tasks.

**Tech Stack:** Python 3.14, Home Assistant 2026.9.3 (via `pytest-homeassistant-custom-component==0.13.366`),
uv, ruff, mypy (strict), pytest + pytest-cov, pre-commit, gitleaks, GitHub Actions, HACS action, hassfest.

**Spec:** `docs/superpowers/specs/2026-09-26-ground-structure-design.md`. Read it with this plan; every section
number (§) below refers to it.

## Global Constraints

- Domain `nortec_go`; name `Nortec Go`; codeowner `@thomas3650`; repo `thomas3650/HA-NortecGo`.
- `requires-python = ">=3.14.2"` (HA 2026.9.3's requirement); dev pin
  `pytest-homeassistant-custom-component==0.13.366` (pins `homeassistant==2026.9.3`).
- `manifest.json`: `"requirements": []`, `"version": "0.0.1"`, keys in the order `domain`, `name`, then
  alphabetical.
- License Apache-2.0. It's merged to `main` in its own PR before this branch's PR (controller step C2), so no
  task creates `LICENSE`.
- Nothing private in the repo: no account, charger or user IDs, tokens, emails (other than the
  `noreply@anthropic.com` commit trailer), captures, APK references, links into the private `NortecGo` repo's
  docs, or raw API endpoints/headers/response shapes (hard rule 3).
- Subagents never read `.env`, `local/` or `config/`.
- Docs are written in plain, short sentences; GitHub-flavoured Markdown; lines ≤ 120 characters in `.md`
  files.
- Gates before every commit (run in the task's working directory):
  `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`.
  A task that runs before Task 1's files exist on its base runs only the gates that apply to its files (stated
  in the task).
- Commit messages end with the co-author trailer given in the dispatch.

## Review Focus

1. A YAML `nortec_go:` key in `configuration.yaml`: HA should still start, log the "does not support YAML
   setup" error and raise the `config_entry_only_nortec_go` repair issue, not crash. → Task 1,
   `test_yaml_config_is_rejected`.
2. HA discovering the component at all (`custom_components` import path clash with the test package): the
   "custom integration nortec_go" loader warning must appear. → Task 1, `test_component_is_discovered`.
3. `strings.json` and `translations/en.json` drifting apart when a later feature edits one. → Task 1,
   `test_translations_match_strings`.
4. A typo'd or missing status in `quality_scale.yaml` (hassfest doesn't validate it for custom integrations).
   → Task 4, `test_quality_scale_statuses`.
5. A release tag that doesn't match `manifest.json`, or a CHANGELOG with no section for it: the release must
   fail, not publish empty notes. → Task 5, the `release.yml` checks, tested locally in Task 5 Step 5.

## Execution overview

**Controller steps (not tasks; spec §4).** ⏸ = wait for the owner's explicit OK.

- **C1 ⏸** Apply the repo settings (§4 step 1) with `gh`, then verify them read-only.
- **C2 ⏸** LICENSE-only PR from `chore/license` (§4 step 2). The owner merges it. Rebase
  `chore/ground-structure` onto `main`.
- **C3** Push `chore/ground-structure`; open a **draft PR** (`Closes #1`, links to spec and plan).
- **C4** Run Tasks 1–8 by wave (SDD, `implementer` + `task-reviewer`); push after each Approved task.
  Worktrees for Tasks 2 and 3 skip `uv sync` (there's no `pyproject.toml` on the base yet).
- **C4a** Before dispatching Task 8: the controller runs `git rm -r .claude/skills/document-endpoint`, commits
  and pushes (Task 8 *Before dispatch*).
- **C5 ⏸** After CI is green on the PR: the full branch-protection `PUT` (§4 step 5).
- **C6** Controller verification (§5 "Local" and "CI"), `full-reviewer` on the branch until Ready, the
  learnings step, then `gh pr ready` and tell the owner. **The owner merges.**
- **C7** After merge: the owner tags `v0.0.1`; the controller verifies the release, Dependabot (§5 "After the
  merge"), checks `hassfest` and `hacs` pass on `main` (§5 *After the release*), files the "Renew interaction
  limit (expires 2027-03-26)" issue (§4 step 8), and asks `nortecgo-af` to file the sync issue in `NortecGo`
  (§3.6). That issue lists the sync note **and** D16's process changes (draft PR once spec and plan are Ready,
  push after each approved task, ready only when owner review is needed, delegated plan approval).

**Waves.**

| Wave | Tasks | Notes |
|---|---|---|
| 1 | 1, 2, 3 | Disjoint files. 2 and 3 are docs written against the names this plan fixes. |
| 2 | 4, 5, 6 | Need Task 1's `pyproject.toml`/`uv.lock`. Disjoint files. |
| 3 | 7 | Guarded (`.pre-commit-config.yaml`), alone, main checkout. |
| 4 | 8 | Guarded (`.claude/`), alone, main checkout. |

## File map

| File | Task | Responsibility |
|---|---|---|
| `pyproject.toml`, `uv.lock` | 1 | Dev deps, ruff, mypy, pytest config |
| `.gitignore` | 1 | Adds HA data patterns |
| `hacs.json` | 1 | HACS metadata |
| `custom_components/nortec_go/{__init__.py,const.py,manifest.json,strings.json,translations/en.json}` | 1 | The skeleton |
| `tests/{__init__.py,conftest.py,test_init.py}` | 1 | Smoke tests |
| `README.md`, `CHANGELOG.md`, `SECURITY.md`, `docs/user/nortec_go.md`, `docs/releasing.md` | 2 | User-facing docs, release process |
| `CLAUDE.md`, `docs/way-of-working.md`, `docs/decisions.md`, `docs/README.md`, `docs/notes.md` | 3 | Process docs |
| `custom_components/nortec_go/quality_scale.yaml`, `custom_components/nortec_go/brand/*`, `tests/test_quality_scale.py` | 4 | Quality scale and brand |
| `.github/**` | 5 | CI, release, Dependabot, templates |
| `scripts/develop`, `.devcontainer/devcontainer.json` | 6 | Manual testing |
| `.pre-commit-config.yaml` | 7 | Local hooks |
| `.claude/agents/*.md`, `.claude/hooks/subagent_guard.py` (docstring) | 8 | Claude setup |
| `.claude/skills/document-endpoint/` (deleted) | C4a | Controller, before Task 8 |

---

### Task 1: Dev tooling and the integration skeleton

**Model:** sonnet · **Wave:** 1

**Files:**
- Create: `pyproject.toml`, `uv.lock` (generated), `hacs.json`
- Create: `custom_components/nortec_go/__init__.py`, `const.py`, `manifest.json`, `strings.json`,
  `translations/en.json`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/test_init.py`
- Modify: `.gitignore` (append)

**Interfaces:**
- Produces: `custom_components.nortec_go.const.DOMAIN: Final = "nortec_go"`;
  `custom_components.nortec_go.async_setup(hass: HomeAssistant, config: ConfigType) -> bool`;
  `custom_components.nortec_go.CONFIG_SCHEMA`; the gate commands in Global Constraints; the autouse fixture
  in `tests/conftest.py` that later test files rely on.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "ha-nortecgo"
version = "0.0.0"
description = "Dev environment for the Nortec Go Home Assistant integration (not a package)."
requires-python = ">=3.14.2"
dependencies = []

[dependency-groups]
dev = [
  "pytest-homeassistant-custom-component==0.13.366",
  "pytest-cov",
  "ruff",
  "mypy",
  "pre-commit",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.mypy]
python_version = "3.14"
strict = true
files = ["custom_components", "tests"]
explicit_package_bases = true

[[tool.mypy.overrides]]
module = ["pytest_homeassistant_custom_component.*"]
ignore_missing_imports = true

[tool.ruff]
required-version = ">=0.16.8"

[tool.ruff.lint]
# Copied from HA core's pyproject.toml (dev, 2026-09-26).
select = [
  "A001", "ASYNC", "B", "BLE", "C", "COM818", "D", "DTZ003", "DTZ004", "DTZ011", "E", "F", "F541", "FLY",
  "FURB", "G", "I", "INP", "ISC", "ICN001", "ICN002", "LOG", "N804", "N805", "N806", "N815", "PERF", "PGH",
  "PIE", "PL", "PT", "PTH", "PYI", "RET", "RSE", "RUF", "S107", "S102", "S103", "S108", "S301", "S306",
  "S307", "S313", "S314", "S315", "S316", "S317", "S318", "S319", "S601", "S602", "S604", "S608", "S609",
  "SIM", "SLF", "SLOT", "T100", "T20", "TC", "TID", "TRY", "UP", "UP031", "UP032", "W",
]
ignore = [
  "ASYNC109", "ASYNC110", "ASYNC240", "B008", "B019", "D202", "D203", "D213", "D406", "D407", "D417", "E501",
  "PLC1901", "PLR0911", "PLR0912", "PLR0913", "PLR0915", "PLR0917", "PLR2004", "PLW0108", "PLW1641",
  "PLW2901", "PT011", "PT018", "RUF001", "RUF012", "RUF015", "RUF043", "SIM102", "SIM103", "SIM108",
  "SIM115", "TC001", "TC002", "TC003", "TC006", "TRY003", "TRY400", "UP047", "UP049",
  # May conflict with the formatter.
  "W191", "E111", "E114", "E117", "D206", "D300", "Q", "COM812", "COM819",
  "PLE0605", "FURB116", "ISC004", "LOG004",
]

[tool.ruff.lint.flake8-import-conventions.extend-aliases]
"homeassistant.core.DOMAIN" = "HOMEASSISTANT_DOMAIN"
"homeassistant.helpers.area_registry" = "ar"
"homeassistant.helpers.config_validation" = "cv"
"homeassistant.helpers.device_registry" = "dr"
"homeassistant.helpers.entity_registry" = "er"
"homeassistant.helpers.issue_registry" = "ir"
"homeassistant.util.dt" = "dt_util"
"homeassistant.util.yaml" = "yaml_util"

[tool.ruff.lint.flake8-import-conventions.banned-aliases]
"probatio" = ["vol"]

[tool.ruff.lint.flake8-pytest-style]
fixture-parentheses = false
mark-parentheses = false

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"async_timeout".msg = "use asyncio.timeout instead"
"pytz".msg = "use zoneinfo instead"
"voluptuous".msg = "use probatio instead"
"__future__.annotations".msg = "It should not be needed because Home Assistant requires Python 3.14+"

[tool.ruff.lint.isort]
force-sort-within-sections = true
known-first-party = ["custom_components.nortec_go", "tests"]
combine-as-imports = true
split-on-trailing-comma = false

[tool.ruff.lint.mccabe]
max-complexity = 25

[tool.ruff.lint.pydocstyle]
convention = "google"
```

Removed from core's config, and why (record this list in the task report):
- `extend-aliases` for the ~40 `homeassistant.components.*.PLATFORM_SCHEMA` entries and the unused
  registries/utils (category, floor, label registries; color, json, location, logging, network, ulid, uuid
  utils): they only matter for YAML platforms or helpers this integration doesn't use. Re-add one when a
  feature imports it.
- `banned-api` `"tests"`: core bans importing its test package; here `tests` is our own package.
- All `per-file-ignores`: they target core paths (`homeassistant/**`, `script/*`, `benchmarks/**`).
- `pydocstyle.property-decorators` (`propcache.api.cached_property`): not used here.

- [ ] **Step 2: Lock and sync**

Run: `uv lock && uv sync`
Expected: `uv.lock` created; resolves `homeassistant==2026.9.3`. If `uv lock` reports the Python range is
unsatisfiable, stop and report BLOCKED (don't change `requires-python`).

- [ ] **Step 3: Write the failing tests**

`tests/__init__.py`:

```python
"""Tests for the Nortec Go integration."""
```

`tests/conftest.py`:

```python
"""Fixtures for the Nortec Go tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from custom_components in every test."""
```

`tests/test_init.py`:

```python
"""Tests for the Nortec Go integration setup."""

import json
import logging
from pathlib import Path

from homeassistant import loader
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
import pytest

from custom_components.nortec_go.const import DOMAIN

INTEGRATION_DIR = Path(__file__).parent.parent / "custom_components" / DOMAIN


async def test_setup(hass: HomeAssistant) -> None:
    """The integration sets up without any configuration."""
    assert await async_setup_component(hass, DOMAIN, {})
    assert DOMAIN in hass.config.components


async def test_yaml_config_is_rejected(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A YAML key doesn't break setup; it logs an error and raises a repair issue."""
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    assert "does not support YAML setup" in caplog.text
    issue = ir.async_get(hass).async_get_issue(
        HOMEASSISTANT_DOMAIN, f"config_entry_only_{DOMAIN}"
    )
    assert issue is not None


async def test_component_is_discovered(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Home Assistant's loader finds the custom component."""
    caplog.set_level(logging.WARNING)
    await loader.async_get_integration(hass, "sun")
    assert f"custom integration {DOMAIN}" in caplog.text


def test_translations_match_strings() -> None:
    """translations/en.json is an exact copy of strings.json."""
    strings = json.loads((INTEGRATION_DIR / "strings.json").read_text(encoding="utf-8"))
    english = json.loads(
        (INTEGRATION_DIR / "translations" / "en.json").read_text(encoding="utf-8")
    )
    assert english == strings
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest -q`
Expected: collection error `ModuleNotFoundError: No module named 'custom_components'`.

- [ ] **Step 5: Write the skeleton**

`custom_components/nortec_go/const.py`:

```python
"""Constants for the Nortec Go integration."""

from typing import Final

DOMAIN: Final = "nortec_go"
```

`custom_components/nortec_go/__init__.py`:

```python
"""The Nortec Go integration."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Nortec Go integration."""
    return True
```

`custom_components/nortec_go/manifest.json` (exact key order):

```json
{
  "domain": "nortec_go",
  "name": "Nortec Go",
  "codeowners": ["@thomas3650"],
  "config_flow": false,
  "dependencies": [],
  "documentation": "https://github.com/thomas3650/HA-NortecGo/blob/main/docs/user/nortec_go.md",
  "integration_type": "hub",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/thomas3650/HA-NortecGo/issues",
  "requirements": [],
  "version": "0.0.1"
}
```

`custom_components/nortec_go/strings.json` and `custom_components/nortec_go/translations/en.json` (identical):

```json
{}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest -q`
Expected: 4 passed. If `test_component_is_discovered` fails because the warning text differs, read
`homeassistant/loader.py` (`resolve_from_root`) in `.venv`, match the actual text, and note it in the report.
If `test_yaml_config_is_rejected` fails on the issue ID, read `_no_yaml_config_schema` in
`homeassistant/helpers/config_validation.py` and match it.

- [ ] **Step 7: Write `hacs.json` and extend `.gitignore`**

`hacs.json`:

```json
{
  "name": "Nortec Go",
  "homeassistant": "2026.9.3"
}
```

Append to `.gitignore` (keep existing lines):

```gitignore

# HA diagnostics downloads (real data goes in local/)
config_entry-*.json
*diagnostics*.json

# HA logs and state
*.log
home-assistant_v2.db*
.storage/
```

- [ ] **Step 8: Run all gates**

Run: `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`
Expected: all pass, coverage 100%. Fix lint/format/type findings in the files of this task (`uv run ruff format`
is allowed). If mypy reports `import-untyped` for a module other than
`pytest_homeassistant_custom_component`, report it rather than adding overrides.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock hacs.json .gitignore custom_components tests
git commit -F <message file>   # "feat: add dev tooling and nortec_go integration skeleton" + trailer
```

---

### Task 2: User-facing docs and release process

**Model:** sonnet · **Wave:** 1

**Files:**
- Create: `README.md`, `CHANGELOG.md`, `SECURITY.md`, `docs/user/nortec_go.md`, `docs/releasing.md`

**Interfaces:**
- Consumes (names fixed by this plan): `manifest.json` `version` `0.0.1`; `release.yml` behaviour (Task 5:
  tag must equal `v` + manifest version; the CHANGELOG section `## [X.Y.Z]` must exist and be non-empty;
  `--prerelease` for `0.0.x` or a `-` suffix); `hacs.json` `homeassistant` minimum.
- Produces: `docs/user/nortec_go.md` (linked from `manifest.json` and `README.md`).

Gates for this task: docs only; run `git diff --check` and the private-data scan from spec §5 (both print
nothing).

- [ ] **Step 1: Write `README.md`**

Sections, in order (short; no private data):
1. `# Nortec Go for Home Assistant` and one sentence: an unofficial Home Assistant integration for Nortec Go
   EV chargers (a white-label Monta app).
2. A blockquote: **Unofficial.** Not affiliated with, endorsed by or supported by Nortec or Monta. It uses the
   same private API as the app (through the `pynortecgo` library), which can change without notice.
3. `## Status`: "Skeleton only; not usable yet. Follow the [changelog](CHANGELOG.md)."
4. `## Installation`: via HACS as a custom repository (HACS → ⋮ → Custom repositories → add
   `https://github.com/thomas3650/HA-NortecGo`, type *Integration*), then restart Home Assistant.
5. `## Documentation`: link to [`docs/user/nortec_go.md`](docs/user/nortec_go.md).
6. `## License`: Apache-2.0, see `LICENSE`.

- [ ] **Step 2: Write `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.0.1] - 2026-09-26

### Added

- Initial project skeleton; not usable yet.
```

(The controller updates the date when readying the PR, per spec §1.2.)

- [ ] **Step 3: Write `SECURITY.md`**

Content: how to report a vulnerability privately (GitHub → Security → *Report a vulnerability*, i.e. private
vulnerability reporting); don't open public issues or PRs for security problems; supported version is the
latest release only.

- [ ] **Step 4: Write `docs/user/nortec_go.md`**

Follow spec §3.4 exactly. Start with this front matter, then the sections in the spec's order, each as `##`
headings (Actions, Conditions and Triggers as one `## Actions, conditions and triggers` section). Plain
Markdown only: no Liquid tags. Each section with nothing to describe yet contains exactly "Not available yet."

```markdown
---
title: Nortec Go
description: Instructions on how to integrate a Nortec Go EV charger into Home Assistant.
ha_iot_class: Cloud Polling
ha_domain: nortec_go
ha_integration_type: hub
ha_codeowners:
  - '@thomas3650'
---
```

Intro (before the first `##`): the **Nortec Go** integration connects Home Assistant to an EV charger managed
through the Nortec Go app, a white-label version of the [Monta](https://monta.com) app, plus the unofficial
disclaimer from `README.md`. Prerequisites: a Nortec Go account with exactly one charger and one car (as the
client library supports). Installation: the HACS custom-repository steps from `README.md`, noting this
section isn't in core's template. Removing the integration: remove it from *Settings → Devices & services*
(once it has a config flow), then remove it in HACS and restart.

- [ ] **Step 5: Write `docs/releasing.md`**

Sections:
- **Versioning:** semver; `0.0.x` and versions with a `-` suffix are published as pre-releases.
- **The bump PR:** set `version` in `custom_components/nortec_go/manifest.json`; move *Unreleased* entries under
  `## [X.Y.Z] - YYYY-MM-DD` in `CHANGELOG.md`; merge.
- **Tagging (owner only):** `git switch main && git pull && git tag vX.Y.Z && git push origin vX.Y.Z`.
- **What `release.yml` checks:** tag = `v` + manifest version, else fail; the `## [X.Y.Z]` section exists and
  isn't empty, else fail; then `gh release create` with that section as notes.
- **Bumping `pynortecgo`:** once the integration depends on it, `requirements` pins `pynortecgo==X.Y.Z`
  exactly; a new client release gets its own PR that bumps the pin and runs the gates.
- **Bumping HA:** a `pytest-homeassistant-custom-component` bump PR also raises `hacs.json` → `homeassistant`
  to the HA version it pins, and `requires-python` if that HA version needs it.

- [ ] **Step 6: Check and commit**

Run: `git diff --check` and
`git grep -nE 'ory_st_[A-Za-z0-9]{8,}|[A-Za-z0-9._%+-]+@[A-Za-z][A-Za-z0-9-]*\.[A-Za-z]{2,}' | grep -v 'noreply@anthropic\.com'`
Expected: both print nothing.

```bash
git add README.md CHANGELOG.md SECURITY.md docs/user/nortec_go.md docs/releasing.md
git commit -F <message file>   # "docs: add README, changelog, security policy, user docs and release process" + trailer
```

---

### Task 3: Process docs

**Model:** sonnet · **Wave:** 1

**Files:**
- Create: `CLAUDE.md`, `docs/way-of-working.md`, `docs/decisions.md`, `docs/README.md`, `docs/notes.md`
- Read (source for the copy): `/Users/thomas/Documents/Sourcecode/NortecGo/CLAUDE.md`,
  `/Users/thomas/Documents/Sourcecode/NortecGo/docs/way-of-working.md`,
  `/Users/thomas/Documents/Sourcecode/NortecGo/docs/decisions.md` (only these three files in that repo).

**Interfaces:**
- Consumes (names fixed by this plan): the gate commands (Global Constraints); `scripts/develop` (Task 6);
  doc paths in the File map; the spec's Appendix A links.
- Produces: `CLAUDE.md` imports `@docs/way-of-working.md` and `@docs/README.md`.

Gates for this task: docs only; `git diff --check` and the private-data scan (print nothing).

- [ ] **Step 1: Write `CLAUDE.md`**

Structure per spec §3.1, modelled on `NortecGo/CLAUDE.md`:
- `## What this repo is`: the public HACS integration; talks only to `pynortecgo`'s public API; the client
  lives in the private `NortecGo` repo; unofficial.
- `## Layout`: `custom_components/nortec_go/`, `tests/`, `docs/` (map: `docs/README.md`), `scripts/`,
  `.devcontainer/` (manual testing only), `.claude/`, `.github/`.
- `## Commands` (a bash block):

```bash
uv sync                          # set up / update the dev environment
uv run pytest -q                 # tests, fast, no coverage
uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95   # coverage gate
uv run ruff check && uv run ruff format --check && uv run mypy
uv run pre-commit install        # once per clone: local hooks incl. no-commit and no-push to main
scripts/develop                  # run Home Assistant locally with the integration (config/ is gitignored)
```

- `## Way of working` + `@docs/way-of-working.md`.
- `## Code and docs rules`: the three bullets of spec §3.1.
- `## Hard rules`: rules 1–9 exactly as in spec §3.1 (rule 9 as amended: `.env`, `local/`, `config/`).
- `## Context`: authorised work on the owner's own charger and account; the same note as `NortecGo` about the
  safety classifier interrupting `gh`/`git` calls (check whether an interrupted call ran before retrying).
- `## Documentation map` + `@docs/README.md`.

- [ ] **Step 2: Write `docs/way-of-working.md`**

Copy `NortecGo/docs/way-of-working.md` and adapt per spec §3.2 (Removed, Renumbered, `captures/` → `local/`,
Changed, Added, Controller permissions). Also:
- The sync note is the first paragraph after the title.
- §1 Flow, step 6 (draft PR) reads: "**Draft PR:** once the spec and plan are both Ready, commit them, push,
  and open a **draft** PR with `Closes #n` and links to the spec and plan. The owner reviews the spec and plan
  there."
- §1 Flow, step 7 keeps "push once it is Approved" (every approved task is committed and pushed).
- §1 Flow, step 10 reads: "**Ready:** update the PR description (Rulings, learnings), then `gh pr ready` only
  when the owner's review is needed, and tell the owner."
- Add to §6 Conventions: "**Delegated plan approval:** the owner may let the controller approve a plan once
  `full-reviewer` rates it Ready; the spec always needs the owner's approval."
- §5 Model policy: the `Model: opus` list from spec §3.2 *Changed*.
- Gates: the Global Constraints gate command; "hassfest and HACS run in CI only".
- Keep *Parallel waves* but replace `uv sync` references with this repo's, and `#5` (a NortecGo issue number)
  with plain text.

- [ ] **Step 3: Write `docs/decisions.md`**

The header paragraph from `NortecGo/docs/decisions.md` (pointing to `way-of-working.md` §7), then D1–D15 as
listed in spec §3.4, each in the format:

```markdown
### D1: Domain `nortec_go`
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** The integration's domain is `nortec_go`.
- **Why:** Core names two-word brands in snake_case; the domain can't change later.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions
```

Each entry's Decision and Why come from the spec's Decisions table and the section it cites; one or two
sentences each. D13 notes it's inherited from `NortecGo` ("NortecGo D10"), with no link.

Then add **D16: PR lifecycle and delegated plan approval** (Source: this plan, Task 3, owner request on
2026-09-26): a draft PR is opened once the spec and plan are both Ready so the owner can review them there;
every approved task is committed and pushed; the PR is marked ready only when the owner's review is needed; the
owner may delegate plan approval to the controller once `full-reviewer` rates the plan Ready, but the spec
always needs the owner's approval. Why: the owner reviews in the PR, and doesn't need to approve a plan the
reviewer has already passed.

- [ ] **Step 4: Write `docs/README.md`**

Title `# Documentation map`, one sentence (root `README.md` is the public intro). Table 1 (Doc | Contents | Read
it when) with rows for: `../README.md`, `../CLAUDE.md`, `way-of-working.md`, `decisions.md`, `releasing.md`,
`notes.md`, `user/nortec_go.md`, `superpowers/specs/`, `superpowers/plans/`. Then `## Useful links` with the
spec's Appendix A copied exactly (same groups, same URLs). Check every URL:

```bash
grep -oE 'https://[^ )>]+' docs/README.md | sort -u | while read -r u; do printf '%s %s\n' "$(curl -s -o /dev/null -L -w '%{http_code}' "$u")" "$u"; done
```

Expected: every line starts with `200`. A non-200 URL: find the current URL for the same page and use it;
note it in the report.

- [ ] **Step 5: Write `docs/notes.md`**

```markdown
# Notes

Small learned facts that fit no other doc, newest last. When a topic passes about three entries, propose
moving it to its own doc.

## 2026-09-26: Interaction limit

Issues and PRs from non-collaborators are blocked by a GitHub interaction limit (collaborators only), which
expires after six months. Renew it with:

`gh api -X PUT repos/thomas3650/HA-NortecGo/interaction-limits -f limit=collaborators_only -f expiry=six_months`

Check the current limit and its expiry with `gh api repos/thomas3650/HA-NortecGo/interaction-limits`.

Set on 2026-09-26; expires 2027-03-26.

## 2026-09-26: CI images aren't pinned

The workflow actions are pinned to commit SHAs, but `hacs/action` runs the Docker image
`ghcr.io/hacs/action:main` and the hassfest action runs `ghcr.io/home-assistant/hassfest` unpinned, so their
checks can change without a change here. That's why both also run weekly.
```

- [ ] **Step 6: Check and commit**

Run `git diff --check` and the private-data scan (Task 2 Step 6). Expected: both print nothing.

```bash
git add CLAUDE.md docs/way-of-working.md docs/decisions.md docs/README.md docs/notes.md
git commit -F <message file>   # "docs: add CLAUDE.md, way of working, decisions, doc map and notes" + trailer
```

---

### Task 4: Quality scale and brand icon

**Model:** sonnet · **Wave:** 2

**Files:**
- Create: `custom_components/nortec_go/quality_scale.yaml`, `tests/test_quality_scale.py`
- Create: `custom_components/nortec_go/brand/icon.png`, `brand/icon@2x.png`, `brand/README.md`

**Interfaces:**
- Consumes: Task 1's `tests/conftest.py` fixture and `INTEGRATION_DIR` pattern; `DOMAIN`.
- Produces: `quality_scale.yaml` with every rule key below.

- [ ] **Step 1: Write the failing test**

`tests/test_quality_scale.py`:

```python
"""Tests for the quality scale file."""

from pathlib import Path

from homeassistant.util.yaml import load_yaml_dict

from custom_components.nortec_go.const import DOMAIN

QUALITY_SCALE = (
    Path(__file__).parent.parent / "custom_components" / DOMAIN / "quality_scale.yaml"
)
STATUSES = {"done", "todo", "exempt"}


def test_quality_scale_statuses() -> None:
    """Every rule has a known status, and every exemption says why."""
    rules = load_yaml_dict(QUALITY_SCALE)["rules"]
    assert rules
    for name, value in rules.items():
        if isinstance(value, str):
            assert value in STATUSES, name
            assert value != "exempt", f"{name}: exempt needs a comment"
        else:
            assert value["status"] in STATUSES, name
            if value["status"] == "exempt":
                assert value.get("comment"), name


def test_dependency_transparency_comment() -> None:
    """The comment isn't cut short by a YAML '#' comment marker."""
    rule = load_yaml_dict(QUALITY_SCALE)["rules"]["dependency-transparency"]
    assert rule["comment"].endswith("(issue #34).")


def test_rule_count() -> None:
    """All 54 rules from Bronze to Platinum are listed."""
    assert len(load_yaml_dict(QUALITY_SCALE)["rules"]) == 54
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_quality_scale.py -q`
Expected: FAIL with `FileNotFoundError` (or HA's `HomeAssistantError`) for `quality_scale.yaml`.

- [ ] **Step 3: Write `quality_scale.yaml`**

```yaml
rules:
  # Bronze
  action-setup: todo
  appropriate-polling: todo
  brands:
    status: done
    comment: "Local brand/ folder (HA >= 2026.3), accepted by HACS; moves to home-assistant/brands for a core submission."
  common-modules: todo
  config-flow: todo
  config-flow-test-coverage: todo
  dependency-transparency:
    status: todo
    comment: "The pynortecgo source repo is private; the rule needs an open repo, tags and a public publishing pipeline. Tracked in the pynortecgo repo (issue #34)."
  docs-actions: todo
  docs-conditions: todo
  docs-high-level-description: todo
  docs-installation-instructions: todo
  docs-removal-instructions: todo
  docs-triggers: todo
  entity-event-setup: todo
  entity-unique-id: todo
  has-entity-name: todo
  runtime-data: todo
  test-before-configure: todo
  test-before-setup: todo
  unique-config-entry: todo

  # Silver
  action-exceptions: todo
  config-entry-unloading: todo
  docs-configuration-parameters: todo
  docs-installation-parameters: todo
  entity-unavailable: todo
  integration-owner: todo
  log-when-unavailable: todo
  parallel-updates: todo
  reauthentication-flow: todo
  test-coverage: todo

  # Gold
  devices: todo
  diagnostics: todo
  discovery: todo
  discovery-update-info: todo
  docs-data-update: todo
  docs-examples: todo
  docs-known-limitations: todo
  docs-supported-devices: todo
  docs-supported-functions: todo
  docs-troubleshooting: todo
  docs-use-cases: todo
  dynamic-devices: todo
  entity-category: todo
  entity-device-class: todo
  entity-disabled-by-default: todo
  entity-translations: todo
  exception-translations: todo
  icon-translations: todo
  reconfiguration-flow: todo
  repair-issues: todo
  stale-devices: todo

  # Platinum
  async-dependency: todo
  inject-websession: todo
  strict-typing: todo
```

Before writing, confirm the rule list against the current docs: fetch
`https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/` and compare names. If the
count or names differ, use the docs' list, update `test_rule_count`, and note the difference in the report.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_quality_scale.py -q`
Expected: 3 passed.

- [ ] **Step 5: Render the brand icons**

The source is the Material Design Icons `ev-station` glyph, distributed under Apache-2.0 (Pictogrammers Free
License, "Icons: Apache 2.0"). Render it in HA blue with a transparent background:

Use a scratch directory outside the repo, e.g. `/tmp/nortec-brand` (create it; don't rely on `$TMPDIR`
being set). The guard refuses heredocs, so write the script with the **Write tool**.

```bash
mkdir -p custom_components/nortec_go/brand /tmp/nortec-brand
gh api repos/Templarian/MaterialDesign/contents/svg/ev-station.svg --jq .content | base64 -d > /tmp/nortec-brand/ev-station.svg
```

Write `/tmp/nortec-brand/render.py` (Write tool):

```python
"""Render the MDI ev-station glyph to the integration's brand icons."""

from pathlib import Path

import resvg_py

svg = Path("/tmp/nortec-brand/ev-station.svg").read_text(encoding="utf-8")
svg = svg.replace("<path ", '<path fill="#41BDF5" ')
for size, name in ((256, "icon.png"), (512, "icon@2x.png")):
    data = resvg_py.svg_to_bytes(svg_string=svg, width=size, height=size)
    Path("custom_components/nortec_go/brand", name).write_bytes(bytes(data))
```

```bash
uv run --no-project --with resvg-py==0.5.0 python /tmp/nortec-brand/render.py
file custom_components/nortec_go/brand/icon.png custom_components/nortec_go/brand/icon@2x.png
```

Expected: `PNG image data, 256 x 256, 8-bit/color RGBA` and `512 x 512, 8-bit/color RGBA`.

- [ ] **Step 6: Write `brand/README.md`**

```markdown
# Brand images

`icon.png` (256×256) and `icon@2x.png` (512×512) show the `ev-station` glyph from
[Material Design Icons](https://pictogrammers.com/library/mdi/icon/ev-station/) by Pictogrammers, used under
the Apache License 2.0 (Pictogrammers Free License: "Icons: Apache 2.0"), rendered in `#41BDF5` on a
transparent background. It is a neutral pictogram: no Nortec or Monta marks.

Home Assistant 2026.3 and later serves these local images for custom integrations, and HACS's brands check
accepts `brand/icon.png`. For a core submission, move them to
[home-assistant/brands](https://github.com/home-assistant/brands) instead.
```

- [ ] **Step 7: Run all gates and commit**

Run the gate command from Global Constraints. Expected: all pass.

```bash
git add custom_components/nortec_go/quality_scale.yaml custom_components/nortec_go/brand tests/test_quality_scale.py
git commit -F <message file>   # "feat: add quality scale tracking and brand icon" + trailer
```

---

### Task 5: CI, release, Dependabot and templates

**Model:** sonnet · **Wave:** 2

**Files:**
- Create: `.github/workflows/lint.yml`, `tests.yml`, `hassfest.yml`, `hacs.yml`, `gitleaks.yml`, `release.yml`
- Create: `.github/dependabot.yml`, `.github/pull_request_template.md`
- Create: `.github/ISSUE_TEMPLATE/config.yml`, `bug.yml`, `feature.yml`

**Interfaces:**
- Consumes: the gate commands; `manifest.json` `version`; `CHANGELOG.md` `## [X.Y.Z] - date` headings.
- Produces: required check names `lint`, `tests`, `hassfest`, `hacs`, `gitleaks` (job names).

Action pins (resolved 2026-09-26; keep the version comment):

| Action | Pin |
|---|---|
| `actions/checkout` | `3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1` |
| `astral-sh/setup-uv` | `c18668ad3cf93ea998bef934396af7bb5c839dc7  # v10.2.0` |
| `gitleaks/gitleaks-action` | `e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e  # v3.0.0` |
| `hacs/action` | `d556e736723344f83838d08488c983a15381059a  # 22.5.0` |
| `home-assistant/actions/hassfest` | `58bff37c8947f690ace498be413a9b78d6f30f93  # master 2026-09-26` |

- [ ] **Step 1: Write the check workflows**

`.github/workflows/lint.yml`:

```yaml
name: lint
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7  # v10.2.0
      - run: uv sync --locked
      - run: uv run ruff check
      - run: uv run ruff format --check
      - run: uv run mypy
```

`.github/workflows/tests.yml`: same header with `name: tests`, job `tests`, steps checkout, setup-uv,
`uv sync --locked`, then
`uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`.

`.github/workflows/hassfest.yml`:

```yaml
name: hassfest
on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: "0 6 * * 1"

permissions:
  contents: read

jobs:
  hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
      - uses: home-assistant/actions/hassfest@58bff37c8947f690ace498be413a9b78d6f30f93  # master 2026-09-26
```

`.github/workflows/hacs.yml`: same triggers and permissions as hassfest, job `hacs`, one step:

```yaml
      - uses: hacs/action@d556e736723344f83838d08488c983a15381059a  # 22.5.0
        with:
          category: integration
          comment: false
```

(`comment: false`: the default tries to comment on the PR, which needs write permission.)

`.github/workflows/gitleaks.yml`:

```yaml
name: gitleaks
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  pull-requests: read

jobs:
  gitleaks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e  # v3.0.0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 2: Write `release.yml`**

```yaml
name: release
on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
      - name: Tag must match manifest.json version
        run: |
          version="$(python3 -c 'import json; print(json.load(open("custom_components/nortec_go/manifest.json"))["version"])')"
          test "${GITHUB_REF_NAME}" = "v${version}" || { echo "Tag ${GITHUB_REF_NAME} != v${version}"; exit 1; }
          echo "VERSION=${version}" >> "$GITHUB_ENV"
      - name: Extract release notes from CHANGELOG.md
        run: |
          awk -v v="$VERSION" '
            $0 ~ "^## \\[" v "\\]" {found=1; next}
            found && /^## \[/ {exit}
            found {print}
          ' CHANGELOG.md > notes.md
          grep -q '[^[:space:]]' notes.md || { echo "No CHANGELOG section for $VERSION"; exit 1; }
      - name: Create the GitHub release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          flags=""
          case "$VERSION" in 0.0.*|*-*) flags="--prerelease" ;; esac
          gh release create "$GITHUB_REF_NAME" --title "$GITHUB_REF_NAME" --notes-file notes.md $flags
```

- [ ] **Step 3: Write Dependabot and templates**

`.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: monthly
    groups:
      github-actions:
        patterns: ["*"]
  - package-ecosystem: uv
    directory: /
    schedule:
      interval: monthly
    groups:
      uv:
        patterns: ["*"]
```

`.github/pull_request_template.md`:

```markdown
## What and why

<!-- One or two sentences. Link the spec/plan in docs/superpowers/ for non-trivial work. -->

Closes #

## Checklist

- [ ] Gates pass (ruff, ruff format, mypy, pytest with coverage ≥ 95%)
- [ ] `CHANGELOG.md` updated under *Unreleased* (user-visible changes)
- [ ] `custom_components/nortec_go/quality_scale.yaml` updated (rules completed or changed)
- [ ] `docs/user/nortec_go.md` updated (user-visible changes)
- [ ] No private data: IDs, tokens, emails, captures, raw API details, links into the private repo
- [ ] `pytest-homeassistant-custom-component` bump → `hacs.json` `homeassistant` minimum raised
- [ ] Lasting decision → `docs/decisions.md` entry
- [ ] `full-reviewer` run on the branch (non-trivial changes)
```

`.github/ISSUE_TEMPLATE/config.yml`:

```yaml
blank_issues_enabled: false
contact_links:
  - name: This repository isn't accepting external issues yet
    url: https://github.com/thomas3650/HA-NortecGo#status
    about: The integration is at an early stage and maintained for the owner's own use. Security problems go through SECURITY.md.
```

`bug.yml` (issue form, `name: Bug report`, `labels: [bug]`) with required textareas *What happened*, *What
you expected*, and required inputs *Home Assistant version*, *Integration version*; plus an optional
*Diagnostics / logs* textarea whose description says to redact tokens, email and IDs. `feature.yml`
(`name: Feature request`, `labels: [enhancement]`) with a required *User story* textarea ("As a …, I want …,
so that …").

- [ ] **Step 4: Validate the YAML**

Run: `uv run python -c "import sys, yaml; [yaml.safe_load(open(p)) for p in sys.argv[1:]]; print('ok')" .github/workflows/*.yml .github/dependabot.yml .github/ISSUE_TEMPLATE/*.yml`
Expected: `ok`. (PyYAML is available through Home Assistant's dependencies.)

- [ ] **Step 5: Test the release scripts locally**

Run the two `release.yml` shell snippets against the repo with `GITHUB_REF_NAME=v0.0.1`, and again with
`GITHUB_REF_NAME=v0.0.2`, in a temp dir copy (`cp CHANGELOG.md custom_components/nortec_go/manifest.json`
into matching paths under `/tmp/nortec-reltest`). Write the snippets to a script file with the Write tool (the
guard refuses heredocs).
Expected: `v0.0.1` passes both steps and `notes.md` contains "Initial project skeleton"; `v0.0.2` fails the
tag check. Also check an empty section (`## [0.0.1] - x` followed directly by another `## [`) fails the notes
step. Report the outputs.

- [ ] **Step 6: Commit**

```bash
git add .github
git commit -F <message file>   # "ci: add lint, tests, hassfest, hacs, gitleaks and release workflows" + trailer
```

---

### Task 6: Manual-testing setup

**Model:** sonnet · **Wave:** 2

**Files:**
- Create: `scripts/develop` (executable), `.devcontainer/devcontainer.json`

**Interfaces:**
- Consumes: `uv` environment from Task 1.

- [ ] **Step 1: Write `scripts/develop`**

```bash
#!/usr/bin/env bash
# Run Home Assistant locally with the nortec_go integration, for manual testing.
# config/ is gitignored and holds a real HA config: never commit it (CLAUDE.md, hard rule 4).
# On first start HA installs runtime packages for default_config into .venv; the next `uv sync` removes
# them again, so they are reinstalled after each sync. That is expected.
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p config/custom_components
if [ ! -f config/configuration.yaml ]; then
  printf 'default_config:\n' > config/configuration.yaml
fi
ln -sfn "$(pwd)/custom_components/nortec_go" config/custom_components/nortec_go

exec uv run hass -c config --debug
```

Run: `chmod +x scripts/develop`

- [ ] **Step 2: Syntax-check the script**

Run: `bash -n scripts/develop && echo ok`
Expected: `ok`. (Starting HA is controller step C6, not part of this task.)

**Controller step (C6), for reference; not run by the implementer.** Run it in the background (the Bash
tool's `run_in_background`), wait up to 3 minutes for `Home Assistant initialized`, then stop it:

```bash
scripts/develop > "$TMPDIR/develop.log" 2>&1 &
pid=$!
for i in $(seq 1 180); do grep -q "Home Assistant initialized" "$TMPDIR/develop.log" && break; sleep 1; done
kill "$pid"; wait "$pid" 2>/dev/null || true
grep -n "custom integration nortec_go" "$TMPDIR/develop.log"
grep -n "ERROR" "$TMPDIR/develop.log" | grep -i nortec_go || echo "no nortec_go errors"
```

Expected: the warning line is found, and "no nortec_go errors". The log stays local (it holds local data).

- [ ] **Step 3: Write `.devcontainer/devcontainer.json`**

Plain JSON, no comments:

```json
{
  "name": "HA-NortecGo (manual testing only; gates run on the host)",
  "image": "mcr.microsoft.com/devcontainers/python:3.14",
  "features": {
    "ghcr.io/va-h/devcontainers-features/uv:1": {}
  },
  "postCreateCommand": "uv sync",
  "forwardPorts": [8123],
  "customizations": {
    "vscode": {
      "extensions": ["charliermarsh.ruff", "ms-python.python"]
    }
  }
}
```

Check the image tag exists: `curl -s https://mcr.microsoft.com/v2/devcontainers/python/tags/list` must list
`3.14`. The Python in the image must satisfy `>=3.14.2`.

- [ ] **Step 4: Validate and commit**

Run: `python3 -m json.tool .devcontainer/devcontainer.json > /dev/null && echo ok`
Expected: `ok`.

```bash
git add scripts/develop .devcontainer/devcontainer.json
git commit -F <message file>   # "chore: add scripts/develop and optional devcontainer" + trailer
```

---

### Task 7: pre-commit hooks

**Model:** sonnet · **Wave:** 3
**Guarded files:** `.pre-commit-config.yaml`

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: Write `.pre-commit-config.yaml`**

```yaml
default_install_hook_types: [pre-commit, pre-push]
default_stages: [pre-commit]

repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: no-commit-to-branch
        args: [--branch, main]
      - id: check-yaml
      - id: check-json
      - id: check-toml
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: detect-private-key
      - id: check-added-large-files
        exclude: ^uv\.lock$
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.16.9
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1
    hooks:
      - id: gitleaks
  - repo: local
    hooks:
      - id: no-push-to-main
        name: refuse pushing to main (open a PR)
        entry: sh -c 'if [ "$PRE_COMMIT_REMOTE_BRANCH" = "refs/heads/main" ]; then echo "Pushing to main is not allowed - open a PR."; exit 1; fi'
        language: system
        stages: [pre-push]
        always_run: true
        pass_filenames: false
```

- [ ] **Step 2: Install and run on all files**

Run: `uv run pre-commit install && uv run pre-commit run --all-files`
Expected: all hooks pass. If `end-of-file-fixer`/`trailing-whitespace`/ruff changed files, review the change,
and include those files in this task's commit (they are fixes to earlier tasks' files; list them in the
report). A refusing hook (e.g. `gitleaks`, `detect-private-key`) → BLOCKED.

- [ ] **Step 3: Commit**

```bash
git add .pre-commit-config.yaml   # plus any files the hooks fixed, listed in the report
git commit -F <message file>   # "chore: add pre-commit hooks" + trailer
```

Expected: the commit runs the hooks and succeeds.

---

### Task 8: Adapt the `.claude/` setup

**Model:** sonnet · **Wave:** 4
**Guarded files:** `.claude/agents/implementer.md`, `.claude/agents/task-reviewer.md`,
`.claude/agents/full-reviewer.md`, `.claude/hooks/subagent_guard.py` (reason: docstring-only change, replacing
links into the private repo and the `captures/` known-limit line; no code change)

**Before dispatch (controller):** the guard refuses subagents any delete under `.claude/`, so the controller
deletes the skill itself in the main checkout and commits it (step C4a):
`git rm -r .claude/skills/document-endpoint` and a commit "chore: remove the document-endpoint skill (API docs
stay in NortecGo)" with the trailer.

**Files:**
- Modify: `.claude/agents/implementer.md`, `.claude/agents/task-reviewer.md`, `.claude/agents/full-reviewer.md`
- Modify: `.claude/hooks/subagent_guard.py` (docstring only)

- [ ] **Step 1: Adapt the agents (Edit tool only)**

Per spec §3.3:
- Every "pynortecgo repo" / "the pynortecgo repo (private source of a public PyPI package; …)" becomes "the
  HA-NortecGo repo (the public Home Assistant custom integration for Nortec Go, installed via HACS)".
- Gate commands become: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`,
  `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95` (full and
  task reviewers also list `uv sync --locked` and `uv run pre-commit run --all-files`).
- Remove `uv run python tools/check_api_md.py`, `uv build`, `docs/api.md`, `docs/api-standard.md`,
  "the published package", and the `document-endpoint` skill mention in `implementer.md`.
- "Never read `.env` or anything under `captures/`" → "Never read `.env`, or anything under `local/` or
  `config/`".
- `full-reviewer.md` *Branch* check: replace "anything private reaching `README.md` or the published package"
  with "anything private anywhere in this public repo (`CLAUDE.md` hard rule 3)", and add "`quality_scale.yaml`
  and `docs/user/nortec_go.md` match the change".

- [ ] **Step 2: Adapt the guard hook docstring (Edit tool only)**

In `.claude/hooks/subagent_guard.py`, change only the module docstring:
- Replace the `Design:` line's two links with:
  `Design: copied from the NortecGo repo; see docs/superpowers/specs/2026-09-26-ground-structure-design.md §3.3.`
- In the known-limits text, replace "and reads of ``captures/`` (the hard rule covers them)" with "and reads
  of ``local/`` and ``config/`` (hard rule 9 covers them)".

Verify the code is unchanged:
`git diff -U0 .claude/hooks/subagent_guard.py | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)'` shows only
docstring lines, and `python3 -c "import ast; ast.parse(open('.claude/hooks/subagent_guard.py').read())"`
succeeds.

- [ ] **Step 3: Check and commit**

Run: `grep -rnE 'pynortecgo repo|captures/|check_api_md|api-standard|document-endpoint|uv build' .claude`
Expected: no output.

```bash
git add .claude
git commit -F <message file>   # "chore: adapt Claude agents and guard docs to HA-NortecGo" + trailer
```

---

## Controller verification (C6)

After Task 8, in the main checkout on `chore/ground-structure`:
1. `uv sync --locked`, then the gate command, then `uv run pre-commit run --all-files`: all pass.
   `scripts/develop` check (Task 6, *Controller step*).
2. A throwaway commit on `main` is refused: `git switch main && git commit --allow-empty -m test` → refused by
   `no-commit-to-branch`; then `git switch chore/ground-structure`.
3. The private-data scans from spec §5 (files and commit messages).
4. CI: all five checks green on the PR (`gh pr checks`).
5. The branch-protection PUT (C5) and its read-back.
6. Update `CHANGELOG.md`'s `0.0.1` date to the day the PR is readied, if it differs (a commit on the branch).
