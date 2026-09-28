# pynortecgo 0.5.0: total price and the forecast's currency — design

Date: 2026-09-28 · Branch: `feat/pynortecgo-0.5.0` · Issues: #33, #20

## Goal

- **What:**
  - #33: bump `pynortecgo` from 0.2.0 to 0.5.0 (the issue named 0.4.0; the owner widened it to 0.5.0, the
    latest on PyPI, checked 2026-09-28), and choose the total or the spot price.
  - #20: the price sensor's unit comes from the forecast's currency.
- **Why:** the client's later releases give the total price (what the owner pays, with the grid tariff
  that decides which slots are cheapest), the prices' currency, a state for a charge the car paused, and
  the open charge's energy and power that #24 needs.
- **Not in this work:** the energy and power sensors (#24; its own PR on top of this one, under D25);
  `PriceSlot.spot_price` and `PriceSlot.tariff_estimated` (not used); a repair issue when the forecast's
  currency differs from Home Assistant's (#20 asked to consider it: with the unit from the forecast
  nothing is wrong to repair).
- **Done when:** built TDD with `pynortecgo` mocked in every test; the gates pass; `scripts/smoke` passes;
  user docs, changelog and decision log updated.

## Decisions

Answered by the owner in the brainstorm (2026-09-28), unless marked *controller*.

| Topic | Decision |
|---|---|
| Target version | 0.5.0 |
| Process | This bump gets the full flow; #24 follows under D25 (short design in chat, no spec or plan) |
| Which price | The total price per kWh incl. VAT (`PriceSlot.price` since 0.3.0), for the *Current price* sensor and EV Smart Charging's `prices_today` / `prices_tomorrow` |
| Currency | In this work (#20): the unit is `<forecast currency>/kWh`, falling back to Home Assistant's currency while none is known |
| Stored spot prices | *Controller.* The price store goes to version 2; the migration from version 1 drops the stored slots rather than mixing spot and total prices in one day |
| Last known currency | *Controller.* Kept across a forecast whose `currency` is `None`, and stored with the slots, so a failed price read at startup still has it |
| Extra request while charging | *Controller.* Accepted, no change: `get_charger()` makes a second request while a charge is open (0.5.0), so two requests per read, 4 a minute at the 30 s reads while starting or stopping |

Facts used, public-safe:

- `pynortecgo` changelog and public models, 0.3.0 to 0.5.0:
  - 0.3.0: `PriceSlot.price` is the total (spot + fixed fees + grid tariff); the spot price is
    `PriceSlot.spot_price` (a `float`, never `None`); `PriceSlot.tariff_estimated` is new; the new required
    `PriceForecast.currency` is an ISO 4217 code or `None`; `get_price_forecast()` takes no arguments.
  - 0.4.0: the client remembers exact grid tariffs per weekday and hour and uses them for estimates; the
    memory lives in the client, which the integration keeps per entry.
  - 0.4.2: `ChargerState.BUSY_NON_CHARGING`, seen while the car paused an open charge (its `charge_state`
    was `PAUSED`); before, it came as `ChargerState.UNKNOWN`. `start_charge()` treats it as a charge in
    progress (`ChargeAlreadyActiveError`).
  - 0.5.0: the new required fields `Charger.charge_kwh` and `Charger.charge_kw`, `None` without an open
    charge.
- The bump checklist (`docs/releasing.md`), run against the client's source from 0.2.0 to 0.5.0:
  - No new exception classes and no new exports; the new raises are `AuthError` and
    `UnexpectedResponseError`, which the integration already handles.
  - The new messages name endpoint templates and field names only; no email, password, token, IDs or
    request bodies.
- Home Assistant's `Store` (installed source): loading data of an older version calls
  `_async_migrate_func`; without an override that raises `NotImplementedError`.

## 1. Files

| File | Change |
|---|---|
| `manifest.json`, `pyproject.toml`, `uv.lock` | `pynortecgo==0.5.0` |
| `charge_control.py` | `BUSY_NON_CHARGING` in `charge_is_open` (§2) |
| `prices.py` | total price, the currency, the store's version 2 (§3, §4) |
| `coordinator.py` | keeps and saves `price_currency` (§4) |
| `sensor.py` | the price sensor's unit (§4) |
| `const.py` | `PRICE_STORE_VERSION = 2` |
| `tests/` | fixtures and tests (§5) |
| `CHANGELOG.md`, `docs/user/nortec_go.md`, `docs/decisions.md` | §6 |

## 2. A charge the car paused

- `charge_is_open` matches the client's test for a charge in progress again: `charge_state` is not `None`,
  or the state is `BUSY`, `BUSY_CHARGING` or `BUSY_NON_CHARGING`.
- Effects, all through `charge_is_open` and `_charge_happened`:
  - *Charge status* shows `paused` for a charge the car paused (the charge's `PAUSED` state), where the old
    client's `UNKNOWN` state showed unknown.
  - Turning *Charge* on then is a no-op (a charge is open), where it was refused with "charger state
    unknown". No start is sent either way.
  - A pending start ends, a pending stop request is sent, and a start block clears on that state, as for
    the other busy states.
- Nothing in the charge control relies on a car-paused charge arriving as `UNKNOWN`: the paths that
  remember a state (`_remembered`) look only at `BUSY_NON_RELEASED` and `AVAILABLE`.

## 3. Total price

- `merge_forecast` stores `slot.price`, which is the total since 0.3.0. The rest of `prices.py` is unchanged.
- Estimated grid tariffs go in as they come; each read overwrites them with newer values, as for any slot.

## 4. Currency and the price store

- **Coordinator:** `price_currency: str | None`, loaded with the slots. A forecast with a `currency` sets
  it; one with `None` keeps the last known one. It is saved with the slots after each successful read.
- **Price sensor:** `native_unit_of_measurement` becomes a property: `f"{currency}/kWh"`, where currency is
  `coordinator.price_currency`, or `hass.config.currency` while that is `None`. So a change of Home
  Assistant's currency also shows without a reload (#20's note).
  - Accepted: if the unit changes while the sensor has long-term statistics (the fallback differed from
    the forecast's currency), Home Assistant raises its own unit-change repair. For DK2 both are `DKK`.
- **Store version 2:** `{"currency": str | None, "slots": [{"start": …, "price": …}]}`.
  - `PriceStore` loads to a small result type holding the slots and the currency, and saves both.
  - The migration from version 1 returns `{"currency": None, "slots": []}`: the stored spot prices are
    dropped. Setup reads the forecast right after loading, so every slot from now on is refilled with
    total prices. Only today's past slots are lost; EV Smart Charging's list pads them with
    `PAST_SLOT_PRICE`, as for any past gap.
  - A wrong shape (a missing key, a wrong type, a start without a time zone, a currency that isn't a
    string or `None`) is ignored with the existing warning, giving no slots and no currency.

## 5. Tests

TDD, `pynortecgo` mocked, fixtures built from `pynortecgo` model objects (hard rule 7).

- **Fixtures:** `make_charger` sets `charge_kwh` and `charge_kw` to `None`. `make_forecast` takes a
  `currency` (default `"DKK"`) and builds slots with `spot_price` (a value below `price`) and
  `tariff_estimated=False`.
- **Charge control:** `BUSY_NON_CHARGING` rows in the `charge_is_open` and *Charge status* tables
  (`PAUSED` charge state gives `paused`); turning *Charge* on with `BUSY_NON_CHARGING` sends no start.
- **Prices:** the merged slot holds `price`, not `spot_price`.
- **Currency:** the unit follows the forecast's currency; a `None` currency keeps the last one; with none
  known the unit is Home Assistant's currency; the currency survives a reload with a failing price read.
- **Store:** a version 1 file migrates to no slots and no currency; version 2 round trip; each wrong shape
  from §4.

## 6. Docs, changelog and decision log

- **`CHANGELOG.md`** (*Unreleased*):
  - *Changed:* prices are the total price per kWh (spot, fees and grid tariff); the price unit comes from
    the price data's currency; the prices stored by an earlier version are dropped once on upgrade, so
    today's earlier slots show as 0 until tomorrow.
  - *Fixed:* a charge the car paused shows *Charge status* `paused` instead of unknown.
- **`docs/user/nortec_go.md`:**
  - The *Current price* row says the total price (spot, fees and grid tariff) incl. VAT.
  - Known limitations: remove the two on the spot price and on Home Assistant's currency; add that the grid
    tariff is estimated for the hours beyond those the charger prices itself, and that the price is
    checked only for DK2 (DKK).
- **`quality_scale.yaml`:** no rule changes status.
- **`docs/decisions.md`:** D34 below.

```markdown
### D34: The total price, in the forecast's currency
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** The price sensor and EV Smart Charging's lists use the total price per kWh incl. VAT (spot, fees and grid tariff); the unit is the forecast's currency per kWh, falling back to Home Assistant's currency.
- **Why:** the total is what the owner pays, and the hourly grid tariff changes which slots are cheapest.
- **Source:** [spec](superpowers/specs/2026-09-28-pynortecgo-0.5.0-design.md) (Decisions)
```

## 7. Verification

- The gates in `CLAUDE.md` → Commands, including the coverage gate.
- `scripts/smoke` on the branch before the PR is marked ready: the version 1 store in the owner's dev
  config migrates without an error.
- After merge: #24 gets a comment that 0.5.0 unblocks it, with a measured power (`charge_kw`) instead of an
  average between reads.
