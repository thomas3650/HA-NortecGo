# Manual testing

How to test the integration by hand against the owner's own account and charger, without leaking data or
starting a charge by accident.

## Rules

Manual testing runs against the owner's real Nortec Go account and real charger, so every read and every
action is real. The rules that apply are [hard rules 2, 3, 4, 5, 6 and 9](../CLAUDE.md#hard-rules) in
`CLAUDE.md`; they aren't repeated here.

**Turning *Charge* on or off, by hand, from EV Smart Charging or from an automation, is a real start or
stop, and needs the owner's explicit OK first. One OK covers one charging session, that is one charge:
starting it and stopping it. A new charge needs a new OK. A refused start uses its OK; trying again needs
a new one.** That includes a turn-on you expect to be refused: it counts as a start, because once the
integration's own checks pass, it sends a real start request. The rule is
[D36](decisions.md#d36-one-ok-per-charge).

## Running Home Assistant

- Start it with `scripts/develop`, or with F5 in VS Code, which runs `scripts/develop --setup-only` first.
  Home Assistant listens on `http://localhost:8123`. The commands are in
  [`CLAUDE.md` → *Commands*](../CLAUDE.md#commands).
- Stop it with Ctrl+C in its terminal, with VS Code's stop button for F5, or with
  `pkill -f "hass -c config"` for a `scripts/develop` running in the background (see
  [Tooling](ha-notes.md#tooling)).
- Run one Home Assistant on `config/` at a time, the devcontainer included: `scripts/smoke` can't see one
  running there. Stop it before you run `scripts/smoke`. The devcontainer is for manual testing only.

## Where real data lives

- `config/`: the Home Assistant config, the stored session, its database and its log. Gitignored, never
  committed, never read by agents.
- `local/`: everything taken from a real instance that you keep: logs copied out, a debug-log download (it
  lands in the browser's downloads folder first; move it), anything else downloaded from Home Assistant,
  screenshots (`local/screenshots/<topic>/`), notes with real values. Gitignored, never committed, never
  read by agents.
- Nothing from either goes into a commit, an issue, a PR or a review comment. Results posted on GitHub
  follow *Public text* in [`way-of-working.md` §8](way-of-working.md#escalation).

## Pitfalls

- Sign-ins are rate-limited. A restart or a reload reuses the stored session and needs none. Don't delete
  and re-add the entry to "try again": that costs a sign-in, and deleting it also drops the stored start
  guard and any start-block repair, which are there to prevent a second card hold, and restarts *Total
  energy* at 0.
- `config/` is shared by every branch: data a newer branch stored can break an older one. If a branch
  fails to load after a switch, suspect this first and tell the owner (fixing it means touching
  `config/`).
- After each `uv sync`, the first start is slower: Home Assistant reinstalls its runtime packages.
- `--debug` in `scripts/develop` turns on asyncio debug mode, not debug logging (see
  [Tooling](ha-notes.md#tooling)). For debug logs, see [Debug logging](user/nortec_go.md#debug-logging).
- `config/` has no EV Smart Charging and no automation that turns *Charge* on or off, and stays that way
  unless the owner adds one: anything there runs on every start of Home Assistant, `scripts/smoke` and the
  PO's visual check included (see *EV Smart Charging* below).

## Who does what

**Owner only:**

- the config flow, and anything with credentials;
- setting up EV Smart Charging, and creating or turning on an automation that turns *Charge* on or off;
- acting on any repair;
- the entry's ⋮ menu (reload, delete, disable);
- anything that calls an action on the charger;
- everything under *Start and stop*.

**Agents** (the PO's visual check) navigate and read, and operate no control: not the *Charge* row or its
toggle anywhere (read its state without opening it), not *Refresh*, not **Submit** in a repair, not the
entry's ⋮ menu. The rules of the check itself are in `way-of-working.md` §8,
[*From branch ready to PR ready*](way-of-working.md#from-branch-ready-to-pr-ready), step 3.

To check for errors from the integration, agents use `scripts/smoke`'s output or Home Assistant's log page
(**Settings** > **System** > **Logs**), never the log file in `config/`.

## Checklists

Each item says what to look at; the linked section of the user docs says what is right. Items marked
**Owner** are done only by the owner.

### Setup and restart (#7)

- [ ] **Owner** Add the integration (only when `config/` has no Nortec Go entry yet): the entry's name and
  its devices ([Configuration](user/nortec_go.md#configuration),
  [Supported functionality](user/nortec_go.md#supported-functionality)).
- [ ] The config flow's errors aren't tried live: every submit signs in, and the automated tests cover
  them.
- [ ] Restart Home Assistant (stop and start it as in *Running Home Assistant*, not from the UI): the entry
  loads without a new sign-in, the entities come back, and there are no errors from the integration (see
  *Who does what* for how to check).
- [ ] **Owner** Reload the entry: the same.
- [ ] Reauthentication isn't tested by hand; the automated tests cover it.

### Entities (#8)

For each entity: it exists, and its name and type match its row in
[Supported functionality](user/nortec_go.md#supported-functionality). The owner also checks that its value
or state is plausible for what the charger, the car and the app show; an agent sees neither.

Charger:

- [ ] *Current price*: its value, unit and price-list attributes as its row and
  [Use cases](user/nortec_go.md#use-cases) describe them.
- [ ] *Cable connected*.
- [ ] *Charging*.
- [ ] *Charge*: its state only.
- [ ] *Charge status*.
- [ ] *Energy this charge*.
- [ ] *Total energy*.
- [ ] *Charging power*.
- [ ] *Cost this charge*.
- [ ] *Last charge cost*.
- [ ] *Refresh*: present.
- [ ] *Last read*.

Car:

- [ ] *Battery*.
- [ ] *Charge limit*.
- [ ] *Last seen*.
- [ ] *Plugged in*.
- [ ] *Connected to charger*.
- [ ] The car device's name ([Car](user/nortec_go.md#car)).

Reads and the device page:

- [ ] **Owner** Press *Refresh*: *Last read* moves ([Data updates](user/nortec_go.md#data-updates)).
  *Refresh* only reads. A press whose read fails shows an error; the checklist has no step that makes one
  fail.
- [ ] The device page: both devices, their entities, and the diagnostic entities in the diagnostic group.

### EV Smart Charging (#8)

- EV Smart Charging isn't set up in `config/` and isn't tested there: the owner tests it in the owner's own
  production Home Assistant, outside this guide.
- Setting it up in `config/`, or creating or turning on an automation there that turns *Charge* on or off,
  is owner only and counts as a start or stop (see *Rules*), so nobody adds one to the dev config by
  accident. If one is ever set up there, its smart-charging switch and any such automation stay off unless
  the owner has given the OK for a charge (see *Rules*), and the owner turns them off again when that
  charge ends: `config/` keeps them for every later start of Home Assistant.
- The *Current price* attributes that EV Smart Charging reads are checked under *Entities*, without it.

### Start and stop (#9)

Every item here is **owner only, and needs the owner's explicit OK first. One OK covers one charging
session, that is one charge: starting it and stopping it. A new charge needs a new OK. A refused start uses
its OK; trying again needs a new one.** Agents never do them.

- [ ] Before: the cable is connected, and *Charge status* is not *Waiting for replug* or *Start blocked*.
- [ ] Start: turn *Charge* on; the switch and *Charge status* follow
  [Starting a charge](user/nortec_go.md#starting-a-charge).
- [ ] Stop: turn *Charge* off; the same section describes a stop.
- [ ] After a stop: the replug rule in the same section.
- [ ] A start that should be refused (for example with the cable unplugged) may still be a real start
  request: it counts as a start and uses its OK; trying again needs a new one.
- [ ] The start block and its repair are checked only if one happens; there is no way here to cause a
  failed start.

### Diagnostics (#11)

- [ ] **Owner** Download the diagnostics from the entry's menu and save the file in `local/`: the email,
  both tokens and the device ID show as `**REDACTED**`, and the charger's and car's data are there
  ([Diagnostics](user/nortec_go.md#diagnostics)). Agents never open the file.
