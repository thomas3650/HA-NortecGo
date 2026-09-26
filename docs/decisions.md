# Decisions

Lasting decisions, newest last. Each entry is short and links to the spec with the reasoning. Entries
aren't edited, except to set their status to `superseded by D<n>`. How to add one:
[`way-of-working.md`](way-of-working.md) §7.

### D1: Domain `nortec_go`
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** The integration's domain is `nortec_go`.
- **Why:** Core names two-word brands in snake_case; the domain can't change later.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions

### D2: HACS install, core-quality target, Silver first
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** The integration installs as a HACS custom repository, for the owner's own Home Assistant. It
  targets Home Assistant core quality, with Silver as the first tier.
- **Why:** HACS is the install route while the integration stays outside core; core quality keeps the door
  open to a future core submission.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions

### D3: Apache-2.0
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** The repo is licensed Apache-2.0.
- **Why:** The same license as Home Assistant core.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions

### D4: `uv` tooling; current stable HA only; optional devcontainer
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** The dev environment uses `uv`, ruff (core's rules), `mypy --strict`, pytest with
  `pytest-homeassistant-custom-component` and pre-commit. Only the current stable Home Assistant is
  supported; the Python version matches the pinned HA's `requires-python`. A devcontainer is optional, for
  manual testing only, and is never the gate environment.
- **Why:** Gates run on the host with `uv` so they are reproducible and don't depend on the devcontainer.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions, §2.1

### D5: Squash-only merges
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** PRs merge by squash only, with the PR title and body as the commit message, and head
  branches are deleted on merge.
- **Why:** Keeps `main`'s history one commit per change.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions

### D6: Five required checks
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** `lint`, `tests`, `hassfest`, `hacs` and `gitleaks` are required checks, with branches
  required to be up to date before merge.
- **Why:** Covers code quality, HA's own integration checks, HACS's publish checks and secret scanning
  before every merge.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions, §2.3

### D7: No dependency in the skeleton; `pynortecgo` pinned exactly once added
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** `manifest.json` has `"requirements": []` until the first feature adds `pynortecgo==X.Y.Z`,
  pinned exactly. The integration only ever uses `pynortecgo`'s public API.
- **Why:** The ground structure carries no feature yet; an exact pin keeps behaviour reproducible once the
  dependency lands.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions, §1.1

### D8: Way of working copied with a sync note; client change requests via `nortecgo-af` or `gh issue create`
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** `docs/way-of-working.md` is copied from `NortecGo` and adapted, with a sync note in both
  repos. Anything the client needs goes to `NortecGo` as a change request, sent to the `nortecgo-af` session
  or filed with `gh issue create -R thomas3650/nortecgo --label ha-integration`.
- **Why:** One process, kept in step across both repos; the client is never patched or vendored here.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions, §3.2

### D9: User docs in home-assistant.io format
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** `docs/user/nortec_go.md` follows home-assistant.io's integration docs template and section
  order, as plain GitHub Markdown. `README.md` stays short and links to it.
- **Why:** Keeps the user docs close to core's format, so a future core submission needs little rework.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions, §3.4

### D10: Manual releases
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** Releases are manual: a bump PR updates `manifest.json`'s version and moves the CHANGELOG
  section from *Unreleased*, then the owner pushes tag `vX.Y.Z`, and `release.yml` publishes the GitHub
  release.
- **Why:** No automatic version bumps; the owner controls when a release goes out.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions, §2.3

### D11: GitHub settings applied once with `gh`; issues limited to collaborators
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** Repo settings (branch protection, security features, the interaction limit) are applied once
  by the controller with `gh`, each step approved by the owner. Issues are enabled, limited to
  `collaborators_only` for six months, renewed as it expires.
- **Why:** A public repo with no maintainers yet needs its issue tracker fenced off from drive-by traffic
  while it's set up.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions, §4

### D12: Real data only in `local/`
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** Anything from a real Home Assistant instance (diagnostics downloads, logs, dumps) goes in
  `local/`, which is gitignored; the `.gitignore` patterns are a backstop, not the only guard.
- **Why:** Keeps account, charger and log data out of this public repo.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions, §1.3

### D13: No Claude memory; questions as plain text (inherited)
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** Claude's auto-memory is disabled for the project, and questions to the owner are plain
  terminal text, one at a time.
- **Why:** Project knowledge lives in the repo, where it's reviewed.
- **Source:** inherited from NortecGo D10

### D14: A neutral brand icon of our own
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** `custom_components/nortec_go/brand/` holds a neutral EV-charger icon of our own, with no
  Nortec or Monta marks. Home Assistant serves local brand images from 2026.3, and HACS accepts them.
- **Why:** No license to use Nortec's or Monta's marks; a local icon still satisfies HACS's brands check.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), Decisions, §1.1

### D15: `dependency-transparency` stays `todo` while `pynortecgo`'s source is private
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** The `dependency-transparency` quality-scale rule stays `todo`, tracked upstream, until
  `pynortecgo`'s source repo is public with tags and a public publishing pipeline.
- **Why:** The rule needs an open source repo for the dependency, which doesn't exist yet.
- **Source:** [ground-structure spec](superpowers/specs/2026-09-26-ground-structure-design.md), §1.1

### D16: PR lifecycle and delegated plan approval
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** A draft PR is opened once the spec and plan are both Ready, so the owner can review them
  there. Every approved task is committed and pushed. The PR is marked ready only when the owner's review is
  needed. The owner may delegate plan approval to the controller once `full-reviewer` rates the plan Ready,
  but the spec always needs the owner's approval.
- **Why:** The owner reviews in the PR, and doesn't need to approve a plan the reviewer has already passed.
- **Source:** this plan, Task 3, owner request on 2026-09-26
