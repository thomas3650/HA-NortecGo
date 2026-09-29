# Diagnostics with redaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** A config entry diagnostics download that shows what the integration last read and how its reads are going, with only the sign-in secrets (email, password, access and refresh tokens, the client's device ID) redacted, and the docs and hard rule 5 brought in line (D38).

**Architecture:** Task 1 adds `diagnostics.py`, three read-only coordinator properties it needs, the tests, and `diagnostics: done`. Task 2 writes the docs: hard rule 5, D38, the release checklist, the user docs, the manual-testing checklist, the bug template and the changelog. Both run in wave 1, on disjoint files; Task 2 is written against the names this plan fixes.

**Tech Stack:** Python 3.14, Home Assistant custom integration (`homeassistant.components.diagnostics`), `pynortecgo` 0.5.0 (always mocked in tests), pytest with `pytest-homeassistant-custom-component` and freezegun, uv.

**Spec:** `docs/superpowers/specs/2026-09-29-diagnostics-design.md` (issue #11).

## Global Constraints

- TDD: write the failing test, see it fail, then write the code. Tests always mock `pynortecgo`, and fixtures come from `pynortecgo` model objects and the `tests/conftest.py` helpers, never raw API JSON (hard rules 2, 7).
- Nothing private (hard rule 3): no real IDs, tokens, emails, captures, raw endpoints, response shapes, or links into the private client repo. Only the fake values in `tests/conftest.py`.
- Redacted, exactly: `TO_REDACT = {CONF_ACCESS_TOKEN, CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD, CONF_REFRESH_TOKEN}` (`CONF_REFRESH_TOKEN` from `const.py`, the rest from `homeassistant.const`), applied with `async_redact_data` to the whole output, loaded or not. Everything else is kept: the charger's and car's `id` and `name`, `charge_id`, the entry's title and unique ID, brand, model, `expires_at`, the `*_raw` fields.
- Never read `.env`, `local/` or `config/` (hard rule 9). Never start or stop a real charge.
- Gates before every commit (`CLAUDE.md` → Commands): `uv run pytest -q`, then `uv run ruff check && uv run ruff format --check && uv run mypy`. The coverage gate (`--cov-fail-under=95`) passes at the end of each task.
- Subagents write commit messages with the Write tool to a file outside the repo (for example `/tmp/diagnostics-task-<n>-msg.txt`), and commit with `git commit -F <file>` (no heredocs). End each message with the co-author trailer given in the dispatch.
- Match the surrounding code: one-line docstrings ending in a period, comment density, names.
- Decision number: D38. Hard rule 5's new wording is the owner-approved text in Task 2, word for word.

## Rulings (after merging `origin/main` with #60 into the branch)

Three places where the spec differs from the code; the plan follows the code. 1 and 2 come from #60 (exception translations, #37), which merged before this plan; 3 was in the code already.

1. The coordinator comment that spec §6 rewrites ("pynortecgo's messages hold no tokens, emails or IDs …") is gone: #60 replaced it. No `coordinator.py` comment change.
2. `last_exception` and the entry's `reason` now hold the integration's own translated texts (for example "Can't reach the Nortec Go service. Home Assistant will try again"), not `pynortecgo`'s messages. So spec test 5's setup retry expects that text as the reason, not `None`; the setup error expects the *charger not found* text. The same makes stale: spec *Facts used* and §2 *Messages* (that these fields may hold `pynortecgo` messages, that `reason` is `None` in `setup_retry`, that setup errors use `ConfigEntryError(str(err))`), and spec §8's "expected error messages come from fake exception strings": the tests assert the integration's own `strings.json` texts, as `tests/test_coordinator.py` does. Hard rule 3 holds: these are our own public texts.
3. An open charge clears a start block (`charge_control.py`, `on_charger_read`), so spec test 2's "a charge open and starts blocked" can't be one state. Test 2 downloads twice: once while blocked (the repair issue is in the download), once after a read that sees a charge open (the charge ID is in the download).

## Review Focus

1. The entry is unloaded (a reload in progress, or disabled): the download still works and shows `"state": "not_loaded"`, no error (Task 1, `test_unloaded_entry`).
2. Reads recover after a failure: `last_exception` shows `None`, not the old error, which HA keeps (Task 1, `test_failing_reads`).
3. No known prices (an empty forecast): the summary is 0 slots and `None` starts, and the download still serializes (Task 1, `test_no_car_and_no_prices`).
4. A password stored by a later bug never reaches the download (Task 1, `test_secrets_never_appear`).
5. A download requested while the clock was moved in a test: fetched with a fresh token, never a 401 (Task 1, the `_download_text` helper used by every test).

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (code and tests), Task 2 (docs) | Disjoint files, two worktrees off the feature branch. Task 2 is written against this plan's names and re-checked against the code that lands |

No task has guarded files.

---

### Task 1: The diagnostics platform

**Model:** opus — it handles the tokens and the redaction list.
**Wave:** 1

**Files:**
- Create: `custom_components/nortec_go/diagnostics.py`
- Modify: `custom_components/nortec_go/coordinator.py` (three properties)
- Modify: `custom_components/nortec_go/quality_scale.yaml` (`diagnostics: todo` → `diagnostics: done`)
- Test: `tests/test_diagnostics.py` (new)

**Interfaces:**
- Consumes: `NortecGoCoordinator` (`coordinator.py`) with `data: NortecGoData` (`read_at`, `charger`, `vehicle`, `control`), `last_update_success`, `last_exception`, `update_interval`, `has_car`, `known_prices: dict[datetime, float]`, `price_currency: str | None`; `NortecGoConfigEntry` (`entry.py`); `CONF_REFRESH_TOKEN` (`const.py`).
- Produces:
  - `NortecGoCoordinator.car_read_failing -> bool`, `.price_read_failing -> bool`, `.price_retry_pending -> bool` (read-only properties).
  - `custom_components/nortec_go/diagnostics.py`: `TO_REDACT: Final` (a `set[str]`) and `async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: NortecGoConfigEntry) -> dict[str, Any]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_diagnostics.py`:

```python
"""Tests for the Nortec Go diagnostics: only the sign-in secrets are redacted (D38)."""

from dataclasses import fields
from datetime import UTC, datetime
from http import HTTPStatus
import json
from typing import Any
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pynortecgo import (
    Charger,
    ChargerNotFoundError,
    ChargerState,
    ChargeState,
    NortecGoConnectionError,
    Vehicle,
    VehicleNotFoundError,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    CLIENT_ID,
    MockConfigEntry,
    MockUser,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.nortec_go.const import DOMAIN
from custom_components.nortec_go.entry import tokens_to_data

from .conftest import (
    DEFAULT_FORECAST_START,
    FAKE_CHARGER_ID,
    FAKE_CHARGER_NAME,
    FAKE_DEVICE_ID,
    FAKE_EMAIL,
    FAKE_PASSWORD,
    FAKE_TOKENS,
    FAKE_VEHICLE_NAME,
    NEW_TOKENS,
    make_charger,
    make_forecast,
    setup_integration,
)

# 2026-09-27 12:00 local (CEST): conftest's forecast slots (2026-09-27 00:00 to 02:00 local) are
# today's, and a price retry at 12:15 comes before the 15:05 read.
NOON = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
REDACTED = "**REDACTED**"
FAKE_CHARGE_ID = "fake-charge-id"  # make_charger's charge ID while a charge is open
# strings.json exceptions, without the final period (HA strips it).
CANNOT_CONNECT = "Can't reach the Nortec Go service. Home Assistant will try again"
CHARGER_NOT_FOUND = (
    "The charger is no longer on the Nortec Go account. "
    "Remove the integration and add it again"
)
SECRETS = (
    FAKE_EMAIL,
    FAKE_PASSWORD,
    FAKE_DEVICE_ID,
    FAKE_TOKENS.access_token,
    FAKE_TOKENS.refresh_token,
    NEW_TOKENS.access_token,
    NEW_TOKENS.refresh_token,
)
ENTRY = {
    "title": FAKE_CHARGER_NAME,
    "unique_id": str(FAKE_CHARGER_ID),
    "data": {
        "email": REDACTED,
        "device_id": REDACTED,
        "access_token": REDACTED,
        "refresh_token": REDACTED,
        "expires_at": "2030-01-01T12:00:00+00:00",
    },
    "options": {},
}
# The pynortecgo fields the download shows. A client bump that changes them fails
# test_client_model_fields_are_pinned: decide for each new field whether it is a secret (D38).
CHARGER_FIELDS = {
    "id",
    "name",
    "max_kw",
    "state",
    "state_raw",
    "is_connected",
    "charge_state",
    "charge_state_raw",
    "charge_id",
    "can_stop",
    "charge_kwh",
    "charge_kw",
}
VEHICLE_FIELDS = {
    "id",
    "name",
    "capacity_kwh",
    "max_kw_ac",
    "brand",
    "model",
    "battery_level",
    "charge_limit",
    "plugged_in",
    "power_delivery_state",
    "power_delivery_state_raw",
    "last_seen",
}


@pytest.fixture(autouse=True)
async def copenhagen(hass: HomeAssistant) -> None:
    """Run every test in the owner's time zone."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")


async def _download_text(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    user: MockUser,
    entry: MockConfigEntry,
) -> str:
    """The whole download as text, fetched with a token made now.

    hass_client's own token is made at fixture setup, and a clock moved before its issue
    time, or more than 30 minutes past it, gets a 401.
    """
    assert await async_setup_component(hass, "diagnostics", {})
    refresh_token = await hass.auth.async_create_refresh_token(user, CLIENT_ID)
    client = await hass_client(hass.auth.async_create_access_token(refresh_token))
    response = await client.get(f"/api/diagnostics/config_entry/{entry.entry_id}")
    assert response.status == HTTPStatus.OK
    text: str = await response.text()
    return text


async def _download(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    user: MockUser,
    entry: MockConfigEntry,
) -> dict[str, Any]:
    """The integration's part of the download."""
    body = json.loads(await _download_text(hass, hass_client, user, entry))
    data: dict[str, Any] = body["data"]
    return data


def _blocked(hass_storage: dict[str, Any], entry: MockConfigEntry) -> None:
    """Store a start block for the entry, as a failed start leaves it."""
    key = f"nortec_go.{entry.entry_id}.charge_control"
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": "2026-09-26T20:00:00+00:00",
            "start_pending_since": None,
            "stop_asked": False,
        },
    }


async def test_diagnostics_output(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The whole output: the four stored secrets redacted, everything else kept (D38)."""
    freezer.move_to(NOON)
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        state=ChargerState.BUSY_CHARGING,
        charge_state=ChargeState.CHARGING,
        charge_kwh=4.2,
        charge_kw=7.1,
    )
    await setup_integration(hass, mock_config_entry)

    assert await _download(hass, hass_client, hass_admin_user, mock_config_entry) == {
        "entry": ENTRY,
        "loaded": True,
        "coordinator": {
            "last_update_success": True,
            "last_exception": None,
            "update_interval_seconds": 300.0,
            "has_car": True,
            "car_read_failing": False,
            "price_read_failing": False,
            "price_retry_pending": False,
        },
        "data": {
            "read_at": "2026-09-27T10:00:00+00:00",
            "charger": {
                "id": FAKE_CHARGER_ID,
                "name": FAKE_CHARGER_NAME,
                "max_kw": 11.0,
                "state": "busy-charging",
                "state_raw": "busy-charging",
                "is_connected": True,
                "charge_state": "charging",
                "charge_state_raw": "charging",
                "charge_id": FAKE_CHARGE_ID,
                "can_stop": True,
                "charge_kwh": 4.2,
                "charge_kw": 7.1,
            },
            "vehicle": {
                "id": 424242,
                "name": FAKE_VEHICLE_NAME,
                "capacity_kwh": 60.0,
                "max_kw_ac": 11.0,
                "brand": "Example",
                "model": "Model E",
                "battery_level": 55.0,
                "charge_limit": 80.0,
                "plugged_in": False,
                "power_delivery_state": None,
                "power_delivery_state_raw": None,
                "last_seen": "2026-09-26T08:30:00+00:00",
            },
            "control": {
                "blocked": False,
                "start_pending": False,
                "stop_asked": False,
                "stop_pending": False,
            },
        },
        "prices": {
            "currency": "DKK",
            "slot_count": 8,
            "first_slot_start": "2026-09-26T22:00:00+00:00",
            "last_slot_start": "2026-09-26T23:45:00+00:00",
        },
    }


async def test_secrets_never_appear(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    hass_storage: dict[str, Any],
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """No secret anywhere in the download, a stored password included; the kept fields are there."""
    freezer.move_to(NOON)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=FAKE_CHARGER_NAME,
        unique_id=str(FAKE_CHARGER_ID),
        data={
            CONF_EMAIL: FAKE_EMAIL,
            CONF_DEVICE_ID: FAKE_DEVICE_ID,
            CONF_PASSWORD: FAKE_PASSWORD,  # never stored; here as the safeguard's case
            **tokens_to_data(FAKE_TOKENS),
        },
    )
    _blocked(hass_storage, entry)
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, entry)
    blocked = await _download_text(hass, hass_client, hass_admin_user, entry)
    assert f"start_blocked_{entry.entry_id}" in blocked  # the repair issue is in it

    # An open charge clears the block, so the charge ID gets its own download.
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        state=ChargerState.BUSY_CHARGING,
        charge_state=ChargeState.CHARGING,
    )
    await entry.runtime_data.async_refresh()
    charging = await _download_text(hass, hass_client, hass_admin_user, entry)

    for body in (blocked, charging):
        for secret in SECRETS:
            assert secret not in body
        assert FAKE_CHARGER_NAME in body
        assert FAKE_VEHICLE_NAME in body
        assert str(FAKE_CHARGER_ID) in body
    assert FAKE_CHARGE_ID in charging


async def test_no_car_and_no_prices(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """No car: vehicle is None; no known prices: an empty summary."""
    mock_client.get_vehicle.side_effect = VehicleNotFoundError("fake no car")
    mock_client.get_price_forecast.return_value = make_forecast(
        DEFAULT_FORECAST_START, []
    )
    await setup_integration(hass, mock_config_entry)

    data = await _download(hass, hass_client, hass_admin_user, mock_config_entry)
    assert data["coordinator"]["has_car"] is False
    assert data["data"]["vehicle"] is None
    assert data["prices"] == {
        "currency": "DKK",
        "slot_count": 0,
        "first_slot_start": None,
        "last_slot_start": None,
    }


async def test_failing_reads(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed read shows its error; after a good read the old error is gone."""
    freezer.move_to(NOON)
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    error = NortecGoConnectionError("fake network down")
    mock_client.get_charger.side_effect = error
    mock_client.get_vehicle.side_effect = error
    mock_client.get_price_forecast.side_effect = error

    await coordinator.async_refresh()
    await coordinator.async_read_prices(retry_on_failure=True)
    failing = await _download(hass, hass_client, hass_admin_user, mock_config_entry)
    assert failing["coordinator"]["last_update_success"] is False
    assert failing["coordinator"]["last_exception"] == CANNOT_CONNECT
    assert failing["coordinator"]["price_read_failing"] is True
    assert failing["coordinator"]["price_retry_pending"] is True

    # The charger reads again; the car still fails.
    mock_client.get_charger.side_effect = None
    await coordinator.async_read_now(with_car=True)
    recovered = await _download(hass, hass_client, hass_admin_user, mock_config_entry)
    assert recovered["coordinator"]["last_update_success"] is True
    assert recovered["coordinator"]["last_exception"] is None
    assert recovered["coordinator"]["car_read_failing"] is True


@pytest.mark.parametrize(
    ("error", "state", "reason"),
    [
        (NortecGoConnectionError("fake network down"), "setup_retry", CANNOT_CONNECT),
        (ChargerNotFoundError("fake charger gone"), "setup_error", CHARGER_NOT_FOUND),
    ],
)
async def test_failed_setup(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
    state: str,
    reason: str,
) -> None:
    """A failed setup: the entry, its state and why, secrets redacted."""
    mock_client.get_charger.side_effect = error
    await setup_integration(hass, mock_config_entry)

    assert await _download(hass, hass_client, hass_admin_user, mock_config_entry) == {
        "entry": ENTRY,
        "loaded": False,
        "state": state,
        "reason": reason,
    }


async def test_unloaded_entry(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """An unloaded entry still downloads, with no reason."""
    await setup_integration(hass, mock_config_entry)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert await _download(hass, hass_client, hass_admin_user, mock_config_entry) == {
        "entry": ENTRY,
        "loaded": False,
        "state": "not_loaded",
        "reason": None,
    }


def test_client_model_fields_are_pinned() -> None:
    """A pynortecgo bump that changes these fields fails here: judge each new one (D38)."""
    assert {f.name for f in fields(Charger)} == CHARGER_FIELDS
    assert {f.name for f in fields(Vehicle)} == VEHICLE_FIELDS
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_diagnostics.py -q`
Expected: `test_client_model_fields_are_pinned` passes (it pins the installed client); every other test FAILs with a 404 from the download (the integration has no diagnostics platform yet).

- [ ] **Step 3: Add the coordinator properties**

In `custom_components/nortec_go/coordinator.py`, add these to `NortecGoCoordinator`, right after `__init__` (shown in a `text` block because the `ruff-format` hook dedents class methods in Markdown; indent them as methods):

```text
    @property
    def car_read_failing(self) -> bool:
        """Whether the car reads fail now: from the first failure to the next good read."""
        return self._car_failing

    @property
    def price_read_failing(self) -> bool:
        """Whether the price reads fail now: from the first failure to the next good read (D37)."""
        return self._prices_failing

    @property
    def price_retry_pending(self) -> bool:
        """Whether a price read retry is scheduled (D37)."""
        return self._price_retry is not None
```

- [ ] **Step 4: Write `diagnostics.py`**

Create `custom_components/nortec_go/diagnostics.py`:

```python
"""Diagnostics for Nortec Go: only the sign-in secrets are redacted (D38)."""

from dataclasses import asdict
from typing import Any, Final

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
)
from homeassistant.core import HomeAssistant

from .const import CONF_REFRESH_TOKEN
from .entry import NortecGoConfigEntry

# The password is never stored; it is here in case a later bug stores it. The device ID is
# sent at sign-in. IDs and names stay (D38).
TO_REDACT: Final = {
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NortecGoConfigEntry
) -> dict[str, Any]:
    """Return the entry, the last read and how the reads are going."""
    diagnostics: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "unique_id": entry.unique_id,
            "data": dict(entry.data),
            "options": dict(entry.options),
        }
    }
    if entry.state is not ConfigEntryState.LOADED:
        # The download is served for any entry; an unloaded one has no coordinator.
        diagnostics.update(
            {"loaded": False, "state": entry.state.value, "reason": entry.reason}
        )
        return async_redact_data(diagnostics, TO_REDACT)

    coordinator = entry.runtime_data
    data = coordinator.data  # set: the entry loads only after a good first read
    error = coordinator.last_exception
    interval = coordinator.update_interval
    slots = coordinator.known_prices
    diagnostics.update(
        {
            "loaded": True,
            "coordinator": {
                "last_update_success": coordinator.last_update_success,
                # HA keeps the last error after a good read; show only a current one.
                "last_exception": (
                    str(error)
                    if error is not None and not coordinator.last_update_success
                    else None
                ),
                "update_interval_seconds": (
                    interval.total_seconds() if interval is not None else None
                ),
                "has_car": coordinator.has_car,
                "car_read_failing": coordinator.car_read_failing,
                "price_read_failing": coordinator.price_read_failing,
                "price_retry_pending": coordinator.price_retry_pending,
            },
            "data": {
                "read_at": data.read_at,
                "charger": asdict(data.charger),
                "vehicle": asdict(data.vehicle) if data.vehicle is not None else None,
                "control": asdict(data.control),
            },
            # A summary: the slots are keyed by datetime and would show every price.
            "prices": {
                "currency": coordinator.price_currency,
                "slot_count": len(slots),
                "first_slot_start": min(slots, default=None),
                "last_slot_start": max(slots, default=None),
            },
        }
    )
    return async_redact_data(diagnostics, TO_REDACT)
```

If ruff flags the unused `hass` argument, keep it: Home Assistant calls the function with it. Don't add a `noqa` unless ruff actually reports something.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_diagnostics.py -q`
Expected: all PASS. If an exact value differs (a float, an ISO string), check the code against the spec before touching the expected value; the expected dict follows spec §2 and §3.

- [ ] **Step 6: Mark the rule done**

In `custom_components/nortec_go/quality_scale.yaml`, change `  diagnostics: todo` to `  diagnostics: done`.

- [ ] **Step 7: Run the gates**

Run: `uv run pytest -q && uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95 -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: all pass; `diagnostics.py` fully covered.

- [ ] **Step 8: Commit**

Write the message to `/tmp/diagnostics-task-1-msg.txt` with the Write tool:

```text
feat: diagnostics with the sign-in secrets redacted (#11)

A config entry diagnostics download: the entry, the last charger and car read,
the charge control's flags, how the reads are going, and a price summary.
Only the email, password, tokens and device ID are redacted (D38); a test pins
the pynortecgo fields the download shows.

<co-author trailer from the dispatch>
```

Then: `git add custom_components/nortec_go/diagnostics.py custom_components/nortec_go/coordinator.py custom_components/nortec_go/quality_scale.yaml tests/test_diagnostics.py && git commit -F /tmp/diagnostics-task-1-msg.txt`

---

### Task 2: Docs, hard rule 5 and D38

**Model:** opus — a docs task (D33), and it rewords a hard rule.
**Wave:** 1

**Files:**
- Modify: `CLAUDE.md` (hard rule 5)
- Modify: `docs/decisions.md` (append D38)
- Modify: `docs/releasing.md` (the client-bump checklist)
- Modify: `docs/user/nortec_go.md` (*Troubleshooting*)
- Modify: `docs/manual-testing.md` (a checklist)
- Modify: `.github/ISSUE_TEMPLATE/bug.yml` (the *Diagnostics / logs* field)
- Modify: `CHANGELOG.md` (*Unreleased* → *Added*)

**Interfaces:**
- Consumes (names fixed by this plan; Task 1 lands them): the download is Home Assistant's **Download diagnostics** on the entry; it redacts `email`, `password`, `access_token`, `refresh_token` and `device_id` as `**REDACTED**`; it keeps the charger's and car's names and IDs; the field-pin test is `test_client_model_fields_are_pinned` in `tests/test_diagnostics.py`.
- Produces: D38 in `docs/decisions.md`; the user docs heading `### Diagnostics` (anchor `#diagnostics`).

There are no tests for docs. Check each edit by reading it back, and run `uv run pre-commit run --files <the changed files>` before committing (it runs the Markdown and YAML hooks).

- [ ] **Step 1: Hard rule 5**

In `CLAUDE.md`, replace:

```text
5. Diagnostics and logs redact tokens, email, IDs and location (`async_redact_data`), and credentials and
   usernames are never logged, even wrong ones. Anything taken from a real instance (diagnostics downloads,
   logs, dumps) goes in `local/` and is never committed.
```

with, word for word (the owner approved it):

```text
5. Diagnostics and logs redact the email, the password, the access and refresh tokens and the client's
   device ID (`async_redact_data`; D38), and credentials and usernames are never logged, even wrong ones.
   Anything taken from a real instance (diagnostics downloads, logs, dumps) goes in `local/` and is never
   committed.
```

Change nothing else in `CLAUDE.md`.

- [ ] **Step 2: D38**

Append to the end of `docs/decisions.md` (after D37, with one blank line before it):

```markdown
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
```

- [ ] **Step 3: The release checklist**

In `docs/releasing.md`, in the client-bump checklist, replace:

```text
- [ ] Read the new version's exception messages, including errors it wraps from lower layers, and confirm
  they hold no email, password, token, IDs or request bodies. The integration passes them into its logs
  (`CLAUDE.md`, hard rule 5).
```

with:

```text
- [ ] Read the new version's exception messages, including errors it wraps from lower layers, and confirm
  they hold no email, password, tokens, device ID or request bodies. The integration passes them into its
  logs (`CLAUDE.md`, hard rule 5).
- [ ] If `test_client_model_fields_are_pinned` in `tests/test_diagnostics.py` fails, the diagnostics show
  a changed `Charger` or `Vehicle` field: decide for each new field whether it is a secret, add it to
  `TO_REDACT` in `diagnostics.py` if so, and update the pinned sets (D38).
```

- [ ] **Step 4: The user docs**

In `docs/user/nortec_go.md`, *Troubleshooting*: insert this subsection after *Debug logging* (after its last paragraph, "The logs hold no passwords or session tokens, …") and before `### Reporting a problem`:

```markdown
### Diagnostics

The diagnostics file shows what the integration last read from the charger and the car, and how its reads
are going. To download it, go to **Settings** > **Devices & services** > **Nortec Go**, open the entry's
menu (⋮) and select **Download diagnostics**.

The file leaves out your email, the session tokens and the device ID the integration signs in with; your
password is never stored. It keeps your charger's and car's names and IDs, and Home Assistant adds its own
information, such as its version, your installed custom integrations and your time zone. Check the file
before you share it, and remove what you don't want public.
```

In *Reporting a problem*, after the sentence ending "not the whole log.", add: "You can also attach the
diagnostics file (see *Diagnostics*)." Leave the rest of that paragraph as it is (its advice is about pasted
log lines). Reflow the paragraph to the file's line width (about 110 characters).

- [ ] **Step 5: The manual-testing checklist**

In `docs/manual-testing.md`, add at the end of *Checklists* (after the *Start and stop (#9)* list):

```markdown
### Diagnostics (#11)

- [ ] **Owner** Download the diagnostics from the entry's menu and save the file in `local/`: the email,
  both tokens and the device ID show as `**REDACTED**`, and the charger's and car's data are there
  ([Diagnostics](user/nortec_go.md#diagnostics)). Agents never open the file.
```

- [ ] **Step 6: The bug template**

In `.github/ISSUE_TEMPLATE/bug.yml`, in the `diagnostics` field's `description` (a `>-` folded block), after `"Reporting a problem" lists.` add the sentence `You can also attach the diagnostics file (see the docs' "Diagnostics").`, keeping the block's indentation and wrapping its lines like the others.

- [ ] **Step 7: The changelog**

In `CHANGELOG.md`, add as the last bullet under *Unreleased* → *Added*:

```markdown
- A diagnostics download for the integration, with your email, the session tokens and the device ID left
  out.
```

- [ ] **Step 8: Check and commit**

Run: `uv run pre-commit run --files CLAUDE.md docs/decisions.md docs/releasing.md docs/user/nortec_go.md docs/manual-testing.md .github/ISSUE_TEMPLATE/bug.yml CHANGELOG.md`
Expected: all hooks pass (fix what they report; re-run).

Write the message to `/tmp/diagnostics-task-2-msg.txt` with the Write tool:

```text
docs: diagnostics, hard rule 5 and D38 (#11)

Hard rule 5 redacts only the sign-in secrets (the owner's ruling, D38). The
user docs get a Diagnostics part in Troubleshooting; the release checklist,
manual-testing guide, bug template and changelog follow.

<co-author trailer from the dispatch>
```

Then: `git add CLAUDE.md docs/decisions.md docs/releasing.md docs/user/nortec_go.md docs/manual-testing.md .github/ISSUE_TEMPLATE/bug.yml CHANGELOG.md && git commit -F /tmp/diagnostics-task-2-msg.txt`
