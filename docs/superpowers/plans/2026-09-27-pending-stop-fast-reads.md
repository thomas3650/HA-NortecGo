# Pending stop, fast reads and a Last read sensor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** The Charge switch stays off after a stop until the charger catches up, the charger is read every 30 s while a charge starts or stops, a *Last read* sensor shows the data's age, the charger device follows a rename, an unknown client error fails a read cleanly, and pin bumps re-check the client's errors.

**Architecture:** `ChargeControl` gains a pending stop that isn't stored. The coordinator picks its interval from `charge_status()`, reads right away with `async_refresh()` after an action, skips the car on fast reads, and stamps each read with `read_at`, which a new diagnostic sensor shows. Docs and the decision log follow.

**Tech Stack:** Python 3.14, Home Assistant custom integration, `pynortecgo` 0.2.0 (always mocked in tests), pytest with `pytest-homeassistant-custom-component` and freezegun, uv.

**Spec:** `docs/superpowers/specs/2026-09-27-pending-stop-fast-reads-design.md` (issues #30, #22, #23, #16).

## Global Constraints

- TDD: write the failing test, see it fail, then the code. Tests always mock `pynortecgo`; fixtures come from `pynortecgo` model objects and `tests/conftest.py` helpers, never raw API JSON (hard rules 2, 7).
- Never start or stop a real charge (hard rule 2). Never retry `start_charge` (hard rule 6).
- Nothing private (hard rule 3): no IDs, tokens, emails, captures, raw endpoints or links into the private repo.
- Gates before every commit (`CLAUDE.md` → Commands): `uv run pytest -q`, `uv run ruff check && uv run ruff format --check && uv run mypy`; the coverage gate (`--cov-fail-under=95`) passes at the end of each task.
- Subagents write commit messages with the Write tool to a file outside the repo and commit with `git commit -F <file>` (no heredocs). End each message with the co-author trailer given in the dispatch.
- Match the surrounding code: its comment density, docstring style (one line, a period), names.
- Constants: `INTERVAL_CHANGING = 30 s`, `INTERVAL_CHARGING = 5 min`, `INTERVAL_IDLE = 60 min`, `CAR_READ_MIN_AGE = INTERVAL_CHARGING - INTERVAL_CHANGING` (4.5 min), `STOP_CONFIRM_TIMEOUT = 2 min`.
- New translation keys: exception `stop_pending`; sensor `last_read` ("Last read"). `strings.json` and `translations/en.json` stay identical.

## Review Focus

1. A `turn_off` between the read that queues the background stop and the background stop running must not send a second `stop_charge()` (Task 1 test `test_turn_off_before_the_background_stop_is_noop`).
2. A start whose read right away fails must still be read again 30 s later, not 60 min later (Task 3 test `test_start_whose_read_fails_is_read_again_after_30_s`).
3. The 5-minute read that fires up to about 1 s early must still read the car (Task 3 test `test_car_read_on_an_early_charging_read`).
4. Two actions within HA's 10 s debounce cooldown each get their own read right away (Task 3 tests `test_actions_within_the_cooldown_each_read_right_away` and `test_press_twice_reads_twice`).
5. An upgrade from a stored start guard of the current shape must not block starts, and the pending stop must never reach the store (Task 1 test `test_pending_stop_is_not_stored`).

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (pending stop), Task 2 (pin-bump checklist) | Disjoint files: two worktrees |
| 2 | Task 3 (reads) | Needs Task 1's `ChargeControlState.stop_pending` |
| 3 | Task 4 (Last read sensor), Task 5 (rename and catch-all) | Disjoint files: two worktrees; both need Task 3 |
| 4 | Task 6 (docs, changelog, quality scale, decision log) | Shared files, last |

No task has guarded files.

---

### Task 1: Pending stop

**Model:** opus — near charge start and stop.
**Wave:** 1

**Files:**
- Modify: `custom_components/nortec_go/const.py` (add `STOP_CONFIRM_TIMEOUT`)
- Modify: `custom_components/nortec_go/charge_control.py`
- Modify: `custom_components/nortec_go/switch.py` (`is_on` docstring)
- Modify: `custom_components/nortec_go/strings.json`, `custom_components/nortec_go/translations/en.json` (exception `stop_pending`)
- Test: `tests/test_charge_control.py`, `tests/test_switch.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ChargeControlState(blocked: bool = False, start_pending: bool = False, stop_asked: bool = False, stop_pending: bool = False)`; `is_charge_on` and `charge_status` honour `stop_pending`; `STOP_CONFIRM_TIMEOUT` in `const.py`. The `ChargeControl.start_pending` property stays in this task (the coordinator still uses it; Task 3 removes it).

- [ ] **Step 1: Rename the test constant and write the pure-function tests**

In `tests/test_charge_control.py`, rename the existing constant `PENDING_STOP` to `STOP_ASKED` everywhere in the file (it means a stop asked during a pending start), and add below it:

```python
STOP_PENDING = ChargeControlState(stop_pending=True)
```

Add to `test_is_charge_on`'s parameter list:

```python
((ChargeState.CHARGING, STOP_PENDING, False),)
((ChargeState.PAUSED, STOP_PENDING, False),)
```

Add to `test_charge_status`'s parameter list:

```python
((CHARGING, STOP_PENDING, "stopping"),)
((CHARGING, ChargeControlState(blocked=True, stop_pending=True), "start_blocked"),)
```

Change the import from `custom_components.nortec_go.const` to:

```python
from custom_components.nortec_go.const import (
    DOMAIN,
    START_CONFIRM_TIMEOUT,
    STOP_CONFIRM_TIMEOUT,
)
```

- [ ] **Step 2: Write the control tests**

Add `import contextlib` at the top. Add these tests to `tests/test_charge_control.py` (after `test_stop_connection_error_asks_for_a_read`):

```python
async def test_stop_sets_pending_stop(
    control: ChargeControl, client: AsyncMock, on_change: MagicMock
) -> None:
    """A successful stop is pending: the switch shows off until the charger follows."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_PENDING
    on_change.assert_called()


@pytest.mark.parametrize(
    "error",
    [
        NoActiveChargeError("x"),
        ChargeNotStoppableError("x"),
        NortecGoConnectionError("x"),
    ],
)
async def test_stop_without_success_sets_no_pending_stop(
    control: ChargeControl, client: AsyncMock, error: Exception
) -> None:
    """No charge to stop, or a failed stop: nothing to wait for."""
    control.on_charger_read(CHARGING, control.start_attempts)
    client.stop_charge.side_effect = error
    with contextlib.suppress(HomeAssistantError):
        await control.async_stop()
    assert control.state == IDLE


async def test_stop_while_stop_pending_is_noop(
    control: ChargeControl, client: AsyncMock
) -> None:
    """A second turn_off while the stop is pending makes no API call."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    client.stop_charge.assert_awaited_once()


async def test_start_while_stop_pending_is_refused(
    control: ChargeControl, client: AsyncMock
) -> None:
    """turn_on while a stop is pending raises stop_pending; no start, no attempt counted."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    attempts = control.start_attempts
    with pytest.raises(ServiceValidationError) as exc_info:
        await control.async_start()
    assert exc_info.value.translation_key == "stop_pending"
    client.start_charge.assert_not_awaited()
    assert control.start_attempts == attempts


@pytest.mark.parametrize(
    "charger",
    [
        make_charger(
            is_connected=True,
            charge_state=ChargeState.STOPPING,
            state=ChargerState.BUSY_CHARGING,
        ),
        make_charger(is_connected=True, charge_state=ChargeState.COMPLETED),
        make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
        make_charger(is_connected=False),
    ],
)
async def test_pending_stop_ends_when_the_charge_is_not_on(
    control: ChargeControl, charger: Any
) -> None:
    """A read with STOPPING, COMPLETED or no open charge ends the pending stop."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(charger, control.start_attempts)
    assert control.state == IDLE


@pytest.mark.parametrize("charge_state", [ChargeState.CHARGING, ChargeState.PAUSED])
async def test_pending_stop_stays_while_the_charge_is_on(
    control: ChargeControl, charge_state: ChargeState
) -> None:
    """A read that still shows the charge on (the charger lags) keeps the pending stop."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(
        make_charger(is_connected=True, charge_state=charge_state),
        control.start_attempts,
    )
    assert control.state == STOP_PENDING


async def test_pending_stop_stays_on_a_stale_read(control: ChargeControl) -> None:
    """A stale read (begun before the latest start attempt) still showing CHARGING keeps it."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts - 1)
    assert control.state == STOP_PENDING


async def test_pending_stop_times_out_on_a_read(
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """After 2 minutes a read ends the pending stop, with a warning."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    freezer.tick(STOP_CONFIRM_TIMEOUT - timedelta(seconds=1))
    control.on_charger_read(CHARGING, control.start_attempts)
    assert control.state == STOP_PENDING
    freezer.tick(timedelta(seconds=1))
    control.on_charger_read(CHARGING, control.start_attempts)
    assert control.state == IDLE
    assert "No stop seen within" in caplog.text


async def test_stop_after_the_timeout_without_a_read(
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With no read for 2 minutes, turn_off counts the pending stop as ended and stops again."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    freezer.tick(STOP_CONFIRM_TIMEOUT)
    await control.async_stop()
    assert client.stop_charge.await_count == 2
    assert "No stop seen within" in caplog.text


async def test_start_after_the_timeout_takes_the_normal_checks(
    control: ChargeControl, client: AsyncMock, freezer: FrozenDateTimeFactory
) -> None:
    """With no read for 2 minutes, turn_on isn't refused; the open charge makes it a no-op."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    freezer.tick(STOP_CONFIRM_TIMEOUT)
    await control.async_start()
    client.start_charge.assert_not_awaited()
    assert control.state == IDLE


async def test_background_stop_shows_off_at_once(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """The read that queues the background stop already shows the switch off and Stopping."""
    await control.async_start()
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts)
    assert control.state == STOP_PENDING
    assert not is_charge_on(CHARGING, control.state)
    assert charge_status(CHARGING, control.state) == "stopping"
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    assert control.state == STOP_PENDING


async def test_turn_off_before_the_background_stop_is_noop(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock
) -> None:
    """A turn_off before the queued background stop runs sends no second stop (Review Focus 1)."""
    await control.async_start()
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()


@pytest.mark.parametrize(
    "error", [NoActiveChargeError("x"), ChargeNotStoppableError("x")]
)
async def test_background_stop_without_success_ends_pending_stop(
    hass: HomeAssistant, control: ChargeControl, client: AsyncMock, error: Exception
) -> None:
    """The background stop finds no charge or fails: the pending stop it queued ends."""
    client.stop_charge.side_effect = error
    await control.async_start()
    await control.async_stop()
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert control.state == IDLE


async def test_pending_stop_is_not_stored(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    hass_storage: dict[str, Any],
) -> None:
    """The stored shape keeps its three keys; the pending stop never reaches it (Review Focus 5)."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    await control.async_shutdown()
    saved = hass_storage[STORE_KEY.format(entry.entry_id)]["data"]
    assert saved == {
        "blocked_since": None,
        "start_pending_since": None,
        "stop_asked": False,
    }
    again = ChargeControl(
        hass, entry, AsyncMock(), on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await again.async_load()
    assert again.state == IDLE
```

Update the existing tests whose stop now leaves a pending stop:
- `test_stop_during_pending_start`: the last line becomes `assert control.state == STOP_PENDING`.
- `test_stop_with_a_pending_start_and_a_charge_seen`: the last line becomes `assert control.state == STOP_PENDING`.

`test_background_stop_error_is_logged` keeps `assert control.state == IDLE` (the failure ends the pending stop).

- [ ] **Step 3: Write the switch test**

Add to `tests/test_switch.py` (`ServiceValidationError` is already imported; add `ChargerState` to the `pynortecgo` import):

```python
async def test_switch_off_right_after_a_stop(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """After a stop the switch stays off while the charger still says CHARGING; on is refused."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        charge_state=ChargeState.CHARGING,
        state=ChargerState.BUSY_CHARGING,
    )
    await setup_integration(hass, mock_config_entry)
    assert _state(hass) == STATE_ON
    await _call(hass, SERVICE_TURN_OFF)
    await hass.async_block_till_done()
    assert _state(hass) == STATE_OFF
    with pytest.raises(ServiceValidationError) as exc_info:
        await _call(hass, SERVICE_TURN_ON)
    assert exc_info.value.translation_key == "stop_pending"
    assert "A stop is under way" in str(exc_info.value)
    mock_client.start_charge.assert_not_awaited()
```

- [ ] **Step 4: Run the tests and see them fail**

Run: `uv run pytest tests/test_charge_control.py tests/test_switch.py -q`
Expected: FAIL (`ImportError: cannot import name 'STOP_CONFIRM_TIMEOUT'` first; after adding the constant, `TypeError: ... unexpected keyword argument 'stop_pending'` and the new tests failing).

- [ ] **Step 5: Add the constant**

In `custom_components/nortec_go/const.py`, under `START_CONFIRM_TIMEOUT`:

```python
# How long the switch shows off after a stop while the charger still reports the charge (D29).
STOP_CONFIRM_TIMEOUT: Final = timedelta(minutes=2)
```

- [ ] **Step 6: Implement the pending stop**

In `custom_components/nortec_go/charge_control.py`:

1. Update the module docstring to `"""The Nortec Go charge control: start and stop, the pending start and stop, and the start guard (D26, D29)."""`, and import `STOP_CONFIRM_TIMEOUT` from `.const`.
2. `ChargeControlState` gains `stop_pending: bool = False` (last field).
3. `is_charge_on`:

```python
def is_charge_on(charger: Charger, control: ChargeControlState) -> bool:
    """The Charge switch's state (§2.1; the pending stop, D29)."""
    if control.stop_pending or control.stop_asked:
        return False
    return control.start_pending or charger.charge_state in _CHARGE_ON
```

4. `charge_status`: right after the `start_blocked` check:

```python
    if control.stop_pending:
        return "stopping"
```

5. `ChargeControl.__init__`: add `self._stop_pending_since: datetime | None = None` after `self._stop_asked = False`.
6. `state`: add `stop_pending=self._stop_pending_since is not None`.
7. Add these helpers next to `_raise_if_closed`:

```python
def _expire_stop_pending(self) -> bool:
    """Clear a pending stop older than STOP_CONFIRM_TIMEOUT; True when it was cleared."""
    if (
        self._stop_pending_since is None
        or dt_util.utcnow() - self._stop_pending_since < STOP_CONFIRM_TIMEOUT
    ):
        return False
    _LOGGER.warning(
        "No stop seen within %s; showing the charger's state again",
        STOP_CONFIRM_TIMEOUT,
    )
    self._stop_pending_since = None
    return True


def _clear_stop_pending(self) -> None:
    """End a pending stop outside a read; it isn't stored, so only tell the coordinator."""
    if self._stop_pending_since is not None:
        self._stop_pending_since = None
        self._on_change()
```

8. `async_start`, right after `self._raise_if_closed()`:

```python
            if self._expire_stop_pending():
                self._on_change()
            if self._stop_pending_since is not None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="stop_pending"
                )
```

9. `async_stop`, right after `self._raise_if_closed()`:

```python
            if self._expire_stop_pending():
                self._on_change()
            if self._stop_pending_since is not None:
                return
```

10. `_async_send_stop` becomes:

```python
async def _async_send_stop(self) -> None:
    """Call stop_charge() once, under the lock; raises translated errors.

    A successful stop is pending until a read sees the charge no longer on (D29).
    """
    try:
        await self._client.stop_charge()
    except NoActiveChargeError:
        stopped = False
    except ChargeNotStoppableError:
        self._clear_stop_pending()
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="charge_not_stoppable"
        ) from None
    except AuthError:
        self._clear_stop_pending()
        self._entry.async_start_reauth(self._hass)
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="auth_failed"
        ) from None
    except NortecGoError as err:
        self._clear_stop_pending()
        _LOGGER.warning("Stopping the charge failed: %s: %s", type(err).__name__, err)
        self._request_read()
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="stop_failed"
        ) from None
    else:
        stopped = True
    if self._pending_since is not None:
        self._pending_since = None
        self._stop_asked = False
        self._save()
    self._stop_pending_since = dt_util.utcnow() if stopped else None
    self._on_change()
    self._request_read()
```

11. `on_charger_read`: after the `_closed` return and before the stale-read return, add:

```python
# The pending stop (D29), before the stale-read check: that check is about start
# attempts, and a read begun before the stop saw the charge on, so it can't end it early.
if self._stop_pending_since is not None and charger.charge_state not in _CHARGE_ON:
    self._stop_pending_since = None
else:
    self._expire_stop_pending()
```

   In the branch that queues the background stop (`if self._stop_asked and charge_is_open(charger):`), add `self._stop_pending_since = dt_util.utcnow()` after `self._stop_asked = False`. The rest of `on_charger_read` is unchanged (the read's data carries the new state; a pending-stop change alone isn't saved).

12. `_async_background_stop`: unchanged. Its docstring gains: "It owns the pending stop set when it was queued, so it doesn't make the no-op check."

- [ ] **Step 7: Translations and the switch docstring**

In both `custom_components/nortec_go/strings.json` and `custom_components/nortec_go/translations/en.json`, add to `exceptions` after `stop_failed`:

```json
    "stop_pending": {
      "message": "A stop is under way. Try again when it has ended."
    },
```

In `custom_components/nortec_go/switch.py`, the `is_on` docstring becomes `"""On for an open, not ending charge, or our pending start; off while our stop is pending."""`.

- [ ] **Step 8: Run the tests and the gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: all pass.
Run: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95 -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add custom_components/nortec_go/const.py custom_components/nortec_go/charge_control.py custom_components/nortec_go/switch.py custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json tests/test_charge_control.py tests/test_switch.py
git commit -F <message file>   # "feat: pending stop keeps the Charge switch off until the charger follows (#30)"
```

---

### Task 2: Pin-bump checklist

**Model:** sonnet
**Wave:** 1

**Files:**
- Modify: `docs/releasing.md` (section *Bumping `pynortecgo`*)
- Modify: `.github/pull_request_template.md`

**Interfaces:**
- Consumes: nothing. Refers to the charger read's catch-all by description only (Task 5 adds it).
- Produces: nothing code uses.

- [ ] **Step 1: Rewrite the section**

In `docs/releasing.md`, replace the body of `## Bumping \`pynortecgo\`` (the paragraph starting "Once the integration depends on…") with:

```markdown
`requirements` in `manifest.json` pins the `pynortecgo` client library to an exact version, for example
`pynortecgo==X.Y.Z`, and `pyproject.toml` pins the same version. A new client release gets its own pull
request that bumps both pins, runs the usual gates, and works through this checklist before merging:

- [ ] Read the new version's exception messages, including errors it wraps from lower layers, and confirm
  they hold no email, password, token, IDs or request bodies. The integration passes them into logs and
  `ConfigEntry*` errors (`CLAUDE.md`, hard rule 5).
- [ ] Look for new exception classes the charger, car, price, start and stop calls can raise, and give each
  the right handling. The charger read's catch-all only keeps an unknown error from crashing the read.
- [ ] Read the client's changelog for breaking changes to the models the entities use.
```

- [ ] **Step 2: Add the PR template line**

In `.github/pull_request_template.md`, add after the `pytest-homeassistant-custom-component` line:

```markdown
- [ ] `pynortecgo` bump → the checklist in `docs/releasing.md` → *Bumping `pynortecgo`* done
```

- [ ] **Step 3: Check and commit**

Run: `uv run pre-commit run --files docs/releasing.md .github/pull_request_template.md`
Expected: all hooks pass.

```bash
git add docs/releasing.md .github/pull_request_template.md
git commit -F <message file>   # "docs: re-check pynortecgo's exception texts on every pin bump (#16)"
```

---

### Task 3: Reads — interval, car skip, read right away, read time

**Model:** opus — near charge start and stop (the reads that confirm them) and the mapping of charger state to polling.
**Wave:** 2

**Files:**
- Modify: `custom_components/nortec_go/const.py`
- Modify: `custom_components/nortec_go/coordinator.py`
- Modify: `custom_components/nortec_go/charge_control.py` (remove the `start_pending` property)
- Modify: `custom_components/nortec_go/button.py`
- Test: `tests/test_coordinator.py`, `tests/test_charge_control.py`, `tests/test_button.py`

**Interfaces:**
- Consumes: `ChargeControlState.stop_pending`, `charge_status(charger, control)` from Task 1.
- Produces:
  - `interval_for(charger: Charger, control: ChargeControlState) -> timedelta`
  - `NortecGoData(charger: Charger, vehicle: Vehicle | None, control: ChargeControlState, read_at: datetime)`
  - `NortecGoCoordinator.async_read_now(self, *, with_car: bool = False) -> None`
  - `const.py`: `INTERVAL_CHANGING`, `INTERVAL_CHARGING`, `INTERVAL_IDLE`, `CAR_READ_MIN_AGE`; `INTERVAL_CONNECTED` and `INTERVAL_UNPLUGGED` are gone.

- [ ] **Step 1: Write the interval tests**

In `tests/test_coordinator.py`, change the const import to `DOMAIN, INTERVAL_CHANGING, INTERVAL_CHARGING, INTERVAL_IDLE, START_CONFIRM_TIMEOUT`, add `ChargerState` and `NortecGoConnectionError` (already there) to the `pynortecgo` import, and replace `test_interval_for` with:

```python
_PENDING = ChargeControlState(start_pending=True)


@pytest.mark.parametrize(
    ("charger", "control", "interval"),
    [
        (make_charger(is_connected=True), _PENDING, INTERVAL_CHANGING),
        (
            make_charger(is_connected=True, charge_state=ChargeState.STARTING),
            _PENDING,
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            _PENDING,
            INTERVAL_CHARGING,
        ),
        (
            make_charger(is_connected=True),
            ChargeControlState(start_pending=True, stop_asked=True),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            ChargeControlState(stop_pending=True),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.STARTING),
            ChargeControlState(),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.STOPPING),
            ChargeControlState(),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            ChargeControlState(),
            INTERVAL_CHARGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.PAUSED),
            ChargeControlState(),
            INTERVAL_IDLE,
        ),
        (make_charger(is_connected=True), ChargeControlState(), INTERVAL_IDLE),
        (make_charger(is_connected=False), ChargeControlState(), INTERVAL_IDLE),
        (
            make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
            ChargeControlState(),
            INTERVAL_IDLE,
        ),
        (
            make_charger(is_connected=True),
            ChargeControlState(blocked=True),
            INTERVAL_IDLE,
        ),
    ],
)
def test_interval_for(
    charger: Any, control: ChargeControlState, interval: timedelta
) -> None:
    """30 s while starting or stopping, 5 min while charging, 60 min otherwise (D29)."""
    assert interval_for(charger, control) == interval
```

Replace every other `INTERVAL_UNPLUGGED` in the file with `INTERVAL_IDLE`, and in `test_setup_reads_charger_car_and_prices` assert `coordinator.update_interval == INTERVAL_IDLE`. In `test_interval_while_start_pending`, assert `coordinator.update_interval == INTERVAL_CHANGING` and change its docstring to `"""A pending start reads every 30 s."""`.

- [ ] **Step 2: Write the read-right-away, car and read-time tests**

Delete `test_start_soon_after_a_refresh_gets_its_read` (it tested the debounced read that `async_read_now` replaces) and add:

```python
async def test_actions_within_the_cooldown_each_read_right_away(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A start and a stop within HA's 10 s debounce cooldown each read at once (Review Focus 4)."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    calls = mock_client.get_charger.await_count
    await coordinator.charge_control.async_start()
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == calls + 1
    await (
        coordinator.charge_control.async_stop()
    )  # a stop asked during the pending start
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == calls + 2


async def test_start_whose_read_fails_is_read_again_after_30_s(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The control change sets the 30 s interval before its read, so a failed read retries soon (Review Focus 2)."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("x")
    await coordinator.charge_control.async_start()
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert coordinator.update_interval == INTERVAL_CHANGING
    mock_client.get_charger.side_effect = None
    calls = mock_client.get_charger.await_count
    freezer.tick(
        INTERVAL_CHANGING + timedelta(seconds=1)
    )  # HA adds a sub-second offset
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == calls + 1


async def test_car_skipped_on_fast_reads(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """30 s reads skip the car until its last try is 4.5 minutes old."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.STARTING
    )
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.update_interval == INTERVAL_CHANGING
    vehicles = mock_client.get_vehicle.await_count
    chargers = mock_client.get_charger.await_count
    # Direct refreshes: HA's timer adds a random sub-second offset, and the car rule is
    # about the clock, not the timer.
    for _ in range(8):  # 4 minutes of 30 s reads
        freezer.tick(INTERVAL_CHANGING)
        await coordinator.async_refresh()
    assert mock_client.get_charger.await_count == chargers + 8
    assert mock_client.get_vehicle.await_count == vehicles
    freezer.tick(INTERVAL_CHANGING)  # 4.5 minutes after the last car read
    await coordinator.async_refresh()
    assert mock_client.get_vehicle.await_count == vehicles + 1


async def test_car_read_on_an_early_charging_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A 5-minute read that comes a second early still reads the car (Review Focus 3)."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True, charge_state=ChargeState.CHARGING
    )
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    vehicles = mock_client.get_vehicle.await_count
    freezer.tick(INTERVAL_CHARGING - timedelta(seconds=1))
    await coordinator.async_refresh()
    assert mock_client.get_vehicle.await_count == vehicles + 1


async def test_read_now_with_car(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """async_read_now skips a fresh car unless asked; the read that reads it clears the ask."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    vehicles = mock_client.get_vehicle.await_count
    await coordinator.async_read_now()
    assert mock_client.get_vehicle.await_count == vehicles
    await coordinator.async_read_now(with_car=True)
    assert mock_client.get_vehicle.await_count == vehicles + 1
    await coordinator.async_read_now()
    assert mock_client.get_vehicle.await_count == vehicles + 1


async def test_read_at_on_every_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Each successful read stamps read_at, so listeners hear of a read with unchanged data."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    first = coordinator.data.read_at
    listener = MagicMock()
    coordinator.async_add_listener(listener)
    freezer.tick(timedelta(seconds=5))
    await coordinator.async_refresh()
    assert coordinator.data.read_at == first + timedelta(seconds=5)
    listener.assert_called()


async def test_read_at_kept_on_a_control_change(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A change outside a read keeps the last read's time."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    read_at = coordinator.data.read_at
    coordinator.charge_control._on_change()  # noqa: SLF001
    assert coordinator.data.read_at == read_at
```

In `tests/test_charge_control.py`, delete `test_start_pending_property`.

- [ ] **Step 3: Write the button test**

Add to `tests/test_button.py`:

```python
async def test_press_twice_reads_twice(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Two presses within HA's 10 s debounce cooldown each read the charger and the car."""
    await setup_integration(hass, mock_config_entry)
    chargers = mock_client.get_charger.await_count
    vehicles = mock_client.get_vehicle.await_count

    await _press(hass)
    await _press(hass)

    assert mock_client.get_charger.await_count == chargers + 2
    assert mock_client.get_vehicle.await_count == vehicles + 2
```

- [ ] **Step 4: Run the tests and see them fail**

Run: `uv run pytest tests/test_coordinator.py tests/test_charge_control.py tests/test_button.py -q`
Expected: FAIL (`ImportError: cannot import name 'INTERVAL_CHANGING'` first).

- [ ] **Step 5: Constants**

In `custom_components/nortec_go/const.py`, replace the polling block with:

```python
# Charger polling, by the charge status (D29): 30 s while a charge starts or stops.
INTERVAL_CHANGING: Final = timedelta(seconds=30)
INTERVAL_CHARGING: Final = timedelta(minutes=5)
INTERVAL_IDLE: Final = timedelta(minutes=60)
# A read also reads the car when its last try is at least this old; the margin keeps an
# early 5-minute read from skipping it (D29).
CAR_READ_MIN_AGE: Final = INTERVAL_CHARGING - INTERVAL_CHANGING
```

- [ ] **Step 6: The coordinator**

In `custom_components/nortec_go/coordinator.py`:

1. Imports: from `.charge_control` import `ChargeControl, ChargeControlState, charge_status`; from `.const` import `CAR_READ_MIN_AGE, DOMAIN, INTERVAL_CHANGING, INTERVAL_CHARGING, INTERVAL_IDLE, PRICE_READ_HOURS, PRICE_READ_MINUTE, TICK_MINUTES`. Remove `_CHARGE_UNDER_WAY`.
2. `NortecGoData` gains a last field `read_at: datetime`; its docstring adds "read_at is when the charger was last read successfully."
3. `interval_for`:

```python
def interval_for(charger: Charger, control: ChargeControlState) -> timedelta:
    """The next polling interval, from the charge status the sensor shows (D29)."""
    if charge_status(charger, control) in ("starting", "stopping"):
        return INTERVAL_CHANGING
    if charger.charge_state is ChargeState.CHARGING:
        return INTERVAL_CHARGING
    return INTERVAL_IDLE
```

4. `__init__`: `update_interval=INTERVAL_IDLE`; `request_refresh=self.async_read_now`; add `self._car_read_at: datetime | None = None` and `self._read_car_next = False`.
5. `_async_update_data`, from `self.charge_control.on_charger_read(...)` on:

```python
        self.charge_control.on_charger_read(charger, start_attempts)
        read_at = dt_util.utcnow()
        if self._car_due(read_at):
            self._car_read_at = read_at
            self._read_car_next = False
            vehicle = await self._async_read_vehicle()
        else:
            vehicle = self._vehicle
        control = self.charge_control.state
        self.update_interval = interval_for(charger, control)
        return NortecGoData(
            charger=charger, vehicle=vehicle, control=control, read_at=read_at
        )

    def _car_due(self, now: datetime) -> bool:
        """Read the car the first time, when asked, or when its last try is old enough (§3.2)."""
        return (
            self._read_car_next
            or self._car_read_at is None
            or now - self._car_read_at >= CAR_READ_MIN_AGE
        )
```

   Its docstring becomes `"""Read the charger, then the car when due; set the next interval."""`.
6. `_async_control_changed`:

```python
        if self.data is None:
            return
        control = self.charge_control.state
        self.data = replace(self.data, control=control)
        # Before the read right away: if that read fails, HA reuses this interval.
        self.update_interval = interval_for(self.data.charger, control)
        self.async_update_listeners()
```

7. Add after `_async_control_changed`:

```python
    async def async_read_now(self, *, with_car: bool = False) -> None:
        """Read the charger now, not debounced; the car too when asked (§3.3)."""
        if with_car:
            self._read_car_next = True
        await self.async_refresh()
```

- [ ] **Step 7: The control and the button**

In `custom_components/nortec_go/charge_control.py`, delete the `start_pending` property (and nothing else).

In `custom_components/nortec_go/button.py`:

```python
    async def async_press(self) -> None:
        """Read the charger and the car now, then the prices."""
        await self.coordinator.async_read_now(with_car=True)
        await self.coordinator.async_read_prices()
```

Its module docstring stays; the class docstring stays.

- [ ] **Step 8: Run the tests and the gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: all pass. If a test elsewhere builds `NortecGoData` or imports the removed constants, update it the same way (none did at planning time).
Run: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95 -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add custom_components/nortec_go/const.py custom_components/nortec_go/coordinator.py custom_components/nortec_go/charge_control.py custom_components/nortec_go/button.py tests/test_coordinator.py tests/test_charge_control.py tests/test_button.py
git commit -F <message file>   # "feat: read every 30 s while a charge starts or stops, and right away after an action (#30)"
```

---

### Task 4: Last read sensor

**Model:** sonnet
**Wave:** 3

**Files:**
- Modify: `custom_components/nortec_go/sensor.py`
- Modify: `custom_components/nortec_go/strings.json`, `custom_components/nortec_go/translations/en.json`
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `NortecGoData.read_at: datetime` (Task 3).
- Produces: entity `sensor.<charger>_last_read`, unique ID `<charger id>_last_read`.

- [ ] **Step 1: Write the tests**

Add to `tests/test_sensor.py` (import `EntityCategory` from `homeassistant.const`, `entity_registry as er` from `homeassistant.helpers`, `FrozenDateTimeFactory` from `freezegun.api`, `timedelta` from `datetime`, and `NortecGoConnectionError` from `pynortecgo`, where not imported yet):

```python
LAST_READ = "sensor.garage_charger_last_read"


async def test_last_read_sensor(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Last read shows when the charger was read, as a diagnostic timestamp."""
    freezer.move_to("2026-09-27 10:00:00+00:00")
    await setup_integration(hass, mock_config_entry)
    state = hass.states.get(LAST_READ)
    assert state is not None
    assert state.state == "2026-09-27T10:00:00+00:00"
    assert state.attributes["device_class"] == "timestamp"
    registry_entry = entity_registry.async_get(LAST_READ)
    assert registry_entry is not None
    assert registry_entry.entity_category is EntityCategory.DIAGNOSTIC


async def test_last_read_available_after_a_failed_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a failed read Last read stays available and keeps the last good time."""
    freezer.move_to("2026-09-27 10:00:00+00:00")
    await setup_integration(hass, mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("x")
    freezer.tick(timedelta(minutes=1))
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(LAST_READ)
    assert state is not None
    assert state.state == "2026-09-27T10:00:00+00:00"
```

If `test_sensor.py` has a test that lists every sensor entity of the charger, add `LAST_READ` to it.

- [ ] **Step 2: Run the tests and see them fail**

Run: `uv run pytest tests/test_sensor.py -q`
Expected: FAIL (`state is None` for `sensor.garage_charger_last_read`).

- [ ] **Step 3: Implement**

In `custom_components/nortec_go/sensor.py`, update the module docstring to `"""Nortec Go sensors: the price for EV Smart Charging, the charge status, the last read and the car's values."""`, add `NortecGoLastReadSensor(coordinator)` to the `entities` list after `NortecGoChargeStatusSensor(coordinator)`, and add after `NortecGoChargeStatusSensor`:

```python
class NortecGoLastReadSensor(NortecGoChargerEntity, SensorEntity):
    """When the charger was last read successfully (§4)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: NortecGoCoordinator) -> None:
        """Name the sensor Last read."""
        super().__init__(coordinator, "last_read")

    @property
    def available(self) -> bool:
        """Always available: after a failed read it shows how old the data is."""
        return True

    @property
    def native_value(self) -> datetime:
        """The last successful read's time."""
        return self.coordinator.data.read_at
```

In both `strings.json` and `translations/en.json`, add under `entity` → `sensor`, after `charge_status`:

```json
      "last_read": {
        "name": "Last read"
      }
```

(with the comma after `charge_status`'s closing brace).

- [ ] **Step 4: Run the tests and the gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: all pass. Then the coverage gate: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95 -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/nortec_go/sensor.py custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json tests/test_sensor.py
git commit -F <message file>   # "feat: Last read sensor on the charger (#30)"
```

---

### Task 5: Charger device rename and the charger read's catch-all

**Model:** sonnet
**Wave:** 3

**Files:**
- Modify: `custom_components/nortec_go/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: the Task 3 coordinator.
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the tests**

Add to `tests/test_coordinator.py` (import `NortecGoError` from `pynortecgo` and `UpdateFailed` from `homeassistant.helpers.update_coordinator`):

```python
async def test_charger_device_follows_a_rename(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """A rename in the app renames the charger device; an empty name falls back to the title."""
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    identifiers = {(DOMAIN, str(FAKE_CHARGER_ID))}

    mock_client.get_charger.return_value = make_charger(name="Driveway charger")
    await coordinator.async_refresh()
    device = device_registry.async_get_device(identifiers=identifiers)
    assert device is not None
    assert device.name == "Driveway charger"

    mock_client.get_charger.return_value = make_charger(name="")
    await coordinator.async_refresh()
    device = device_registry.async_get_device(identifiers=identifiers)
    assert device is not None
    assert device.name == mock_config_entry.title


async def test_charger_rename_before_the_device_exists(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Before the entities create the device, a read creates none."""
    mock_config_entry.add_to_hass(hass)
    coordinator = NortecGoCoordinator(hass, mock_config_entry, mock_client)
    mock_client.get_charger.return_value = make_charger(name="Driveway charger")
    await coordinator.async_refresh()
    assert (
        device_registry.async_get_device(identifiers={(DOMAIN, str(FAKE_CHARGER_ID))})
        is None
    )


async def test_unknown_client_error_fails_the_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A NortecGoError subclass this integration doesn't know fails the read cleanly."""

    class FutureClientError(NortecGoError):
        """A client error type from a later pynortecgo version."""

    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = FutureClientError("something new")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert isinstance(coordinator.last_exception, UpdateFailed)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert "Unexpected error" not in caplog.text
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `uv run pytest tests/test_coordinator.py -q -k "rename or unknown_client"`
Expected: FAIL (the device keeps "Garage charger"; the unknown error logs "Unexpected error fetching").

- [ ] **Step 3: Implement**

In `_async_update_data`, add after the `(ChargerNotFoundError, UnexpectedResponseError)` clause, as the last one:

```python
        except NortecGoError as err:
            # Last: the specific errors above are its subclasses. A later client version may add more.
            raise UpdateFailed(str(err)) from err
```

Call `self._async_update_charger_device(charger)` right after `self.charge_control.on_charger_read(charger, start_attempts)`, and add next to `_async_update_car_device`:

```python
    @callback
    def _async_update_charger_device(self, charger: Charger) -> None:
        """Follow a rename of the charger in the app (#22); the owner's own name still wins."""
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(identifiers={(DOMAIN, self.charger_id)})
        if device is None:
            return  # the entities create the device
        name = charger.name or self.config_entry.title
        if device.name != name:
            registry.async_update_device(device.id, name=name)
```

- [ ] **Step 4: Run the tests and the gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: all pass. Then the coverage gate → PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/nortec_go/coordinator.py tests/test_coordinator.py
git commit -F <message file>   # "feat: charger device follows a rename; unknown client errors fail the read cleanly (#22, #23)"
```

---

### Task 6: User docs, changelog, quality scale and D29

**Model:** sonnet
**Wave:** 4

**Files:**
- Modify: `docs/user/nortec_go.md`
- Modify: `CHANGELOG.md`
- Modify: `custom_components/nortec_go/quality_scale.yaml`
- Modify: `docs/decisions.md`

**Interfaces:**
- Consumes: the entity names and behaviour of Tasks 1–5 (check them against the code on the feature branch).
- Produces: nothing code uses.

- [ ] **Step 1: User docs**

In `docs/user/nortec_go.md`:

1. *Supported functionality → Charger*: the *Charge* row's description becomes "Starts and stops a charge. On while a charge is starting, charging or paused, and right after a start until the charger shows it; off right after a stop until the charger shows it". Add after the *Refresh* row:

```markdown
| Last read | Sensor (diagnostic) | When the charger was last read. Shows how old the other values are, also after a failed read |
```

2. *Starting a charge*: add a paragraph at the end:

```markdown
After you turn *Charge* off, it shows off and *Charge status* shows *Stopping* for up to 2 minutes while
Home Assistant waits for the charger to show the stop. Turning *Charge* on in that time is refused.
```

3. *Data updates*: replace the list and the paragraph under it (up to *Known limitations*) with:

```markdown
The integration reads the charger:

- every 30 seconds while a charge is starting or stopping, including right after you turn *Charge* on or
  off,
- every 5 minutes while a charge is running,
- every 60 minutes otherwise.

It reads the car with the charger, but at most about every 5 minutes. It reads the price forecast when it
starts and at 00:05, 05:05, 10:05, 15:05 and 20:05. The current price moves to the next 15 minutes by
itself, without a read.

Turning *Charge* on or off reads the charger right away. To read the charger, the car and the prices now,
press the *Refresh* button. From an automation, the `homeassistant.update_entity` action on any Nortec Go
entity reads the charger, and the car if it wasn't read in the last few minutes, but not the prices (see
*Automation examples*).
```

4. *Known limitations*: "(up to 15 minutes apart while a cable is connected)" becomes "(up to 60 minutes apart while no charge is running)". Add:

```markdown
- A charge started or resumed outside Home Assistant, for example in the Nortec Go app, can take up to 60
  minutes to show. Press *Refresh* to see it sooner.
```

5. *Automation examples*: leave as is (its "once an hour while no cable is connected" still holds).

- [ ] **Step 2: Changelog**

In `CHANGELOG.md` under *Unreleased → Added*:
- the *Charge* switch line becomes: "A *Charge* switch that starts and stops charging, guarded against repeated starts that could place extra card holds, and shown off right after a stop until the charger follows; a *Charge status* sensor; and a repair issue to allow starts again after a failed start."
- add:

```markdown
- A *Last read* sensor that shows when the charger was last read.
- The charger is read every 30 seconds while a charge is starting or stopping, and right away after turning
  *Charge* on or off.
- The charger's device name follows a rename in the Nortec Go app.
```

- [ ] **Step 3: Quality scale**

In `custom_components/nortec_go/quality_scale.yaml`:
- `entity-unavailable` comment: "The Charge switch, the Current price sensor, the Refresh button and the Last read sensor stay available after a failed read on purpose (turn_off still reaches the charger; the price lists and the last read's time stay visible); the other entities follow the rule."
- `appropriate-polling` becomes:

```yaml
  appropriate-polling:
    status: done
    comment: "30 s only while a charge is starting or stopping, 5 min while charging, 60 min otherwise (D29)."
```

Run: `uv run pytest tests/test_quality_scale.py -q` → PASS.

- [ ] **Step 4: Decision log**

Append to `docs/decisions.md`:

```markdown
### D29: Pending stop and fast reads
- **Date:** 2026-09-27 · **Status:** active
- **Decision:** After a successful stop the switch shows off and *Charge status* *Stopping* until a read sees
  the charge no longer on, or for 2 minutes, and a start is refused meanwhile. The charger is read every
  30 s while *Charge status* is *starting* or *stopping*, 5 min while charging and 60 min otherwise
  (replacing D27's intervals and D26's last sentence), and right away after a start, a stop or Refresh; the
  car at most about every 5 minutes, and on every Refresh.
- **Why:** The charger reports the old state for about 25 s after a stop, so the switch flipped back on and
  a stop was pressed twice; 30 s reads were observed without a rate limit.
- **Source:** [pending stop and fast reads spec](superpowers/specs/2026-09-27-pending-stop-fast-reads-design.md), Decisions and §2–3
```

D26 and D27 keep their status `active`.

- [ ] **Step 5: Check and commit**

Run: `uv run pytest -q && uv run pre-commit run --files docs/user/nortec_go.md CHANGELOG.md custom_components/nortec_go/quality_scale.yaml docs/decisions.md`
Expected: all pass.

```bash
git add docs/user/nortec_go.md CHANGELOG.md custom_components/nortec_go/quality_scale.yaml docs/decisions.md
git commit -F <message file>   # "docs: pending stop, fast reads and Last read in the user docs, changelog and D29 (#30)"
```
