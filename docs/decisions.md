# Decisions

Lasting decisions, newest last. Each entry is short and links to the spec with the reasoning. Entries
aren't edited, except to set their status to `superseded by D<n>`, or to name a part a later decision
superseded. How to add one:
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
- **Date:** 2026-09-26 · **Status:** superseded by D20
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
- **Date:** 2026-09-26 · **Status:** superseded by D40
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
- **Date:** 2026-09-26 · **Status:** active; the spec approval superseded by D35 for the PO flow
- **Decision:** A draft PR is opened once the spec and plan are both Ready, so the owner can review them
  there. Every approved task is committed and pushed. The PR is marked ready only when the owner's review is
  needed. The owner may delegate plan approval to the controller once `full-reviewer` rates the plan Ready,
  but the spec always needs the owner's approval.
- **Why:** The owner reviews in the PR, and doesn't need to approve a plan the reviewer has already passed.
- **Source:** [ground-structure plan](superpowers/plans/2026-09-26-ground-structure.md), Task 3, owner
  request on 2026-09-26

### D17: CodeQL default setup, advisory
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** Code scanning runs as CodeQL default setup (no workflow file) for Python and GitHub Actions,
  on PRs, pushes to `main` and weekly. It is not a required check on `main`; revisit once the config flow
  and auth code land.
- **Why:** Catches security problems in the integration and the workflows early, without a false positive
  blocking merges.
- **Source:** issue #5

### D18: Config entry holds tokens and device_id; charger ID is the unique ID
- **Date:** 2026-09-26 · **Status:** superseded by D21
- **Decision:** The config entry stores the email, the session tokens and the client's `device_id`, never the
  password. The account's charger ID is the entry's `unique_id`; it isn't stored in the entry data, since
  the client finds the charger itself. Pin bumps (D7) come as PRs, with a test keeping the manifest and dev
  pins equal.
- **Why:** Login is rate-limited and the password shouldn't sit in Home Assistant's storage; the charger ID
  stops the same charger being added twice and catches a changed account at setup.
- **Source:** [config-flow spec](superpowers/specs/2026-09-26-config-flow-design.md), Decisions

### D19: GitHub issues are the backlog
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** Anything found that won't be fixed in the current work becomes a GitHub issue, or is added
  to an existing one.
- **Why:** One place for everything still to do, instead of notes scattered over specs and PRs.
- **Source:** owner request on 2026-09-26; [config-flow spec](superpowers/specs/2026-09-26-config-flow-design.md), §7

### D20: Each repo owns its way of working
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** This repo's `docs/way-of-working.md` is its own, with no duty to keep it in step with
  `NortecGo`'s. A learning that clearly helps the other repo may be sent there as an issue. Anything the
  client needs still goes to `NortecGo` as a change request, sent to the `nortecgo-af` session or filed
  with `gh issue create -R thomas3650/nortecgo --label ha-integration`. Supersedes D8.
- **Why:** The repos do different jobs; a sync duty costs an issue for every process change, most of
  which don't apply to the other repo.
- **Source:** owner decision on 2026-09-26 (NortecGo#41 closed);
  [config-flow spec](superpowers/specs/2026-09-26-config-flow-design.md), §7

### D21: Setup reads the stored charger with `set_charger()`
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** As D18, except that setup no longer lets the client find the charger: it passes the
  entry's `unique_id` (the charger ID from the config flow) to `set_charger()`, and a charger the API no
  longer knows stops setup with `ChargerNotFoundError`. The config flow and reauth still find the charger by
  logging in. `pynortecgo` is pinned to 0.2.0.
- **Why:** Setup reads one known charger instead of discovering it on every start, so the manual
  charger-ID check is gone; 0.2.0 also turns a rejected token refresh into `AuthError`, which starts reauth.
- **Source:** issue #17; owner decision on 2026-09-26 to do it without a spec, as nothing is released yet

### D22: State-based polling, no polling settings
- **Date:** 2026-09-26 · **Status:** superseded by D27
- **Decision:** The charger and car are read every 60 min unplugged, 15 min connected and 5 min while a
  charge is under way; prices at setup and at 00:05, 05:05, 10:05, 15:05 and 20:05. There is no options flow
  and no refresh button; `homeassistant.update_entity` reads the charger and car now.
- **Why:** Reads match how fast things change (the car mostly stands unplugged), and Home Assistant doesn't
  allow integrations to offer polling settings.
- **Source:** [read-only entities spec](superpowers/specs/2026-09-26-read-only-entities-design.md), Decisions

### D23: Padded price lists, predictions kept, prices stored
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** EV Smart Charging's lists are padded to full days: 0 for a missing past slot, 10 for a
  missing current or future slot, and `[]` when no slot of tomorrow is known. Predicted prices are shown and
  replaced by later reads. Known slots are saved with Home Assistant's `Store`.
- **Why:** The API has no earlier hours of today and EV Smart Charging rejects a short day. Past prices never
  affect a plan, a high price keeps it away from unknown slots, and a forecast beats no prices.
- **Source:** [read-only entities spec](superpowers/specs/2026-09-26-read-only-entities-design.md), §3.3–3.4

### D24: Version labels on issues
- **Date:** 2026-09-26 · **Status:** superseded by D30
- **Decision:** Each issue gets one of `v1` (needed for version 1), `v2` (can wait for version 2) or
  `enhancement` (an improvement with no version decided). Chores may have none. When in doubt, ask the owner.
- **Why:** Not every issue is an enhancement; the labels show what v1 needs.
- **Source:** owner request on 2026-09-26

### D25: Light-weight changes before the first working release
- **Date:** 2026-09-26 · **Status:** active
- **Decision:** Until the first working release (the first version the owner has tested locally; the `v0.0.1`
  skeleton doesn't count), the owner may rule that a small, well-scoped behaviour change skips the spec, the
  plan and the `full-reviewer` review. It still has an issue, a short design in chat, TDD and the gates.
- **Why:** Nothing is released yet, so a behaviour change reaches no user, and the owner's local test before
  the release catches what a review would have.
- **Source:** owner rulings on 2026-09-26 (#17, and PR #21)

### D26: Start guard
- **Date:** 2026-09-26 · **Status:** active; the reads while a start is pending (last sentence) superseded by D29
- **Decision:** A start that may have left a card hold (a `ChargeStartError` with `hold_may_be_placed`, a
  cancelled start, or a start whose charge isn't seen within 10 minutes) blocks further starts until a read
  begun after the latest start attempt sees the cable unplugged, a charge open, or the charger going from
  `BUSY_NON_RELEASED` to `AVAILABLE`, or the owner confirms in the repair issue. A pending start ends without
  a block when a read sees a charge happened (open, or `BUSY_NON_RELEASED`) or the cable unplugged; reads
  begun before the latest start attempt change nothing. The block is stored, so reload and restart don't
  clear it. While a start is pending the charger is read every 5 minutes (extending D22).
- **Why:** EV Smart Charging repeats "on" up to 8 times an hour, and each start can place a new hold; a
  human looks before the next one.
- **Source:** [charge switch spec](superpowers/specs/2026-09-26-charge-switch-design.md), Decisions and §3

### D27: State-based polling and a Refresh button
- **Date:** 2026-09-27 · **Status:** active; the polling intervals superseded by D29
- **Decision:** D22's schedule stands: the charger and car are read every 60 / 15 / 5 min by the charger's
  state (5 min also while a start is pending, D26), and prices at setup and five fixed times; there are no
  polling settings. A *Refresh* button on the charger reads the charger, the car and the prices now.
- **Why:** The owner wants a one-press refresh in the UI; `homeassistant.update_entity` needs an automation
  and doesn't read prices.
- **Source:** issue #27; owner ruling on 2026-09-27 under D25 (no spec)

### D28: Smoke start before a PR is ready
- **Date:** 2026-09-27 · **Status:** active
- **Decision:** Before a PR is marked ready, `scripts/smoke` starts Home Assistant with the owner's dev
  config and fails unless the integration sets up with no errors from it. It only reads; it never starts or
  stops a charge.
- **Why:** The unit tests mock Home Assistant's startup; the owner wants proof that the integration really
  starts before reviewing a PR.
- **Source:** owner request on 2026-09-27

### D29: Pending stop and fast reads
- **Date:** 2026-09-27 · **Status:** active; the 30 s reads while the charger can't be read superseded by D31
- **Decision:** After a successful stop the switch shows off and *Charge status* *Stopping* until a read sees
  the charge no longer on, or for 2 minutes, and a start is refused meanwhile. The charger is read every
  30 s while *Charge status* is *starting* or *stopping*, 5 min while charging and 60 min otherwise
  (replacing D27's intervals and D26's last sentence), and right away after a start, a stop or Refresh; the
  car at most about every 5 minutes, and on every Refresh.
- **Why:** The charger reports the old state for about 25 s after a stop, so the switch flipped back on and
  a stop was pressed twice; 30 s reads were observed without a rate limit.
- **Source:** [pending stop and fast reads spec](superpowers/specs/2026-09-27-pending-stop-fast-reads-design.md), Decisions and §2–3

### D30: Urgency labels v1 to v3, with type labels on top
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** Each issue gets one urgency label: `v1` (needed for version 1), `v2` (can wait for version 2)
  or `v3` (nice to have, after version 2); chores may have none. `bug`, `enhancement` and `documentation`
  are type labels added on top, and `enhancement` no longer means "no version decided". `active` marks an
  issue whose work has started and not stopped.
- **Why:** The owner wants every issue ranked by urgency, bugs marked as such (replacing D24), and to see
  what is being worked on; GitHub has no filterable in-progress state without a Projects board.
- **Source:** owner rulings on 2026-09-28 (#46)

### D31: The start and stop deadlines hold without reads
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** The 10-minute pending start (D26) and the 2-minute pending stop (D29) end by timers that
  fire whether or not the charger is read; a read ends them early only on evidence. The charger's own
  starting or stopping state gives 30 s reads only while the last good read is under 2 minutes old
  (5 min after that), and a failed read works the interval out again.
- **Why:** Checked only on successful reads, they lasted a whole outage, with reads every 30 s, and never
  ended with polling disabled; D29's "no cap" on the charger's own states assumed working reads.
- **Source:** [outage deadlines and start needs spec](superpowers/specs/2026-09-28-outage-deadlines-start-needs-design.md), §2–3

### D32: The Charge switch is always added
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** The *Charge* switch is added whatever cars the account has. A start without exactly one car
  and one saved card is refused with the reason, before any card hold.
- **Why:** The saved card can't be checked beforehand, so hiding the switch for the car alone would only
  half solve it, and the refusal explains itself.
- **Source:** [outage deadlines and start needs spec](superpowers/specs/2026-09-28-outage-deadlines-start-needs-design.md), Decisions

### D33: Docs tasks run on Opus
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** Every docs task (a plan task whose output is docs) is tagged `Model: opus`.
- **Why:** Docs written so far were often not precise enough; the owner expects Opus to write more precise
  docs.
- **Source:** owner ruling on 2026-09-28 (PR for #34, #35)

### D34: The total price, in the forecast's currency
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** The price sensor and EV Smart Charging's lists use the total price per kWh incl. VAT
  (spot, fees and grid tariff); the unit is the forecast's currency per kWh, falling back to Home
  Assistant's currency.
- **Why:** The total is what the owner pays, and the hourly grid tariff changes which slots are cheapest;
  the forecast knows its own currency, so the unit is right without a Home Assistant setting (#20).
- **Source:** [pynortecgo 0.5.0 spec](superpowers/specs/2026-09-28-pynortecgo-0.5.0-design.md), Decisions

### D35: The PO flow
- **Date:** 2026-09-28 · **Status:** active; the owner merges superseded by D45
- **Decision:** Besides the direct flow (way-of-working §1), the owner can start a PO session that runs up
  to 2 team leads (each with up to 3 workers). In that flow the PO answers brainstorm questions and approves
  specs and plans in the owner's place, escalating below 90% certainty and always for a fixed list; the owner
  still merges.
- **Why:** Several issues move forward in parallel while the owner only answers escalations and merges.
- **Source:** [spec comment on #50](https://github.com/thomas3650/HA-NortecGo/issues/50#issuecomment-5877369877), §§2–8

### D36: One OK per charge
- **Date:** 2026-09-29 · **Status:** active
- **Decision:** For hard rule 2, one explicit OK from the owner covers one charge, its start and its stop; a
  new charge, or a new try after a refused start, needs a new OK. A turn-on expected to be refused counts as
  a start.
- **Why:** The owner's ruling, so that what one OK covers is clear in manual testing.
- **Source:** [manual testing spec](superpowers/specs/2026-09-29-manual-testing-design.md), §2.1 and
  §3.4; the owner's ruling on PR #57

### D37: One retry for a failed price read
- **Date:** 2026-09-29 · **Status:** active
- **Decision:** A failed setup or scheduled price read, except on an `AuthError`, is read once more after
  15 minutes (or a longer `retry_after`), unless the next scheduled read comes first; a failed retry or
  *Refresh* gets none. A run of failed price reads logs one warning and one recovery line.
- **Why:** A failed 15:05 read left EV Smart Charging on the forecast until 20:05; one retry per read keeps
  the rate-limited API's load at most doubled.
- **Source:** [price read retry spec](superpowers/specs/2026-09-29-price-read-retry-design.md), Decisions and §3

### D38: Diagnostics redact only the sign-in secrets
- **Date:** 2026-09-29 · **Status:** active
- **Decision:** Diagnostics and logs redact only the email, the password, the access and refresh tokens and
  the client's device ID, with `async_redact_data` over the whole diagnostics output; the charger's and car's
  IDs and names and the entry's title and unique ID stay. A test pins the `pynortecgo` model fields the
  output dumps, so a client bump that adds a field fails the tests until someone decides whether it is a
  secret.
- **Why:** The owner's ruling (issue #11): the IDs and names help match a download to an issue and to the
  devices, and aren't secrets. `asdict` shows every field, and Dependabot bumps the client; a new secret key
  in `entry.data` under another name still needs adding to the list by hand.
- **Source:** [diagnostics spec](superpowers/specs/2026-09-29-diagnostics-design.md), §3, §4 and §6

### D39: A merged bump PR is the release
- **Date:** 2026-09-29 · **Status:** active; the bump PR and the fallbacks superseded by D40
- **Decision:** When CI passes on `main` for a commit that raises the version and adds its changelog
  section, `auto-release.yml` tags that commit and publishes the release through `release.yml`. A dispatch
  of `auto-release.yml` is the fallback, also for a bump merged before it; tagging by hand is the last one.
- **Why:** The bump PR already holds everything a release needs; the owner still decides when a release goes
  out by merging it.
- **Source:** [auto-release spec](superpowers/specs/2026-09-29-auto-release-design.md), Decisions and §2

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

### D41: pre-commit runs ruff from `uv.lock`
- **Date:** 2026-09-30 · **Status:** active
- **Decision:** pre-commit runs ruff as local hooks through `uv run ruff`, so it uses the version in `uv.lock`,
  as CI does. Dependabot's `pre-commit` ecosystem bumps the remaining remote hooks (`pre-commit-hooks`,
  `gitleaks`) monthly.
- **Why:** a separately pinned `ruff-pre-commit` drifts from `uv.lock` after a Dependabot `uv` bump, so a
  commit that passes the hook can fail CI's `ruff format --check`. Letting Dependabot bump both would still
  bring them in separate PRs.
- **Source:** [tooling hygiene spec](superpowers/specs/2026-09-30-tooling-hygiene-design.md), Decisions

### D42: Charge costs are the client's exact values
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** *Cost this charge* shows the open charge's cost as `pynortecgo` reports it, with no state
  class; *Last charge cost* shows the last completed charge's billed total as `total`, with `last_reset` at
  the charge's completion time. No cost is computed from energy and price, and the unit is the charger's
  currency, then D34's order.
- **Why:** The owner chose exact values over estimates (#75). A per-charge value without `last_reset` gives a
  wrong statistics sum, and the live value ends below the bill, so only the billed totals are summed.
- **Source:** [session cost spec](superpowers/specs/2026-10-01-session-cost-design.md), Decisions and §3

### D43: A Refresh press raises when its read fails
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** A press on *Refresh* raises a translated error when its charger read or its price read
  fails. The price read always runs, and the charger's error is the one raised when both fail.
- **Why:** a silent press during an outage lets the owner think the data is fresh, and the quality scale's
  `action-exceptions` rule asks actions to raise when they fail.
- **Source:** [refresh feedback spec](superpowers/specs/2026-10-01-refresh-feedback-design.md), Decisions

### D44: The car device is decided at setup
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** Car entities are added and removed only at setup (first setup, a reload, a restart), never
  while running; a failed car read at setup retries setup rather than guessing. While running, a "no car"
  answer makes the car entities unavailable and raises a repair issue whose fix reloads the entry, and a
  different car updates the same device.
- **Why:** The owner wants no entities to appear or disappear at random times, and a guessed car left
  no-car accounts with a dead device (#41).
- **Source:** [car device lifecycle spec](superpowers/specs/2026-10-01-car-device-lifecycle-design.md),
  Decisions; owner answer on issue #42

### D45: The PO merges ready PRs
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** In the PO flow the PO squash-merges a PR it has made ready, releasing PRs included, once
  the required checks are green on the head it checked, and then checks `main` and the release. PRs that
  touch charge start or stop, auth, tokens or reauth, a hard rule, `.claude/`, `.pre-commit-config.yaml` or
  `.github/workflows/` stay the owner's to merge, and nobody else merges.
- **Why:** The owner's ruling (#84): a finished PR shouldn't wait for the owner to press merge, while the
  changes that can cost money, lock the account or weaken the process keep the owner's eye.
- **Source:** [PO merge spec](superpowers/specs/2026-10-01-po-merge-design.md), Decisions

### D46: The shape of the diagnostics download isn't user-visible
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** A change that only moves, renames, adds or removes keys in the diagnostics download isn't a
  user-visible change, as long as what the user docs say the file keeps and leaves out stays true: it needs
  no changelog entry and doesn't make a PR releasing. D38 still decides what the download may show.
- **Why:** The owner's ruling (#81): the download is a support file, the user docs don't name its keys, and
  nothing is meant to be built on them. Without the rule, every client release that changes a model would
  force a release of the integration.
- **Source:** [pynortecgo 0.8.0 spec](superpowers/specs/2026-10-01-pynortecgo-0.8.0-design.md), Decisions
  and §4

### D47: Total energy is summed in the integration
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** *Total energy* is summed by the integration from the per-charge energy `pynortecgo`
  reports, in a stored ledger that starts at 0: each completed charge once, by its charge ID, at its final
  energy, and the open charge at its live reading. It is `total_increasing` and never goes down: a charge
  whose final record never arrives, or is lower, keeps its highest live reading.
- **Why:** The client can't expose a lifetime meter (the owner, #75), and *Energy this charge* restarts
  with every charge, so the Energy dashboard can miss charges. This replaces the owner's earlier answer on
  #75 to wait for the client.
- **Source:** [total energy spec](superpowers/specs/2026-10-01-total-energy-design.md), Decisions and §2

### D49: The PO flow's sessions are told apart by their directory
- **Date:** 2026-10-02 · **Status:** active
- **Decision:** The session names stay `po`, `team-lead` and `tl-<topic>`, and a session belongs to this
  repo when its `cwd` is in the main checkout or one of its worktrees (`scripts/sessions.py` decides it).
  The start scripts count only this repo's sessions, a team lead sends to `po` only when exactly one
  running session has that name and it is this repo's, and the PO runs that check in every round of its
  loop and sends `hello` again once it passes.
- **Why:** The names are not unique on the machine (#53). Filtering by directory changes no name, so
  running sessions keep working; a repo prefix needs a transition and is the next step if two projects
  ever run a PO flow at once.
- **Source:** [session names spec](superpowers/specs/2026-10-02-session-names-design.md), Decisions
