# Refresh press reports a failed read — design

Date: 2026-10-01 · Branch: `fix/refresh-feedback` · Issue: #40

## Goal

- **What:** a press on the *Refresh* button raises a translated error when its charger read or its price read
  fails. The press and the quality scale rule `action-exceptions` then agree, and the rule goes to `done`.
- **Why:** today a press during an outage succeeds silently, so the owner can think the data is fresh when it
  isn't. The only signs are unavailable entities and the *Last read* time.
- **Not in this work:**
  - The scheduled reads. Polling, the price read times and the price read retry (D37) behave as today.
  - What fails a read. The coordinator decides that as today, also for the car: a rejected car read
    (`AuthError`) fails the read, and every other car error keeps the car's last data and fails nothing. So
    a press reports a rejected car read, and no other car error (§2).
  - `homeassistant.update_entity`. It is Home Assistant's own action and stays silent on a failed read.
  - Anything in charge start or stop.
- **Done when:** the cases in §1 hold in tests with `pynortecgo` mocked, `action-exceptions` is `done`, the
  user docs and `CHANGELOG.md` say what a failed press does, D43 is in `decisions.md`, and the gates pass.

## Decisions

Answered by the owner through the PO (issue #40, 2026-10-01).

| Topic | Decision |
|---|---|
| A press whose read fails | Raises a translated `HomeAssistantError` (D43) |
| A press where only the price read fails | Raises too |
| Both reads fail | The charger's error is the one raised |
| The price read after a failed charger read | Still runs, as the issue asks |
| Texts | The charger read reuses the #37 texts. The price read gets one new text (§3) |
| Release level | Releasing: the title is `fix: …`, with a CHANGELOG entry and the bump step |

Facts used, from the installed Home Assistant source (`helpers/update_coordinator.py`):

- Outside setup, `DataUpdateCoordinator.async_refresh()` stores a read's error in `last_exception` instead
  of raising it, and sets `last_update_success` to `False`. This includes `ConfigEntryAuthFailed` and
  `ConfigEntryError`. For `ConfigEntryAuthFailed` the coordinator itself starts reauth.
- A good read sets `last_update_success` back to `True` but doesn't clear `last_exception`
  (`docs/ha-notes.md`), so the button goes by `last_update_success`.
- `HomeAssistantError` and its subclasses (`UpdateFailed`, `ConfigEntryAuthFailed`, `ConfigEntryError`) carry
  `translation_domain`, `translation_key` and `translation_placeholders`.

## 1. Behaviour

A press does what it does today, in the same order: it reads the charger and the car, then the prices. New
is what it reports afterwards. "The charger read" below is the coordinator's read of the charger and the car
(`async_read_now(with_car=True)`); "fails" means a failure the integration handles today: any error for the
charger read, and a `NortecGoError` for the price read.

| Charger read | Price read | The press |
|---|---|---|
| works | works | Returns, as today |
| fails | works | Raises the charger read's error |
| works | fails | Raises the price read's error |
| fails | fails | Raises the charger read's error |

- The price read runs in every row.
- The error is a `HomeAssistantError` with `translation_domain` `nortec_go`, chained (`from`) to the error it
  reports. It is never a `ConfigEntryAuthFailed`, `ConfigEntryError` or `UpdateFailed` itself: those belong
  to setup and to the coordinator.
- The button stays available after a failed press, so the read can be tried again.
- The entities and the logging behave as today. The press logs nothing of its own: Home Assistant shows and
  logs the raised error.
- **An error outside `pynortecgo` from the price read** (a bug, not a failed read) isn't caught by
  `async_read_prices` today and leaves the press as it is, untranslated. That stays so, also when the
  charger read failed: the unexpected error is the one raised, and the charger's error is dropped. The
  button catches only what §3 raises.
- **Shutdown:** once the coordinator is shut down (the entry is unloading), `async_refresh()` returns
  without reading and leaves `last_update_success` as it was. A press in that window after an earlier failed
  read raises that earlier error. This is accepted.

## 2. The charger read: `button.py`

After `await self.coordinator.async_read_now(with_car=True)`, the button looks at the coordinator:

- `last_update_success` is `True`: the charger read worked.
- Otherwise the read failed, and `last_exception` is its error. The button keeps it and goes on to the price
  read.

After the price read, a failed charger read is raised as a new `HomeAssistantError`:

- When `last_exception` is a `HomeAssistantError` with `translation_domain` `nortec_go` and a
  `translation_key`, the new error takes that key and its `translation_placeholders`. These are the #37
  keys the coordinator already sets: `auth_failed`, `rate_limited`, `cannot_connect`, `api_error`,
  `charger_not_found`, `unexpected_response` and `read_failed`.
- Anything else (an error that isn't from `pynortecgo`, such as a timeout) is raised with `read_failed`.

A rejected car read comes out the same way: the coordinator raises `ConfigEntryAuthFailed` (`auth_failed`)
for it, so the press raises `auth_failed`. Every other car error fails nothing and isn't reported.

The choice of key is a small module-level function in `button.py`, so it can be read and tested on its own.

`coordinator.async_read_now` and `_async_update_data` don't change.

## 3. The price read: `coordinator.py`

`async_read_prices` swallows every `NortecGoError` today, and its auth branch sets no flag, so the button
can't tell whether the read worked. It gets one new keyword argument:

```python
async def async_read_prices(
    self,
    *,
    during_setup: bool = False,
    retry_on_failure: bool = False,
    raise_on_failure: bool = False,
) -> None: ...
```

With `raise_on_failure=True`, a failed read raises a translated `HomeAssistantError` after everything the
method does today for that failure:

| The read fails with | Today (unchanged) | Then, with `raise_on_failure` |
|---|---|---|
| `AuthError` | Debug log, cancel a pending retry, start reauth | Raises `auth_failed` |
| any other `NortecGoError` | Log (warning the first time, D37), mark the reads as failing, schedule a retry if asked | Raises `price_read_failed` |

- The default is `False`, so the setup read, the scheduled reads and the retry behave exactly as today.
  Only the button passes `True`.
- `during_setup=True` keeps raising `ConfigEntryAuthFailed` on an `AuthError`, whatever `raise_on_failure`
  says. No caller passes both.
- **Auth path:** this is the one place the change touches it. In the `except AuthError` branch of
  `async_read_prices`, the debug line, the retry cancel and the reauth start stay as they are, in the same
  order and with the same effect. With `raise_on_failure` set, the branch then raises `auth_failed` where
  it returns today. Nothing logs in again or retries a login, so hard rule 6 holds. For the charger read,
  the coordinator starts reauth as today, and the button only reads `last_exception`.

The button calls `async_read_prices(raise_on_failure=True)`. When the charger read failed, the button
catches the price read's `HomeAssistantError` and raises the charger's error instead (§1).

The new text, in `strings.json` under `exceptions` and copied to `translations/en.json`:

```json
"price_read_failed": {
  "message": "Reading the prices failed. The known prices are kept. Check the Home Assistant logs."
}
```

The #37 charger texts aren't reused for the prices: they say "Home Assistant will try again", which is the
charger poll, and `read_failed` names the charger. `auth_failed` is reused as it is.

## 4. Quality scale

In `custom_components/nortec_go/quality_scale.yaml`:

```yaml
action-exceptions:
  status: done
  comment: "The Charge switch and the Refresh button raise translated errors when their action fails."
```

In `tests/test_quality_scale.py`: the pinned status of `action-exceptions` becomes `done`, and
`test_action_exceptions_comment` is removed (the comment no longer ends with an issue number, so nothing can
be cut short at a `#`).

## 5. Tests

All with `pynortecgo` mocked, and fixtures from `pynortecgo` model objects (hard rule 7). The cases with an
`AuthError` patch `ConfigEntry.async_start_reauth`, as the coordinator tests do.

In `tests/test_button.py`:

- `test_press_after_failed_read_does_not_raise` is replaced: a press with a failing charger read raises
  `HomeAssistantError` with `translation_key` `cannot_connect`, the price forecast was still read, and the
  button is not unavailable. It keeps its check that *Cable connected* is unavailable.
- One parametrized test over the charger read's errors and their keys: `AuthError` → `auth_failed`,
  `RateLimitError` → `rate_limited`, `NortecGoConnectionError` → `cannot_connect`, `ApiError` → `api_error`,
  `ChargerNotFoundError` → `charger_not_found`, `UnexpectedResponseError` → `unexpected_response`,
  `NortecGoError` → `read_failed`. Each asserts that the raised error is exactly a `HomeAssistantError`
  (not a subclass).
- A charger read that fails with an error outside `pynortecgo` raises `read_failed`.
- A rejected car read (`AuthError` from the car read) raises `auth_failed`, and the price forecast was
  still read. Another car error raises nothing.
- A press with only the price read failing raises `price_read_failed`, and with an `AuthError` from the
  price read `auth_failed`.
- Both reads failing raises the charger's key, and the price forecast was read.
- A press after a failed press, with the reads working again, returns without an error (a stale
  `last_exception` isn't raised).
- The existing tests for a good press stay.

In `tests/test_coordinator.py`:

- `async_read_prices(raise_on_failure=True)` raises `price_read_failed` on a `NortecGoError` and still
  marks the reads as failing; on an `AuthError` it starts reauth and raises `auth_failed`.
- Without the argument, a failed read raises nothing (already covered by the existing tests, which stay).

`tests/test_init.py::test_translations_match_strings` already checks that `translations/en.json` is a copy
of `strings.json`.

## 6. Docs

- `docs/user/nortec_go.md`: under *Data updates*, say that a press shows an error when the charger read or
  the price read fails, that the other read still runs, and that a `button.press` step in a script or
  automation fails then too. The entity table's row for *Refresh* stays.
- `CHANGELOG.md`, under *Unreleased* → *Fixed*: the *Refresh* button shows an error when its read fails.
- `docs/decisions.md`, D43:
  - **Decision:** a *Refresh* press raises a translated error when its charger read or its price read
    fails; the charger's error wins, and the price read always runs.
  - **Why:** a silent press during an outage lets the owner think the data is fresh, and the quality scale's
    `action-exceptions` rule asks actions to raise when they fail.
  - **Source:** this spec, Decisions.
- `docs/manual-testing.md`: a note beside the owner's existing *Refresh* check, not a new checkbox: a press
  whose read fails shows an error. The checklist gives no way to provoke a failure, and no agent presses
  *Refresh*.
- `docs/ha-notes.md`, *Coordinators and actions*: one new fact, attached to the existing bullet on
  `last_exception`: outside setup, `async_refresh()` stores a read's error instead of raising it, including
  `ConfigEntryAuthFailed` and `ConfigEntryError`. The existing bullet isn't restated.

## 7. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/button.py` | §2, §3 |
| `custom_components/nortec_go/coordinator.py` | §3: `async_read_prices` only |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | §3: one new text |
| `custom_components/nortec_go/quality_scale.yaml` | §4 |
| `tests/test_button.py`, `tests/test_coordinator.py`, `tests/test_quality_scale.py` | §4, §5 |
| `docs/user/nortec_go.md`, `docs/manual-testing.md`, `docs/ha-notes.md`, `docs/decisions.md`, `CHANGELOG.md` | §6 |

Not touched: `sensor.py`, the `Charger` test fixtures in `tests/conftest.py`, `manifest.json` and `uv.lock`
(another branch, #76, changes those).

The code task touches the auth path (§3), so the plan tags it `Model: opus` (`docs/way-of-working.md` §5).
