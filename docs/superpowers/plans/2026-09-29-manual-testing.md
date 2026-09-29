# Manual test guide and debug logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** A guide for manual testing against the owner's real account that never leads to an accidental start, stop or data leak (#10), and user docs on debug logging and bug reports, with the manifest's `loggers` (#38).

**Architecture:** Docs only, plus one manifest key with its test. The guide (`docs/manual-testing.md`) restates no expected behaviour: each checklist item links to the section of `docs/user/nortec_go.md` that describes it, and each rule links to where it lives. The user docs gain two parts under *Troubleshooting*; the manifest gains `"loggers": ["pynortecgo"]` so the integration page's debug logging covers the client.

**Tech Stack:** Markdown, Home Assistant manifest JSON, GitHub issue-form YAML, pytest, uv, pre-commit.

**Spec:** `docs/superpowers/specs/2026-09-29-manual-testing-design.md` (issues #10, #38).

## Global Constraints

- Nothing private (hard rule 3): no email address, account, charger or user IDs, tokens, captures, raw API endpoints or endpoint names, quoted log lines, links into the private `NortecGo` repo, and no real values or states seen in HA.
- Never read `.env`, `config/` or `local/` (hard rule 9). Never start or stop a charge, and never run `scripts/develop` or `scripts/smoke`: this work needs neither.
- The guide never tells anyone to turn *Charge* on or off, by hand, from EV Smart Charging or from an automation, without the owner's explicit OK first, each time; and never tells an agent to do it at all.
- No duplication (`docs/way-of-working.md` §7): link to the section that owns a fact; don't restate values, units, price kinds, sequences or timings. States are named only as preconditions, spelled exactly as in `custom_components/nortec_go/strings.json`. No link to D34 or to anything only on `origin/feat/pynortecgo-0.5.0`.
- Style: the repo's docs style — short sentences, plain words, lines wrapped at 110 characters (table rows excepted), `*Entity name*` in italics, UI paths as **Settings** > **System** > **Logs**.
- Gates before every commit (`CLAUDE.md` → Commands): `uv run pytest -q` and `uv run ruff check && uv run ruff format --check && uv run mypy`; the coverage gate passes at the end of Task 2. The pre-commit hooks run on commit; never bypass them.
- Subagents write commit messages with the Write tool to a file outside the repo and commit with `git commit -F <file>` (no heredocs). End each message with the co-author trailer given in the dispatch.
- Section names fixed by this plan (Task 1 links to them before Task 2 writes them): `### Debug logging` (anchor `#debug-logging`) and `### Reporting a problem` (anchor `#reporting-a-problem`) under `## Troubleshooting` in `docs/user/nortec_go.md`.
- Leak check, per task, a pass being no output from each command:

  ```text
  PAT='[[:alnum:]._%+-]+@[[:alnum:].-]+\.[a-z]{2,}|https?://[^ )]*api'
  git diff <BASE> -- <the task's files other than docs/manual-testing.md> | grep '^+' | grep -nE "$PAT"
  grep -nE "$PAT" docs/manual-testing.md        # Task 1 only
  ```

  `<BASE>` is the commit the task started from (`git -C <worktree> merge-base HEAD docs/manual-testing` right after the worktree is made). The diff's `+++ b/<file>` header lines pass through `grep '^+'`; they can't match the pattern.

## Review Focus

1. An agent following the guide during the PO's visual check must find no instruction that leads it to operate a control (the *Charge* toggle, *Refresh*, a repair's **Submit**, the entry's ⋮ menu) — Task 1, Step 4 check (a).
2. An EV Smart Charging setup or an automation on *Charge* added to `config/` would start or stop real charges on the next `scripts/smoke` or visual check; the guide must say `config/` has none, adding one is owner only, and the owner's session rule if one is ever added — Task 1, Step 4 check (b).
3. The price item must still be right after #51 (total price, the forecast's currency): no unit, currency or price kind in the guide — Task 1, Step 4 check (c).
4. A section link from the guide to *Debug logging* or *Reporting a problem* must resolve once Task 2 lands — Task 1 re-check when held (see *Waves*).
5. The user docs' logging text must hold for `pynortecgo` 0.2.0 and 0.5.0 alike: it claims only "no tokens or passwords", and names no endpoints and quotes no lines — Task 2, Step 6 check.

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (the guide, the map row, the §8 pointer), Task 2 (#38) | Disjoint files: two worktrees. Task 1 links to Task 2's section names, fixed above; it is a docs task starting ahead of its input, so it is held until Task 2 is on the feature branch and then re-checked against the names that landed |

No task has guarded files.

---

### Task 1: The manual test guide, its map row and the §8 pointer

**Model:** opus — a docs task (D33).
**Wave:** 1

**Files:**
- Create: `docs/manual-testing.md`
- Modify: `docs/README.md` (one table row)
- Modify: `docs/way-of-working.md` (one sentence in §8 *From branch ready to PR ready*, step 3)

**Interfaces:**
- Consumes: the section names `### Debug logging` / `#debug-logging` and `### Reporting a problem` / `#reporting-a-problem` in `docs/user/nortec_go.md` (Task 2).
- Produces: `docs/manual-testing.md`, linked from `docs/README.md` and from `way-of-working.md` §8 step 3.

- [ ] **Step 1: Read the sources**

Read the spec's §2, §3 and §5, then: `docs/user/nortec_go.md` (every section heading), `custom_components/nortec_go/strings.json`, `scripts/develop`, `scripts/smoke`, `.vscode/launch.json`, `.vscode/tasks.json`, `.gitignore`, `docs/ha-notes.md` (*Tooling*), `CLAUDE.md` (*Commands*, *Hard rules*), `docs/way-of-working.md` §8. Every name the guide uses comes from these files.

- [ ] **Step 2: Write `docs/manual-testing.md`**

Title `# Manual testing`, then one intro line: how to test the integration by hand against the owner's own account and charger, without leaking data or starting a charge by accident. Then these sections, in this order. Links are relative from `docs/` (for example `../CLAUDE.md#hard-rules`, `user/nortec_go.md#starting-a-charge`, `ha-notes.md#tooling`).

`## Rules`
- One paragraph: testing is against the owner's real account and charger. Link, don't restate: CLAUDE.md hard rules 2, 3, 4, 5, 6 and 9 (one link to `../CLAUDE.md#hard-rules`, naming the numbers).
- In bold, stated here: turning *Charge* on or off — by hand, from EV Smart Charging or from an automation — is a real start or stop and needs the owner's explicit OK first, each time. This includes a turn-on you expect to be refused: once the integration's own checks pass, it sends a real start request.

`## Running Home Assistant`
- `scripts/develop`, or F5 in VS Code (it runs `scripts/develop --setup-only` first); Home Assistant listens on `http://localhost:8123`. Link `../CLAUDE.md#commands` for the commands.
- Stop it with Ctrl+C in its terminal, VS Code's stop button for F5, or `pkill -f "hass -c config"` for a background `scripts/develop` (link `ha-notes.md#tooling`).
- One Home Assistant on `config/` at a time, the devcontainer included (`scripts/smoke` can't see one running there). Stop it before `scripts/smoke`. The devcontainer is for manual testing only.

`## Where real data lives`
- `config/`: the Home Assistant config, the stored session, its database and log. Gitignored, never committed, never read by agents.
- `local/`: everything taken from a real instance that you keep — logs copied out, a debug-log download (it lands in the browser's downloads folder first; move it), anything else downloaded from Home Assistant, screenshots (`local/screenshots/<topic>/`), notes with real values. Gitignored, never committed, never read by agents.
- Nothing from either goes into a commit, an issue, a PR or a review comment. Results posted on GitHub follow *Public text* in `way-of-working.md` §8 (link `way-of-working.md#escalation`, where *Public text* is).

`## Pitfalls`
- Sign-ins are rate-limited. A restart or a reload reuses the stored session and needs none. Don't delete and re-add the entry to "try again": that costs a sign-in, and deleting it also drops the stored start guard and any start-block repair, which are there to prevent a second card hold.
- `config/` is shared by every branch: data a newer branch stored can break an older one. If a branch fails to load after a switch, suspect this first and tell the owner (fixing it means touching `config/`).
- After each `uv sync`, the first start is slower: Home Assistant reinstalls its runtime packages.
- `--debug` in `scripts/develop` turns on asyncio debug mode, not debug logging (link `ha-notes.md#tooling`). For debug logs, see [Debug logging](user/nortec_go.md#debug-logging).
- `config/` has no EV Smart Charging and no automation that turns *Charge* on or off, and stays that way unless the owner adds one: anything there runs on every start of Home Assistant, `scripts/smoke` and the PO's visual check included (see *EV Smart Charging* below).

`## Who does what`
- **Owner only** (a list): the config flow and anything with credentials; setting up EV Smart Charging, and creating or turning on an automation that turns *Charge* on or off; acting on any repair; the entry's ⋮ menu (reload, delete, disable); anything that calls an action on the charger; everything under *Start and stop*.
- **Agents** (the PO's visual check): navigate and read, and operate no control. Not the *Charge* row or its toggle anywhere (read its state without opening it), not *Refresh*, not **Submit** in a repair, not the entry's ⋮ menu. The rules of the check itself: `way-of-working.md` §8, *From branch ready to PR ready*, step 3 (link `way-of-working.md#from-branch-ready-to-pr-ready`).
- To check for errors from the integration, agents use `scripts/smoke`'s output or Home Assistant's log page (**Settings** > **System** > **Logs**), never the log file in `config/`.

`## Checklists`
One intro line: each item says what to look at; the linked section of the user docs says what is right. Items marked **Owner** are done only by the owner. Then four subsections; each but *EV Smart Charging* is a `- [ ]` list:

`### Setup and restart (#7)`
- [ ] **Owner** Add the integration (only when `config/` has no Nortec Go entry yet): the entry's name and its devices — [Configuration](user/nortec_go.md#configuration), [Supported functionality](user/nortec_go.md#supported-functionality).
- [ ] The config flow's errors aren't tried live: every submit signs in, and the automated tests cover them.
- [ ] Restart Home Assistant (stop and start it as in *Running Home Assistant*, not from the UI): the entry loads without a new sign-in, the entities come back, and there are no errors from the integration (see *Who does what* for how to check).
- [ ] **Owner** Reload the entry: the same.
- [ ] Reauthentication isn't tested by hand; the automated tests cover it.

`### Entities (#8)`
- One line: for each entity, it exists and its name and type match its row in [Supported functionality](user/nortec_go.md#supported-functionality); the owner also checks that its value or state is plausible for what the charger, the car and the app show (an agent sees neither).
- [ ] Charger: *Current price* (its value, unit and price-list attributes as its row and [Use cases](user/nortec_go.md#use-cases) describe them), *Cable connected*, *Charging*, *Charge* (its state only), *Charge status*, *Refresh* (present), *Last read* — one item per entity.
- [ ] Car: *Battery*, *Charge limit*, *Last seen*, *Plugged in*, *Connected to charger* — one item per entity; and the car device's name ([Car](user/nortec_go.md#car)).
- [ ] **Owner** Press *Refresh*: *Last read* moves ([Data updates](user/nortec_go.md#data-updates)). *Refresh* only reads.
- [ ] The device page: both devices, their entities, the diagnostic entities in the diagnostic group.

`### EV Smart Charging (#8)`
No checklist; three short points:
- EV Smart Charging isn't set up in `config/` and isn't tested there: the owner tests it in the owner's own production Home Assistant, outside this guide.
- Setting it up in `config/`, or creating or turning on an automation there that turns *Charge* on or off, is owner only and counts as a start or stop (see *Rules*), so nobody adds one to the dev config by accident. If one is ever set up there, its smart-charging switch and any such automation stay off unless the owner has given an explicit OK for that session, and the owner turns them off again when the session ends: `config/` keeps them for every later start of Home Assistant.
- The *Current price* attributes that EV Smart Charging reads are checked under *Entities*, without it.

`### Start and stop (#9)`
- One line: every item here is **owner only, with explicit OK for that session**. Agents never do them.
- [ ] Before: the cable is connected, and *Charge status* is not *Waiting for replug* or *Start blocked*.
- [ ] Start: turn *Charge* on; the switch and *Charge status* follow [Starting a charge](user/nortec_go.md#starting-a-charge).
- [ ] Stop: turn *Charge* off; the same section describes a stop.
- [ ] After a stop: the replug rule in the same section.
- [ ] A start that should be refused (for example with the cable unplugged) may still be a real start request, so it needs the same OK.
- [ ] The start block and its repair are checked only if one happens; there is no way here to cause a failed start.

- [ ] **Step 3: Add the map row and the §8 pointer**

In `docs/README.md`, after the `ha-notes.md` row, add:

```text
| [`manual-testing.md`](manual-testing.md) | Testing by hand against the owner's real account: running it, where real data lives, who may do what, checklists per feature | Testing the integration live |
```

In `docs/way-of-working.md` §8 *From branch ready to PR ready*, step 3, after "check against the spec," change the sentence so it reads "check against the spec (what to look at, and that an agent operates no control, are in [`manual-testing.md`](manual-testing.md)),". Rewrap the rest of step 3 at 110 characters if needed; nothing else in the file changes.

- [ ] **Step 4: Check**

(a) Read the guide as the PO doing a visual check: no instruction leads an agent to operate any control. (b) *EV Smart Charging* says it isn't set up or tested in `config/`, that adding it or an automation on *Charge* there is owner only, and the session rule if one is ever set up; *Pitfalls* says anything in `config/` runs on every start. (c) No unit, currency, price kind, timing or state sequence is restated; the only *Charge status* states named are *Waiting for replug* and *Start blocked*, spelled as in `strings.json` (`not_released`, `start_blocked`). (d) Every entity name matches `strings.json`. (e) Every relative link resolves to an existing file and heading (list them with `grep -on '](\([^)]*\))' docs/manual-testing.md` and check each heading's anchor against the target file's headings), except `#debug-logging` and `#reporting-a-problem`, which Task 2 adds. (f) The leak check from *Global Constraints*, over `docs/README.md docs/way-of-working.md` and `docs/manual-testing.md`: no output. (g) `uv run pre-commit run --files docs/manual-testing.md docs/README.md docs/way-of-working.md`: all pass.

- [ ] **Step 5: Commit**

```bash
git add docs/manual-testing.md docs/README.md docs/way-of-working.md
git commit -F <message file>   # "docs: manual test guide (#10)" + the co-author trailer
```

---

### Task 2: Debug logging and bug reports (#38)

**Model:** opus — a docs task (D33).
**Wave:** 1

**Files:**
- Modify: `tests/test_manifest.py`
- Modify: `custom_components/nortec_go/manifest.json`
- Modify: `docs/user/nortec_go.md` (two parts at the end of `## Troubleshooting`)
- Modify: `.github/ISSUE_TEMPLATE/bug.yml`
- Modify: `custom_components/nortec_go/quality_scale.yaml`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `### Debug logging` and `### Reporting a problem` under `## Troubleshooting` in `docs/user/nortec_go.md` (Task 1 links to both).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_manifest.py`:

```python
def test_loggers_include_the_client() -> None:
    """Debug logging from the integration page also covers pynortecgo."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["loggers"] == ["pynortecgo"]
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest tests/test_manifest.py -q`
Expected: FAIL with `KeyError: 'loggers'`.

- [ ] **Step 3: Add the key**

In `custom_components/nortec_go/manifest.json`, between `"issue_tracker"` and `"requirements"` (hassfest's order: `domain`, `name`, then alphabetical):

```json
  "loggers": ["pynortecgo"],
```

Run: `uv run pytest tests/test_manifest.py -q` — Expected: PASS.

- [ ] **Step 4: The user docs**

At the end of `## Troubleshooting` in `docs/user/nortec_go.md` (after `### "Starts are blocked"`, before `## Removing the integration`), add:

````markdown
### Debug logging

To see what the integration does, turn on debug logging from its page in Home Assistant, as described in
[Enabling debug logging](https://www.home-assistant.io/docs/configuration/troubleshooting/#enabling-debug-logging).
For Nortec Go this also covers `pynortecgo`, the library it uses to talk to the service.

Or add this to `configuration.yaml` (or merge it into your `logger:` block if you have one) and restart
Home Assistant:

```yaml
logger:
  default: warning
  logs:
    custom_components.nortec_go: debug
    pynortecgo: debug
```

Remove it again when you're done: debug logging writes a lot.

The logs hold no passwords or session tokens, but check them before you share them (see *Reporting a
problem*).

### Reporting a problem

Open an issue with the bug report template. Include your Home Assistant and integration versions and the
lines of the debug log around the problem, not the whole log. Before you post, remove your email address,
your charger's and car's names, and anything else that identifies you or where you live.
````

(The outer four-backtick fence is only for this plan; in the file, the `yaml` block is an ordinary fenced
block.)

- [ ] **Step 5: Bug template, quality scale, changelog**

In `.github/ISSUE_TEMPLATE/bug.yml`, the `diagnostics` field's `description` becomes:

```yaml
      description: >-
        Optional. Turn on debug logging as described in
        https://github.com/thomas3650/HA-NortecGo/blob/main/docs/user/nortec_go.md#debug-logging,
        reproduce the problem, and paste the lines around it. Before pasting, remove what the docs'
        "Reporting a problem" lists.
```

In `custom_components/nortec_go/quality_scale.yaml`: `docs-troubleshooting: done`.

In `CHANGELOG.md`, under `## [Unreleased]` → `### Added`, append:

```markdown
- Debug logging turned on from the integration's page also covers the `pynortecgo` client, and the docs
  explain debug logging and what to leave out of a bug report.
```

- [ ] **Step 6: Check**

The logging text claims only "no passwords or session tokens" (true for `pynortecgo` 0.2.0 and 0.5.0), names no endpoint and quotes no log line. The leak check from *Global Constraints* over `tests/test_manifest.py custom_components/nortec_go/manifest.json docs/user/nortec_go.md .github/ISSUE_TEMPLATE/bug.yml custom_components/nortec_go/quality_scale.yaml CHANGELOG.md`: no output (the home-assistant.io link has no `api` in it). The gates: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95` and `uv run ruff check && uv run ruff format --check && uv run mypy`; `uv run pre-commit run --files <the six files>`: all pass.

- [ ] **Step 7: Commit**

```bash
git add tests/test_manifest.py custom_components/nortec_go/manifest.json docs/user/nortec_go.md .github/ISSUE_TEMPLATE/bug.yml custom_components/nortec_go/quality_scale.yaml CHANGELOG.md
git commit -F <message file>   # "docs: debug logging and bug reports, manifest loggers (#38)" + the co-author trailer
```
