# The car device is decided at setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** Whether the entry has a *Car* device is decided by the setup read alone: a failed car read at setup retries setup instead of guessing (#41), a car that goes while running makes its entities unavailable and raises a repair issue whose fix reloads, and a change of car updates the same device (#42, D44).

**Architecture:** Three tasks. Task 1 (wave 1) is the setup read in `coordinator.py`: its own car read with the retry rows, and the car read moved before the charge control gets the charger read, so a failed setup can't lose a stop. Task 2 (wave 2, same file) is the running side: the gone state, its repair issue and fix flow, the device's brand and model, and diagnostics. Task 3 (wave 1) is the docs, D44, the CHANGELOG entry and the quality scale comments, written against the names this plan fixes and held until Tasks 1 and 2 are on the feature branch.

**Tech Stack:** Python 3.14, Home Assistant 2026.9 custom integration, pytest with `pytest-homeassistant-custom-component`, mypy strict, ruff, uv.

**Spec:** `docs/superpowers/specs/2026-10-01-car-device-lifecycle-design.md` (issues #41 and #42).

## Global Constraints

- TDD: write the failing test, see it fail, then change the code.
- "No car" means `VehicleNotFoundError` or `MultipleVehiclesError`, treated alike everywhere.
- Car entities and the car device are added and removed only at setup. Nothing in this plan adds or removes an entity or a device while the entry is loaded (D44). `sensor.py`, `binary_sensor.py`, `entity.py` and `__init__.py` get no behaviour change; the only edits there are the docstrings Task 2 names.
- `has_car` is set by the setup read and never changes afterwards.
- Charge start and stop: `charge_control.py` and `switch.py` are not edited. The only change next to them is where `_async_update_data` calls `charge_control.on_charger_read`: at setup after the car read, while running before it, as today (spec §1, *Order*). The call's arguments don't change.
- Auth path: a rejected car read (`AuthError`) raises `ConfigEntryAuthFailed` with `auth_failed`, at setup and while running, with the debug line `Reading the car was rejected: %s`, as today. Nothing logs in again or retries a login (hard rule 6).
- Never auto-retry `start_charge` (hard rule 6). No test and no code calls a real charger; tests mock `pynortecgo`.
- Keep `Charger` reads small: no new `Charger` field is read (`pynortecgo` 0.8.0 will move the open-charge fields, #81).
- The price reads, the polling intervals, `async_read_now` and `interval_for` don't change.
- Texts, word for word (spec §4). `translations/en.json` is an exact copy of `strings.json`:
  - `exceptions.car_read_failed.message`: `Reading the car failed. Home Assistant will try again.`
  - `issues.car_gone.title`: `The Nortec Go account of {name} no longer has exactly one car`
  - `issues.car_gone.fix_flow.step.confirm.title`: `Remove the car device of {name}`
  - `issues.car_gone.fix_flow.step.confirm.description`: `The Nortec Go account no longer has exactly one car, so the car's entities are unavailable.\n\nIf the car comes back on the account, they work again by themselves and this notice goes away. To remove the car device and its entities now, select **Submit**: the integration reloads. A restart of Home Assistant removes them too, if the account still doesn't have exactly one car.`
  - `issues.car_gone.fix_flow.abort.entry_not_found`: `The Nortec Go entry no longer exists.`
- Names this plan fixes: the property `NortecGoCoordinator.car_gone`, the constant `CAR_GONE_ISSUE_ID = "car_gone_{entry_id}"`, the issue translation key `car_gone`, the exception key `car_read_failed`, the diagnostics key `car_gone`, the decision D44.
- Tests build cars with `make_vehicle` and chargers with `make_charger` from `tests/conftest.py` (hard rule 7). Nothing private (hard rule 3): no IDs, tokens, emails, captures or raw endpoints.
- Gates before every commit (`CLAUDE.md` → Commands, including the coverage gate): `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`, then `uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`. The "Run:" lines in the steps are the quick checks on the way; these gates come on top, right before each commit.
- Subagents write commit messages with the Write tool to a file outside the repo (a new file per commit, named in the step), and commit with `git commit -F <file>` (no heredocs). End the message with the co-author trailer given in the dispatch.
- Match the surrounding code: one-line docstrings ending in a period; comments say why, not what.
- The version bump (`manifest.json`, the CHANGELOG's version heading) is not part of any task: the controller runs the bump step last.

## Review Focus

- **A stop asked for before a restart, with a car read that fails at setup:** the stop must not be sent by the failed setup and must not be forgotten. Pinned by `test_failed_setup_car_read_keeps_a_stop_asked` (Task 1).
- **The order while running changes by accident:** the charge control must still get the charger read before the car is read. Pinned by `test_control_gets_the_charger_read_before_the_car_while_running` (Task 1).
- **The old car's data coming back while the car is gone:** a read of the charger alone returns the cached car. Pinned by the charger-only read in `test_car_gone_while_running` (Task 2).
- **A second car added (`MultipleVehiclesError`), not only a car removed:** every "no car" test is parametrized over both errors (Tasks 1 and 2).
- **The start-block repair getting the wrong flow:** `async_create_fix_flow` now picks by issue ID. The existing `test_repairs.py` tests stay unchanged and must pass (Task 2).
- **A reload from the fix while the car is back:** the device and entities must stay. Pinned by `test_car_gone_fix_keeps_a_car_that_is_back` (Task 2).

---

### Task 1: The setup read retries on a failed car read, and reads the car before the charge control

**Model:** opus — the setup path and the order next to charge stop (the PO's instruction), and the auth branch of the car read.
**Wave:** 1

**Files:**
- Modify: `tests/test_coordinator.py`
- Modify: `tests/test_sensor.py` (replace one test)
- Modify: `custom_components/nortec_go/coordinator.py` (`_async_update_data` after the charger read's `try`, `_async_read_vehicle`, a new `_async_read_setup_vehicle`, the `_car_checked` flag, the `NortecGoData` docstring)
- Modify: `custom_components/nortec_go/strings.json`
- Modify: `custom_components/nortec_go/translations/en.json`

**Interfaces:**
- Consumes: `ChargeControl.on_charger_read(charger: Charger, start_attempts: int) -> None` (unchanged), `NortecGoClient.get_vehicle() -> Vehicle`.
- Produces: the exception key `car_read_failed`. After this task `has_car` true means the setup read got the car. Task 2 edits the same file after this task is on the feature branch.

Facts you need:
- `DataUpdateCoordinator.async_config_entry_first_refresh()` turns an `UpdateFailed` raised by `_async_update_data` into `ConfigEntryNotReady` (the entry goes to `SETUP_RETRY`, with the error's translation key in `entry.error_reason_translation_key`), and lets `ConfigEntryAuthFailed` through (`SETUP_ERROR`, reauth).
- Every setup try builds a new coordinator, so `self.data is None` inside `_async_update_data` is true exactly for the setup read.
- A setup that fails cancels the entry's background tasks. `charge_control.on_charger_read` can queue the stop the owner asked for as such a task, after clearing and saving the stored pending start. That is why the car is read first at setup.
- In tests Home Assistant retries a `SETUP_RETRY` entry on a timer; `async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))` followed by `await hass.async_block_till_done(wait_background_tasks=True)` runs the retry.
- `RateLimitError` is listed before `ApiError` below because the first matching class wins.

- [ ] **Step 1: Write the failing setup tests**

In `tests/test_coordinator.py`, replace the whole of `test_car_error_at_setup_continues` with the tests below. Add `import json` and `from pathlib import Path` to the imports, and `Vehicle` to the `pynortecgo` import. Everything else used is already imported or defined in the file.

```python
@pytest.mark.parametrize(
    ("error", "key"),
    [
        (RateLimitError("too many requests", retry_after=30.0), "rate_limited"),
        (NortecGoConnectionError("network down"), "cannot_connect"),
        (ApiError("GET /example", 500), "api_error"),
        (UnexpectedResponseError("GET /example", "bad shape"), "unexpected_response"),
        (_UnknownClientError("something new"), "car_read_failed"),
    ],
)
@pytest.mark.parametrize(
    "answer", [None, VehicleNotFoundError("no car"), MultipleVehiclesError("two cars")]
)
async def test_car_error_at_setup_retries(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    key: str,
    answer: Exception | None,
) -> None:
    """A failed car read at setup retries setup; the retry's answer decides the car device (#41)."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    identifier = car_device_identifier(str(FAKE_CHARGER_ID))
    mock_client.get_vehicle.side_effect = error
    await setup_integration(hass, mock_config_entry)

    state = mock_config_entry.state  # a local, so mypy doesn't keep the narrowing
    assert state is ConfigEntryState.SETUP_RETRY
    assert mock_config_entry.error_reason_translation_domain == DOMAIN
    assert mock_config_entry.error_reason_translation_key == key
    assert str(error) not in (mock_config_entry.reason or "")
    assert f"Reading the car failed: {error}" in caplog.text
    assert (
        device_registry.async_get_device_by_identifier(
            identifier, mock_config_entry.entry_id
        )
        is None
    )

    mock_client.get_vehicle.side_effect = answer
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    coordinator = _coordinator(mock_config_entry)
    has_car = answer is None
    assert coordinator.has_car is has_car
    assert coordinator.data.vehicle == (make_vehicle() if has_car else None)
    device = device_registry.async_get_device_by_identifier(
        identifier, mock_config_entry.entry_id
    )
    assert (device is not None) is has_car


def test_car_read_failed_text() -> None:
    """The setup car read's own text is in the strings."""
    strings = json.loads(
        (
            Path(__file__).parent.parent / "custom_components" / DOMAIN / "strings.json"
        ).read_text(encoding="utf-8")
    )
    assert strings["exceptions"]["car_read_failed"] == {
        "message": "Reading the car failed. Home Assistant will try again."
    }


@pytest.mark.parametrize(
    "error", [NortecGoConnectionError("network down"), AuthError("token rejected")]
)
async def test_failed_setup_car_read_keeps_a_stop_asked(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
) -> None:
    """A setup that fails on the car read sends no stop and keeps the stored control (D44).

    The setup that then works sends the stop the owner asked for, once.
    """
    key = f"nortec_go.{mock_config_entry.entry_id}.charge_control"
    stored = {
        "blocked_since": None,
        "start_pending_since": dt_util.utcnow().isoformat(),
        "stop_asked": True,
    }
    hass_storage[key] = {"version": 1, "key": key, "data": dict(stored)}
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    mock_client.get_vehicle.side_effect = error
    with patch.object(ConfigEntry, "async_start_reauth_if_available"):
        await setup_integration(hass, mock_config_entry)

    state = mock_config_entry.state  # a local, so mypy doesn't keep the narrowing
    assert state in (ConfigEntryState.SETUP_RETRY, ConfigEntryState.SETUP_ERROR)
    mock_client.stop_charge.assert_not_awaited()
    assert hass_storage[key]["data"] == stored

    mock_client.get_vehicle.side_effect = None
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    # The stop is sent as a background task of the entry.
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_client.stop_charge.assert_awaited_once()


async def test_control_gets_the_charger_read_before_the_car_while_running(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """While running the order is as before: the charge control first, then the car."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    calls: list[str] = []

    async def _get_vehicle() -> Vehicle:
        calls.append("car")
        return make_vehicle()

    mock_client.get_vehicle.side_effect = _get_vehicle
    with patch.object(
        coordinator.charge_control,
        "on_charger_read",
        side_effect=lambda *args: calls.append("control"),
    ):
        await coordinator.async_read_now(with_car=True)

    assert calls == ["control", "car"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_coordinator.py -q -k "test_car_error_at_setup_retries or test_car_read_failed_text or test_failed_setup_car_read_keeps_a_stop_asked or test_control_gets_the_charger_read_before_the_car_while_running"`

Expected: `test_car_error_at_setup_retries` fails on `state is ConfigEntryState.SETUP_RETRY` (the entry is `LOADED` today); `test_car_read_failed_text` fails with `KeyError: 'car_read_failed'`; `test_failed_setup_car_read_keeps_a_stop_asked` fails in both cases: with `NortecGoConnectionError` on `assert state in (…)` (the entry is `LOADED` today), with `AuthError` on `stop_charge.assert_not_awaited()` (today the control gets the charger read first and sends the stop); `test_control_gets_the_charger_read_before_the_car_while_running` passes already (it pins today's order).

- [ ] **Step 3: Add the text**

In `custom_components/nortec_go/strings.json`, in `exceptions`, right after the `read_failed` entry:

```json
    "car_read_failed": {
      "message": "Reading the car failed. Home Assistant will try again."
    },
```

Make the same edit in `custom_components/nortec_go/translations/en.json`, so the two files stay identical (`tests/test_init.py` checks it).

- [ ] **Step 4: Change the setup read in `coordinator.py`**

Below `_LOGGER = logging.getLogger(__name__)`, add the keys of the setup car read:

```python
# The setup car read's errors by class, the first match wins; anything else is car_read_failed (D44).
_SETUP_CAR_ERROR_KEYS: tuple[tuple[type[NortecGoError], str], ...] = (
    (RateLimitError, "rate_limited"),
    (NortecGoConnectionError, "cannot_connect"),
    (ApiError, "api_error"),
    (UnexpectedResponseError, "unexpected_response"),
)
```

Change the `NortecGoData` docstring's second paragraph to:

```text
    vehicle is None when the account has no single car. read_at is when the charger was
    last read successfully.
```

In `__init__`, delete the line `self._car_checked = False`.

Change `_car_due`'s docstring to `"""Read the car when asked, or when its last try is old enough (§3.2); the setup read always reads it."""`.

In `_async_update_data`, replace everything from `self.charge_control.on_charger_read(charger, start_attempts)` to the end of the method with:

```text
        read_at = dt_util.utcnow()
        setup = self.data is None
        if setup:
            # The car first: a setup that fails on it must leave the charge control as loaded,
            # or a stop asked for before the restart is sent and cancelled, or forgotten (D44).
            self._car_read_at = read_at
            vehicle = await self._async_read_setup_vehicle()
        self.charge_control.on_charger_read(charger, start_attempts)
        self._async_update_charger_device(charger)
        if not setup:
            if self._car_due(read_at):
                self._car_read_at = read_at
                self._read_car_next = False
                vehicle = await self._async_read_vehicle()
            else:
                vehicle = self._vehicle
        control = self.charge_control.state
        self.update_interval = interval_for(charger, control, timedelta(0))
        return NortecGoData(
            charger=charger, vehicle=vehicle, control=control, read_at=read_at
        )
```

Replace the whole of `_async_read_vehicle` with these two methods:

```text
    async def _async_read_setup_vehicle(self) -> Vehicle | None:
        """The setup's car read decides has_car; a failed read fails setup rather than guessing (D44)."""
        try:
            vehicle = await self.client.get_vehicle()
        except AuthError as err:
            _LOGGER.debug("Reading the car was rejected: %s", err)
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except (VehicleNotFoundError, MultipleVehiclesError) as err:
            self.has_car = False
            _LOGGER.info("No car entities: %s", err)
            return None
        except NortecGoError as err:
            _LOGGER.debug("Reading the car failed: %s", err)
            key = next(
                (
                    key
                    for error_type, key in _SETUP_CAR_ERROR_KEYS
                    if isinstance(err, error_type)
                ),
                "car_read_failed",
            )
            raise UpdateFailed(translation_domain=DOMAIN, translation_key=key) from err
        self._vehicle = vehicle
        self._async_update_car_device(vehicle)
        return vehicle

    async def _async_read_vehicle(self) -> Vehicle | None:
        """Read the car while running; only a rejected read fails the update."""
        if not self.has_car:
            return None
        try:
            vehicle = await self.client.get_vehicle()
        except AuthError as err:
            _LOGGER.debug("Reading the car was rejected: %s", err)
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except NortecGoError as err:
            self._log_car_error(err)
            return self._vehicle

        if self._car_failing:
            self._car_failing = False
            _LOGGER.info("Reading the car works again")
        self._vehicle = vehicle
        self._async_update_car_device(vehicle)
        return vehicle
```

mypy must see `vehicle` bound on every path in `_async_update_data`; if it reports it possibly unbound, declare `vehicle: Vehicle | None` before the `if setup:` block. `MultipleVehiclesError` and `VehicleNotFoundError` stay imported (the setup read uses them). A "no car" answer while running still keeps the last data after this task; Task 2 changes that.

- [ ] **Step 5: Run the new tests**

Run: `uv run pytest tests/test_coordinator.py -q -k "test_car_error_at_setup_retries or test_car_read_failed_text or test_failed_setup_car_read_keeps_a_stop_asked or test_control_gets_the_charger_read_before_the_car_while_running"`

Expected: all pass (15 + 1 + 2 + 1 = 19 tests).

- [ ] **Step 6: Replace the test of the state that no longer exists**

In `tests/test_sensor.py`, replace the whole of `test_car_placeholder_until_first_read` with the test below. The old test loads the entry with a failing car read at setup, which is now a retry. It was also the only test where the entities are created without a car name (the `translation_key` branch in `entity.py`); the test above it reaches only the coordinator's fallback on a later read. Remove any import that only the old test used (ruff reports them).

```python
async def test_car_without_a_name_at_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """A car without a name at setup: the device is called Car, and so are its entity IDs."""
    mock_client.get_vehicle.return_value = make_vehicle(name="")
    await setup_integration(hass, mock_config_entry)
    car = _device(device_registry, mock_config_entry, f"{FAKE_CHARGER_ID}_car")
    assert car is not None
    assert car.name == "Car"
    state = hass.states.get("sensor.car_battery")
    assert state is not None
    assert state.state == "55.0"
```

Run: `uv run pytest tests/test_sensor.py -q -k test_car_without_a_name_at_setup`

Expected: passes (it pins behaviour that exists; it replaces the coverage the old test gave `entity.py`).

- [ ] **Step 7: Run the whole suite**

Run: `uv run pytest -q`

Expected: all pass. If another test loaded the entry with a car read that fails at setup with an error other than "no car", it now ends in `SETUP_RETRY`; report it instead of changing what it tests.

- [ ] **Step 8: Gates and commit**

Run the gates from *Global Constraints*. Then write the message to `/tmp/car-device-lifecycle-task-1-msg.txt` with the Write tool:

```text
feat: a failed car read at setup retries setup (#41)

The setup read decides has_car and no longer guesses "a car" on a failed
car read: it fails setup as a failed charger read does, so Home Assistant
retries. At setup the car is read before the charge control gets the
charger read, so a setup that fails on the car can't send or forget a
stop asked for before the restart (D44).

<the co-author trailer from the dispatch>
```

```bash
git add tests/test_coordinator.py tests/test_sensor.py custom_components/nortec_go/coordinator.py custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json
git commit -F /tmp/car-device-lifecycle-task-1-msg.txt
```

---

### Task 2: The car that goes while running, its repair, and the device's brand and model

**Model:** opus — maps `pynortecgo` car answers to entities and the device, and changes the fix-flow choice next to the start-block repair.
**Wave:** 2

**Files:**
- Modify: `tests/test_coordinator.py`
- Modify: `tests/test_init.py`
- Modify: `tests/test_repairs.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `custom_components/nortec_go/const.py`
- Modify: `custom_components/nortec_go/coordinator.py` (`__init__`, `_async_read_vehicle`, `_async_update_car_device`, new `car_gone`, `_async_car_gone`, `_async_delete_car_issue`, the `NortecGoData` docstring)
- Modify: `custom_components/nortec_go/repairs.py`
- Modify: `custom_components/nortec_go/diagnostics.py`
- Modify: `custom_components/nortec_go/entity.py` (docstrings only)
- Modify: `custom_components/nortec_go/binary_sensor.py` (one docstring only)
- Modify: `custom_components/nortec_go/strings.json`
- Modify: `custom_components/nortec_go/translations/en.json`

**Interfaces:**
- Consumes: Task 1's `_async_read_vehicle` (the running car read) and `_async_read_setup_vehicle`; `START_BLOCKED_ISSUE_ID` and `StartBlockedRepairFlow` as they are.
- Produces:
  - `CAR_GONE_ISSUE_ID: Final = "car_gone_{entry_id}"` in `const.py`
  - `NortecGoCoordinator.car_gone -> bool` (read-only property)
  - `CarGoneRepairFlow(entry_id: str)` in `repairs.py`
  - the issue translation key `car_gone` and the diagnostics key `coordinator.car_gone`

Facts you need:
- `NortecGoCarEntity.available` is `super().available and self.coordinator.data.vehicle is not None`. Setting `data.vehicle` to `None` is what makes the car entities unavailable; `entity.py`'s code doesn't change.
- A read where the car isn't due returns the cached `self._vehicle`, so the gone state must clear that cache.
- `ir.async_delete_issue` on a missing issue does nothing. An issue with `is_persistent=False` is dropped by a restart. A fix flow that ends with `async_create_entry` deletes its issue itself.
- `DeviceRegistry.async_get_or_create(..., manufacturer=None, model=None)` clears those fields on an existing device; `UNDEFINED` leaves them.
- A custom `RepairsFlow` doesn't get the issue's placeholders; it passes `description_placeholders` itself, as `StartBlockedRepairFlow` does.
- `hass.config_entries.async_schedule_reload(entry_id)` raises `UnknownEntry` for a missing entry, so the flow checks the entry first.

- [ ] **Step 1: Write the failing coordinator tests**

In `tests/test_coordinator.py`: add `from homeassistant.helpers import issue_registry as ir` to the imports (extend the existing `homeassistant.helpers` import) and `CAR_GONE_ISSUE_ID` to the `custom_components.nortec_go.const` import.

Replace the whole of `test_later_car_error_keeps_car_data` with:

```python
async def test_later_car_error_keeps_car_data(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A later car error that isn't "no car" keeps the last car data, logs once, and logs the recovery."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_vehicle.side_effect = ApiError("GET /example", 500)
    for _ in range(2):
        await coordinator.async_read_now(with_car=True)
        assert coordinator.last_update_success
        assert coordinator.car_read_failing
        assert not coordinator.car_gone
        assert coordinator.data.vehicle == make_vehicle()
    assert caplog.text.count("Could not read the car") == 1

    mock_client.get_vehicle.side_effect = None
    await coordinator.async_read_now(with_car=True)
    assert "Reading the car works again" in caplog.text


@pytest.mark.parametrize(
    "error", [VehicleNotFoundError("no car"), MultipleVehiclesError("two cars")]
)
async def test_car_gone_while_running(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
) -> None:
    """A "no car" answer while running: no car data, a repair issue, one warning; a good read ends it (D44)."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    issues = ir.async_get(hass)
    issue_id = CAR_GONE_ISSUE_ID.format(entry_id=mock_config_entry.entry_id)
    assert issues.async_get_issue(DOMAIN, issue_id) is None
    assert not coordinator.car_gone

    mock_client.get_vehicle.side_effect = error
    for _ in range(2):
        await coordinator.async_read_now(with_car=True)
        assert coordinator.last_update_success
        assert coordinator.has_car
        assert coordinator.car_gone
        assert coordinator.car_read_failing
        assert coordinator.data.vehicle is None
    assert caplog.text.count("no longer has exactly one car") == 1
    issue = issues.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "car_gone"
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable
    assert not issue.is_persistent
    assert issue.translation_placeholders == {"name": mock_config_entry.title}
    assert issue.data == {"entry_id": mock_config_entry.entry_id}

    # A read of the charger alone must not bring the old car's data back.
    car_reads = mock_client.get_vehicle.await_count
    await coordinator.async_read_now()
    assert mock_client.get_vehicle.await_count == car_reads
    assert coordinator.data.vehicle is None

    # Another car error keeps it gone, with no second warning.
    mock_client.get_vehicle.side_effect = ApiError("GET /example", 500)
    await coordinator.async_read_now(with_car=True)
    assert coordinator.car_gone
    assert coordinator.data.vehicle is None
    assert "Could not read the car" not in caplog.text

    mock_client.get_vehicle.side_effect = None
    await coordinator.async_read_now(with_car=True)
    assert not coordinator.car_gone
    assert not coordinator.car_read_failing
    assert coordinator.data.vehicle == make_vehicle()
    assert issues.async_get_issue(DOMAIN, issue_id) is None
    assert "Reading the car works again" in caplog.text


async def test_car_gone_warns_after_another_car_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The "no car" warning is logged also when another car error was logged just before."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_vehicle.side_effect = ApiError("GET /example", 500)
    await coordinator.async_read_now(with_car=True)
    assert coordinator.data.vehicle == make_vehicle()
    assert caplog.text.count("Could not read the car") == 1

    mock_client.get_vehicle.side_effect = VehicleNotFoundError("no car")
    await coordinator.async_read_now(with_car=True)
    assert coordinator.car_gone
    assert coordinator.data.vehicle is None
    assert caplog.text.count("no longer has exactly one car") == 1


async def test_car_gone_issue_deleted_at_unload(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """The issue doesn't outlive the loaded entry."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    issues = ir.async_get(hass)
    issue_id = CAR_GONE_ISSUE_ID.format(entry_id=mock_config_entry.entry_id)

    mock_client.get_vehicle.side_effect = VehicleNotFoundError("no car")
    await coordinator.async_read_now(with_car=True)
    assert issues.async_get_issue(DOMAIN, issue_id) is not None

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert issues.async_get_issue(DOMAIN, issue_id) is None


async def test_car_device_follows_another_car(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Another car: the device takes its name and drops a brand and model it lacks; the owner's name stays."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    device = device_registry.async_get_device_by_identifier(
        car_device_identifier(str(FAKE_CHARGER_ID)), mock_config_entry.entry_id
    )
    assert device is not None
    assert (device.manufacturer, device.model) == ("Example", "Model E")
    device_registry.async_update_device(device.id, name_by_user="My car")

    mock_client.get_vehicle.return_value = make_vehicle(
        name="Other car", brand=None, model=""
    )
    await coordinator.async_read_now(with_car=True)

    updated = device_registry.async_get(device.id, include_child_devices=False)
    assert updated is not None
    assert (
        updated.name,
        updated.name_by_user,
        updated.manufacturer,
        updated.model,
    ) == ("Other car", "My car", None, None)
```

In the existing `test_no_car`, add after `assert caplog.text.count("No car entities") == 1`:

```text
    issue_id = CAR_GONE_ISSUE_ID.format(entry_id=mock_config_entry.entry_id)
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert not coordinator.car_gone
```

- [ ] **Step 2: Write the failing entity, repair and diagnostics tests**

In `tests/test_init.py`, add `STATE_UNAVAILABLE` to the `homeassistant.const` import, and after `test_reload_without_car_removes_car_device`:

```python
@pytest.mark.parametrize(
    "error",
    [VehicleNotFoundError("no car"), MultipleVehiclesError("two cars")],
)
async def test_car_gone_makes_the_car_entities_unavailable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
) -> None:
    """While the car is gone its entities are unavailable but still there; a good read brings them back."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    entity_registry = er.async_get(hass)

    mock_client.get_vehicle.side_effect = error
    await coordinator.async_read_now(with_car=True)
    await hass.async_block_till_done()
    for entity_id in CAR_ENTITY_IDS:
        assert entity_registry.async_get(entity_id) is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_UNAVAILABLE

    mock_client.get_vehicle.side_effect = None
    await coordinator.async_read_now(with_car=True)
    await hass.async_block_till_done()
    for entity_id in CAR_ENTITY_IDS:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state != STATE_UNAVAILABLE
    battery = hass.states.get("sensor.family_car_battery")
    assert battery is not None
    assert battery.state == "55.0"
```

In `tests/test_repairs.py`, keep the standard-library imports (`HTTPStatus`, `Any`, `cast`, `AsyncMock`); the third-party and local imports become:

```python
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.setup import async_setup_component
from pynortecgo import VehicleNotFoundError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.nortec_go.const import CAR_GONE_ISSUE_ID, DOMAIN
from custom_components.nortec_go.coordinator import car_device_identifier

from .conftest import FAKE_CHARGER_ID, make_charger, setup_integration
```

and add `import json` and `from pathlib import Path` at the top. Then add at the end of the file (the existing tests stay as they are):

```python
async def _car_gone(
    hass: HomeAssistant, entry: MockConfigEntry, mock_client: AsyncMock
) -> str:
    """Set the entry up and let the car go; return the issue's ID."""
    await setup_integration(hass, entry)
    assert await async_setup_component(hass, "repairs", {})
    mock_client.get_vehicle.side_effect = VehicleNotFoundError("no car")
    await entry.runtime_data.async_read_now(with_car=True)
    await hass.async_block_till_done()
    return CAR_GONE_ISSUE_ID.format(entry_id=entry.entry_id)


async def test_car_gone_fix_reloads_and_removes_the_car_device(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Confirming reloads the entry; with the car still gone, its device and entities go."""
    issue_id = await _car_gone(hass, mock_config_entry, mock_client)
    identifier = car_device_identifier(str(FAKE_CHARGER_ID))
    entry_id = mock_config_entry.entry_id
    assert device_registry.async_get_device_by_identifier(identifier, entry_id)
    assert entity_registry.async_get("sensor.family_car_battery") is not None

    client = await hass_client()
    flow = await _start_fix(client, issue_id)
    assert flow["step_id"] == "confirm"
    assert flow["description_placeholders"] == {"name": mock_config_entry.title}
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}", json={})
    assert (await resp.json())["type"] == "create_entry"
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert not mock_config_entry.runtime_data.has_car
    assert device_registry.async_get_device_by_identifier(identifier, entry_id) is None
    assert entity_registry.async_get("sensor.family_car_battery") is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_car_gone_fix_keeps_a_car_that_is_back(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Confirming when the car is back: the reload keeps the device and its entities."""
    issue_id = await _car_gone(hass, mock_config_entry, mock_client)
    mock_client.get_vehicle.side_effect = None

    client = await hass_client()
    flow = await _start_fix(client, issue_id)
    resp = await client.post(f"/api/repairs/issues/fix/{flow['flow_id']}", json={})
    assert (await resp.json())["type"] == "create_entry"
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.has_car
    assert device_registry.async_get_device_by_identifier(
        car_device_identifier(str(FAKE_CHARGER_ID)), mock_config_entry.entry_id
    )
    battery = hass.states.get("sensor.family_car_battery")
    assert battery is not None
    assert battery.state == "55.0"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_car_gone_fix_aborts_without_the_entry(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """An issue whose entry no longer exists: the flow aborts with entry_not_found."""
    await setup_integration(hass, mock_config_entry)
    assert await async_setup_component(hass, "repairs", {})
    issue_id = CAR_GONE_ISSUE_ID.format(entry_id="missing")
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="car_gone",
        translation_placeholders={"name": "Gone"},
        data={"entry_id": "missing"},
    )

    client = await hass_client()
    flow = await _start_fix(client, issue_id)
    assert flow["type"] == "abort"
    assert flow["reason"] == "entry_not_found"


def test_car_gone_texts() -> None:
    """The issue's texts, word for word."""
    strings = json.loads(
        (
            Path(__file__).parent.parent / "custom_components" / DOMAIN / "strings.json"
        ).read_text(encoding="utf-8")
    )
    assert strings["issues"]["car_gone"] == {
        "title": "The Nortec Go account of {name} no longer has exactly one car",
        "fix_flow": {
            "step": {
                "confirm": {
                    "title": "Remove the car device of {name}",
                    "description": (
                        "The Nortec Go account no longer has exactly one car, so the car's"
                        " entities are unavailable.\n\nIf the car comes back on the account,"
                        " they work again by themselves and this notice goes away. To remove"
                        " the car device and its entities now, select **Submit**: the"
                        " integration reloads. A restart of Home Assistant removes them too,"
                        " if the account still doesn't have exactly one car."
                    ),
                }
            },
            "abort": {"entry_not_found": "The Nortec Go entry no longer exists."},
        },
    }
```

In `tests/test_diagnostics.py`, add `"car_gone": False,` right after `"car_read_failing": False,` in the expected output of the full-download test (the dict that holds `"has_car": True`), and add this test after `test_no_car_and_no_prices`:

```python
async def test_car_gone_is_in_the_download(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    hass_admin_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """A car that went while running: car_gone is true, has_car stays true, and there is no car data."""
    await setup_integration(hass, mock_config_entry)
    mock_client.get_vehicle.side_effect = VehicleNotFoundError("fake no car")
    await mock_config_entry.runtime_data.async_read_now(with_car=True)

    data = await _download(hass, hass_client, hass_admin_user, mock_config_entry)
    assert data["coordinator"]["has_car"] is True
    assert data["coordinator"]["car_gone"] is True
    assert data["coordinator"]["car_read_failing"] is True
    assert data["data"]["vehicle"] is None
```

- [ ] **Step 3: Run them to see them fail**

Run: `uv run pytest tests/test_coordinator.py tests/test_init.py tests/test_repairs.py tests/test_diagnostics.py -q`

Expected: collection of `tests/test_coordinator.py` and `tests/test_repairs.py` fails with `ImportError: cannot import name 'CAR_GONE_ISSUE_ID'`; in the other two files the new tests fail (`test_car_gone_makes_the_car_entities_unavailable` on `STATE_UNAVAILABLE`, the diagnostics tests on the missing `car_gone` key).

- [ ] **Step 4: The constant and the texts**

In `custom_components/nortec_go/const.py`, right after `START_BLOCKED_ISSUE_ID`:

```python
# The repair issue for a car that went from the account while running (D44).
CAR_GONE_ISSUE_ID: Final = "car_gone_{entry_id}"
```

In `custom_components/nortec_go/strings.json`, in `issues`, after the `start_blocked_store` entry (add the comma after its closing brace):

```json
    "car_gone": {
      "title": "The Nortec Go account of {name} no longer has exactly one car",
      "fix_flow": {
        "step": {
          "confirm": {
            "title": "Remove the car device of {name}",
            "description": "The Nortec Go account no longer has exactly one car, so the car's entities are unavailable.\n\nIf the car comes back on the account, they work again by themselves and this notice goes away. To remove the car device and its entities now, select **Submit**: the integration reloads. A restart of Home Assistant removes them too, if the account still doesn't have exactly one car."
          }
        },
        "abort": {
          "entry_not_found": "The Nortec Go entry no longer exists."
        }
      }
    }
```

Make the same edit in `custom_components/nortec_go/translations/en.json`.

- [ ] **Step 5: The gone state in `coordinator.py`**

Imports: add `issue_registry as ir` to the `homeassistant.helpers` import (`from homeassistant.helpers import device_registry as dr, issue_registry as ir`), and `CAR_GONE_ISSUE_ID` to the `.const` import.

Change the `NortecGoData` docstring's second paragraph to:

```text
    vehicle is None when the account has no single car, at setup or since (D44). read_at is
    when the charger was last read successfully.
```

In `__init__`, add `self._car_gone = False` right after `self._car_failing = False`, and after the line `entry.async_on_unload(self._async_cancel_price_retry)` add:

```text
        # Once, here: the issue must not outlive this coordinator, however setup or unload goes.
        entry.async_on_unload(self._async_delete_car_issue)
```

After the `car_read_failing` property, add:

```text
    @property
    def car_gone(self) -> bool:
        """Whether the car went from the account while running: from a "no car" answer to the next good read (D44)."""
        return self._car_gone
```

In `_async_read_vehicle`, add a branch for "no car" before the `except NortecGoError` one, and end the gone state on a good read. The method becomes:

```text
    async def _async_read_vehicle(self) -> Vehicle | None:
        """Read the car while running; only a rejected read fails the update."""
        if not self.has_car:
            return None
        try:
            vehicle = await self.client.get_vehicle()
        except AuthError as err:
            _LOGGER.debug("Reading the car was rejected: %s", err)
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except (VehicleNotFoundError, MultipleVehiclesError) as err:
            self._async_car_gone(err)
            return None
        except NortecGoError as err:
            self._log_car_error(err)
            return self._vehicle

        if self._car_failing:
            self._car_failing = False
            _LOGGER.info("Reading the car works again")
        if self._car_gone:
            self._car_gone = False
            self._async_delete_car_issue()
        self._vehicle = vehicle
        self._async_update_car_device(vehicle)
        return vehicle
```

After `_log_car_error`, add:

```text
    @callback
    def _async_car_gone(self, err: NortecGoError) -> None:
        """The account no longer has exactly one car: drop its data and raise the repair issue (D44).

        Nothing is removed here; the next setup removes the device.
        """
        self._vehicle = None  # also for the reads where the car isn't due
        self._car_failing = True
        if self._car_gone:
            return
        self._car_gone = True
        _LOGGER.warning(
            "The account no longer has exactly one car; the car's entities are unavailable: %s",
            err,
        )
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            CAR_GONE_ISSUE_ID.format(entry_id=self.config_entry.entry_id),
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="car_gone",
            translation_placeholders={"name": self.config_entry.title},
            data={"entry_id": self.config_entry.entry_id},
        )

    @callback
    def _async_delete_car_issue(self) -> None:
        """Delete the car's repair issue, if there is one."""
        ir.async_delete_issue(
            self.hass,
            DOMAIN,
            CAR_GONE_ISSUE_ID.format(entry_id=self.config_entry.entry_id),
        )
```

In `_async_update_car_device`, write the brand and model on every read, so a car without them clears the old car's:

```text
            manufacturer=vehicle.brand or None,
            model=vehicle.model or None,
```

(these replace `manufacturer=vehicle.brand or UNDEFINED,` and `model=vehicle.model or UNDEFINED,`; the `name` and `translation_key` lines stay). Change the method's docstring to `"""Bring the car device's name, brand and model up to date, also for another car (D44)."""`.

- [ ] **Step 6: Diagnostics and the entity docstrings**

In `custom_components/nortec_go/diagnostics.py`, right after `"car_read_failing": coordinator.car_read_failing,`:

```text
                "car_gone": coordinator.car_gone,
```

In `custom_components/nortec_go/entity.py`, change three docstrings and nothing else:
- `NortecGoCarEntity`: `"""An entity on the car device; unavailable while the car is gone from the account (D44)."""`
- its `__init__`: `"""Attach the entity to the car device, named "Car" when the car has no name."""`
- its `available`: `"""Available when the last update worked and the account has its car."""`

In `custom_components/nortec_go/binary_sensor.py`, change one docstring and nothing else: `NortecGoCarBinarySensor.is_on`'s `"""The value from the charger and the car, or None before the car is read."""` becomes `"""The value from the charger and the car, or None while the car is gone."""`.

- [ ] **Step 7: The fix flow in `repairs.py`**

Change the module docstring to `"""The Nortec Go repair fix flows: allow charge starts again (§3.5), and remove a car that is gone (D44)."""`, add `from .const import CAR_GONE_ISSUE_ID` above the `.entry` import, add this class after `StartBlockedRepairFlow`:

```python
class CarGoneRepairFlow(RepairsFlow):
    """One confirm step that reloads the entry; its setup removes a car device without a car."""

    def __init__(self, entry_id: str) -> None:
        """Remember the entry the issue belongs to."""
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Go to the confirm step."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Reload the entry when the owner confirms."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="entry_not_found")
        if user_input is not None:
            self.hass.config_entries.async_schedule_reload(self._entry_id)
            return self.async_create_entry(data={})
        return self.async_show_form(
            step_id="confirm", description_placeholders={"name": entry.title}
        )
```

and replace `async_create_fix_flow` with:

```python
async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the fix flow for a car_gone or a start_blocked issue."""
    assert data is not None  # every issue is created with its entry ID
    entry_id = str(data["entry_id"])
    if issue_id == CAR_GONE_ISSUE_ID.format(entry_id=entry_id):
        return CarGoneRepairFlow(entry_id)
    return StartBlockedRepairFlow(entry_id)
```

- [ ] **Step 8: Run the tests**

Run: `uv run pytest tests/test_coordinator.py tests/test_init.py tests/test_repairs.py tests/test_diagnostics.py -q`

Expected: all pass, the unchanged start-block tests in `tests/test_repairs.py` included.

Then run: `uv run pytest -q`

Expected: all pass. A test elsewhere that expected a later "no car" answer to keep the car's data now sees `None`; change only that expectation, and report it.

- [ ] **Step 9: Gates and commit**

Run the gates from *Global Constraints*. Then write the message to `/tmp/car-device-lifecycle-task-2-msg.txt` with the Write tool:

```text
feat: a car that goes while running is unavailable, with a repair (#42)

A "no car" answer while running drops the car's data, so its entities
are unavailable, and raises a repair issue whose fix reloads the entry;
the reload's setup removes the device. Nothing is added or removed while
running (D44). A good read ends it. The car device takes another car's
brand and model, also when it has none. Diagnostics show car_gone.

<the co-author trailer from the dispatch>
```

```bash
git add tests/test_coordinator.py tests/test_init.py tests/test_repairs.py tests/test_diagnostics.py custom_components/nortec_go/const.py custom_components/nortec_go/coordinator.py custom_components/nortec_go/repairs.py custom_components/nortec_go/diagnostics.py custom_components/nortec_go/entity.py custom_components/nortec_go/binary_sensor.py custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json
git commit -F /tmp/car-device-lifecycle-task-2-msg.txt
```

---

### Task 3: User docs, D44, the CHANGELOG entry and the quality scale comments

**Model:** opus — a docs task (D33).
**Wave:** 1 (started ahead of its inputs, Tasks 1 and 2; held until both are on the feature branch, then re-checked against that code and only then picked: `docs/way-of-working.md` §1, *Starting ahead of inputs*)

**Files:**
- Modify: `docs/user/nortec_go.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/decisions.md`
- Modify: `custom_components/nortec_go/quality_scale.yaml`

**Interfaces:**
- Consumes: the behaviour of Tasks 1 and 2, through the names in *Global Constraints* (the issue's title text, `car_read_failed`'s text, D44). It edits no code and can be written before they land, but it isn't picked onto the feature branch before they are.
- Produces: nothing other tasks use.

`tests/test_quality_scale.py` doesn't change: both rules stay `todo`.

- [ ] **Step 1: `docs/user/nortec_go.md`, *Prerequisites***

Replace the sentence `A car added later appears after you reload the integration.` with:

```markdown
A car added to the account later appears after you reload the integration (see *Known limitations*).
```

Keep the paragraph's line wrapping at the file's width.

- [ ] **Step 2: `docs/user/nortec_go.md`, *Car***

Replace the paragraph that starts `Values the car doesn't report show as unknown. Until the car has been read once,` (through `rename them in the entity settings if you like.`) with:

```markdown
Values the car doesn't report show as unknown.

If the car goes from the account, or a second car is added, the car's entities become unavailable and a
repair notice offers to remove the car device (see *Troubleshooting*). If you replace the car with another
one, the same device takes the new car's name, brand and model. The entity IDs keep the old car's name;
rename them in the entity settings if you like.
```

- [ ] **Step 3: `docs/user/nortec_go.md`, *Known limitations***

Replace the bullet `- A car removed from the account, with its entities, disappears after you reload the integration.` with:

```markdown
- The car device is added and removed only when the integration starts (a reload, or a restart of Home
  Assistant), never while it runs. A car added to the account appears after a reload. One removed makes its
  entities unavailable until then.
```

- [ ] **Step 4: `docs/user/nortec_go.md`, *Troubleshooting***

Add these two entries right after the `"Starts are blocked"` entry and before `### Debug logging`:

```markdown
### "The Nortec Go account … no longer has exactly one car"

The account had one car when the integration started, and now has none or more than one, so the car's
entities are unavailable. If the car comes back on the account, they work again by themselves and the
notice goes away. To remove the car device and its entities, select **Submit** in the notice: the
integration reloads. Reloading the integration yourself, or restarting Home Assistant, does the same.

### "Reading the car failed"

When the integration starts, it reads the charger and then the car. If the car can't be read then (the
service can't be reached, limits requests or returns an error), Home Assistant tries the start again by
itself: first after a few seconds (or, while Home Assistant itself is starting, when it has started), then
at longer gaps of up to 10 minutes. Until a try works, all the integration's entities are unavailable,
*Charge* included. The integration's entry shows the reason, which can also be one of the texts for a
service that can't be reached, limits requests or returns an error.
```

- [ ] **Step 5: `CHANGELOG.md`**

Under `## [Unreleased]`, add (the section is empty now):

```markdown
### Changed

- If the car can't be read when the integration starts, the start is tried again until the service answers,
  instead of adding a car device that may not exist. All entities are unavailable until then.
- A car that goes from the account while Home Assistant runs makes its entities unavailable and raises a
  repair notice that offers to remove the car device. Before, the entities kept showing the last data.

### Fixed

- An account without a car no longer keeps an unavailable *Car* device after a failed first car read.
- After a change of car, the car device no longer keeps the old car's brand and model.
- A stop asked for before a restart is no longer lost when the car read is rejected at the start.
```

- [ ] **Step 6: `docs/decisions.md`**

Add at the end of the file, after D43:

```markdown
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
```

- [ ] **Step 7: `custom_components/nortec_go/quality_scale.yaml`**

Replace the two comments; the statuses stay `todo`:

```yaml
  dynamic-devices:
    status: todo
    comment: "Deliberately not done (D44): car entities are added only at setup, so a car added to the account shows up after a reload."
```

```yaml
  stale-devices:
    status: todo
    comment: "Deliberately not done while running (D44): a car that goes from the account makes its entities unavailable and raises a repair issue whose fix reloads the entry; the device is removed at setup. No async_remove_config_entry_device."
```

- [ ] **Step 8: Check and commit**

Run: `uv run pytest tests/test_quality_scale.py -q`

Expected: all pass (the comments hold no `#`, which would cut them short).

Check that the relative link in D44 resolves from `docs/`: `ls docs/superpowers/specs/2026-10-01-car-device-lifecycle-design.md`.

Run the gates from *Global Constraints*. Then write the message to `/tmp/car-device-lifecycle-task-3-msg.txt` with the Write tool:

```text
docs: the car device is decided at setup (#41, #42)

User docs, D44, the CHANGELOG entry and the quality scale comments for
the car device rule: added and removed only at setup; unavailable with
a repair notice when the car goes while running.

<the co-author trailer from the dispatch>
```

```bash
git add docs/user/nortec_go.md CHANGELOG.md docs/decisions.md custom_components/nortec_go/quality_scale.yaml
git commit -F /tmp/car-device-lifecycle-task-3-msg.txt
```

---

## After the tasks (the controller)

- Task 3 is held, not picked, until Tasks 1 and 2 are on the feature branch. Then re-review it against that head (the issue's title text, `car_read_failed`'s text, the behaviour its texts describe, D44) and pick it.
- Learnings (way-of-working §1 step 8), the branch review, then the bump step (`docs/releasing.md`) as the last step before `branch ready`. The PR title is `feat: …`, and its body has a separate `Closes #41` and `Closes #42`.
