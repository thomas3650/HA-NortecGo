# Start and stop deadlines without reads, and what a start needs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** The pending start (10 min) and the pending stop (2 min) end on time even while the charger can't be read or isn't read at all, the 30 s reads end with them, and the docs say what a start needs.

**Architecture:** `ChargeControl` arms an `async_call_later` timer for each deadline; the timer's work runs under the control's lock and is the only thing that ends a pending state because its time is up. `interval_for` takes the age of the last good read, so the charger's own starting or stopping state stops giving 30 s reads during an outage, and a failed charger read works the interval out again. Docs, changelog, quality scale and the decision log follow.

**Tech Stack:** Python 3.14, Home Assistant custom integration, `pynortecgo` 0.2.0 (always mocked in tests), pytest with `pytest-homeassistant-custom-component` and freezegun, uv.

**Spec:** `docs/superpowers/specs/2026-09-28-outage-deadlines-start-needs-design.md` (issues #34, #35).

## Global Constraints

- TDD: write the failing test, see it fail, then the code. Tests always mock `pynortecgo`; fixtures come from `pynortecgo` model objects and `tests/conftest.py` helpers, never raw API JSON (hard rules 2, 7).
- Never start or stop a real charge (hard rule 2). Never retry `start_charge` (hard rule 6).
- Nothing private (hard rule 3): no IDs, tokens, emails, captures, raw endpoints or links into the private repo.
- Gates before every commit (`CLAUDE.md` → Commands): `uv run pytest -q`, `uv run ruff check && uv run ruff format --check && uv run mypy`; the coverage gate (`--cov-fail-under=95`) passes at the end of each task.
- Subagents write commit messages with the Write tool to a file outside the repo and commit with `git commit -F <file>` (no heredocs). End each message with the co-author trailer given in the dispatch.
- Match the surrounding code: its comment density, docstring style (one line, a period), names.
- Constants (existing): `INTERVAL_CHANGING = 30 s`, `INTERVAL_CHARGING = 5 min`, `INTERVAL_IDLE = 60 min`, `START_CONFIRM_TIMEOUT = 10 min`, `STOP_CONFIRM_TIMEOUT = 2 min`. New: `START_LOAD_GRACE = 2 min` (Task 1), `FAST_READ_MAX_AGE = 2 min` (Task 2).
- Timers in tests: `freezer.tick(...)`, then `async_fire_time_changed(hass)`, then `await hass.async_block_till_done(wait_background_tasks=True)` (the timer's work runs as a background task). The test plugin fails a test that leaves a timer scheduled unless its job has `cancel_on_shutdown=True`.
- Log texts stay as today: "No charge seen within %s of the start; blocking starts" and "No stop seen within %s; showing the charger's state again".

## Review Focus

1. A pending start that is overdue at a restart, whose first read sees `BUSY_NON_RELEASED` (the charge ran and ended while Home Assistant was down), must end with no block (Task 1 test `test_overdue_start_at_load_decided_by_the_first_read`).
2. A setup that fails with a stored pending start must never raise the repair issue later from the failed setup's timer (Task 1 test `test_failed_setup_leaves_no_start_timer`).
3. The start timer coming due while `stop_charge()` is in flight must not block starts (Task 1 test `test_start_timer_waits_for_a_stop_in_flight`).
4. The background stop sets the pending stop twice (the read, then the stop itself); only one stop timer may be left, so the timeout warning appears once (Task 1 test `test_background_stop_leaves_one_stop_timer`).
5. The charger's own `STOPPING` with the charger unreachable must drop from 30 s to 5 min after about 2 minutes (Task 2 test `test_charger_stopping_during_an_outage_slows_down`).

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (timers), Task 3 (docs, changelog, quality scale, decisions) | Disjoint files: two worktrees. Task 3 is written against the names this plan fixes |
| 2 | Task 2 (interval rule) | Needs Task 1's timers for its outage tests; edits `const.py` and `tests/test_coordinator.py` after Task 1 |

No task has guarded files.

---

### Task 1: The start and stop timers in `ChargeControl`

**Model:** opus — near charge start and stop, and the start guard.
**Wave:** 1

**Files:**
- Modify: `custom_components/nortec_go/const.py` (add `START_LOAD_GRACE`)
- Modify: `custom_components/nortec_go/charge_control.py`
- Test: `tests/test_charge_control.py`, `tests/test_coordinator.py` (one existing test), `tests/test_init.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `START_LOAD_GRACE: Final = timedelta(minutes=2)` in `const.py`. `ChargeControl`'s public API is unchanged (`state`, `async_load`, `async_start`, `async_stop`, `on_charger_read`, `clear_block`, `async_shutdown`, `start_attempts`); when a timer ends a pending state it calls the existing `on_change` callback (and saves, for the start). `_expire_stop_pending` is removed.

- [ ] **Step 1: Rewrite the timeout tests to fire the timers**

In `tests/test_charge_control.py`, add at module level (after `STORE_KEY`):

```python
def _timers(hass: HomeAssistant, name: str) -> int:
    """The scheduled, not cancelled timers whose job has this name."""
    return sum(
        1
        for handle in get_scheduled_timer_handles(hass.loop)
        if not handle.cancelled()
        and handle._args  # noqa: SLF001
        and isinstance(job := handle._args[-1], HassJob)  # noqa: SLF001
        and job.name == name
    )


async def _fire(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta
) -> None:
    """Move time on, fire due timers and wait for their background work."""
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
```

Change the `control` fixture to shut the control down at teardown (the timers are also `cancel_on_shutdown`, this keeps tests tidy):

```python
@pytest.fixture
async def control(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    on_change: MagicMock,
    request_refresh: AsyncMock,
) -> AsyncGenerator[ChargeControl]:
    """A loaded control that has seen one connected, idle read; shut down at teardown."""
    control = ChargeControl(
        hass, entry, client, on_change=on_change, request_refresh=request_refresh
    )
    await control.async_load()
    control.on_charger_read(CONNECTED, control.start_attempts)
    yield control
    await control.async_shutdown()
```

(`from collections.abc import AsyncGenerator`; `from homeassistant.core import HassJob, HomeAssistant`; `from homeassistant.util.async_ import get_scheduled_timer_handles`. The `handle._args and` guard matters: a handle with no args would raise `IndexError`.)

Replace these existing tests (same names unless noted):

```python
async def test_pending_start_times_out_into_block(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
) -> None:
    """No charge seen within 10 minutes, with no read at all: the start counts as failed with a hold."""
    await control.async_start()
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT - timedelta(seconds=1))
    assert control.state == PENDING
    on_change.reset_mock()
    await _fire(hass, freezer, timedelta(seconds=1))
    assert control.state == BLOCKED
    assert _issue(hass, entry) is not None
    on_change.assert_called()


async def test_unplugged_read_after_the_timeout_clears_the_block(
    hass: HomeAssistant, control: ChargeControl, freezer: FrozenDateTimeFactory
) -> None:
    """The timer blocks at 10 minutes; a later read that sees the cable unplugged clears it (D26)."""
    await control.async_start()
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT)
    assert control.state == BLOCKED
    control.on_charger_read(make_charger(is_connected=False), control.start_attempts)
    assert control.state == IDLE


async def test_stop_asked_ends_with_the_timeout(
    hass: HomeAssistant, control: ChargeControl, freezer: FrozenDateTimeFactory
) -> None:
    """The stop request ends with the pending start's timeout, which blocks."""
    await control.async_start()
    await control.async_stop()
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT)
    assert control.state == BLOCKED


async def test_pending_stop_times_out_without_a_read(
    hass: HomeAssistant,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """After 2 minutes, with no read, the pending stop ends with a warning and tells the coordinator."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT - timedelta(seconds=1))
    assert control.state == STOP_PENDING
    on_change.reset_mock()
    await _fire(hass, freezer, timedelta(seconds=1))
    assert control.state == IDLE
    assert "No stop seen within" in caplog.text
    on_change.assert_called()


async def test_stop_after_the_timeout_without_a_read(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Once the pending stop has timed out, turn_off stops again."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    await control.async_stop()
    assert client.stop_charge.await_count == 2


async def test_start_after_the_timeout_takes_the_normal_checks(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Once the pending stop has timed out, turn_on isn't refused; the open charge makes it a no-op."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    await control.async_start()
    client.start_charge.assert_not_awaited()
    assert control.state == IDLE
```

Delete `test_pending_stop_times_out_on_a_read` and `test_timeout_on_unplugged_read_ends_without_block` (replaced above).

- [ ] **Step 2: Add the new timer tests**

```python
async def test_read_with_a_charge_ends_the_start_timer(
    hass: HomeAssistant, control: ChargeControl, freezer: FrozenDateTimeFactory
) -> None:
    """A read that sees a charge ends the pending start; its timer blocks nothing later."""
    await control.async_start()
    control.on_charger_read(CHARGING, control.start_attempts)
    assert control.state == IDLE
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT)
    assert control.state == IDLE


async def test_read_without_the_charge_ends_the_stop_timer(
    hass: HomeAssistant,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A read that sees the charge off ends the pending stop; its timer does nothing later."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    control.on_charger_read(CONNECTED, control.start_attempts)
    assert control.state == IDLE
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    assert "No stop seen within" not in caplog.text


async def test_new_start_gets_a_fresh_timer(
    hass: HomeAssistant, control: ChargeControl, freezer: FrozenDateTimeFactory
) -> None:
    """A second start after the first ended has its own 10 minutes; the first timer is gone."""
    await control.async_start()
    control.on_charger_read(make_charger(is_connected=False), control.start_attempts)
    await _fire(hass, freezer, timedelta(minutes=5))
    await control.async_start()
    await _fire(hass, freezer, timedelta(minutes=6))
    assert control.state == PENDING
    await _fire(hass, freezer, timedelta(minutes=4))
    assert control.state == BLOCKED


async def test_start_timer_does_nothing_after_shutdown(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
) -> None:
    """After unload the start timer changes nothing."""
    await control.async_start()
    await control.async_shutdown()
    on_change.reset_mock()
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT)
    assert control.state == PENDING
    assert _issue(hass, entry) is None
    on_change.assert_not_called()


async def test_stop_timer_does_nothing_after_shutdown(
    hass: HomeAssistant,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    on_change: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """After unload the stop timer changes nothing."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    await control.async_shutdown()
    on_change.reset_mock()
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    assert control.state == STOP_PENDING
    assert "No stop seen within" not in caplog.text
    on_change.assert_not_called()


async def test_stop_timer_after_the_stop_ended_does_nothing(
    hass: HomeAssistant,
    control: ChargeControl,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A stop timer whose work waits for the lock while a read ends the pending stop does nothing."""
    control.on_charger_read(CHARGING, control.start_attempts)
    await control.async_stop()
    async with control._lock:  # noqa: SLF001
        freezer.tick(STOP_CONFIRM_TIMEOUT)
        async_fire_time_changed(hass)
        await asyncio.sleep(0)
        control.on_charger_read(CONNECTED, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert control.state == IDLE
    assert "No stop seen within" not in caplog.text


async def test_start_timer_waits_for_a_stop_in_flight(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The start timer coming due during stop_charge() waits for the lock and blocks nothing (Review Focus 3)."""
    attempts_before = control.start_attempts
    await control.async_start()
    freezer.tick(START_CONFIRM_TIMEOUT - timedelta(seconds=1))
    control.on_charger_read(
        CHARGING, attempts_before
    )  # stale: pending stays, charge seen
    release = asyncio.Event()

    async def slow_stop() -> None:
        await release.wait()

    client.stop_charge.side_effect = slow_stop
    stop = hass.async_create_task(control.async_stop())
    await asyncio.sleep(0)
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await asyncio.sleep(0)
    release.set()
    await stop
    await hass.async_block_till_done(wait_background_tasks=True)
    assert control.state == STOP_PENDING


async def test_background_stop_leaves_one_stop_timer(
    hass: HomeAssistant,
    control: ChargeControl,
    client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The read and the background stop both set the pending stop; one timeout warning only (Review Focus 4)."""
    await control.async_start()
    await control.async_stop()  # asked during the pending start
    control.on_charger_read(CHARGING, control.start_attempts)
    await hass.async_block_till_done(wait_background_tasks=True)
    client.stop_charge.assert_awaited_once()
    assert _timers(hass, f"{DOMAIN} stop deadline") == 1
    await _fire(hass, freezer, STOP_CONFIRM_TIMEOUT)
    assert caplog.text.count("No stop seen within") == 1


@pytest.mark.parametrize(
    ("age", "left"),
    [
        (timedelta(minutes=3), timedelta(minutes=7)),
        (timedelta(minutes=9), START_LOAD_GRACE),
        (timedelta(minutes=30), START_LOAD_GRACE),
        (-timedelta(hours=1), START_CONFIRM_TIMEOUT),
    ],
)
async def test_load_arms_the_start_timer(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    age: timedelta,
    left: timedelta,
) -> None:
    """A stored pending start gets the time left, at least the grace, at most 10 minutes."""
    key = STORE_KEY.format(entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": None,
            "start_pending_since": (dt_util.utcnow() - age).isoformat(),
            "stop_asked": False,
        },
    }
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    assert control.state == PENDING
    await _fire(hass, freezer, left - timedelta(seconds=1))
    assert control.state == PENDING
    await _fire(hass, freezer, timedelta(seconds=1))
    assert control.state == BLOCKED
    await control.async_shutdown()


@pytest.mark.parametrize(
    "charger",
    [
        CHARGING,
        make_charger(is_connected=True, state=ChargerState.BUSY_NON_RELEASED),
        make_charger(is_connected=False),
    ],
)
async def test_overdue_start_at_load_decided_by_the_first_read(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    charger: Any,
) -> None:
    """An overdue stored start is ended by a first read with evidence, with no block (Review Focus 1).

    The read here runs before the loop could fire any timer; the grace itself is pinned by
    test_load_arms_the_start_timer's 9- and 30-minute rows.
    """
    key = STORE_KEY.format(entry.entry_id)
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": None,
            "start_pending_since": (dt_util.utcnow() - timedelta(hours=8)).isoformat(),
            "stop_asked": False,
        },
    }
    control = ChargeControl(
        hass, entry, client, on_change=MagicMock(), request_refresh=AsyncMock()
    )
    await control.async_load()
    control.on_charger_read(charger, control.start_attempts)
    await _fire(hass, freezer, START_CONFIRM_TIMEOUT)
    assert control.state == IDLE
    assert _issue(hass, entry) is None
    await control.async_shutdown()
```

(`from homeassistant.util import dt as dt_util`; add `START_LOAD_GRACE` to the `const` import.)

In `tests/test_init.py`, add (Review Focus 2):

```python
async def test_failed_setup_leaves_no_start_timer(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A setup whose first read fails cancels its start timer: no repair issue appears later."""
    key = f"nortec_go.{mock_config_entry.entry_id}.charge_control"
    hass_storage[key] = {
        "version": 1,
        "key": key,
        "data": {
            "blocked_since": None,
            "start_pending_since": dt_util.utcnow().isoformat(),
            "stop_asked": False,
        },
    }
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    for _ in range(4):
        freezer.tick(timedelta(minutes=3))
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"start_blocked_{mock_config_entry.entry_id}"
    )
    assert issue is None
    assert hass_storage[key]["data"]["blocked_since"] is None
```

(`tests/test_init.py` already imports everything this needs except `from homeassistant.util import dt as dt_util`.)

In `tests/test_coordinator.py`, replace `test_timeout_on_unchanged_read_updates_entities`:

```python
async def test_timeout_on_unchanged_read_updates_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The start timer's block reaches listeners even when the reads don't change."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    await coordinator.charge_control.async_start()
    await hass.async_block_till_done()
    listener = MagicMock()
    coordinator.async_add_listener(listener)
    freezer.tick(START_CONFIRM_TIMEOUT)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.data.control.blocked
    listener.assert_called()
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `uv run pytest tests/test_charge_control.py tests/test_init.py tests/test_coordinator.py -q`
Expected: FAIL — `START_LOAD_GRACE` can't be imported; once added, the timer tests fail because nothing ends a pending state without a read.

- [ ] **Step 4: Add the constant**

In `custom_components/nortec_go/const.py`, after `STOP_CONFIRM_TIMEOUT`:

```python
# At a restart a pending start waits at least this long, so the setup's first read decides first (D31).
START_LOAD_GRACE: Final = timedelta(minutes=2)
```

- [ ] **Step 5: Implement the timers**

In `custom_components/nortec_go/charge_control.py`:

Module docstring: `"""The Nortec Go charge control: start and stop, the pending start and stop, and the start guard (D26, D29, D31)."""`

Imports: `from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback`, `from homeassistant.helpers.event import async_call_later`, `from datetime import datetime, timedelta`, and `START_LOAD_GRACE` from `.const`.

In `__init__`, after `self._stop_pending_since`:

```text
        self._start_timer: CALLBACK_TYPE | None = None
        self._stop_timer: CALLBACK_TYPE | None = None
        # A setup that fails after async_load never calls async_shutdown, but runs these.
        entry.async_on_unload(self._cancel_timers)
```

In `async_load`, replace `self._pending_since = pending_since` and the `stop_asked` line with:

```text
        self._stop_asked = stop_asked and pending_since is not None
        if pending_since is not None:
            left = START_CONFIRM_TIMEOUT - (dt_util.utcnow() - pending_since)
            self._set_start_pending(
                pending_since, min(max(left, START_LOAD_GRACE), START_CONFIRM_TIMEOUT)
            )
```

In `async_start`: delete the two lines `if self._expire_stop_pending(): self._on_change()`. Replace `self._pending_since = dt_util.utcnow()` with `self._set_start_pending(dt_util.utcnow())` (keep `self._stop_asked = False` after it).

In `async_stop`: delete the two lines `if self._expire_stop_pending(): self._on_change()`.

In `_async_send_stop`, replace the tail from `if self._pending_since is not None:` to `self._stop_pending_since = dt_util.utcnow() if stopped else None` with:

```text
        if self._pending_since is not None:
            self._end_start_pending()
            self._save()
        if stopped:
            self._set_stop_pending()
        else:
            self._end_stop_pending()
```

In `on_charger_read`, replace the pending-stop block and the pending-start block with:

```text
        # The pending stop (D29), before the stale-read check: that check is about start
        # attempts, and a read begun before the stop saw the charge on, so it can't end it early.
        # Only a read with evidence ends it here; the stop timer owns the time limit (D31).
        if (
            self._stop_pending_since is not None
            and charger.charge_state not in _CHARGE_ON
        ):
            self._end_stop_pending()
        if start_attempts != self.start_attempts:
            return  # a stale read: it began before the latest start attempt
        changed = False
        if self._pending_since is not None:
            if self._stop_asked and charge_is_open(charger):
                self._end_start_pending()
                self._set_stop_pending()
                changed = True
                self._entry.async_create_background_task(
                    self._hass, self._async_background_stop(), f"{DOMAIN} stop"
                )
            elif _charge_happened(charger) or not charger.is_connected:
                self._end_start_pending()
                changed = True
```

(The `elif dt_util.utcnow() - self._pending_since >= START_CONFIRM_TIMEOUT:` branch goes: the start timer owns it.)

In `async_shutdown`, after `self._closed = True`: `self._cancel_timers()`.

Delete `_expire_stop_pending`. Replace `_clear_stop_pending` and add the helpers:

```text
    def _clear_stop_pending(self) -> None:
        """End a pending stop outside a read; it isn't stored, so only tell the coordinator."""
        if self._stop_pending_since is not None:
            self._end_stop_pending()
            self._on_change()

    def _set_start_pending(
        self, since: datetime, delay: timedelta = START_CONFIRM_TIMEOUT
    ) -> None:
        """Start pending since `since`; its timer ends it with a block after `delay` (D31)."""
        self._pending_since = since
        self._cancel_start_timer()

        @callback
        def _due(_now: datetime) -> None:
            self._start_timer = None
            self._entry.async_create_background_task(
                self._hass, self._async_start_due(since), f"{DOMAIN} start deadline"
            )

        self._start_timer = async_call_later(
            self._hass, delay, HassJob(_due, f"{DOMAIN} start deadline", cancel_on_shutdown=True)
        )

    def _end_start_pending(self) -> None:
        self._pending_since = None
        self._stop_asked = False
        self._cancel_start_timer()

    async def _async_start_due(self, since: datetime) -> None:
        """The start timer's work, under the lock: no charge seen in time blocks starts (D26)."""
        async with self._lock:
            if self._closed or self._pending_since != since:
                return
            _LOGGER.warning(
                "No charge seen within %s of the start; blocking starts",
                START_CONFIRM_TIMEOUT,
            )
            self._end_start_pending()
            self._set_block("start_blocked")
            self._changed()

    def _set_stop_pending(self) -> None:
        """Stop pending from now; its timer ends it after STOP_CONFIRM_TIMEOUT (D29, D31)."""
        since = dt_util.utcnow()
        self._stop_pending_since = since
        self._cancel_stop_timer()

        @callback
        def _due(_now: datetime) -> None:
            self._stop_timer = None
            self._entry.async_create_background_task(
                self._hass, self._async_stop_due(since), f"{DOMAIN} stop deadline"
            )

        self._stop_timer = async_call_later(
            self._hass,
            STOP_CONFIRM_TIMEOUT,
            HassJob(_due, f"{DOMAIN} stop deadline", cancel_on_shutdown=True),
        )

    def _end_stop_pending(self) -> None:
        self._stop_pending_since = None
        self._cancel_stop_timer()

    async def _async_stop_due(self, since: datetime) -> None:
        """The stop timer's work, under the lock: show the charger's state again."""
        async with self._lock:
            if self._closed or self._stop_pending_since != since:
                return
            _LOGGER.warning(
                "No stop seen within %s; showing the charger's state again",
                STOP_CONFIRM_TIMEOUT,
            )
            self._end_stop_pending()
            self._on_change()

    def _cancel_start_timer(self) -> None:
        if self._start_timer is not None:
            self._start_timer()
            self._start_timer = None

    def _cancel_stop_timer(self) -> None:
        if self._stop_timer is not None:
            self._stop_timer()
            self._stop_timer = None

    @callback
    def _cancel_timers(self) -> None:
        self._cancel_start_timer()
        self._cancel_stop_timer()
```

Check that no other code sets or clears `_pending_since` or `_stop_pending_since` directly (`grep -n "_pending_since =" custom_components/nortec_go/charge_control.py` shows only the helpers and `__init__`).

- [ ] **Step 6: Run the tests to see them pass**

Run: `uv run pytest tests/test_charge_control.py tests/test_init.py tests/test_coordinator.py tests/test_switch.py -q`
Expected: PASS. If a boundary test ("not a second earlier") is off by the sub-second scheduling, move its first tick to 2 s before the deadline rather than changing the code.

- [ ] **Step 7: Run the gates and commit**

Run the gates in Global Constraints, including the coverage gate. Commit: `fix: start and stop deadlines hold without reads (#34)`.

---

### Task 2: The interval rule during an outage, and the switch without a car

**Model:** opus — polling tied to charge start and stop.
**Wave:** 2

**Files:**
- Modify: `custom_components/nortec_go/const.py` (add `FAST_READ_MAX_AGE`)
- Modify: `custom_components/nortec_go/coordinator.py`
- Test: `tests/test_coordinator.py`, `tests/test_switch.py`

**Interfaces:**
- Consumes: Task 1's timers (a timer ending a pending state calls `on_change` → `_async_control_changed`).
- Produces: `FAST_READ_MAX_AGE: Final = timedelta(minutes=2)`; `interval_for(charger: Charger, control: ChargeControlState, age: timedelta) -> timedelta` (the third argument is new and required).

- [ ] **Step 1: Write the failing tests**

In `tests/test_coordinator.py`, change the last line of the existing `test_interval_for` to `assert interval_for(charger, control, timedelta(0)) == interval`, and add:

```python
def _switch(hass: HomeAssistant) -> str:
    """The Charge switch's state."""
    state = hass.states.get("switch.garage_charger_charge")
    assert state is not None
    return state.state


_STARTING = make_charger(is_connected=True, charge_state=ChargeState.STARTING)
_STOPPING = make_charger(is_connected=True, charge_state=ChargeState.STOPPING)


@pytest.mark.parametrize(
    ("charger", "control", "age", "interval"),
    [
        (
            _STOPPING,
            ChargeControlState(),
            FAST_READ_MAX_AGE - timedelta(seconds=1),
            INTERVAL_CHANGING,
        ),
        (_STOPPING, ChargeControlState(), FAST_READ_MAX_AGE, INTERVAL_CHARGING),
        (_STARTING, ChargeControlState(), FAST_READ_MAX_AGE, INTERVAL_CHARGING),
        (
            _STARTING,
            ChargeControlState(start_pending=True),
            timedelta(minutes=9),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True, charge_state=ChargeState.CHARGING),
            ChargeControlState(stop_pending=True),
            timedelta(minutes=1, seconds=50),
            INTERVAL_CHANGING,
        ),
        (
            make_charger(is_connected=True),
            ChargeControlState(start_pending=True),
            timedelta(minutes=9),
            INTERVAL_CHANGING,
        ),
        (_STOPPING, ChargeControlState(blocked=True), timedelta(0), INTERVAL_IDLE),
        (
            make_charger(is_connected=True, state=ChargerState.UNKNOWN),
            ChargeControlState(),
            timedelta(0),
            INTERVAL_IDLE,
        ),
        (
            make_charger(is_connected=True),
            ChargeControlState(),
            timedelta(hours=5),
            INTERVAL_IDLE,
        ),
    ],
)
def test_interval_for_by_read_age(
    charger: Any, control: ChargeControlState, age: timedelta, interval: timedelta
) -> None:
    """Our own pending states keep 30 s; the charger's own starting or stopping only while the read is fresh (D31)."""
    assert interval_for(charger, control, age) == interval


async def test_charger_stopping_during_an_outage_slows_down(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The charger's own STOPPING gives 30 s reads for about 2 minutes of an outage, then 5 min (Review Focus 5)."""
    mock_client.get_charger.return_value = _STOPPING
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert coordinator.update_interval == INTERVAL_CHANGING
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    freezer.tick(INTERVAL_CHANGING + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert coordinator.update_interval == INTERVAL_CHANGING
    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.update_interval == INTERVAL_CHARGING


async def test_pending_stop_during_an_outage_ends_at_2_minutes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """With reads failing, the pending stop ends at 2 minutes: the switch shows the last read, reads every 5 min."""
    mock_client.get_charger.return_value = make_charger(
        is_connected=True,
        charge_state=ChargeState.CHARGING,
        state=ChargerState.BUSY_CHARGING,
    )
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await coordinator.charge_control.async_stop()
    await hass.async_block_till_done()
    assert coordinator.data.control.stop_pending
    assert _switch(hass) == "off"
    freezer.tick(STOP_CONFIRM_TIMEOUT)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not coordinator.data.control.stop_pending
    assert _switch(hass) == "on"
    assert coordinator.update_interval == INTERVAL_CHARGING


async def test_pending_start_during_an_outage_blocks_at_10_minutes(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """With reads failing, the pending start ends at 10 minutes with the block, and reads every 60 min."""
    mock_client.get_charger.return_value = make_charger(is_connected=True)
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await coordinator.charge_control.async_start()
    await hass.async_block_till_done()
    assert coordinator.update_interval == INTERVAL_CHANGING
    freezer.tick(START_CONFIRM_TIMEOUT)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.data.control.blocked
    assert coordinator.update_interval == INTERVAL_IDLE
    assert _switch(hass) == "off"
```

(Imports: `FAST_READ_MAX_AGE`, `STOP_CONFIRM_TIMEOUT` from `custom_components.nortec_go.const`; `ChargerState` from `pynortecgo` if missing.) The existing `test_rate_limit_retry_after` and `test_later_charger_errors` stay as they are and must still pass: `retry_after` still wins, and an idle charger keeps 60 min.

Also add (the age in `_async_control_changed`, and `retry_after` beating the recomputed 30 s):

```python
async def test_control_change_during_an_outage_keeps_the_read_age(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A control change works the interval out from the last good read's real age."""
    mock_client.get_charger.return_value = _STOPPING
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    freezer.tick(timedelta(minutes=3))
    coordinator.charge_control._on_change()  # noqa: SLF001
    assert coordinator.update_interval == INTERVAL_CHARGING


async def test_rate_limit_retry_after_beats_the_fast_interval(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A RateLimitError's retry_after wins over the 30 s the failed read works out."""
    mock_client.get_charger.return_value = _STOPPING
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_charger.side_effect = RateLimitError(
        "too many requests", retry_after=120.0
    )
    await coordinator.async_refresh()
    reads = mock_client.get_charger.await_count
    # HA rounds timers to whole seconds, so check well before and well after 120 s.
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == reads
    freezer.tick(timedelta(seconds=70))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.get_charger.await_count == reads + 1
```

In `tests/test_switch.py`, add:

```python
async def test_switch_added_without_a_car(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """The Charge switch is added even when the account has no car (D32)."""
    mock_client.get_vehicle.side_effect = VehicleNotFoundError("no car")
    await setup_integration(hass, mock_config_entry)
    assert not mock_config_entry.runtime_data.has_car
    assert _state(hass) == STATE_OFF
```

(`VehicleNotFoundError` from `pynortecgo`.)

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_coordinator.py tests/test_switch.py -q`
Expected: FAIL — `FAST_READ_MAX_AGE` can't be imported, then `interval_for` takes 2 arguments, then `test_charger_stopping_during_an_outage_slows_down` and `test_control_change_during_an_outage_keeps_the_read_age` keep 30 s. The two outage tests at 2 and 10 minutes, the `retry_after` test and `test_switch_added_without_a_car` already pass after Task 1 (they pin the behaviour and D32).

- [ ] **Step 3: Implement**

In `custom_components/nortec_go/const.py`, after `INTERVAL_IDLE`:

```python
# The charger's own starting or stopping state keeps the 30 s reads only while the last good
# read is younger than this, so an outage doesn't read every 30 s (D31).
FAST_READ_MAX_AGE: Final = timedelta(minutes=2)
```

In `custom_components/nortec_go/coordinator.py` (import `FAST_READ_MAX_AGE`; import `Charger` from `pynortecgo` if not already):

```python
def interval_for(
    charger: Charger, control: ChargeControlState, age: timedelta
) -> timedelta:
    """The next polling interval, from the charge status and the last good read's age (D29, D31)."""
    if charge_status(charger, control) in ("starting", "stopping"):
        if control.start_pending or control.stop_pending or age < FAST_READ_MAX_AGE:
            return INTERVAL_CHANGING
        return INTERVAL_CHARGING  # the charger's own state, not seen for a while: a charge is open
    if charger.charge_state is ChargeState.CHARGING:
        return INTERVAL_CHARGING
    return INTERVAL_IDLE
```

In `_async_update_data`, replace `charger = await self.client.get_charger()` with `charger = await self._async_read_charger()` (the `except` chain around it is unchanged), and `self.update_interval = interval_for(charger, control)` with `self.update_interval = interval_for(charger, control, timedelta(0))`. Add:

```text
    async def _async_read_charger(self) -> Charger:
        """Read the charger; a failed read first sets the next interval from the last good one (D31)."""
        try:
            return await self.client.get_charger()
        except NortecGoError:
            if self.data is not None:
                self.update_interval = interval_for(
                    self.data.charger,
                    self.charge_control.state,
                    dt_util.utcnow() - self.data.read_at,
                )
            raise
```

In `_async_control_changed`, replace `self.update_interval = interval_for(self.data.charger, control)` with:

```text
        self.update_interval = interval_for(
            self.data.charger, control, dt_util.utcnow() - self.data.read_at
        )
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Run the gates and commit**

Run the gates in Global Constraints, including the coverage gate. Commit: `fix: no 30 s reads through an outage (#34)`.

---

### Task 3: User docs, changelog, quality scale, decisions and the docs model rule

**Model:** opus — a docs task (D33, owner ruling 2026-09-28).
**Wave:** 1

**Files:**
- Modify: `docs/user/nortec_go.md`, `CHANGELOG.md`, `custom_components/nortec_go/quality_scale.yaml`, `docs/decisions.md`, `docs/way-of-working.md`

**Interfaces:**
- Consumes: the names this plan fixes (D31, D32, the 10 and 2 minutes); no code.
- Produces: nothing code uses.

- [ ] **Step 1: User docs**

In `docs/user/nortec_go.md`:

*Unsupported devices*: replace "An account with more than one charger. With more than one car, the integration works without car entities." with:

```text
An account with more than one charger. With no car or more than one there are no car entities, and starting
a charge needs exactly one car and one saved card (see *Prerequisites*).
```

*Prerequisites*: replace the paragraph with:

```text
You need a Nortec Go account with exactly one charger. To start charges from Home Assistant, the account
also needs exactly one car and exactly one saved card; without them everything else works (the sensors, the
prices and *Refresh*), and a start is refused with the reason. A car added later appears after you reload
the integration.
```

*Starting a charge*:
- after the first paragraph ("…so a start is never retried."), add a paragraph: "A start is refused, with no card hold, without exactly one car and one saved card (see *Prerequisites*)."
- after the paragraph that ends "If no charge is seen by then, starts are blocked. After a stop, the charger needs the cable unplugged and replugged before the next start.", add a paragraph: "This also applies while the charger can't be read. The block clears the same way."
- replace the 2-minute paragraph with:

```text
After you turn *Charge* off, it shows off for up to 2 minutes, even while the charger can't be read, and
*Charge status* shows *Stopping* while Home Assistant waits for the charger to show the stop. Turning
*Charge* on in that time is refused.
```

*Data updates*: after the three-item list, add a paragraph: "While the charger can't be read, the 30-second reads stop after about 2 minutes, or about 10 minutes after you turn *Charge* on."

*Known limitations*: after "One charger per account…", add the item: "- Starting a charge needs exactly one car and one saved card (see *Prerequisites*)."

Keep lines at most 110 characters, wrapped like the rest of the file.

- [ ] **Step 2: Changelog**

In `CHANGELOG.md` under *Unreleased* → *Added*, replace the item "The charger is read every 30 seconds while a charge is starting or stopping, and right away after turning *Charge* on or off." with:

```text
- The charger is read every 30 seconds while a charge is starting or stopping, for about 2 minutes (10 after
  a start) while it can't be read, and right away after turning *Charge* on or off.
```

- [ ] **Step 3: Quality scale**

In `custom_components/nortec_go/quality_scale.yaml`, `appropriate-polling` stays `done`; its comment becomes:

```text
    comment: "30 s only while a charge is starting or stopping, bounded while reads fail (10 min after a start, 2 min after a stop or the last good read); 5 min while charging, 60 min otherwise (D29, D31)."
```

- [ ] **Step 4: Decisions**

In `docs/decisions.md`, change D29's status line to `- **Date:** 2026-09-27 · **Status:** active; the 30 s reads while the charger can't be read superseded by D31`. Append:

```markdown
### D31: The start and stop deadlines hold without reads
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** The 10-minute pending start (D26) and the 2-minute pending stop (D29) end by timers that
  fire whether or not the charger is read; a read ends them early only on evidence. The charger's own
  starting or stopping state gives 30 s reads only while the last good read is under 2 minutes old
  (5 min after that), and a failed read works the interval out again.
- **Why:** Checked only on successful reads, they lasted a whole outage, with reads every 30 s, and never
  ended with polling disabled; D29's "no cap" on the charger's own states assumed working reads.
- **Source:** [outage deadlines and start needs spec](superpowers/specs/2026-09-28-outage-deadlines-start-needs-design.md), §2–3

### D32: The Charge switch is always added
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** The *Charge* switch is added whatever cars the account has. A start without exactly one car
  and one saved card is refused with the reason, before any card hold.
- **Why:** The saved card can't be checked beforehand, so hiding the switch for the car alone would only
  half solve it, and the refusal explains itself.
- **Source:** [outage deadlines and start needs spec](superpowers/specs/2026-09-28-outage-deadlines-start-needs-design.md), Decisions

### D33: Docs tasks run on Opus
- **Date:** 2026-09-28 · **Status:** active
- **Decision:** Every docs task (a plan task whose output is docs) is tagged `Model: opus`.
- **Why:** Owner ruling.
- **Source:** owner ruling on 2026-09-28 (PR for #34, #35)
```

In `docs/way-of-working.md` §5, the `Model: opus` bullet's first paragraph becomes:

```text
- **`Model: opus`** (with a one-line reason) is for tasks that touch auth, tokens or reauth, anything near
  charge start/stop, or the mapping of `pynortecgo` models to entities; for debugging with an unknown
  cause; and for every docs task (D33).
```

- [ ] **Step 5: Check and commit**

Run: `uv run pytest tests/test_quality_scale.py -q` and `uv run pre-commit run --files docs/user/nortec_go.md CHANGELOG.md custom_components/nortec_go/quality_scale.yaml docs/decisions.md docs/way-of-working.md`
Expected: PASS. For this docs-only task these two checks are its gates (the quality-scale test covers the YAML; nothing else is code). Commit: `docs: what a start needs, the deadlines during an outage, and docs on Opus (#34, #35)`.
