# Keep the grid tariff across restarts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** raise the client to `pynortecgo==0.12.0`, store the grid tariff it hands to `on_grid_tariff`,
and pass it back as `grid_tariff` at the next setup (#130).

**Architecture:** a new `grid_tariff.py` holds `GridTariffStore`, a thin wrapper over Home Assistant's
`Store` that keeps the client's dict unchanged. `create_client` passes two new keywords through, and
`async_setup_entry` loads the store before building the client and saves from the callback.
`async_remove_entry` deletes the file. A docs task then updates the user docs, the changelog and the
decision log.

**Tech Stack:** Python 3.14, Home Assistant 2026.10, `homeassistant.helpers.storage.Store`, pytest with
`pytest-homeassistant-custom-component` (`hass_storage`), uv.

**Spec:** `docs/superpowers/specs/2026-11-16-grid-tariff-store-design.md` (issue #130). Read it with the
task: this plan argues from it.

## Global Constraints

- **Client version:** `pynortecgo==0.12.0` in both `manifest.json` `requirements` and `pyproject.toml`,
  locked with `uv lock --upgrade-package pynortecgo`, then `uv sync`.
- **Public API only:** nothing is imported from `pynortecgo`'s private modules (`pynortecgo._*`). The
  callback type is written out locally.
- **Store:** key `nortec_go.{entry_id}.grid_tariff`, version 1. It holds the client's dict exactly as handed
  over: no wrapper, no parsing, no checks of its own, no migration.
- **Opaque in tests:** the tariff dict in tests is a made-up dict (`FAKE_GRID_TARIFF`), not the client's
  format. `pynortecgo` is always mocked (hard rule 2).
- **Behaviour otherwise unchanged:** no entity, option, flow step, translation or diagnostics change, and
  nothing near charge start or stop. The config flow's sign-in clients don't get the new keywords.
- **Not `version` in `manifest.json`:** the controller runs the bump step.
- **Gates before each commit** (`CLAUDE.md` → Commands):
  - `uv run pytest -q`;
  - `uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`;
  - before the task's last commit, `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`.
- **Where:** in the checkout the dispatch names (`<checkout>`), on branch `fix/grid-tariff-store`. Edit
  files by absolute path.
- **Commit messages:** written with the Write tool to `/tmp/grid-tariff-task-<n>-msg-<k>.txt`, committed with
  `git commit -F <file>`. No heredocs. End each with the co-author trailer from the dispatch.
- **Nothing private** (hard rule 3): no account, charger or user IDs, tokens, captures or raw endpoints, in
  code, tests, docs or commit messages.

## Review Focus

1. **A file whose data isn't a dict** (a hand-edited or corrupt store holding a list, a string or a number).
   Expected: setup still succeeds, the client gets `grid_tariff=None`, and one warning names the stored
   grid tariff. Pinned by Task 1's `test_store_wrong_shape`.
2. **A reload after the client saved a tariff.** Expected: the new client is built with the dict the old
   one saved, so a reload needs no DataHub request. Pinned by Task 1's
   `test_reload_hands_back_the_saved_grid_tariff`.
3. **The first setup after the upgrade** (no grid tariff file yet). Expected: the client gets
   `grid_tariff=None` and a callback, and nothing is written until the callback runs. Pinned by Task 1's
   additions to `test_setup_entry`.
4. **The sign-in clients of the config flow.** Expected: `create_client(hass)` passes `grid_tariff=None`
   and `on_grid_tariff=None`, so a sign-in never writes the store. Pinned by Task 1's updated
   `test_create_client_defaults`.
5. **Deleting the entry.** Expected: the grid tariff file goes with the prices, energy and charge control
   files. Pinned by Task 1's `test_remove_entry_removes_the_stored_grid_tariff`.

---

### Task 1: pynortecgo 0.12.0 and the grid tariff store

**Model:** sonnet
**Wave:** 1

**Files:**
- Modify: `custom_components/nortec_go/manifest.json` (`requirements` only), `pyproject.toml` (the
  `pynortecgo` pin), `uv.lock`
- Modify: `custom_components/nortec_go/const.py` (next to the other store keys, lines 33–53)
- Create: `custom_components/nortec_go/grid_tariff.py`
- Modify: `custom_components/nortec_go/entry.py` (`create_client`)
- Modify: `custom_components/nortec_go/__init__.py` (`async_setup_entry`, `async_remove_entry`)
- Modify: `tests/conftest.py` (one constant)
- Create: `tests/test_grid_tariff.py`
- Modify: `tests/test_entry.py`, `tests/test_init.py`

**Interfaces:**
- Consumes: `NortecGoClient(..., grid_tariff: Mapping[str, Any] | None, on_grid_tariff: <async callback> | None)`
  from `pynortecgo` 0.12.0.
- Produces:
  - `const.GRID_TARIFF_STORE_VERSION: Final = 1`, `const.GRID_TARIFF_STORE_KEY: Final = "nortec_go.{entry_id}.grid_tariff"`;
  - `grid_tariff.GridTariffStore(hass: HomeAssistant, entry_id: str)` with
    `async_load() -> dict[str, Any] | None`, `async_save(tariff: Mapping[str, Any]) -> None`,
    `async_remove() -> None`;
  - `entry.create_client(hass, *, tokens=None, device_id=None, on_tokens_refreshed=None, grid_tariff: Mapping[str, Any] | None = None, on_grid_tariff: Callable[[dict[str, Any]], Awaitable[None]] | None = None) -> NortecGoClient`;
  - `tests.conftest.FAKE_GRID_TARIFF: dict[str, Any]`.

- [ ] **Step 1: Bump the client**

Set `pynortecgo==0.12.0` in `manifest.json` `requirements` and in `pyproject.toml`. Run
`uv lock --upgrade-package pynortecgo`, then `uv sync`.
Check: `uv run python -c "import importlib.metadata as m; print(m.version('pynortecgo'))"` prints `0.12.0`,
and `git diff --stat uv.lock` shows only the `pynortecgo` entry changed (apart from what 0.12.0 needs).

- [ ] **Step 2: Run the whole suite on 0.12.0, unchanged**

Run: `uv run pytest -q`
Expected: PASS. 0.12.0 only adds optional keywords, so nothing should break. If anything fails, stop and
report it.

- [ ] **Step 3: Commit the bump**

```bash
git add custom_components/nortec_go/manifest.json pyproject.toml uv.lock
git commit -F /tmp/grid-tariff-task-1-msg-1.txt   # "fix: pynortecgo 0.12.0 (#130)"
```

- [ ] **Step 4: Write the failing store tests** in `tests/test_grid_tariff.py`

Add to `tests/conftest.py`, next to the other fakes:

```python
# Opaque to the integration: a made-up dict, not the client's format.
FAKE_GRID_TARIFF: dict[str, Any] = {
    "version": 1,
    "label": "made-up",
    "records": [{"p": [0.1, 0.2]}],
}
```

Tests (`KEY = "nortec_go.entry1.grid_tariff"`):

```text
async def test_store_round_trip(hass, hass_storage):
    store = GridTariffStore(hass, "entry1")
    await store.async_save(FAKE_GRID_TARIFF)
    assert hass_storage[KEY]["version"] == 1
    assert hass_storage[KEY]["data"] == FAKE_GRID_TARIFF
    assert await GridTariffStore(hass, "entry1").async_load() == FAKE_GRID_TARIFF
    await store.async_remove()
    assert KEY not in hass_storage

async def test_store_missing_file(hass):
    assert await GridTariffStore(hass, "entry1").async_load() is None

@pytest.mark.parametrize("data", [[1, 2], "text", 5])
async def test_store_wrong_shape(hass, hass_storage, data, caplog):
    hass_storage[KEY] = {"version": 1, "minor_version": 1, "key": KEY, "data": data}
    assert await GridTariffStore(hass, "entry1").async_load() is None
    assert "stored grid tariff" in caplog.text
```

- [ ] **Step 5: Run them to see them fail**

Run: `uv run pytest tests/test_grid_tariff.py -q`
Expected: FAIL (`ModuleNotFoundError` for `custom_components.nortec_go.grid_tariff`).

- [ ] **Step 6: Add the constants and `GridTariffStore`**

The constants go in `const.py`, next to the other store keys. `grid_tariff.py` follows `energy.py`'s
`EnergyStore`: a plain `Store` (no migration), and a module docstring saying it keeps the client's dict
unchanged (D53).
- `async_load`: returns the stored data when it is a `dict`, and `None` when there is no file. Any other
  data returns `None` and logs, with `_LOGGER.warning`, exactly
  `"Ignoring the stored grid tariff: it has an unexpected shape"`. At runtime the stored data can be any
  JSON, whatever the `Store` type says.
- `async_save`: `Store.async_save(dict(tariff))`, at once, not a delayed save.
- `async_remove`: `Store.async_remove()`.

- [ ] **Step 7: Run the store tests**

Run: `uv run pytest tests/test_grid_tariff.py -q`
Expected: PASS.

- [ ] **Step 8: Update the `create_client` tests**

In `tests/test_entry.py`:
- `test_create_client` also passes `grid_tariff=FAKE_GRID_TARIFF` and `on_grid_tariff=tariff_callback` (a
  second `AsyncMock`), and the `assert_called_once_with` adds `grid_tariff=FAKE_GRID_TARIFF,
  on_grid_tariff=tariff_callback`;
- `test_create_client_defaults`'s `assert_called_once_with` adds `grid_tariff=None, on_grid_tariff=None`.

Run: `uv run pytest tests/test_entry.py -q`. Expected: FAIL (`create_client` takes no `grid_tariff`).

- [ ] **Step 9: Add the two keywords to `create_client`**

Signature as in *Interfaces*, both passed straight through to `NortecGoClient`. Import `Mapping` and
`Callable`/`Awaitable` from `collections.abc`; nothing from `pynortecgo._*`. The docstring stays one line.

Run: `uv run pytest tests/test_entry.py -q`. Expected: PASS.

- [ ] **Step 10: Write the failing setup and removal tests** in `tests/test_init.py`

`GRID_TARIFF_KEY = "nortec_go.{entry_id}.grid_tariff"`, formatted with `mock_config_entry.entry_id`.

- In `test_setup_entry`, add: `assert kwargs["grid_tariff"] is None` and
  `assert kwargs["on_grid_tariff"] is not None`.
- New tests:

```text
async def test_setup_passes_the_stored_grid_tariff(hass, mock_config_entry, mock_client_class, hass_storage):
    # hass_storage[key] = {"version": 1, "minor_version": 1, "key": key, "data": FAKE_GRID_TARIFF}
    await setup_integration(hass, mock_config_entry)
    assert mock_client_class.call_args.kwargs["grid_tariff"] == FAKE_GRID_TARIFF

async def test_grid_tariff_from_the_client_is_stored(hass, mock_config_entry, mock_client_class, hass_storage):
    await setup_integration(hass, mock_config_entry)
    await mock_client_class.call_args.kwargs["on_grid_tariff"](FAKE_GRID_TARIFF)
    await hass.async_block_till_done()
    assert hass_storage[key]["data"] == FAKE_GRID_TARIFF
    assert mock_client_class.call_count == 1   # no reload

async def test_reload_hands_back_the_saved_grid_tariff(hass, mock_config_entry, mock_client_class):
    await setup_integration(hass, mock_config_entry)
    await mock_client_class.call_args.kwargs["on_grid_tariff"](FAKE_GRID_TARIFF)
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_client_class.call_count == 2
    assert mock_client_class.call_args.kwargs["grid_tariff"] == FAKE_GRID_TARIFF

async def test_remove_entry_removes_the_stored_grid_tariff(hass, mock_config_entry, mock_client, hass_storage):
    # pre-fill hass_storage[key] as in the first test
    await setup_integration(hass, mock_config_entry)
    assert await hass.config_entries.async_remove(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage
```

Run: `uv run pytest tests/test_init.py -q`. Expected: the new tests and `test_setup_entry` FAIL.

- [ ] **Step 11: Load, pass, save and remove in `__init__.py`**

- In `async_setup_entry`, before `create_client`: `grid_tariff_store = GridTariffStore(hass, entry.entry_id)`
  and `grid_tariff = await grid_tariff_store.async_load()`.
- A local `async def _async_store_grid_tariff(tariff: dict[str, Any]) -> None` that awaits
  `grid_tariff_store.async_save(tariff)`, with the comment
  `# Runs inside the client's price forecast: must not call the client.`
- Pass `grid_tariff=grid_tariff, on_grid_tariff=_async_store_grid_tariff` to `create_client`.
- In `async_remove_entry`, add `await GridTariffStore(hass, entry.entry_id).async_remove()` after the
  energy store. The docstring becomes: `"""Delete the entry's stored prices, energy ledger, grid tariff and
  charge control, and its repair issues."""`

Run: `uv run pytest tests/test_init.py -q`. Expected: PASS.

- [ ] **Step 12: Run every gate, including coverage**

Run the three gate lines in *Global Constraints*.
Expected: all pass; coverage ≥ 95%, and `grid_tariff.py` fully covered.

- [ ] **Step 13: Commit**

```bash
git add custom_components/nortec_go/const.py custom_components/nortec_go/grid_tariff.py \
  custom_components/nortec_go/entry.py custom_components/nortec_go/__init__.py \
  tests/conftest.py tests/test_grid_tariff.py tests/test_entry.py tests/test_init.py
git commit -F /tmp/grid-tariff-task-1-msg-2.txt   # "fix: keep the grid tariff across restarts (#130)"
```

---

### Task 2: User docs, changelog and D53

**Model:** opus. Every docs task is (§5, D33).
**Wave:** 2

**Files:**
- Modify: `docs/user/nortec_go.md` (*Data updates*, the Energi Data Service paragraph, lines 223–230)
- Modify: `CHANGELOG.md` (*Unreleased*)
- Modify: `docs/decisions.md` (append D53)

**Interfaces:**
- Consumes: Task 1's landed code. The names the docs use are behaviour, not code names; check them against
  `grid_tariff.py` and `__init__.py`.
- Produces: nothing other tasks use.

- [ ] **Step 1: Rewrite the Energi Data Service paragraph**

Cover every bullet of the spec's *User docs* section, in the doc's own plain style (no code names, no
`pynortecgo` internals). Keep the host name, what the requests hold, and the several-megabytes note.
Keep "a tariff already found or stored is used without waiting" next to "while it still fits the
charger's own prices", so the condition isn't lost. It may become two paragraphs.

- [ ] **Step 2: Re-check the other two sections**

Read *Known limitations* (the estimate bullet) and *Troubleshooting* → *Warnings about the grid tariff or
DataHub in the log* against the new paragraph. The spec expects no change. Change only a sentence that is
no longer true, and say which in the report.
Check: `git grep -n -i "two requests" -- docs/user` prints nothing.

- [ ] **Step 3: Add the changelog entry**

Under `## [Unreleased]`, add `### Fixed` with the entry from the spec's *CHANGELOG entry* section, word for
word.

- [ ] **Step 4: Append D53 to `docs/decisions.md`**

In the §7 format: `### D53: The grid tariff is stored as the client hands it over`, then
`- **Date:** 2026-11-16 · **Status:** active`, then the spec's D53 *Decision* and *Why* bullets, and
`- **Source:** [spec](superpowers/specs/2026-11-16-grid-tariff-store-design.md) (*The store*)`.

- [ ] **Step 5: Run the gates and commit**

Run the gate lines in *Global Constraints* (the pre-commit hooks also check the Markdown).

```bash
git add docs/user/nortec_go.md CHANGELOG.md docs/decisions.md
git commit -F /tmp/grid-tariff-task-2-msg-1.txt   # "docs: the stored grid tariff, changelog and D53 (#130)"
```
