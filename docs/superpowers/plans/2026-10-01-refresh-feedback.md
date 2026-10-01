# Refresh press reports a failed read Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** A press on the *Refresh* button raises a translated error when its charger read or its price read fails, and the quality scale rule `action-exceptions` goes to `done`.

**Architecture:** Two tasks in one wave, on disjoint files. Task 1 is the code: `async_read_prices` gets a `raise_on_failure` argument, the button reports a failed charger read from the coordinator's `last_update_success` and `last_exception`, one new exception text, and the quality scale status. Task 2 is the docs: user docs, the manual-testing note, one Home Assistant note, D43 and the CHANGELOG entry.

**Tech Stack:** Python 3.14, Home Assistant 2026.9 custom integration, pytest with `pytest-homeassistant-custom-component`, mypy strict, ruff, uv.

**Spec:** `docs/superpowers/specs/2026-10-01-refresh-feedback-design.md` (issue #40).

## Global Constraints

- TDD: write the failing test, see it fail, then change the code.
- The press raises a plain `HomeAssistantError` with `translation_domain` `nortec_go`, never a `ConfigEntryAuthFailed`, `ConfigEntryError` or `UpdateFailed` (spec §1).
- The price read runs on every press, also after a failed charger read. The charger's error wins when both fail (D43).
- `raise_on_failure` defaults to `False`. The setup read, the scheduled reads and the retry (D37) behave exactly as today; only the button passes `True`.
- Auth path (spec §3): in the `except AuthError` branch of `async_read_prices`, the debug line, the retry cancel and the reauth start stay as they are, in the same order. Nothing logs in again or retries a login (hard rule 6). `_async_update_data`, `_async_read_vehicle` and `async_read_now` don't change.
- Nothing touches charge start or stop (`charge_control.py`, `switch.py`).
- Don't touch `sensor.py`, the fixtures in `tests/conftest.py`, `manifest.json` or `uv.lock`: another branch (#76) changes them.
- The new text, word for word: `Reading the prices failed. The known prices are kept. Check the Home Assistant logs.` under the key `price_read_failed`. `translations/en.json` is an exact copy of `strings.json`.
- Tests mock `pynortecgo`; fixtures come from `pynortecgo` model objects through `tests/conftest.py` (hard rule 7). Nothing private (hard rule 3): no IDs, tokens, emails, captures or raw endpoints.
- Gates before every commit, in both tasks (`CLAUDE.md` → Commands, including the coverage gate): `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`, then `uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`. The "Run:" lines in the steps are the quick checks on the way; these gates come on top, right before each commit.
- Subagents write commit messages with the Write tool to a file outside the repo (a new file per commit, named in the step), and commit with `git commit -F <file>` (no heredocs). End the message with the co-author trailer given in the dispatch.
- Match the surrounding code: one-line docstrings ending in a period; comments say why, not what.
- The version bump (`manifest.json`, the CHANGELOG's version heading) is not part of any task: the controller runs the bump step last.

## Review Focus

- **A stale error after a good read:** `last_exception` isn't cleared by a good read. A press that works, after one that failed, must raise nothing. Pinned by `test_press_after_a_failed_press_works_again` (Task 1).
- **The price read skipped after a failed charger read:** the press must still read the prices. Pinned by the `get_price_forecast.await_count` checks in the failing-charger tests (Task 1).
- **A coordinator error class leaking out of the press:** a `ConfigEntryAuthFailed` or `UpdateFailed` raised from a service call. Pinned by `type(raised) is HomeAssistantError` in every failing case (Task 1).
- **A scheduled or setup price read starting to raise:** it runs in a background task, where an error would only be logged as unhandled. Pinned by `test_price_read_raises_nothing_by_default` (Task 1) and the existing price tests, which stay unchanged.
- **A raised key with no text:** a key the press can raise that isn't in `strings.json` shows as a bare key in the UI. Pinned by `test_press_error_keys_have_texts` (Task 1).

---

### Task 1: The press raises, and the quality scale says so

**Model:** opus — touches the auth branch of the price read (reauth path).
**Wave:** 1

**Files:**
- Modify: `tests/test_coordinator.py` (new tests after `test_later_price_auth_error_starts_reauth`)
- Modify: `custom_components/nortec_go/coordinator.py` (`async_read_prices` and the `homeassistant.exceptions` import only)
- Modify: `custom_components/nortec_go/strings.json`
- Modify: `custom_components/nortec_go/translations/en.json`
- Modify: `tests/test_button.py`
- Modify: `custom_components/nortec_go/button.py`
- Modify: `tests/test_quality_scale.py`
- Modify: `custom_components/nortec_go/quality_scale.yaml`

**Interfaces:**
- Consumes: `NortecGoCoordinator.async_read_now(*, with_car: bool = False) -> None` (unchanged), and Home Assistant's `DataUpdateCoordinator.last_update_success: bool` and `last_exception: BaseException | None`.
- Produces:
  - `NortecGoCoordinator.async_read_prices(*, during_setup: bool = False, retry_on_failure: bool = False, raise_on_failure: bool = False) -> None`
  - `read_error(err: BaseException | None) -> HomeAssistantError` in `button.py`
  - the exception key `price_read_failed`

Facts you need:
- Outside setup, `DataUpdateCoordinator.async_refresh()` stores a read's error in `last_exception` and sets `last_update_success` to `False`; it doesn't raise it. For an auth failure it starts reauth itself. A good read sets `last_update_success` to `True` and leaves the old `last_exception` in place.
- The coordinator's `_async_update_data` already raises translated errors with the keys `auth_failed`, `rate_limited`, `cannot_connect`, `api_error`, `charger_not_found`, `unexpected_response` and `read_failed`. A `TimeoutError` is stored as it is (no translation key).
- A rejected car read (`AuthError` from `get_vehicle`) fails the read with `auth_failed`. Every other car error keeps the car's last data and fails nothing.

- [ ] **Step 1: Write the failing coordinator tests**

Add to `tests/test_coordinator.py`, right after `test_later_price_auth_error_starts_reauth`. `HomeAssistantError`, `AuthError`, `NortecGoConnectionError`, `ConfigEntry`, `DOMAIN`, `patch`, `pytest` and `_coordinator` are already imported or defined in the file.

```python
async def test_price_read_raises_when_asked(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A failed price read asked to raise raises our text, after marking the reads as failing."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    error = NortecGoConnectionError("network down")
    mock_client.get_price_forecast.side_effect = error
    with pytest.raises(HomeAssistantError) as exc_info:
        await coordinator.async_read_prices(raise_on_failure=True)

    raised = exc_info.value
    assert type(raised) is HomeAssistantError
    assert raised.translation_domain == DOMAIN
    assert raised.translation_key == "price_read_failed"
    assert raised.__cause__ is error
    assert coordinator.price_read_failing is True


async def test_price_read_auth_error_raises_when_asked(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A rejected price read asked to raise starts reauth first, then raises auth_failed."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    error = AuthError("token rejected")
    mock_client.get_price_forecast.side_effect = error
    with (
        patch.object(ConfigEntry, "async_start_reauth") as start_reauth,
        pytest.raises(HomeAssistantError) as exc_info,
    ):
        await coordinator.async_read_prices(raise_on_failure=True)

    raised = exc_info.value
    assert type(raised) is HomeAssistantError
    assert raised.translation_domain == DOMAIN
    assert raised.translation_key == "auth_failed"
    assert raised.__cause__ is error
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()


@pytest.mark.parametrize("retry_on_failure", [False, True])
async def test_price_read_raises_nothing_by_default(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    retry_on_failure: bool,
) -> None:
    """A failed price read that isn't asked to raise raises nothing, as before."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await coordinator.async_read_prices(retry_on_failure=retry_on_failure)
    assert coordinator.price_read_failing is True

    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth") as start_reauth:
        await coordinator.async_read_prices(retry_on_failure=retry_on_failure)
    start_reauth.assert_called_once()
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest -q tests/test_coordinator.py -k "raises_when_asked or raises_nothing_by_default"`
Expected: the two `raises_when_asked` tests FAIL with `TypeError: ... got an unexpected keyword argument 'raise_on_failure'`; `test_price_read_raises_nothing_by_default` passes (it pins today's behaviour).

- [ ] **Step 3: Add `raise_on_failure` to `async_read_prices`**

In `custom_components/nortec_go/coordinator.py`, add `HomeAssistantError` to the existing import:

```python
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    HomeAssistantError,
)
```

Replace the method's signature, docstring and its two `except` branches with the following. The lines before each new `if raise_on_failure:` are today's lines, unchanged and in the same order; everything after the `except` branches (from `self._async_cancel_price_retry()` on) stays as it is.

```text
    async def async_read_prices(
        self,
        *,
        during_setup: bool = False,
        retry_on_failure: bool = False,
        raise_on_failure: bool = False,
    ) -> None:
        """Read the forecast, merge, prune and save it with its currency; keep the known slots on failure (§4.3).

        A failed read asked to retry on failure is read once more later (D37). One asked to raise
        on failure then raises a translated error, for the Refresh button (D43).
        """
        try:
            forecast = await self.client.get_price_forecast()
        except AuthError as err:
            _LOGGER.debug("Reading the price forecast was rejected: %s", err)
            self._async_cancel_price_retry()
            if during_setup:
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN, translation_key="auth_failed"
                ) from err
            self.config_entry.async_start_reauth(self.hass)
            if raise_on_failure:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="auth_failed"
                ) from err
            return
        except NortecGoError as err:
            self._log_price_error(err)
            if retry_on_failure:
                self._async_schedule_price_retry(err)
            if raise_on_failure:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="price_read_failed"
                ) from err
            return
```

- [ ] **Step 4: Add the text**

In `custom_components/nortec_go/strings.json`, under `"exceptions"`, after the `"read_failed"` entry (add a comma after its closing brace):

```json
"price_read_failed": {
  "message": "Reading the prices failed. The known prices are kept. Check the Home Assistant logs."
}
```

Make the same change in `custom_components/nortec_go/translations/en.json`, so the two files stay identical.

- [ ] **Step 5: Run the coordinator tests**

Run: `uv run pytest -q tests/test_coordinator.py tests/test_init.py`
Expected: PASS (all, including `test_translations_match_strings`).

- [ ] **Step 6: Commit**

```bash
git add tests/test_coordinator.py custom_components/nortec_go/coordinator.py custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json
git commit -F /tmp/refresh-feedback-task-1-prices-msg.txt
```

Message: `fix: a price read can raise a translated error when asked (#40)`, then the co-author trailer.

- [ ] **Step 7: Write the failing button tests**

In `tests/test_button.py`:
- replace the top of the file (the module docstring, the imports and the `ENTITY_ID` line, today's lines 1–13) with the first block below, so `ENTITY_ID` is defined once;
- add `_failed_press` right after `_press`;
- **remove** `test_press_after_failed_read_does_not_raise`, and put the new tests in its place, before `test_press_twice_reads_twice`;
- `test_press_reads_charger_car_and_prices`, `test_press_shows_the_new_read` and `test_press_twice_reads_twice` stay as they are.

The top of the file:

```python
"""Tests for the Nortec Go Refresh button."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from homeassistant.components.button.const import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed
from pynortecgo import (
    ApiError,
    AuthError,
    ChargerNotFoundError,
    NortecGoConnectionError,
    NortecGoError,
    RateLimitError,
    UnexpectedResponseError,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nortec_go.button import read_error
from custom_components.nortec_go.const import DOMAIN

from .conftest import make_charger, setup_integration

ENTITY_ID = "button.garage_charger_refresh"
CABLE_ID = "binary_sensor.garage_charger_cable_connected"
STRINGS = Path(__file__).parent.parent / "custom_components" / DOMAIN / "strings.json"
CHARGER_KEYS = [
    "auth_failed",
    "rate_limited",
    "cannot_connect",
    "api_error",
    "charger_not_found",
    "unexpected_response",
    "read_failed",
]
```

A helper, after `_press`:

```python
async def _failed_press(hass: HomeAssistant) -> HomeAssistantError:
    """Press, and return the error the press raised; reauth is not started for real."""
    with (
        patch.object(ConfigEntry, "async_start_reauth"),
        pytest.raises(HomeAssistantError) as exc_info,
    ):
        await _press(hass)
    await hass.async_block_till_done()
    raised = exc_info.value
    assert type(raised) is HomeAssistantError
    assert raised.translation_domain == DOMAIN
    return raised
```

The tests:

```python
async def test_press_after_failed_read_raises(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A failed charger read raises its text; the prices are still read and the button stays."""
    await setup_integration(hass, mock_config_entry)
    forecasts = mock_client.get_price_forecast.await_count
    error = NortecGoConnectionError("x")
    mock_client.get_charger.side_effect = error

    raised = await _failed_press(hass)

    assert raised.translation_key == "cannot_connect"
    assert isinstance(raised.__cause__, UpdateFailed)
    assert raised.__cause__.__cause__ is error
    assert mock_client.get_price_forecast.await_count == forecasts + 1
    state = hass.states.get(CABLE_ID)
    assert state is not None
    assert state.state == "unavailable"
    button = hass.states.get(ENTITY_ID)
    assert button is not None
    assert button.state != "unavailable"


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (AuthError("token rejected"), "auth_failed"),
        (RateLimitError("too many requests", retry_after=30.0), "rate_limited"),
        (NortecGoConnectionError("network down"), "cannot_connect"),
        (ApiError("GET /example", 500), "api_error"),
        (ChargerNotFoundError("GET /example: not found"), "charger_not_found"),
        (UnexpectedResponseError("GET /example", "bad shape"), "unexpected_response"),
        (NortecGoError("something new"), "read_failed"),
        (TimeoutError(), "read_failed"),
    ],
)
async def test_press_raises_the_charger_reads_text(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
    key: str,
) -> None:
    """Each charger read error raises its own text; one outside pynortecgo raises read_failed."""
    await setup_integration(hass, mock_config_entry)
    mock_client.get_charger.side_effect = error

    raised = await _failed_press(hass)

    assert raised.translation_key == key


async def test_press_reports_a_rejected_car_read(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A rejected car read fails the read, so the press raises auth_failed; the prices are read."""
    await setup_integration(hass, mock_config_entry)
    forecasts = mock_client.get_price_forecast.await_count
    mock_client.get_vehicle.side_effect = AuthError("token rejected")

    raised = await _failed_press(hass)

    assert raised.translation_key == "auth_failed"
    assert mock_client.get_price_forecast.await_count == forecasts + 1


async def test_press_ignores_another_car_error(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A car error that keeps the car's last data fails nothing, and the press raises nothing."""
    await setup_integration(hass, mock_config_entry)
    vehicles = mock_client.get_vehicle.await_count
    mock_client.get_vehicle.side_effect = NortecGoConnectionError("network down")

    await _press(hass)

    assert mock_client.get_vehicle.await_count == vehicles + 1


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (NortecGoConnectionError("network down"), "price_read_failed"),
        (RateLimitError("too many requests", retry_after=30.0), "price_read_failed"),
        (AuthError("token rejected"), "auth_failed"),
    ],
)
async def test_press_raises_when_only_the_price_read_fails(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
    key: str,
) -> None:
    """A failed price read raises its text; the charger's entities stay available."""
    await setup_integration(hass, mock_config_entry)
    mock_client.get_price_forecast.side_effect = error

    raised = await _failed_press(hass)

    assert raised.translation_key == key
    assert raised.__cause__ is error
    state = hass.states.get(CABLE_ID)
    assert state is not None
    assert state.state != "unavailable"


async def test_press_charger_error_wins_when_both_reads_fail(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """With both reads failing, the price read still runs and the charger's text is raised."""
    await setup_integration(hass, mock_config_entry)
    forecasts = mock_client.get_price_forecast.await_count
    mock_client.get_charger.side_effect = ApiError("GET /example", 500)
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")

    raised = await _failed_press(hass)

    assert raised.translation_key == "api_error"
    assert mock_client.get_price_forecast.await_count == forecasts + 1


async def test_press_after_a_failed_press_works_again(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A good press after a failed one raises nothing: the old error isn't raised again."""
    await setup_integration(hass, mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await _failed_press(hass)

    mock_client.get_charger.side_effect = None
    await _press(hass)

    state = hass.states.get(CABLE_ID)
    assert state is not None
    assert state.state != "unavailable"


def test_read_error_copies_our_translated_error() -> None:
    """Our own translated error gives a plain error with the same key and placeholders."""
    source = UpdateFailed(
        translation_domain=DOMAIN,
        translation_key="rate_limited",
        translation_placeholders={"seconds": "30"},
    )

    raised = read_error(source)

    assert type(raised) is HomeAssistantError
    assert raised.translation_domain == DOMAIN
    assert raised.translation_key == "rate_limited"
    assert raised.translation_placeholders == {"seconds": "30"}


@pytest.mark.parametrize(
    "source",
    [
        None,
        TimeoutError(),
        HomeAssistantError("no translation"),
        HomeAssistantError(translation_domain="other", translation_key="some_key"),
    ],
)
def test_read_error_falls_back_to_read_failed(source: BaseException | None) -> None:
    """Anything that isn't our own translated error is reported as read_failed."""
    raised = read_error(source)

    assert type(raised) is HomeAssistantError
    assert raised.translation_domain == DOMAIN
    assert raised.translation_key == "read_failed"


@pytest.mark.parametrize("key", [*CHARGER_KEYS, "price_read_failed"])
def test_press_error_keys_have_texts(key: str) -> None:
    """Every key a press can raise has a text in strings.json."""
    exceptions = json.loads(STRINGS.read_text(encoding="utf-8"))["exceptions"]
    assert exceptions[key]["message"]
```

- [ ] **Step 8: Run them and see them fail**

Run: `uv run pytest -q tests/test_button.py`
Expected: FAIL at collection with `ImportError: cannot import name 'read_error'`.

- [ ] **Step 9: Implement the button**

Replace `custom_components/nortec_go/button.py` from the top (the module docstring) down to `PARALLEL_UPDATES` with:

```python
"""The Nortec Go Refresh button: reads the charger, the car and the prices now (D27)."""

from contextlib import suppress

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import NortecGoCoordinator
from .entity import NortecGoChargerEntity
from .entry import NortecGoConfigEntry

PARALLEL_UPDATES = 1


def read_error(err: BaseException | None) -> HomeAssistantError:
    """The error a press raises for a failed charger read: the read's own text, or read_failed.

    Always a plain HomeAssistantError: the coordinator's error classes belong to setup and polling.
    """
    if (
        isinstance(err, HomeAssistantError)
        and err.translation_domain == DOMAIN
        and err.translation_key
    ):
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key=err.translation_key,
            translation_placeholders=err.translation_placeholders,
        )
    return HomeAssistantError(translation_domain=DOMAIN, translation_key="read_failed")
```

`async_setup_entry`, the class header, `__init__` and `available` stay. Replace the class docstring and `async_press` with:

```text
    """Reads the charger, the car and the prices when pressed; raises when a read fails (D43)."""

    async def async_press(self) -> None:
        """Read the charger and the car now, then the prices; raise when a read failed."""
        coordinator = self.coordinator
        await coordinator.async_read_now(with_car=True)
        # last_exception isn't cleared by a good read, so go by last_update_success.
        if coordinator.last_update_success:
            await coordinator.async_read_prices(raise_on_failure=True)
            return
        failed = coordinator.last_exception
        # The prices are read all the same; the charger's error wins when both fail (D43).
        with suppress(HomeAssistantError):
            await coordinator.async_read_prices(raise_on_failure=True)
        raise read_error(failed) from failed
```

- [ ] **Step 10: Run the button tests**

Run: `uv run pytest -q tests/test_button.py`
Expected: PASS.

If a parametrized charger case fails because Home Assistant logged an error that the test harness turns into a failure, don't weaken the assertion: report it as a concern with the output.

- [ ] **Step 11: Commit**

```bash
git add tests/test_button.py custom_components/nortec_go/button.py
git commit -F /tmp/refresh-feedback-task-1-button-msg.txt
```

Message: `fix: the Refresh button raises when its read fails (#40)`, then the co-author trailer.

- [ ] **Step 12: Pin the quality scale status (failing test first)**

In `tests/test_quality_scale.py`:
- in `CHECKED_STATUSES`, change `"action-exceptions": "todo",` to `"action-exceptions": "done",`;
- remove `test_action_exceptions_comment` (the function, its docstring and the blank lines that belonged to it). The comment no longer ends with an issue number.

Run: `uv run pytest -q tests/test_quality_scale.py`
Expected: `test_checked_statuses` FAILS with `action-exceptions`.

- [ ] **Step 13: Set the status**

In `custom_components/nortec_go/quality_scale.yaml`, replace the `action-exceptions` rule (the three lines under `# Silver`) with:

```yaml
  action-exceptions:
    status: done
    comment: "The Charge switch and the Refresh button raise translated errors when their action fails."
```

Every other line stays as it is.

Run: `uv run pytest -q tests/test_quality_scale.py`
Expected: PASS.

- [ ] **Step 14: Run the gates**

Run the gates from *Global Constraints* (as before every commit).
Expected: all pass; `button.py` and the changed lines of `coordinator.py` are fully covered (no new line under *Missing*).

- [ ] **Step 15: Commit**

```bash
git add tests/test_quality_scale.py custom_components/nortec_go/quality_scale.yaml
git commit -F /tmp/refresh-feedback-task-1-scale-msg.txt
```

Message: `fix: action-exceptions is done (#40)`, then the co-author trailer.

---

### Task 2: Docs, D43 and the CHANGELOG entry

**Model:** opus — docs task (D33).
**Wave:** 1

**Files:**
- Modify: `docs/user/nortec_go.md` (*Data updates*)
- Modify: `docs/manual-testing.md` (the owner's *Refresh* check)
- Modify: `docs/ha-notes.md` (*Coordinators and actions*, the `last_exception` bullet)
- Modify: `docs/decisions.md` (new entry D43, at the end)
- Modify: `CHANGELOG.md` (under `## [Unreleased]`)

**Interfaces:**
- Consumes: the behaviour and names the spec fixes: a press raises when its charger read or its price read fails; the price read always runs; the charger's error wins. This task starts from names the plan fixes, so the controller re-checks it against the code that landed.
- Produces: nothing other tasks use.

Write for the reader of each doc. Keep the existing lines' style and line width (about 110 characters). Don't restate a fact that another doc owns (`docs/way-of-working.md` §7).

- [ ] **Step 1: User docs**

In `docs/user/nortec_go.md`, under *Data updates*, the last paragraph starts "Turning *Charge* on or off reads the charger right away. To read the charger, the car and the prices now, press the *Refresh* button." Add a new paragraph right after that paragraph:

```markdown
If the charger read or the price read of a *Refresh* press fails, the press shows an error. The other read
still runs; when both fail, the error is the charger read's. In a script or an automation, a `button.press`
step on *Refresh* fails then too.
```

The entity table's row for *Refresh* stays as it is.

- [ ] **Step 2: Manual-testing note**

In `docs/manual-testing.md`, the owner's check reads:

```markdown
- [ ] **Owner** Press *Refresh*: *Last read* moves ([Data updates](user/nortec_go.md#data-updates)).
  *Refresh* only reads.
```

Change its second line to:

```markdown
  *Refresh* only reads. A press whose read fails shows an error; the checklist has no step that makes one
  fail.
```

No new checkbox.

- [ ] **Step 3: Home Assistant note**

In `docs/ha-notes.md`, under *Coordinators and actions*, the last bullet reads:

```markdown
- `DataUpdateCoordinator.last_exception` isn't cleared by a successful read. Show it as the current error
  only while `last_update_success` is false.
```

Add one bullet right before it (so the two read together), and leave the existing bullet as it is:

```markdown
- Outside setup, `async_refresh()` stores a read's error in `last_exception` instead of raising it,
  including `ConfigEntryAuthFailed` and `ConfigEntryError`. A caller that must report a failed read looks at
  the coordinator afterwards.
```

- [ ] **Step 4: D43**

Append to `docs/decisions.md`, after D41 (a blank line before the heading):

```markdown
### D43: A Refresh press raises when its read fails
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** A press on *Refresh* raises a translated error when its charger read or its price read
  fails. The price read always runs, and the charger's error is the one raised when both fail.
- **Why:** a silent press during an outage lets the owner think the data is fresh, and the quality scale's
  `action-exceptions` rule asks actions to raise when they fail.
- **Source:** [refresh feedback spec](superpowers/specs/2026-10-01-refresh-feedback-design.md), Decisions
```

D42 is not on this branch: another open branch holds it. Don't add or mention it.

- [ ] **Step 5: CHANGELOG**

In `CHANGELOG.md`, under `## [Unreleased]` (which is empty today), add:

```markdown
## [Unreleased]

### Fixed

- The *Refresh* button shows an error when its charger read or its price read fails, instead of succeeding
  silently. A `button.press` step in a script or an automation fails then too.
```

Keep one blank line before `## [0.1.1]`.

- [ ] **Step 6: Check and commit**

Run: `uv run pre-commit run --files docs/user/nortec_go.md docs/manual-testing.md docs/ha-notes.md docs/decisions.md CHANGELOG.md`
Expected: PASS. If a hook reformats a file, look at the change, keep it, and run the command again.

Then run the gates from *Global Constraints*. `tests/test_release_check.py` reads the real `CHANGELOG.md`, so it must pass with the new entry.

```bash
git add docs/user/nortec_go.md docs/manual-testing.md docs/ha-notes.md docs/decisions.md CHANGELOG.md
git commit -F /tmp/refresh-feedback-task-2-msg.txt
```

Message: `docs: a Refresh press raises when its read fails (#40, D43)`, then the co-author trailer.

---

## After the tasks (controller)

- Cherry-pick each Approved task onto `fix/refresh-feedback`, run the gates and push (`docs/way-of-working.md`, *Parallel waves*).
- Re-check Task 2's wording against the code that landed (a docs task is always re-checked).
- Learnings (step 8), the branch review (step 9), then the bump step (`docs/releasing.md`) as the last step before `branch ready`.
