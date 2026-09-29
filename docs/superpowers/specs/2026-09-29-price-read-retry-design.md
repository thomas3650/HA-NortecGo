# Try a failed price read again sooner — design

Date: 2026-09-29 · Branch: `fix/price-read-retry` · Issue: #39

## Goal

- **What:** a failed setup or scheduled price read is tried once more, 15 minutes later, and a run of failed
  price reads logs one warning and one recovery line (`log-when-unavailable`).
- **Why:** prices are read only at setup and at 00:05, 05:05, 10:05, 15:05 and 20:05 (D27, D29). A failed
  15:05 read leaves EV Smart Charging planning on tomorrow's forecast until 20:05, and a failed setup read on
  an empty store leaves no known prices for up to 5 hours. Today every failed read logs a warning, so an
  outage logs five a day.
- **Not in this work:** retries of the charger or car reads (the coordinator's own polling handles those),
  and any change to the read times.
- **Done when:** built TDD with `pynortecgo` mocked in every test; the gates pass; user docs, changelog and
  decision log updated.

## Decisions

Proposed by the team lead and approved by the owner through the PO (issue #39, 2026-09-29). The cancel at
the start of a scheduled read, the retry timer's form and the DST handling were settled in the spec review.

| Topic | Decision |
|---|---|
| What gets a retry | A failed setup read or scheduled read. A failed *Refresh* doesn't (the user can press it again), and a failed retry doesn't. So each setup or scheduled read makes at most 2 reads |
| Which errors | Every `NortecGoError` except `AuthError`, `UnexpectedResponseError` included: one extra read is cheap |
| `AuthError` | Unchanged: at setup `ConfigEntryAuthFailed`; later (a scheduled read, a retry, *Refresh*) reauth starts. Never a retry, never a login (hard rule 6). It also cancels a pending retry |
| Delay | 15 minutes; for a `RateLimitError` with `retry_after`, the longer of 15 minutes and `retry_after` |
| Retry too late | No retry when it would be due at or after the next scheduled read: that read comes anyway |
| Pending retries | At most one. A successful read (any source, *Refresh* included) cancels it; the start of a scheduled read cancels it; a new retry replaces it; unload cancels it, and a retry read already running |
| Log run | A run is the consecutive failed price reads, from any source. The first failure is logged at warning, later ones at debug, and the first success after a run at info |
| Decision log | D37, which adds to D27's and D29's read schedule without replacing any part of it: their statuses don't change |
| Process | Full path (spec, plan, `full-reviewer`); no D25 ruling |

Facts used, public-safe:

- `pynortecgo` 0.5.0: `RateLimitError.retry_after` is in seconds, or `None`. `AuthError` and
  `RateLimitError` are subclasses of `NortecGoError`.
- `ConfigEntry.async_on_unload` callbacks also run when a setup fails after they were added, so a retry
  scheduled by the setup read is cancelled then too.

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/const.py` | `PRICE_RETRY_DELAY = timedelta(minutes=15)` |
| `custom_components/nortec_go/prices.py` | `next_price_read()` (§2) |
| `custom_components/nortec_go/coordinator.py` | The retry and the log run (§3) |
| `custom_components/nortec_go/__init__.py` | The setup read asks for a retry on failure (§3.1) |
| `docs/user/nortec_go.md` | §4 |
| `CHANGELOG.md` | §5 |
| `docs/decisions.md` | D37 (§6) |
| `tests/test_prices.py`, `tests/test_coordinator.py`, `tests/test_init.py` | §7 |

`button.py` doesn't change: *Refresh* calls `async_read_prices()` with the defaults, which ask for no retry.
`quality_scale.yaml` doesn't change: `log-when-unavailable` is already `done`.

## 2. The next scheduled read

`next_price_read(now: datetime, time_zone: tzinfo) -> datetime` in `prices.py` returns the first local
`PRICE_READ_HOURS`:`PRICE_READ_MINUTE` time strictly after `now`, in UTC. It looks at now's local day and the
next one, and builds each local time with `datetime.combine(day, time(hour, minute), tzinfo=time_zone)`
(`fold=0`), so it is a well-defined UTC instant in every zone. In zones whose DST change falls between about
01:00 and 04:59 local (the EU, for example) each read time exists exactly once a day. In zones whose change
falls at local midnight, 00:05 can be skipped or repeated on a change day; there the result may be off by the
change, which at worst skips a retry or lets a pending retry meet the scheduled read. The cancel rules (§3.2)
cover that, so no zone needs special handling.

## 3. The coordinator

### 3.1 Asking for a retry

`async_read_prices(*, during_setup: bool = False, retry_on_failure: bool = False)`:

- the setup read (`__init__.py`) passes `during_setup=True, retry_on_failure=True`;
- the scheduled read passes `retry_on_failure=True`: `async_start_price_read(*, retry_on_failure: bool = False)`
  passes it on, and the price-time callback asks for it;
- *Refresh* and the retry itself use the defaults, so they never schedule a retry. This keeps the
  one-retry-per-read rule in the call sites, not in state.

### 3.2 The read

On a `NortecGoError` other than `AuthError`:

1. log it by the log run (§3.4);
2. if `retry_on_failure`, schedule the retry (§3.3).

The known slots are kept, as today.

On an `AuthError`: cancel a pending retry; then, as today, raise `ConfigEntryAuthFailed` during setup, or
start reauth. No log-run change: reauth has its own UI.

On success: cancel a pending retry, end the log run (§3.4), then merge, prune, save and update the
listeners, as today.

A scheduled read cancels a pending retry before it starts its read: the `_price_time` callback in
`async_start_timers` cancels it, then calls `async_start_price_read(retry_on_failure=True)`. The scheduled
read replaces the retry, and gets its own retry if it fails.

### 3.3 The retry

- The delay is `PRICE_RETRY_DELAY`, or `retry_after` seconds when the error is a `RateLimitError` whose
  `retry_after` is longer.
- If `now + delay` is at or after `next_price_read(now, time_zone)`, no retry is scheduled. `now` is
  `dt_util.utcnow()` taken after the failed read, and `time_zone` is `dt_util.get_default_time_zone()`, the
  zone `prune` uses.
- Otherwise a pending retry is cancelled, and a new one is scheduled as the charge control schedules its
  deadlines: `async_call_later(hass, delay, HassJob(_due, f"{DOMAIN} price read retry",
  cancel_on_shutdown=True))`. `cancel_on_shutdown` matters because Home Assistant doesn't unload entries when
  it stops. The callback clears the handle and starts the read with `async_start_price_read()` (defaults: no
  further retry), as an entry background task, so unload cancels it while it runs.
- The coordinator keeps one cancel handle (`None` when nothing is pending). It registers one
  `config_entry.async_on_unload` callback, in `__init__`, that cancels a pending retry: the setup read runs
  before `async_start_timers()`.

Because a retry is never due at or after the next scheduled read, a scheduled read normally doesn't meet a
pending retry; the cancel at the start of a scheduled read (§3.2) keeps that true when it does. A retry due
just before a read time (say 15:04:59) can run next to the 15:05 read, two reads a second apart; that is
harmless and still at most 2 reads per scheduled read, so there's no margin. A pending retry can meet a
*Refresh*: a successful *Refresh* cancels it, a failed one leaves it.

### 3.4 The log run

A `_prices_failing` flag, like `_car_failing`:

- a failure while it is false sets it and logs at warning, with the same text as today:
  `Could not read the price forecast; keeping the known prices: %s`;
- a failure while it is true logs the same text at debug;
- a success while it is true clears it and logs at info: `Reading the price forecast works again`.

The error's message may be logged: `pynortecgo`'s messages hold no tokens, emails or IDs. An `AuthError`
neither sets nor clears the flag.

## 4. User docs

In *Data updates*, after the sentence on the price read times:

> If a price read at start-up or at one of these times fails, the integration tries once more 15 minutes
> later (or later, if the Nortec Go service asks it to wait), unless the next read time comes first.

In *Known limitations*, the line on tomorrow's prices becomes:

> Tomorrow's prices are a forecast until the day-ahead prices come out, around 13:00; the 15:05 read
> replaces them (or its retry about 15 minutes later, if it fails).

## 5. Changelog

Nothing is released since `v0.0.1`, so the price read is itself an *Unreleased* addition. One line under
*Added*:

> A failed price read at start-up or at a read time is tried once more 15 minutes later, and an outage logs
> one warning instead of one per read.

## 6. Decision log

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

## 7. Tests

With `pynortecgo` mocked, the freezer and `async_fire_time_changed`, as the existing price tests do.

`tests/test_prices.py`, `next_price_read`:

- before 00:05 → today's 00:05; at 15:05 exactly → 20:05; after 20:05 → tomorrow's 00:05;
- on the DST change days in `Europe/Copenhagen` (the time zone `test_prices.py` uses), the next read is
  right, from before and after the change.

`tests/test_coordinator.py`:

- a failed scheduled read (15:05) makes exactly one more read at 15:20, and none before or after it until
  20:05;
- a failed retry makes no further read until the next scheduled time;
- a successful *Refresh* cancels a pending retry: no read at +15 minutes;
- a failed *Refresh* schedules no retry, and leaves a pending one;
- a failed setup read at 14:55 schedules no retry, since 15:10 is after 15:05; the 15:05 read comes as
  scheduled;
- a `RateLimitError` with `retry_after` 1800 s retries after 30 minutes, not 15; one with `retry_after` 60 s
  retries after 15 minutes; one whose `retry_after` reaches the next read gets no retry;
- an `AuthError` on a scheduled read schedules no retry; an `AuthError` on the retry starts reauth without
  `login`; an `AuthError` cancels a pending retry;
- `UnexpectedResponseError` is retried like a connection error;
- a scheduled read cancels a pending retry, in the one case no other rule covers: at 14:55 a failing
  `async_read_prices(retry_on_failure=True)` with `custom_components.nortec_go.coordinator.next_price_read`
  patched to a later time leaves a retry pending for 15:10; with the patch gone, the 15:05 read fails with a
  `RateLimitError` whose `retry_after` is 18000 s (it reaches 20:05), so it schedules no retry of its own;
  the test asserts the 15:05 read ran, then that no read starts at 15:10;
- log run (with `caplog.set_level(logging.DEBUG)`): two failed reads in a row log one warning (the second at
  debug); the next success logs `Reading the price forecast works again` at info once; a success without a
  failure before it logs no info.

`tests/test_init.py`:

- a failed setup read (non-auth) still loads the entry and makes one more read after 15 minutes;
- unload cancels a pending retry: no read at +15 minutes;
- unload cancels a retry read that is running (like the existing in-flight test).
