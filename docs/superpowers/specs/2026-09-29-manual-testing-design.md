# Manual test guide and debug logging — design

Date: 2026-09-29 · Branch: `docs/manual-testing` · Issues: #10, #38

## Goal

- **What:**
  - #10: a guide, `docs/manual-testing.md`, for testing the integration by hand against the owner's real
    account: how to run it, where real-instance data lives, what to watch out for, what an agent may and
    may not do, and a short checklist per feature.
  - #38: a *Debug logging* part in the user docs' *Troubleshooting*, with what to leave out of a public
    issue; the manifest's `loggers`; a line in the bug template; `docs-troubleshooting` done.
- **Why:** live testing is repeatable, never leaks data into this public repo, and never starts or stops a
  charge by accident (#10). A user who hits a problem can collect debug logs and report it without sharing
  secrets (#38).
- **Not in this work:** diagnostics (#11; `diagnostics` is `todo` in `quality_scale.yaml`, so no doc
  describes a download that doesn't exist yet). #38's "point to diagnostics once #11 lands" moves to #11's
  scope (the PO adds it there), since this PR closes #38. No change to the integration's Python code or
  `scripts/`; the only test change is one manifest assertion (§4.2). Automated tests stay TDD with
  `pynortecgo` mocked, inside each feature.
- **Done when:** the files in §1 are changed as described; every link resolves; every entity, state and
  section name matches the code and the user docs; the gates pass; the branch review is Ready.

## Decisions

Answered by the PO in the brainstorm (2026-09-29), unless marked otherwise.

| Topic | Decision |
|---|---|
| Process | Full §1 path; #10 and #38 in one spec, one plan and one PR (`Closes #10`, `Closes #38`), the owner's request via the PO |
| Audience of the guide | The owner, and agents doing the PO's visual check (`way-of-working.md` §8 step 3) |
| Expected behaviour | Each checklist item says what to check and links to the section of `docs/user/nortec_go.md` that describes it. The guide restates no values, units, sequences or timings, so it stays right when a feature changes (for example the price sensor after #51). States are named only as preconditions, spelled as in `strings.json` |
| Owner-only steps | Marked in the guide (§2.5) |
| What agents may do in the UI | Navigate and read, and operate no control (§2.5). *Controller*, from the review: the narrowest reading of §8 step 3 |
| EV Smart Charging | *Owner, 2026-09-29 (via the PO):* it isn't set up or tested in `config/`; the owner tests it in production, outside this guide (§3.3). Setting it up in `config/`, or an automation there that drives *Charge*, is owner only and counts under hard rule 2. If one is ever set up there, the owner's earlier ruling stands: its smart-charging switch stays off unless the owner gives an explicit OK for that session (and is turned off again at the session's end), and any automation that turns *Charge* on or off counts as a start or stop. The charger-control question is moot |
| Reauth | *Owner, 2026-09-29 (via the PO):* not tested manually, no second account; one line says the automated tests cover it. Normal testing reuses the stored session |
| Public results | Results posted on issues or PRs follow `way-of-working.md` §8 *Public text*; the guide links to it |
| §8 pointer | One line in §8 step 3 points to the guide for what to look at; the guide points back to §8 for the check's rules. §1 step 10 is unchanged |
| Manifest `loggers` | `"loggers": ["pynortecgo"]`, so the integration page's debug logging covers the client too; the standard HA way, not a new decision |
| What the logs hold, in the docs | No tokens or passwords; still check before posting; remove the email, the charger's and car's names and anything identifying; paste only the lines around the problem. The docs quote no log lines and name no endpoints |
| Changelog | One line under *Unreleased* for the debug logging (§4.2); the guide itself isn't user-visible |

Facts used, public-safe:

- A turn-on of *Charge* that passes the integration's own checks (no pending start or stop, no open
  charge, no start block, a known charger state; `charge_control.py`, `async_start`) calls `pynortecgo`'s
  `start_charge()`. The refusals for no cable, a charger not released, or no car or card come back from that
  call. So a turn-on expected to be refused can still be a real start request.
- Deleting the entry removes the stored start guard and the start-block repair
  (`__init__.py`, `async_remove_entry`), and adding it again costs a sign-in.
- The config flow and the reauth form each sign in on every submit (`config_flow.py`): the config flow
  before it checks *already configured*, the reauth form before it checks for another charger
  (*wrong account*). The reauth form asks only for the password and uses the stored email.
- Restarting or reloading the entry reuses the stored session; it needs no new sign-in.
- `scripts/develop` runs `hass -c config --debug`; F5 in VS Code runs `python -m homeassistant -c config
  --debug` (`.vscode/launch.json`). `--debug` turns on asyncio debug mode, not debug logging
  (`docs/ha-notes.md`, *Tooling*). HA's log goes to `config/`. `scripts/smoke` writes its log to
  `local/smoke.log` and prints only the integration's error lines. It refuses to start while an HA runs on
  `config/` on the host (`(homeassistant|hass) -c config`); an HA in the devcontainer on the same `config/`
  is invisible to that check.
- `config/` is shared by every branch checked out in the main checkout; a store written by a newer branch
  can break an older one (`way-of-working.md` §8, *From branch ready to PR ready*, step 2).
- `.gitignore` ignores `config/`, `local/`, logs, `home-assistant_v2.db*`, `.storage/` and diagnostics
  downloads.
- Home Assistant 2026.9.3 (installed source, `components/logger/helpers.py` and `loader.py`): debug logging
  turned on from an integration's page covers the integration's package logger and the manifest's
  `loggers` list. The manifest has no `loggers` today, so `pynortecgo` isn't covered.
- `pynortecgo`'s log lines, 0.2.0 (installed) and 0.5.0 (the PyPI wheel, #51's target): no tokens,
  passwords, email or IDs. They name the request method and endpoint template, HTTP statuses, error class
  names, an unknown state value from the API, and (0.5.0) grid tariff estimates with their hour and
  values. The integration's own log lines hold the same client error messages and no credentials (hard
  rule 5). Home Assistant's own lines can show the entry's title (the charger's name) and entity names.

## 1. Files

| File | Change | Task |
|---|---|---|
| `docs/manual-testing.md` | New: the guide (§2, §3) | 1 |
| `docs/README.md` | One row in the documentation map, after `ha-notes.md` | 1 |
| `docs/way-of-working.md` | One line in §8 step 3 pointing to the guide | 1 |
| `tests/test_manifest.py` | One test for `loggers` (§4.2) | 2 |
| `docs/user/nortec_go.md` | *Debug logging* and *Reporting a problem* under *Troubleshooting* (§4.1) | 2 |
| `custom_components/nortec_go/manifest.json` | `"loggers": ["pynortecgo"]` (§4.2) | 2 |
| `.github/ISSUE_TEMPLATE/bug.yml` | The logs field asks for debug logs (§4.3) | 2 |
| `custom_components/nortec_go/quality_scale.yaml` | `docs-troubleshooting: done` (§4.4) | 2 |
| `CHANGELOG.md` | One line under *Unreleased* (§4.2) | 2 |

The two tasks touch disjoint files. Task 1 links to the user docs' *Debug logging* section by the name
§4.1 fixes (a docs task starting ahead of its input, `way-of-working.md` §1 *Parallel waves*).

## 2. The guide: before testing

Sections, short, in this order.

### 2.1 Purpose and rules

One paragraph: manual testing is against the owner's real account and charger. The rules that apply are
linked, not restated: CLAUDE.md hard rules 2 (start and stop), 3 and 4 (nothing private, nothing from a
real instance committed), 5 (logs and diagnostics), 6 (no retried start; reauth instead of login) and 9
(subagents). Stated in the guide itself, since it is the point of #10: **turning *Charge* on or off, by
hand, from EV Smart Charging or from an automation, is a real start or stop and needs the owner's explicit
OK first, each time**, including a turn-on expected to be refused.

### 2.2 Running Home Assistant

- `scripts/develop`, or F5 in VS Code (which runs `scripts/develop --setup-only` first); HA listens on
  `http://localhost:8123`. The commands themselves are in CLAUDE.md *Commands*, not repeated.
- Stopping it: Ctrl+C in a terminal, VS Code's stop button for F5, `pkill -f "hass -c config"` for a
  background `scripts/develop` (as `ha-notes.md` says).
- One HA on `config/` at a time, the devcontainer included; stop it before `scripts/smoke`. The
  devcontainer is for manual testing only.

### 2.3 Where real-instance data lives

- `config/`: the HA config, the stored session, HA's database and log. Gitignored, never committed (hard
  rule 4), never read by agents (hard rule 9).
- `local/`: everything taken from a real instance and kept: logs copied out, anything downloaded from HA,
  a debug-log download (it lands in the browser's downloads folder first; move it), screenshots
  (`local/screenshots/<topic>/`, §8 step 3), notes with real values. Gitignored, never
  committed, never read by agents.
- Nothing from either goes into a commit, an issue, a PR or a review comment; posted results follow §8
  *Public text* (linked).

### 2.4 Pitfalls

- Sign-ins are rate-limited. A restart or reload reuses the stored session and needs none. Don't remove and
  re-add the entry to "try again": it costs a sign-in, and deleting the entry also drops the stored start
  guard and any start-block repair, which exist to prevent a second card hold.
- `config/` is shared across branches: a store written by a newer branch can break an older one. If a
  branch fails to load after a switch, suspect this first and tell the owner (fixing it means touching
  `config/`).
- After each `uv sync`, HA reinstalls its runtime packages on the first start (`scripts/develop`'s note),
  so that start is slower.
- `--debug` is asyncio debug mode, not debug logging; debug logging is in the user docs' *Debug logging*
  (§4.1).
- `config/` has no EV Smart Charging and no automation on *Charge*, and must stay that way unless the
  owner sets one up (§3.3): anything there runs on every start of HA, `scripts/smoke` and the PO's visual
  check included.

### 2.5 Who does what

- **Owner only:**
  - the config flow and anything with credentials;
  - setting up EV Smart Charging, and creating or turning on an automation that drives *Charge*;
  - acting on any repair (the start-block repair and any other);
  - the entry's ⋮ menu (reload, delete, disable);
  - anything that calls an action on the charger, and every item in §3.4.
- **Agents** (the PO's visual check) look only: they navigate and read, and operate no control. Not the *Charge*
  row or toggle anywhere (its state is read without opening it), not *Refresh*, not **Submit** in a repair, not the entry's ⋮ menu. The rules of the check itself are in
  `way-of-working.md` §8 step 3 (linked).
- Checking for errors: agents use `scripts/smoke`'s output or HA's logs page in the UI (**Settings** >
  **System** > **Logs**), never `config/`'s log file.

## 3. The guide: checklists

Each item is one line, a checkbox, naming what to look at and linking to the user-doc section that says
what is right. Items marked **owner** are done only by the owner; agents skip them. Grouped by feature,
with the issue that built it.

### 3.1 Setup and restart (#7)

- **owner** Add the integration with the config flow (user docs *Configuration*), only when `config/` has
  no Nortec Go entry yet: the entry's name, the devices (*Supported functionality*).
- The config flow's errors aren't tried live: every submit signs in, and the mocked tests cover them.
- Restart HA: the entry loads without a new sign-in, the entities come back, and no errors from the
  integration (§2.5 *Checking for errors*).
- **owner** Reload the entry: the same.
- Reauth isn't tested manually; the automated tests cover it.

### 3.2 Entities (#8, and the later sensors)

For every entity in the user docs' *Supported functionality* tables: it exists, its name and type match the
table, and its value or state is plausible for what the charger, car and app show. The checklist lists the
entities by name (from `strings.json`), each against its table row:

- Charger: *Current price* (value, unit and the price-list attributes as the user docs' row and *Use cases*
  describe them; no restated unit or price kind), *Cable connected*, *Charging*, *Charge* (its state only),
  *Charge status*, *Refresh* (present), *Last read*.
- Car: *Battery*, *Charge limit*, *Last seen*, *Plugged in*, *Connected to charger*; the car device's name
  (the placeholder rule in the user docs).
- **owner** Reads: pressing *Refresh* moves *Last read* (user docs *Data updates*). *Refresh* only reads.
- The device page: both devices, their entities, the diagnostic entities in the diagnostic group.

### 3.3 EV Smart Charging (#8)

- EV Smart Charging isn't set up in `config/`, and it isn't tested there: the owner tests it in the owner's
  own production Home Assistant, outside this guide. No checklist.
- Setting it up in `config/`, or creating or turning on an automation there that turns *Charge* on or off,
  is **owner** only (§2.5) and counts under hard rule 2 (§2.1), so nobody adds one to the dev config by
  accident. If one is ever set up there, the owner's earlier rule applies: its smart-charging switch (and
  any such automation) stays off unless the owner has given an explicit OK for that session, and the owner
  turns it off again at the end of the session, since `config/` keeps it for every later start of HA.
- The *Current price* attributes that EV Smart Charging reads are checked in §3.2, without EV Smart
  Charging.

### 3.4 Start and stop (#9, and the later start and stop deadlines)

Every item is **owner, with explicit OK for that session**. Agents never do them, and the guide never tells
an agent to.

- Before: the cable is connected; *Charge status* is not *Waiting for replug* or *Start blocked*.
- Start: turn *Charge* on; the switch and *Charge status* follow the user docs' *Starting a charge*.
- Stop: turn *Charge* off; the same section's description of a stop.
- The replug rule after a stop (the same section).
- A start refused by design (for example with the cable unplugged) may still be a start request (§2.1), so
  it needs the same OK.
- The start block and its repair are checked only if one happens; the guide gives no way to cause a failed
  start.

## 4. Debug logging (#38)

### 4.1 User docs

Under *Troubleshooting* in `docs/user/nortec_go.md`, two new parts, after the existing ones:

- **`### Debug logging`:**
  - From the integration's page: the steps are Home Assistant's, linked, not restated
    (https://www.home-assistant.io/docs/configuration/troubleshooting/#enabling-debug-logging). What this
    integration adds: it covers the integration and the `pynortecgo` client (§4.2).
  - Or in `configuration.yaml`, a `logger:` block with `default: warning` and `debug` for
    `custom_components.nortec_go` and `pynortecgo`; restart.
  - The logs hold no tokens or passwords, but check them before posting (§ *Reporting a problem*).
- **`### Reporting a problem`:** open an issue with the bug template; include the Home Assistant and
  integration versions and the lines of the debug log around the problem, not the whole log. Before
  posting, remove the email, the charger's and car's names and anything else that identifies you or your
  location. No log lines are quoted and no endpoints named.

No pointer to diagnostics here; it is #11's (Goal).

### 4.2 Manifest and changelog

- TDD: first `tests/test_manifest.py` gains a test that the manifest's `loggers` is `["pynortecgo"]` (red),
  then `manifest.json` gains `"loggers": ["pynortecgo"]` between `issue_tracker` and `requirements` (hassfest's
  order: `domain`, `name`, then alphabetical).
- `CHANGELOG.md`, *Unreleased*: debug logging from the integration's page now includes the `pynortecgo`
  client, and the docs describe debug logging and bug reports.
- If #51 merges first, its `requirements` change sits next to this line: the branch merges `origin/main` in,
  never a force-push.

### 4.3 Bug template

The *Diagnostics / logs* field's description gains one sentence: turn on debug logging as in the docs'
*Debug logging*, reproduce, and paste the lines around the problem. The existing redaction sentence is
replaced by a pointer to the docs' *Reporting a problem*, so the list of what to remove lives in one place.
The field stays optional.

### 4.4 Quality scale

`docs-troubleshooting: done`: the rule asks for a symptom and a fix for common issues, which the existing
entries under *Troubleshooting* already give (sign-in, the charger, the rate limit, blocked starts).

## 5. The pointer in `way-of-working.md`

§8 *From branch ready to PR ready*, step 3, gains one sentence: what to look at, and what an agent may
press, is in [`manual-testing.md`](manual-testing.md). Nothing else in `way-of-working.md` changes.

## 6. Checks

The docs have no tests; `manifest.json` has its one test (§4.2) and is also checked by hassfest in CI. Each task checks,
and the branch review re-checks:

- Every relative link and anchor resolves (from `docs/`: the section names in `docs/user/nortec_go.md`,
  `CLAUDE.md`, `ha-notes.md` and `way-of-working.md`).
- Every entity, state and error name matches `strings.json`.
- A leak grep finds no email address, IDs, tokens or API URLs in what the task adds. With
  `PAT='[[:alnum:]._%+-]+@[[:alnum:].-]+\.[a-z]{2,}|https?://[^ )]*api'`, the task runs
  `grep -nE "$PAT" docs/manual-testing.md` (task 1 only) and
  `git diff <task base> -- <the task's other §1 files, by name> | grep '^+' | grep -nE "$PAT"`; a pass is
  no output from either (whole files would fail on an existing, allowed link in `docs/README.md`).
- No statement contradicts `scripts/develop`, `scripts/smoke`, `.vscode/`, `.gitignore` or the user docs;
  no link to D34 or to anything only on #51's branch.
- The gates (CLAUDE.md *Commands*) and `uv run pre-commit run --all-files` pass.

## 7. Decision log

None: the guide applies existing rules, and the manifest's `loggers` is the standard HA way.
