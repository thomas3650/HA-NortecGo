# One retry for a failed price read Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** A failed setup or scheduled price read is read once more 15 minutes later (or after a longer `retry_after`), unless the next scheduled read comes first, and a run of failed price reads logs one warning and one recovery line.

**Architecture:** Task 1 adds the pure function `next_price_read()` to `prices.py`. Task 2 builds the retry and the log run into the coordinator on top of it, and has the setup read ask for a retry. Task 3 writes the user docs, the changelog line and D37. It runs in wave 1 next to Task 1, written against the names this plan fixes.

**Tech Stack:** Python 3.14, Home Assistant custom integration, `pynortecgo` 0.5.0 (always mocked in tests), pytest with `pytest-homeassistant-custom-component` and freezegun, uv.

**Spec:** `docs/superpowers/specs/2026-09-29-price-read-retry-design.md` (issue #39).

## Global Constraints

- TDD: write the failing test, see it fail, then write the code. Tests always mock `pynortecgo`, and fixtures come from `pynortecgo` model objects and the `tests/conftest.py` helpers, never raw API JSON (hard rules 2, 7).
- Never retry or log in on an `AuthError`: it starts reauth, or raises `ConfigEntryAuthFailed` during setup (hard rule 6). Never start or stop a real charge (hard rule 2).
- Nothing private (hard rule 3): no IDs, tokens, emails, captures, raw endpoints, response shapes, or links into the private client repo. Name only `pynortecgo`'s public API.
- Gates before every commit (`CLAUDE.md` → Commands): `uv run pytest -q`, then `uv run ruff check && uv run ruff format --check && uv run mypy`. The coverage gate (`--cov-fail-under=95`) passes at the end of each task.
- Subagents write commit messages with the Write tool to a file outside the repo, and commit with `git commit -F <file>` (no heredocs). End each message with the co-author trailer given in the dispatch.
- Match the surrounding code: comment density, one-line docstrings ending in a period, names. Exception tuples use the repo's Python 3.14 form `except KeyError, TypeError, ValueError:`.
- Retry delay: `PRICE_RETRY_DELAY = timedelta(minutes=15)`. For a `RateLimitError` whose `retry_after` (seconds) is longer, the delay is `retry_after`. No retry when `now + delay >= next_price_read(now, time_zone)`.
- Log texts, exactly: `Could not read the price forecast; keeping the known prices: %s` (warning for the first failure of a run, debug after that), and `Reading the price forecast works again` (info, the first success after a run).
- Decision number: D37.

## Review Focus

1. An outage that lasts all day makes exactly 2 reads per read time and logs one warning, not five (Task 2 tests `test_failed_scheduled_price_read_retries_once` and `test_price_log_run`).
2. Home Assistant stops while a retry is pending. It doesn't unload entries at stop, so the timer must be `cancel_on_shutdown=True`, the way `charge_control.py` schedules its deadlines. No test catches `False`: the `hass` fixture unloads entries at teardown, so the lingering-timer check never sees it. The reviewer checks the `HassJob` in Task 2 by reading it.
3. A *Refresh* while a retry is pending: a successful one cancels the retry, and a failed one leaves it (Task 2 tests `test_successful_refresh_cancels_price_retry` and `test_failed_refresh_keeps_a_pending_retry`).
4. A rate limit whose `retry_after` reaches the next read time: no retry, and nothing reads until that read time. The rule itself (`>=`, not `>`) is pinned by Task 2 test `test_no_retry_due_at_the_next_read`. In `test_rate_limited_price_read_retry_delay`'s 18000 s row and the 14:55 test, the scheduled read's cancel would hide a missing check.
5. A read at start-up just before a read time (14:55) fails: no retry, because the 15:05 read comes first (Task 2 tests `test_failed_setup_read_near_a_read_time_gets_no_retry` for the behaviour, `test_no_retry_due_at_the_next_read` for the rule).

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (`next_price_read`), Task 3 (docs) | Disjoint files, two worktrees off the feature branch. Task 3 is written against this plan's names and re-checked against the code that lands |
| 2 | Task 2 (coordinator retry and log run) | Needs Task 1's `next_price_read` on the feature branch |

No task has guarded files.

---

### Task 1: The next scheduled read

**Model:** sonnet — a pure time function with tests.
**Wave:** 1

**Files:**
- Modify: `custom_components/nortec_go/prices.py`
- Test: `tests/test_prices.py`

**Interfaces:**
- Consumes: `PRICE_READ_HOURS` (`(0, 5, 10, 15, 20)`) and `PRICE_READ_MINUTE` (`5`) from `const.py`.
- Produces: `next_price_read(now: datetime, time_zone: tzinfo) -> datetime` in `custom_components/nortec_go/prices.py`. It returns the first local read time strictly after `now`, as a UTC datetime (`tzinfo is UTC`).

- [ ] **Step 1: Write the failing test**

In `tests/test_prices.py`, add `next_price_read` to the import from `custom_components.nortec_go.prices` (alphabetical: after `merge_forecast`), then add:

```python
@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (
            datetime(2026, 9, 27, 0, 0, tzinfo=TZ),
            datetime(2026, 9, 27, 0, 5, tzinfo=TZ),
        ),
        (
            datetime(2026, 9, 27, 15, 4, 59, tzinfo=TZ),
            datetime(2026, 9, 27, 15, 5, tzinfo=TZ),
        ),
        (
            datetime(2026, 9, 27, 15, 5, tzinfo=TZ),
            datetime(2026, 9, 27, 20, 5, tzinfo=TZ),
        ),
        (
            datetime(2026, 9, 27, 20, 5, tzinfo=TZ),
            datetime(2026, 9, 28, 0, 5, tzinfo=TZ),
        ),
        (
            datetime(2026, 9, 27, 23, 59, tzinfo=TZ),
            datetime(2026, 9, 28, 0, 5, tzinfo=TZ),
        ),
        # Spring forward (02:00 -> 03:00): from before and after the change.
        (
            datetime(2026, 3, 29, 1, 0, tzinfo=TZ),
            datetime(2026, 3, 29, 5, 5, tzinfo=TZ),
        ),
        (
            datetime(2026, 3, 29, 20, 10, tzinfo=TZ),
            datetime(2026, 3, 30, 0, 5, tzinfo=TZ),
        ),
        # Fall back (03:00 -> 02:00): from before and after the change.
        (
            datetime(2026, 10, 25, 0, 10, tzinfo=TZ),
            datetime(2026, 10, 25, 5, 5, tzinfo=TZ),
        ),
        (
            datetime(2026, 10, 25, 20, 10, tzinfo=TZ),
            datetime(2026, 10, 26, 0, 5, tzinfo=TZ),
        ),
    ],
)
def test_next_price_read(now: datetime, expected: datetime) -> None:
    """The next read time is the first local 00:05, 05:05, 10:05, 15:05 or 20:05 after now, in UTC."""
    result = next_price_read(now.astimezone(UTC), TZ)
    assert result == expected
    assert result.tzinfo is UTC
```

Let `ruff format` lay out the rows. If it reflows them, keep what it produces.

- [ ] **Step 2: Run the test to see it fail**

Run: `uv run pytest tests/test_prices.py -q -k next_price_read`
Expected: FAIL with `ImportError: cannot import name 'next_price_read'`.

- [ ] **Step 3: Write the code**

In `custom_components/nortec_go/prices.py`, add `PRICE_READ_HOURS` and `PRICE_READ_MINUTE` to the `.const` import (keep it alphabetical). Then add this after `current_price`:

```python
def _local_read_time(day: date, hour: int, time_zone: tzinfo) -> datetime:
    """A read time on a local day, in UTC; fold=0 on a repeated hour."""
    return datetime.combine(
        day, time(hour, PRICE_READ_MINUTE), tzinfo=time_zone
    ).astimezone(UTC)


def next_price_read(now: datetime, time_zone: tzinfo) -> datetime:
    """The first scheduled price read after now, in UTC (D37)."""
    today = now.astimezone(time_zone).date()
    for hour in PRICE_READ_HOURS:
        read = _local_read_time(today, hour, time_zone)
        if read > now:
            return read
    return _local_read_time(today + timedelta(days=1), PRICE_READ_HOURS[0], time_zone)
```

Add `date` to the `datetime` import: `from datetime import UTC, date, datetime, time, timedelta, tzinfo`.

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_prices.py -q`
Expected: all pass.

- [ ] **Step 5: Gates and commit**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`, and the coverage gate.

Commit message (written to a file outside the repo, `git commit -F`):

```text
feat: next_price_read, the first price read time after now (#39)
```

---

### Task 2: The retry and the log run in the coordinator

**Model:** opus — the `AuthError` path of the price read (reauth, cancelling the retry, hard rule 6).
**Wave:** 2

**Files:**
- Modify: `custom_components/nortec_go/const.py`
- Modify: `custom_components/nortec_go/coordinator.py`
- Modify: `custom_components/nortec_go/__init__.py:61` (the setup read)
- Test: `tests/test_coordinator.py`, `tests/test_init.py`

**Interfaces:**
- Consumes: `next_price_read(now: datetime, time_zone: tzinfo) -> datetime` from `custom_components/nortec_go/prices.py` (Task 1). Import it into `coordinator.py` by name, so tests can patch `custom_components.nortec_go.coordinator.next_price_read`.
- Produces:
  - `PRICE_RETRY_DELAY: Final = timedelta(minutes=15)` in `const.py`.
  - `NortecGoCoordinator.async_read_prices(*, during_setup: bool = False, retry_on_failure: bool = False) -> None`.
  - `NortecGoCoordinator.async_start_price_read(*, retry_on_failure: bool = False) -> None` (a `@callback`).
  - *Refresh* (`button.py`) still calls `async_read_prices()` with the defaults and doesn't change.

- [ ] **Step 1: Write the failing coordinator tests**

In `tests/test_coordinator.py`, add `import logging` after `from datetime import UTC, datetime, timedelta` (isort order; `uv run ruff check --fix` settles it). Then add these tests after `test_later_price_auth_error_starts_reauth`:

```python
async def _at(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: datetime
) -> None:
    """Move the clock to when and run what is due, background tasks included."""
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done(wait_background_tasks=True)


def _local(hours: int, minutes: int = 0) -> datetime:
    """A local time on 2026-09-27, in UTC."""
    return MIDNIGHT + timedelta(hours=hours, minutes=minutes)


@pytest.mark.parametrize(
    "error",
    [
        NortecGoConnectionError("network down"),
        UnexpectedResponseError("GET /example", "gap"),
    ],
)
async def test_failed_scheduled_price_read_retries_once(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    error: NortecGoError,
) -> None:
    """A failed 15:05 read is read once more at 15:20, and then not until 20:05."""
    freezer.move_to(_local(15))
    await setup_integration(hass, mock_config_entry)
    forecast = mock_client.get_price_forecast
    mock_client.get_price_forecast.side_effect = error

    await _at(hass, freezer, _local(15, 5))
    assert forecast.await_count == 2
    await _at(hass, freezer, _local(15, 19))
    assert forecast.await_count == 2
    await _at(hass, freezer, _local(15, 20))
    assert forecast.await_count == 3
    await _at(hass, freezer, _local(15, 35))
    await _at(hass, freezer, _local(20, 4))
    assert forecast.await_count == 3
    await _at(hass, freezer, _local(20, 5))
    assert forecast.await_count == 4


async def test_successful_refresh_cancels_price_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A successful read (Refresh) cancels a pending retry."""
    freezer.move_to(_local(15))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await _at(hass, freezer, _local(15, 5))

    mock_client.get_price_forecast.side_effect = None
    freezer.move_to(_local(15, 10))
    await coordinator.async_read_prices()
    assert mock_client.get_price_forecast.await_count == 3
    await _at(hass, freezer, _local(15, 20))
    assert mock_client.get_price_forecast.await_count == 3


async def test_failed_refresh_keeps_a_pending_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed Refresh schedules no retry of its own and leaves a pending one."""
    freezer.move_to(_local(12))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    forecast = mock_client.get_price_forecast
    forecast.side_effect = NortecGoConnectionError("network down")

    await coordinator.async_read_prices()
    assert forecast.await_count == 2
    await _at(hass, freezer, _local(12, 15))
    assert forecast.await_count == 2

    await _at(hass, freezer, _local(15, 5))
    assert forecast.await_count == 3
    freezer.move_to(_local(15, 10))
    await coordinator.async_read_prices()
    assert forecast.await_count == 4
    await _at(hass, freezer, _local(15, 20))
    assert forecast.await_count == 5
    await _at(hass, freezer, _local(15, 35))
    assert forecast.await_count == 5


async def test_failed_setup_read_near_a_read_time_gets_no_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed setup read at 14:55 gets no retry: the 15:05 read comes first."""
    freezer.move_to(_local(14, 55))
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    forecast = mock_client.get_price_forecast
    assert forecast.await_count == 1

    await _at(hass, freezer, _local(15, 4))
    assert forecast.await_count == 1
    await _at(hass, freezer, _local(15, 5))
    assert forecast.await_count == 2
    await _at(hass, freezer, _local(15, 10))
    assert forecast.await_count == 2
    await _at(hass, freezer, _local(15, 20))
    assert forecast.await_count == 3


@pytest.mark.parametrize(
    ("retry_after", "retry_minutes"),
    [(1800.0, 30), (60.0, 15), (None, 15), (18000.0, None)],
)
async def test_rate_limited_price_read_retry_delay(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    retry_after: float | None,
    retry_minutes: int | None,
) -> None:
    """The retry waits the longer of 15 minutes and retry_after, and is dropped if it reaches 20:05."""
    freezer.move_to(_local(15))
    await setup_integration(hass, mock_config_entry)
    forecast = mock_client.get_price_forecast
    forecast.side_effect = RateLimitError("too many requests", retry_after=retry_after)
    await _at(hass, freezer, _local(15, 5))
    assert forecast.await_count == 2

    for minutes in range(10, 300, 5):  # 15:15 to 20:00
        await _at(hass, freezer, _local(15, 5 + minutes))
        retried = retry_minutes is not None and minutes >= retry_minutes
        assert forecast.await_count == (3 if retried else 2), minutes


async def test_no_retry_due_at_the_next_read(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A retry that would be due at the next read time is not scheduled."""
    freezer.move_to(_local(12))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    forecast = mock_client.get_price_forecast
    forecast.side_effect = NortecGoConnectionError("network down")
    # The next read time is exactly when the retry would be due; no scheduled read runs then.
    with patch(
        "custom_components.nortec_go.coordinator.next_price_read",
        return_value=_local(12, 15),
    ):
        await coordinator.async_read_prices(retry_on_failure=True)
    await _at(hass, freezer, _local(12, 15))
    assert forecast.await_count == 2


async def test_price_auth_error_schedules_no_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An AuthError in a scheduled read starts reauth, with no retry and no login."""
    freezer.move_to(_local(15))
    await setup_integration(hass, mock_config_entry)
    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth") as start_reauth:
        await _at(hass, freezer, _local(15, 5))
        await _at(hass, freezer, _local(15, 20))
    assert mock_client.get_price_forecast.await_count == 2
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()


async def test_price_auth_error_on_the_retry_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An AuthError in the retry starts reauth, without logging in."""
    freezer.move_to(_local(15))
    await setup_integration(hass, mock_config_entry)
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await _at(hass, freezer, _local(15, 5))

    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth") as start_reauth:
        await _at(hass, freezer, _local(15, 20))
    assert mock_client.get_price_forecast.await_count == 3
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()


async def test_price_auth_error_cancels_a_pending_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """An AuthError (here in a Refresh) cancels a pending retry."""
    freezer.move_to(_local(15))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await _at(hass, freezer, _local(15, 5))

    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    freezer.move_to(_local(15, 10))
    with patch.object(ConfigEntry, "async_start_reauth"):
        await coordinator.async_read_prices()
    mock_client.get_price_forecast.side_effect = None
    await _at(hass, freezer, _local(15, 20))
    assert mock_client.get_price_forecast.await_count == 3


async def test_scheduled_read_cancels_a_pending_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A scheduled read cancels a pending retry, also when it schedules none of its own."""
    freezer.move_to(_local(14, 55))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    forecast = mock_client.get_price_forecast
    forecast.side_effect = NortecGoConnectionError("network down")
    # Let the too-late check pass, so a retry is pending for 15:10, past the 15:05 read.
    with patch(
        "custom_components.nortec_go.coordinator.next_price_read",
        return_value=_local(24),
    ):
        await coordinator.async_read_prices(retry_on_failure=True)
    assert forecast.await_count == 2

    # retry_after reaches 20:05, so the 15:05 read schedules no retry of its own.
    forecast.side_effect = RateLimitError("too many requests", retry_after=18000.0)
    await _at(hass, freezer, _local(15, 5))
    assert forecast.await_count == 3
    await _at(hass, freezer, _local(15, 10))
    assert forecast.await_count == 3


async def test_price_log_run(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A run of failed price reads logs one warning, then debug; its end logs one info line."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    freezer.move_to(_local(12))
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)
    assert "Reading the price forecast works again" not in caplog.text

    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await coordinator.async_read_prices()
    await coordinator.async_read_prices()
    failures = [
        record.levelno
        for record in caplog.records
        if record.getMessage().startswith("Could not read the price forecast")
    ]
    assert failures == [logging.WARNING, logging.DEBUG]

    mock_client.get_price_forecast.side_effect = None
    await coordinator.async_read_prices()
    await coordinator.async_read_prices()
    recoveries = [
        record.levelno
        for record in caplog.records
        if record.getMessage() == "Reading the price forecast works again"
    ]
    assert recoveries == [logging.INFO]
```

`NortecGoError`, `RateLimitError`, `UnexpectedResponseError`, `AuthError`, `ConfigEntry`, `ConfigEntryState` and `patch` are already imported in this file.

- [ ] **Step 2: Write the failing setup tests**

In `tests/test_init.py`, add `from datetime import UTC, datetime, timedelta` (replacing `from datetime import timedelta`). Then add these after `test_unload_cancels_a_price_read_in_flight`:

```python
# 2026-09-27 10:00 local (CEST) is 08:00 UTC.
TEN_AM = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)


async def test_failed_setup_price_read_retries(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed setup price read still loads the entry and is read once more 15 minutes later."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    freezer.move_to(TEN_AM - timedelta(minutes=30))  # 09:30 local
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_client.get_price_forecast.await_count == 1

    mock_client.get_price_forecast.side_effect = None
    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_client.get_price_forecast.await_count == 2
    assert mock_config_entry.runtime_data.known_prices


async def test_unload_cancels_a_pending_price_retry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Unload cancels a retry that isn't due yet."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    freezer.move_to(TEN_AM - timedelta(minutes=30))
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_client.get_price_forecast.await_count == 1


async def test_unload_cancels_a_price_retry_in_flight(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A retry read still running at unload is cancelled."""
    await hass.config.async_set_time_zone("Europe/Copenhagen")
    freezer.move_to(TEN_AM - timedelta(minutes=30))
    mock_client.get_price_forecast.side_effect = NortecGoConnectionError("network down")
    await setup_integration(hass, mock_config_entry)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def _slow_forecast() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    mock_client.get_price_forecast.side_effect = _slow_forecast
    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert started.is_set()  # not started.wait(): without a retry that would hang
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert cancelled.is_set()
```

Check that `NortecGoConnectionError`, `async_fire_time_changed`, `FrozenDateTimeFactory`, `ConfigEntryState` and `asyncio` are imported in `tests/test_init.py` (they are today), and that `setup_integration` is imported from `.conftest`.

- [ ] **Step 3: Run the new tests to see them fail**

Run: `uv run pytest tests/test_coordinator.py tests/test_init.py -q -k "retr or log_run or near_a_read_time or scheduled_read_cancels or next_read"`
Expected: FAIL. With no retry there's no read at +15 minutes, `retry_on_failure` is an unexpected keyword, both failures log at warning, and there's no recovery line. Some tests pass already, because they assert that nothing reads: `test_successful_refresh_cancels_price_retry`, the 18000 s row, `test_price_auth_error_schedules_no_retry`, `test_price_auth_error_cancels_a_pending_retry` and `test_unload_cancels_a_pending_price_retry`. That's expected. Each one fails once the code line it targets is removed.

- [ ] **Step 4: Add the constant**

In `custom_components/nortec_go/const.py`, after `PRICE_READ_MINUTE`:

```python
# A failed setup or scheduled price read is read once more after this (D37).
PRICE_RETRY_DELAY: Final = timedelta(minutes=15)
```

- [ ] **Step 5: Write the coordinator code**

In `custom_components/nortec_go/coordinator.py`:

Imports:
- `from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback`
- `from homeassistant.helpers.event import async_call_later, async_track_time_change`
- add `PRICE_RETRY_DELAY` to the `.const` import (alphabetical: after `PRICE_READ_MINUTE`)
- `from .prices import KnownSlots, PriceStore, merge_forecast, next_price_read, prune`

At the end of `__init__`:

```python
        self._prices_failing = False
        self._price_retry: CALLBACK_TYPE | None = None
        # The setup read can schedule a retry before the timers start.
        entry.async_on_unload(self._async_cancel_price_retry)
```

Replace `async_read_prices` with the block below. These are methods of `NortecGoCoordinator`, indented one level. The block is a `text` block, because the `ruff-format` hook would dedent a Python block of methods.

```text
    async def async_read_prices(
        self, *, during_setup: bool = False, retry_on_failure: bool = False
    ) -> None:
        """Read the forecast, merge, prune and save it with its currency; keep the known slots on failure (§4.3).

        A failed read asked to retry on failure is read once more later (D37).
        """
        try:
            forecast = await self.client.get_price_forecast()
        except AuthError as err:
            self._async_cancel_price_retry()
            if during_setup:
                raise ConfigEntryAuthFailed(str(err)) from err
            self.config_entry.async_start_reauth(self.hass)
            return
        except NortecGoError as err:
            self._log_price_error(err)
            if retry_on_failure:
                self._async_schedule_price_retry(err)
            return
        self._async_cancel_price_retry()
        if self._prices_failing:
            self._prices_failing = False
            _LOGGER.info("Reading the price forecast works again")
        self.known_prices = prune(
            merge_forecast(self.known_prices, forecast),
            dt_util.utcnow(),
            dt_util.get_default_time_zone(),
        )
        if forecast.currency is not None:
            self.price_currency = forecast.currency
        await self._price_store.async_save(self.known_prices, self.price_currency)
        self.async_update_listeners()

    def _log_price_error(self, err: NortecGoError) -> None:
        """Log the first price read failure of a run at warning, later ones at debug (D37)."""
        level = logging.DEBUG if self._prices_failing else logging.WARNING
        self._prices_failing = True
        _LOGGER.log(
            level,
            "Could not read the price forecast; keeping the known prices: %s",
            err,
        )

    @callback
    def _async_schedule_price_retry(self, err: NortecGoError) -> None:
        """Read the prices once more later, unless the next scheduled read comes first (D37)."""
        delay = PRICE_RETRY_DELAY
        if isinstance(err, RateLimitError) and err.retry_after is not None:
            delay = max(delay, timedelta(seconds=err.retry_after))
        now = dt_util.utcnow()
        if now + delay >= next_price_read(now, dt_util.get_default_time_zone()):
            return
        self._async_cancel_price_retry()

        @callback
        def _due(_now: datetime) -> None:
            self._price_retry = None
            self.async_start_price_read()

        self._price_retry = async_call_later(
            self.hass,
            delay,
            HassJob(_due, f"{DOMAIN} price read retry", cancel_on_shutdown=True),
        )

    @callback
    def _async_cancel_price_retry(self) -> None:
        """Cancel a pending price read retry, if any."""
        if self._price_retry is not None:
            self._price_retry()
            self._price_retry = None
```

Replace `async_start_price_read` with:

```python
    @callback
    def async_start_price_read(self, *, retry_on_failure: bool = False) -> None:
        """Start one price read as a background task that unload cancels."""
        self.config_entry.async_create_background_task(
            self.hass,
            self.async_read_prices(retry_on_failure=retry_on_failure),
            f"{DOMAIN} price read",
        )
```

In `async_start_timers`, replace `_price_time`'s body:

```python
        @callback
        def _price_time(now: datetime) -> None:
            # The scheduled read replaces a pending retry (D37).
            self._async_cancel_price_retry()
            self.async_start_price_read(retry_on_failure=True)
```

- [ ] **Step 6: The setup read asks for a retry**

In `custom_components/nortec_go/__init__.py`, change the setup read to:

```python
    await coordinator.async_read_prices(during_setup=True, retry_on_failure=True)
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `uv run pytest tests/test_coordinator.py tests/test_init.py tests/test_sensor.py tests/test_button.py -q`
Expected: all pass, including the existing price tests (`test_failed_price_read_keeps_slots` still finds the warning text; `test_later_price_auth_error_starts_reauth` still passes).

- [ ] **Step 8: Gates and commit**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`, and the coverage gate.

Commit message (written to a file outside the repo, `git commit -F`):

```text
fix: one retry for a failed price read, and one warning per outage (#39)
```

---

### Task 3: Docs, changelog and decision log

**Model:** opus — a docs task (D33).
**Wave:** 1 (written against this plan's names; re-checked against the code that lands)

**Files:**
- Modify: `docs/user/nortec_go.md` (*Data updates*, *Known limitations*)
- Modify: `CHANGELOG.md` (*Unreleased* → *Added*)
- Modify: `docs/decisions.md` (append D37)

**Interfaces:**
- Consumes: the behaviour and constants in this plan's Global Constraints (15 minutes, `retry_after`, no retry at or after the next read time, the log texts), and the spec's §4 to §6.
- Produces: docs only.

- [ ] **Step 1: User docs, *Data updates***

In `docs/user/nortec_go.md`, *Data updates*, the paragraph that ends "…at 00:05, 05:05, 10:05, 15:05 and 20:05. The current price moves to the next 15 minutes by itself, without a read." Insert this sentence after "…15:05 and 20:05.", before "The current price moves…":

```text
If a price read at start-up or at one of these times fails, the integration tries once more 15 minutes
later (or later, if the Nortec Go service asks it to wait), unless the next read time comes first.
```

Re-wrap the paragraph to the file's line length (about 110 characters).

- [ ] **Step 2: User docs, *Known limitations***

Replace the bullet

```text
- Tomorrow's prices are a forecast until the day-ahead prices come out, around 13:00; the 15:05 read
  replaces them.
```

with

```text
- Tomorrow's prices are a forecast until the day-ahead prices come out, around 13:00; the 15:05 read
  replaces them (or its retry about 15 minutes later, if it fails).
```

- [ ] **Step 3: Changelog**

In `CHANGELOG.md`, *Unreleased* → *Added*, after the *Refresh* button line:

```text
- A failed price read at start-up or at a read time is tried once more 15 minutes later, and an outage logs
  one warning instead of one per read.
```

- [ ] **Step 4: Decision log**

Append to `docs/decisions.md` after the last entry (D36), with one blank line before it:

```markdown
### D37: One retry for a failed price read
- **Date:** 2026-09-29 · **Status:** active
- **Decision:** A failed setup or scheduled price read, except on an `AuthError`, is read once more after
  15 minutes (or a longer `retry_after`), unless the next scheduled read comes first; a failed retry or
  *Refresh* gets none. A run of failed price reads logs one warning and one recovery line.
- **Why:** A failed 15:05 read left EV Smart Charging on the forecast until 20:05; one retry per read keeps
  the rate-limited API's load at most doubled.
- **Source:** [price read retry spec](superpowers/specs/2026-09-29-price-read-retry-design.md), Decisions and §3
```

- [ ] **Step 5: Check and commit**

Run: `uv run pre-commit run --files docs/user/nortec_go.md CHANGELOG.md docs/decisions.md`.
Expected: pass.

Commit message (written to a file outside the repo, `git commit -F`):

```text
docs: the price read retry in the user docs, changelog and D37 (#39)
```
