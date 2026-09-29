# Manual test guide for live testing — design

Date: 2026-09-29 · Branch: `docs/manual-testing` · Issue: #10

## Goal

- **What:** a guide, `docs/manual-testing.md`, for testing the integration by hand against the owner's real
  account: how to run it, where real-instance data lives, what to watch out for, and a short checklist per
  feature.
- **Why:** live testing is repeatable, never leaks data into this public repo, and never starts or stops a
  charge by accident (#10).
- **Not in this work:** diagnostics (#11; `diagnostics` is `todo` in `quality_scale.yaml`, so the guide
  doesn't describe a download that doesn't exist yet), debug logging and bug reports (#38), and any change
  to the code, `scripts/` or the automated tests. Automated tests stay TDD with `pynortecgo` mocked, inside
  each feature.
- **Done when:** the guide and its documentation-map row are on the branch; the §8 pointer is in
  `way-of-working.md`; every link resolves and every entity, state and section name matches the code and
  the user docs; the branch review is Ready.

## Decisions

Answered by the PO in the brainstorm (2026-09-29), unless marked otherwise.

| Topic | Decision |
|---|---|
| Process | Full §1 path (spec, plan, `full-reviewer`) |
| Audience | The owner, and agents doing the PO's visual check (`way-of-working.md` §8 step 3) |
| Expected behaviour | Each checklist item says what to check and links to the section of `docs/user/nortec_go.md` that describes it. The guide restates no values, units, states or timings, so it stays right when a feature changes (for example the price sensor after #51, D34) |
| Owner-only steps | Marked in the guide: the config flow, credentials, reauth, confirming the repair issue, and anything that calls an action on the charger |
| Public results | Results posted on issues or PRs follow `way-of-working.md` §8 *Public text*; the guide links to it |
| §8 pointer | One line in §8 step 3 points to the guide for what to look at; the guide points back to §8 for the check's rules. §1 step 10 is unchanged |
| Changelog | None: nothing user-visible changes |
| EV Smart Charging and automations | *Proposal, with the owner (PO question on #10).* See §3.3 |
| Reauth | *Proposal, with the owner (PO question on #10).* See §3.1 |

Facts used, public-safe:

- Every turn-on of *Charge* calls `pynortecgo`'s `start_charge()`, and the refusals (no cable, the charger
  not released, no car or card) come back from that call (`charge_control.py`). A turn-on expected to be
  refused is still a real start request, and may place a card hold if it isn't refused.
- `scripts/develop` runs `hass -c config --debug`; `--debug` turns on asyncio debug mode, not debug logging
  (`docs/ha-notes.md`, *Tooling*). HA's log then goes to `config/`. `scripts/smoke` writes its log to
  `local/smoke.log`.
- `scripts/smoke` refuses to start while an HA runs on `config/`: two instances would share the session.
- Sign-ins are rate-limited (CLAUDE.md hard rule 6; the config flow's `rate_limited` error).
- `config/` is shared by every branch checked out in the main checkout; a store written by a newer branch
  (for example the price store's version 2 in #51) can break an older one (`way-of-working.md` §8
  *From branch ready to PR ready*, step 2).
- `.gitignore` ignores `config/`, `local/`, logs, `home-assistant_v2.db*`, `.storage/` and diagnostics
  downloads (`*diagnostics*.json`, `config_entry-*.json`).

## 1. Files

| File | Change |
|---|---|
| `docs/manual-testing.md` | New: the guide (§2, §3) |
| `docs/README.md` | One row in the documentation map, after `ha-notes.md` |
| `docs/way-of-working.md` | One line in §8 step 3 pointing to the guide |

## 2. The guide: before testing

Sections, short, in this order:

1. **Purpose and rules.** One paragraph: manual testing is against the owner's real account and charger.
   The rules that apply, linked, not restated: CLAUDE.md hard rules 2 (start and stop), 3 and 4 (nothing
   private, nothing from a real instance committed), 5 (logs and diagnostics), 6 (no retried start; reauth
   instead of login), 9 (subagents). Stated in the guide itself, since it is the point of #10: **turning
   *Charge* on or off, by hand, from EV Smart Charging or from an automation, is a real start or stop and
   needs the owner's explicit OK first, each time** — including a turn-on expected to be refused.
2. **Running Home Assistant.** `scripts/develop` (or F5 in VS Code, which runs `scripts/develop
   --setup-only` first), where HA listens (`http://localhost:8123`), how to stop it
   (`pkill -f "hass -c config"`, as `ha-notes.md` says for a background run; Ctrl+C in a terminal). The
   devcontainer is an option for manual testing only. Only one HA runs on `config/` at a time; stop it
   before `scripts/smoke`. Points to CLAUDE.md *Commands* rather than repeating the commands' details.
3. **Where real-instance data lives.**
   - `config/`: the HA config, the stored session (`.storage/`), HA's database and log. Gitignored, never
     committed (hard rule 4), never read by agents (hard rule 9).
   - `local/`: everything taken from a real instance and kept: logs copied out, anything downloaded from HA
     (future diagnostics included), screenshots (`local/screenshots/<topic>/`, §8 step 3), notes with real
     values. Gitignored, never committed, never read by agents.
   - Nothing from either goes into a commit, an issue, a PR or a review comment; posted results follow §8
     *Public text* (linked).
4. **Pitfalls.**
   - Sign-ins are rate-limited: keep them few; don't remove and re-add the entry to "try again".
   - `config/` is shared across branches: a store written by a newer branch can break an older one; if a
     branch fails to load after switching, suspect this first (and tell the owner, since fixing it means
     touching `config/`).
   - After each `uv sync`, HA reinstalls its runtime packages on first start (the note in
     `scripts/develop`), so the first start is slower.
   - `--debug` in `scripts/develop` is asyncio debug mode, not debug logging (links to `ha-notes.md`).

## 3. The guide: checklists

Each item is one line, a checkbox, naming what to look at and linking to the user-doc section that says
what is right. Items marked **owner** are done only by the owner; agents skip them. The order keeps
sign-ins to one per run. The checklists are grouped by feature, with the issue that built it.

### 3.1 Setup, restart and reauth (#7)

- **owner** Add the integration with the config flow (user docs *Configuration*), only when `config/` has
  no Nortec Go entry yet: the entry's name, the devices (*Supported functionality*).
- The config flow's errors are not tried live: each submit of the form signs in (`config_flow.py` signs in
  before it checks for *already configured*), so every one costs a sign-in against the rate limit, and a
  wrong password or a second account adds nothing the mocked tests don't cover.
- Restart HA: the entry loads without a new sign-in, entities come back (the log shows no errors from the
  integration).
- Reload the entry: the same.
- Reauth (*proposal, with the owner*): checked when it happens, not forced. When HA shows the notice, the
  **owner** follows the user docs' *Asked to sign in again*: the notice shows, signing in to the same
  account works (one sign-in), entities come back. Signing in to another account (*wrong account*) is not
  tried live, as for the config flow's errors. The guide gives no method to force a reauth.

### 3.2 Entities (#8, and the later sensors)

For every entity in the user docs' *Supported functionality* tables (charger and car): it exists, its name
and type match the table, and its value or state is plausible for what the charger, car and app show. The
checklist lists the entities by name (taken from `strings.json`, not from memory), each against its table
row:

- Charger: *Current price* (the value, unit and the `prices_today` / `prices_tomorrow` attributes as the
  user docs' row and *Use cases* describe them, with no restated unit or price kind), *Cable connected*,
  *Charging*, *Charge* (its state only; not toggled here), *Charge status* (a state from the user docs'
  list), *Refresh*, *Last read*.
- Car: *Battery*, *Charge limit*, *Last seen*, *Plugged in*, *Connected to charger*; the car device's name
  (the placeholder rule in the user docs).
- Reads: pressing *Refresh* moves *Last read* (user docs *Data updates*). Pressing *Refresh* reads only; it
  is not a start or stop.
- The device page: both devices, their entities, the diagnostic entities in the diagnostic group.

### 3.3 EV Smart Charging (#8)

*Proposal, with the owner (PO question on #10).*

- Setting up EV Smart Charging with the entities in the user docs' *Use cases* table is not an action on
  the charger by itself, but once its charger control is set, EV Smart Charging turns *Charge* on and off by
  its schedule: each is a real start or stop (§2 item 1).
- So, for a test run: set the charger control only with the owner's OK for that run, or keep EV Smart
  Charging's smart-charging switch off. The same holds for any automation in `config/` that turns *Charge*
  on or off: off unless the owner has OK'd the run.
- **Checks without charger actions:** EV Smart Charging accepts each entity, reads the price list
  (its own chart or attributes show today's and, after the day-ahead prices, tomorrow's slots), and its
  plan follows the prices.
- **owner, with explicit OK:** a planned charge starts and stops as the plan says; the user docs' *Use
  cases* notes (continuous charging, the replug) hold.

### 3.4 Start and stop (#9, and the later start and stop deadlines)

Every item here is **owner, with explicit OK for that session**. Agents never do them, and the guide never
tells an agent to.

- Before: the cable is connected, *Charge status* is not *Waiting for replug* or *Start blocked*.
- Start: turn *Charge* on; the switch and *Charge status* follow the user docs' *Starting a charge*
  (starting, then charging), and *Charging* turns on.
- Stop: turn *Charge* off; the same section's description of a stop, and *Charge status* after it.
- The replug rule after a stop (user docs *Starting a charge*).
- A start refused by design (for example with the cable unplugged) is still a start request (§2 item 1),
  so it needs the same OK.
- The start block and the repair issue are checked only if one happens; the guide gives no method to cause
  a failed start.

## 4. The pointer in `way-of-working.md`

§8 *From branch ready to PR ready*, step 3, gains one sentence: what to look at is in
[`manual-testing.md`](manual-testing.md). Nothing else in `way-of-working.md` changes; §1 step 10 is
unchanged.

## 5. Checks

A docs change has no tests. The task checks, and the branch review re-checks:

- Every link and section anchor in the guide resolves (relative links from `docs/`; section names as they
  are in `docs/user/nortec_go.md`, `CLAUDE.md`, `ha-notes.md` and `way-of-working.md`).
- Every entity, state and error name matches `strings.json`.
- `grep` over the changed files finds no email, IDs, tokens, raw endpoints or real values (hard rule 3).
- No statement contradicts `scripts/develop`, `scripts/smoke`, `.gitignore` or the user docs.
- The gates (CLAUDE.md *Commands*) pass; the pre-commit hooks run on the Markdown.

## 6. Decision log

None expected: the guide applies existing rules. If the owner's answers on §3.1 or §3.3 set a new lasting
rule, it gets the next D-number from the PO.
