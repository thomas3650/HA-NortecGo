# Keep the grid tariff across restarts with pynortecgo 0.12.0 — design

Date: 2026-11-16 · Branch: `fix/grid-tariff-store` · Issue: #130

## Goal

- **What:** raise the client to `pynortecgo==0.12.0`. Store the grid tariff it finds and hand it back to the
  client at the next setup.
- **Why:** since about 2026-11-07 every price read logs `Grid tariffs from DataHub unavailable (HTTP 429)`.
  Energi Data Service now allows about one request a minute, and pynortecgo 0.11.0 sends its two search
  requests back to back. So the grid tariff for every hour beyond the charger's own price chart has been
  estimated. Charge plans built on the forecast then pick the wrong hours.
  - 0.12.0 makes at most one request per forecast, spaced as the service asks, and keeps the search's progress
    between reads.
  - It adds two `NortecGoClient` keywords. `grid_tariff` is a dict that `on_grid_tariff` handed over earlier,
    passed back unchanged. `on_grid_tariff` is an async callback, `(tariff: dict[str, Any]) -> None`, that
    runs when the client finds a new tariff.
  - With a stored tariff, a restart or reload needs no request while the tariff still fits the charger's
    own prices and covers the forecast.
- **Not in this work:**
  - the forecast's maths and the estimate;
  - the polling times;
  - any entity, option, flow step or translation;
  - diagnostics (see *Decisions*);
  - anything near charge start or stop.
- **Done when:**
  - the gates and `scripts/smoke` pass;
  - the pins, store, setup, removal, docs and changelog below are in place;
  - the *Bumping `pynortecgo`* checklist in `releasing.md` has been worked through and its results are in
    the PR description;
  - the bump step has run;
  - the PR says `Closes #130`.

## What changes

| Where | Change | Why |
|---|---|---|
| `manifest.json` `requirements`, `pyproject.toml` | `pynortecgo==0.12.0`; `uv lock --upgrade-package pynortecgo` | Ends the 429s (`releasing.md` → *Bumping `pynortecgo`*) |
| `const.py` | `GRID_TARIFF_STORE_VERSION: Final = 1`, `GRID_TARIFF_STORE_KEY: Final = "nortec_go.{entry_id}.grid_tariff"` | Next to the other store keys |
| new `grid_tariff.py` | `GridTariffStore(hass, entry_id)` over a plain `Store[dict[str, Any]]`, with `async_load() -> dict[str, Any] \| None`, `async_save(tariff)` and `async_remove()` | One module per store, as `prices.py` and `energy.py` have |
| `entry.py` `create_client` | Two new keyword arguments, passed through to `NortecGoClient`: `grid_tariff: Mapping[str, Any] \| None = None` (the client's own type) and `on_grid_tariff: Callable[[dict[str, Any]], Awaitable[None]] \| None = None`. Both are typed here: the client's `GridTariffCallback` alias isn't in `pynortecgo.__all__`, and nothing is imported from its private modules | The config flow's sign-in clients keep calling it without them |
| `__init__.py` `async_setup_entry` | Before the client is built: load the store. Pass the result as `grid_tariff`, and a local `_async_store_grid_tariff` that saves the dict as `on_grid_tariff` | The client needs the tariff when it is built |
| `__init__.py` `async_remove_entry` | Also `await GridTariffStore(hass, entry.entry_id).async_remove()`; the docstring names the grid tariff | Nothing stays behind when the entry is deleted |
| `docs/user/nortec_go.md` | See *User docs* | Same PR as the code |
| `CHANGELOG.md` | See *CHANGELOG entry* | User-visible fix |
| `docs/decisions.md` | D53, below *Decisions* | A new store with a lasting rule, as the energy store got D47 |
| `quality_scale.yaml` | No change: no rule is completed or affected | CLAUDE.md asks it to be checked in the same PR |

### The store

- The integration stores the dict exactly as the client handed it over: no wrapper, no parsing, no own checks.
  The dict carries its own version, and the client ignores a stored dict it can't read and searches again,
  without raising. So the store needs no migration of its own while it stays at version 1.
- `async_load` returns the stored dict, or `None` when there is no file or the data isn't a dict. The client
  takes `None` as "nothing stored". Data that isn't a dict logs a warning, "Ignoring the stored grid tariff:
  it has an unexpected shape", as `PriceStore` and `EnergyStore` do. A dict the client can't read is the
  client's to log (at debug), and then it searches again.
- `async_save` writes at once (`Store.async_save`, not a delayed save). The callback runs seldom, only when
  the client finds a new tariff, and a delayed save could be lost on a crash. When the client finds a newer
  tariff, it replaces the stored one.
- The callback runs inside a forecast, so it must not call the client. A comment says so, as
  `_async_store_tokens` has.
- A failed write is already caught and logged by Home Assistant's `Store`, and the client catches any
  `Exception` from the callback and keeps using the tariff. So a failed save can't break a price read, and
  the integration adds no handling of its own.

## User docs

In *Data updates*, the paragraph on Energi Data Service (today `docs/user/nortec_go.md:223-230`) changes. It
no longer says "two requests at its first price read", and its sentence on when they are made again is
replaced. It should say that:

- the integration makes at most one request there per price read, at least a minute apart, and longer if
  the service asks it to wait. A price read that comes sooner makes no request; the hours beyond the
  charger's own prices are then estimated for that read;
- finding the tariff takes two requests. With no stored tariff it is found at the second price read after
  the integration starts. That can be hours later (the reads at 00:05, 05:05, 10:05, 15:05 and 20:05), or
  sooner with a *Refresh* press more than a minute after the start. Until then those hours are estimated;
- the tariff it finds is stored with the integration's other data;
- after a restart or a reload, the stored tariff is used with no request, while it still fits the charger's
  own prices and covers the forecast;
- when the stored tariff ends before the forecast does, one request per start looks for a newer one. A
  network or HTTP failure doesn't use that request up: the next price read tries again;
- after a failed request, the next price read tries again, with one request;
- a new search starts when the charger's tariff changes, or when the stored tariff no longer fits the
  charger's own prices. The tariff it then finds is stored in place of the old one.

What the requests hold and the several-megabytes note stay.

*Known limitations* (`nortec_go.md:253-255`, estimates start over after a restart or reload) and the
*Troubleshooting* entry on DataHub warnings (`:351-357`) were checked against the 0.12.0 wheel and stay
true: no change expected. The branch review re-checks them against the landed text.

## CHANGELOG entry

Under `## [Unreleased]`, `### Fixed`:

- `pynortecgo` 0.12.0. The grid tariff from your grid company is used again for the hours beyond those the
  charger prices itself. Energi Data Service started limiting requests, so it had been estimated since about
  7 November. The tariff the integration finds is now stored, so a restart of Home Assistant or a reload of
  the integration doesn't need to fetch it again.

## Decisions

| Topic | Decision |
|---|---|
| Title | `fix: keep your grid company's tariff across restarts with pynortecgo 0.12.0 (#130)`. A patch release, with the changelog entry and the bump step |
| Diagnostics | Unchanged. The dict is public grid tariff data (a grid company's published prices, DataHub's grid company IDs, and the charger's tariff label and VAT flag), with nothing that identifies the user, and it isn't needed to debug the integration's own reads |
| Store shape | The client's dict, unchanged (see *The store*) |
| Renovate | If Renovate opens its own 0.12.0 PR, it closes it once the version is on `main` (`releasing.md`). Nothing is pushed to it |
| Merge | The owner merges, or tells the controller to (way-of-working §6 *Merging when told*) |

### D53 (for `docs/decisions.md`)

- **Decision:** the grid tariff the client finds is kept per entry in its own store
  (`nortec_go.{entry_id}.grid_tariff`), exactly as the client hands it over, with no parsing, checks or
  migration of the integration's own. It is handed back to the client at setup, deleted with the entry, and
  left out of diagnostics.
- **Why:** the dict is the client's format, versioned and checked by the client, which ignores one it can't
  read. Owning a copy of that format here would duplicate the client and break when it changes.
- **Source:** this spec, *The store*.

## Client bump checklist (`releasing.md` → *Bumping `pynortecgo`*)

Already checked against the 0.12.0 wheel while writing this spec. The PR re-states the results.

- **Public API and models:** `__all__`, the model fields and the enums are unchanged from 0.11.0. The only
  signature change is the two new optional `NortecGoClient` keywords. This also covers the checklist's
  "breaking changes to the models" item: there are none.
- **New exceptions:** none. The DataHub path still never raises.
- **Log and exception text:** the new messages hold an HTTP status, a wait in seconds, an exception type name,
  or a grid company ID and tariff code. None of them holds an email, password, token, device ID or request
  body.
- **Diagnostics pin test:** expected to pass; it runs with the gates.

## Testing

`pynortecgo` is mocked, as everywhere (hard rule 2). Store contents come from `hass_storage`. The tariff dict in
tests is a made-up dict: the integration treats it as opaque, so it doesn't need to look like the client's
format (hard rule 7 covers model objects, and this is not one).

- `GridTariffStore`: load with no file gives `None`; a saved dict loads back equal; data that isn't a dict
  gives `None`; remove deletes the file.
- Setup: with a stored tariff, `NortecGoClient` is built with that dict as `grid_tariff`. With none stored,
  it gets `grid_tariff=None`. Both cases pass an `on_grid_tariff` callback.
- The callback: calling the `on_grid_tariff` given to the client writes the dict to the store.
- Removal: `async_remove_entry` deletes the grid tariff file along with the others.
- `create_client` called without the new arguments passes `None` for both (the config flow's sign-in
  clients).
- Existing tests that change: `test_create_client` and `test_create_client_defaults` in
  `tests/test_entry.py` assert the exact `NortecGoClient` call, so they get the two new keywords. Setup
  asserts in `tests/test_init.py` that check `create_client`'s or the client's arguments are updated the
  same way.
- Order: `mock_client_class` (`tests/conftest.py`) patches the client with `autospec=True`, so a call with
  `grid_tariff=` raises `TypeError` against 0.11.0. The pin and lock bump (and `uv sync`) comes before, or
  in the same task as, the code and tests that use the new keywords.
- The coverage gate stays at 95% or more.
