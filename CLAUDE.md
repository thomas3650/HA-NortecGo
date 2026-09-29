# CLAUDE.md

## What this repo is

The **public** HACS custom integration for a **Nortec Go** EV charger (a white-label Monta app), for Home
Assistant. It talks only to the public API of `pynortecgo`, an async client that lives in the separate,
**private** `NortecGo` repo. The integration is unofficial and not affiliated with Nortec or Monta.

## Layout

- `custom_components/nortec_go/` — the integration
- `tests/` — tests against the integration, with `pynortecgo` mocked
- `docs/` — the docs; the map is `docs/README.md`
- `scripts/` — dev scripts, including `scripts/develop` and `scripts/smoke`
- `.devcontainer/` — optional, for manual testing only; never the gate environment
- `.claude/` — project settings, the subagent guard hook, agents (`implementer`, `task-reviewer`,
  `full-reviewer`, and the session agents `po` and `team-lead`)
- `.github/` — CI, release workflow, Dependabot, issue and PR templates

## Commands

```bash
uv sync                          # set up / update the dev environment
uv run pytest -q                 # tests, fast, no coverage
uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95   # coverage gate
uv run ruff check && uv run ruff format --check && uv run mypy
uv run pre-commit install        # once per clone: local hooks incl. no-commit and no-push to main
scripts/develop                  # run Home Assistant locally with the integration (config/ is gitignored); or F5 in VS Code
scripts/smoke                    # start HA with the dev config and fail on integration errors; before a PR is ready
scripts/po                       # PO mode: the PO runs the backlog through team leads (docs/way-of-working.md §8)
scripts/team-lead                # team lead mode, for hard problems; never while a PO runs
```

## Way of working

The process (flow, agents, model policy, conventions, doc principles) lives in `docs/way-of-working.md`,
imported below. Lasting decisions are in `docs/decisions.md`.

@docs/way-of-working.md

## Code and docs rules

- TDD, and the gates (Commands above, including the coverage gate) pass before committing.
- Add a `CHANGELOG.md` entry under *Unreleased* for user-visible changes.
- `quality_scale.yaml` and `docs/user/nortec_go.md` are updated in the same PR as the code they describe.

## Hard rules

1. Every change reaches `main` only through a merged PR. Never commit on or push to `main`.
2. Never start or stop a real charge without the owner's explicit OK, in dev or manual testing. Tests always
   mock `pynortecgo`.
3. Nothing private in this public repo: no account, charger or user IDs, tokens, emails, captures, APK
   references, links into the private `NortecGo` repo's docs, or raw API endpoints, headers and response
   shapes. The integration uses only `pynortecgo`'s public API.
4. Never commit `.env`, `config/`, or anything taken from a real instance.
5. Diagnostics and logs redact the email, the password, the access and refresh tokens and the client's
   device ID (`async_redact_data`; D38), and credentials and usernames are never logged, even wrong ones.
   Anything taken from a real instance (diagnostics downloads, logs, dumps) goes in `local/` and is never
   committed.
6. Never auto-retry `start_charge`. On `AuthError`, start reauth instead of retrying login (login is
   rate-limited; a start places a card hold).
7. Test fixtures are built from `pynortecgo` model objects, never from raw API JSON.
8. What the client needs goes to `NortecGo` as a change request (`docs/way-of-working.md`), never patched or
   vendored here.
9. Subagents never read `.env` directly, and never read anything under `local/` or `config/`.

## Context

This is authorised work on the owner's own charger and account.

## Documentation map

@docs/README.md
