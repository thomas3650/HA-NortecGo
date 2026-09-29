# Translated errors for setup and reads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** The errors that setup and the charger, car and price reads raise to Home Assistant carry a `translation_key` of our own instead of `pynortecgo`'s message, and the client's message goes to a debug log.

**Architecture:** Task 1 changes the coordinator's 7 raise sites to 9 translated raises with unchanged exception types, adds the 6 new keys to `strings.json` and `translations/en.json`, and adds 3 debug lines. Task 2 changes the docs, changelog and quality scale. It runs in wave 1 next to Task 1, written against the texts this plan fixes.

**Tech Stack:** Python 3.14, Home Assistant 2026.9 custom integration, `pynortecgo` 0.5.0 (always mocked in tests), pytest with `pytest-homeassistant-custom-component`, uv.

**Spec:** `docs/superpowers/specs/2026-09-29-exception-translations-design.md` (issue #37).

## Global Constraints

- TDD: write the failing test, see it fail, then write the code. Tests always mock `pynortecgo`, and fixtures come from `pynortecgo` model objects and the `tests/conftest.py` helpers, never raw API JSON (hard rules 2, 7).
- Exception types don't change at any site: `AuthError` → `ConfigEntryAuthFailed`, `RateLimitError` → `UpdateFailed` with `retry_after=err.retry_after`, `NortecGoConnectionError` and `ApiError` → `UpdateFailed`, `ChargerNotFoundError` and `UnexpectedResponseError` → `ConfigEntryError`, any other `NortecGoError` → `UpdateFailed`, caught last. Never retry or log in on an `AuthError` (hard rule 6). Never start or stop a real charge (hard rule 2).
- Every raise is `raise X(translation_domain=DOMAIN, translation_key="<key>") from err`, with no message and no placeholders.
- Nothing private (hard rule 3): no IDs, tokens, emails, captures, raw endpoints, response shapes, or links into the private client repo. Name only `pynortecgo`'s public API.
- `strings.json` and `translations/en.json` stay identical (`test_translations_match_strings`).
- Gates before every commit (`CLAUDE.md` → Commands): `uv run pytest -q`, then `uv run ruff check && uv run ruff format --check && uv run mypy`. The coverage gate (`--cov-fail-under=95`) passes at the end of each task.
- Subagents write commit messages with the Write tool to a file outside the repo, and commit with `git commit -F <file>` (no heredocs). End each message with the co-author trailer given in the dispatch.
- Match the surrounding code: comment density, one-line docstrings ending in a period, names.
- The texts, exactly (key: text):
  - `rate_limited`: `The Nortec Go service is limiting requests. Home Assistant will read again later.`
  - `cannot_connect`: `Can't reach the Nortec Go service. Home Assistant will try again.`
  - `api_error`: `The Nortec Go service returned an error. Home Assistant will try again.`
  - `charger_not_found`: `The charger is no longer on the Nortec Go account. Remove the integration and add it again.`
  - `unexpected_response`: `The Nortec Go service sent an answer this integration doesn't understand. Check for an update of the integration.`
  - `read_failed`: `Reading the charger failed. Home Assistant will try again.`
  - `auth_failed` (existing, unchanged): `The Nortec Go session was rejected. Sign in again from the repair notice.`
- Debug log texts, exactly: `Reading the charger failed: %s`, `Reading the car was rejected: %s`, `Reading the price forecast was rejected: %s`.
- `str()` of a translated HA exception is the text without its final period (HA strips it).
- No decision-log entry (spec, *Decisions*).

## Review Focus

1. An `AuthError` from the charger, the car or the setup price read still starts reauth and never logs in. The existing tests `test_first_refresh_auth_error_starts_reauth`, `test_later_auth_error_starts_reauth`, `test_later_price_auth_error_starts_reauth`, `test_price_auth_error_schedules_no_retry` and `test_price_auth_error_on_the_retry_starts_reauth` must pass **unchanged**. The reviewer checks the diff leaves them alone (Task 1).
2. A rate-limited read still waits `retry_after`: the `RateLimitError` branch keeps `retry_after=err.retry_after` (Task 1 test `test_charger_error_texts`, the `RateLimitError` row, and the existing `retry_after` tests).
3. A client error class this integration doesn't know still fails the read cleanly with our `read_failed` text (Task 1 test `test_charger_error_texts`, the unknown-error row, plus the existing `test_unknown_client_error_fails_the_read`).
4. A key missing from the translations renders as the bare key. The rendered-text assertion (`str(err) == text`) catches that, and so does `error_reason_translation_key` at setup (Task 1 tests `test_charger_error_texts` and `test_first_refresh_charger_errors`).
5. The branch order: once the tuples are split, the catch-all `except NortecGoError` must still come last, or it swallows every specific error. Each row of `test_charger_error_texts` pins its own key, so a wrong order fails the test.

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (coordinator, strings, tests), Task 2 (docs, changelog, quality scale) | Disjoint files, two worktrees off the feature branch. Task 2 is written against this plan's texts and re-checked against the code that lands |

No task has guarded files.

---

### Task 1: Translated raises in the coordinator

**Model:** opus — the raise sites sit on the `AuthError` → `ConfigEntryAuthFailed` / reauth path (hard rule 6).
**Wave:** 1

**Files:**
- Modify: `custom_components/nortec_go/coordinator.py` (`_async_update_data`, `_async_read_charger`, `_async_read_vehicle`, `async_read_prices`)
- Modify: `custom_components/nortec_go/strings.json`, `custom_components/nortec_go/translations/en.json`
- Test: `tests/test_coordinator.py` (`tests/test_init.py` needs no change: `test_setup_logs_no_credentials` checks HA's own "could not authenticate" line)

**Interfaces:**
- Consumes: `DOMAIN` from `const.py`; `setup_integration`, `mock_client`, `mock_config_entry` from `tests/conftest.py`.
- Produces: the `exceptions` keys `rate_limited`, `cannot_connect`, `api_error`, `charger_not_found`, `unexpected_response`, `read_failed`, with the Global Constraints texts. Task 2 quotes `charger_not_found`'s text.

- [ ] **Step 1: Write the failing tests**

In `tests/test_coordinator.py`, add these imports (keep the import blocks sorted; ruff will say if not):

```python
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    HomeAssistantError,
)
```

Below the `_coordinator` helper, add:

```python
class _UnknownClientError(NortecGoError):
    """A client error type from a later pynortecgo version."""


AUTH_TEXT = "The Nortec Go session was rejected. Sign in again from the repair notice"
```

Replace `test_first_refresh_charger_errors`' parametrize and body with a version that also takes the key, and checks the entry's error reason instead of the client's text:

```python
@pytest.mark.parametrize(
    ("error", "state", "key"),
    [
        (
            NortecGoConnectionError("network down"),
            ConfigEntryState.SETUP_RETRY,
            "cannot_connect",
        ),
        (
            RateLimitError("too many requests"),
            ConfigEntryState.SETUP_RETRY,
            "rate_limited",
        ),
        (ApiError("GET /example", 500), ConfigEntryState.SETUP_RETRY, "api_error"),
        (
            UnexpectedResponseError("GET /example", "bad shape"),
            ConfigEntryState.SETUP_ERROR,
            "unexpected_response",
        ),
        (
            ChargerNotFoundError("GET /example: the set charger was not found"),
            ConfigEntryState.SETUP_ERROR,
            "charger_not_found",
        ),
    ],
)
async def test_first_refresh_charger_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
    state: ConfigEntryState,
    key: str,
) -> None:
    """Charger errors at setup retry or stop setup with our text; the car isn't read."""
    mock_client.get_charger.side_effect = error
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is state
    assert mock_config_entry.error_reason_translation_domain == DOMAIN
    assert mock_config_entry.error_reason_translation_key == key
    assert str(error) not in (mock_config_entry.reason or "")
    mock_client.get_vehicle.assert_not_awaited()
```

After `test_first_refresh_auth_error_starts_reauth` (which stays unchanged), add:

```python
@pytest.mark.parametrize(
    ("method", "debug_line"),
    [
        ("get_charger", "Reading the charger failed: token rejected"),
        ("get_vehicle", "Reading the car was rejected: token rejected"),
        (
            "get_price_forecast",
            "Reading the price forecast was rejected: token rejected",
        ),
    ],
)
async def test_first_refresh_auth_error_text(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    method: str,
    debug_line: str,
) -> None:
    """An AuthError at setup fails it with our auth_failed text; the client's text is at debug."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    getattr(mock_client, method).side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth_if_available"):
        await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.error_reason_translation_domain == DOMAIN
    assert mock_config_entry.error_reason_translation_key == "auth_failed"
    assert "token rejected" not in (mock_config_entry.reason or "")
    assert debug_line in caplog.text
```

After `test_unknown_client_error_fails_the_read`, add:

```python
@pytest.mark.parametrize(
    ("error", "error_type", "key", "text"),
    [
        (AuthError("token rejected"), ConfigEntryAuthFailed, "auth_failed", AUTH_TEXT),
        (
            RateLimitError("too many requests", retry_after=30.0),
            UpdateFailed,
            "rate_limited",
            "The Nortec Go service is limiting requests. Home Assistant will read again later",
        ),
        (
            NortecGoConnectionError("network down"),
            UpdateFailed,
            "cannot_connect",
            "Can't reach the Nortec Go service. Home Assistant will try again",
        ),
        (
            ApiError("GET /example", 500),
            UpdateFailed,
            "api_error",
            "The Nortec Go service returned an error. Home Assistant will try again",
        ),
        (
            ChargerNotFoundError("GET /example: the set charger was not found"),
            ConfigEntryError,
            "charger_not_found",
            "The charger is no longer on the Nortec Go account. "
            "Remove the integration and add it again",
        ),
        (
            UnexpectedResponseError("GET /example", "bad shape"),
            ConfigEntryError,
            "unexpected_response",
            "The Nortec Go service sent an answer this integration doesn't understand. "
            "Check for an update of the integration",
        ),
        (
            _UnknownClientError("something new"),
            UpdateFailed,
            "read_failed",
            "Reading the charger failed. Home Assistant will try again",
        ),
    ],
)
async def test_charger_error_texts(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    error_type: type[HomeAssistantError],
    key: str,
    text: str,
) -> None:
    """A failed charger read raises our translated text; the client's text goes to the debug log."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_charger.side_effect = error
    with patch.object(ConfigEntry, "async_start_reauth"):
        await coordinator.async_refresh()

    raised = coordinator.last_exception
    assert isinstance(raised, HomeAssistantError)
    assert type(raised) is error_type
    assert raised.translation_domain == DOMAIN
    assert raised.translation_key == key
    assert str(raised) == text
    assert str(error) not in str(raised)
    assert f"Reading the charger failed: {error}" in caplog.text
    if isinstance(error, RateLimitError):
        assert isinstance(raised, UpdateFailed)
        assert raised.retry_after == 30.0


async def test_later_car_auth_error_text(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A later AuthError from the car raises our auth_failed text; the client's text is at debug."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_vehicle.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth"):
        await coordinator.async_read_now(with_car=True)

    raised = coordinator.last_exception
    assert isinstance(raised, ConfigEntryAuthFailed)
    assert raised.translation_domain == DOMAIN
    assert raised.translation_key == "auth_failed"
    assert str(raised) == AUTH_TEXT
    assert "Reading the car was rejected: token rejected" in caplog.text


async def test_later_price_auth_error_debug_line(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A later price read's AuthError logs the client's text at debug."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    await setup_integration(hass, mock_config_entry)
    coordinator = _coordinator(mock_config_entry)

    mock_client.get_price_forecast.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth"):
        await coordinator.async_read_prices()
    assert "Reading the price forecast was rejected: token rejected" in caplog.text
```

If `ruff format` reflows any of these, take its version.

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_coordinator.py -q -k "first_refresh_charger_errors or first_refresh_auth_error_text or charger_error_texts or later_car_auth_error_text or later_price_auth_error_debug_line"`
Expected: FAIL. The translation keys are `None`, and `str()` is the client's text.

- [ ] **Step 3: Add the texts**

In `custom_components/nortec_go/strings.json`, in `"exceptions"`, after the `"unloading"` entry, add (mind the comma after `"unloading"`'s closing brace):

```json
    "rate_limited": {
      "message": "The Nortec Go service is limiting requests. Home Assistant will read again later."
    },
    "cannot_connect": {
      "message": "Can't reach the Nortec Go service. Home Assistant will try again."
    },
    "api_error": {
      "message": "The Nortec Go service returned an error. Home Assistant will try again."
    },
    "charger_not_found": {
      "message": "The charger is no longer on the Nortec Go account. Remove the integration and add it again."
    },
    "unexpected_response": {
      "message": "The Nortec Go service sent an answer this integration doesn't understand. Check for an update of the integration."
    },
    "read_failed": {
      "message": "Reading the charger failed. Home Assistant will try again."
    }
```

Then make `translations/en.json` an exact copy: `cp custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json`.

- [ ] **Step 4: Change the raises and add the debug lines**

In `coordinator.py`, `_async_update_data`, replace the comment and the `try` block:

```text
        # pynortecgo's messages hold no tokens, emails or IDs, so they may be passed on.
        try:
            charger = await self._async_read_charger()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        ...
        except NortecGoError as err:
            # Last: the specific errors above are its subclasses. A later client version may add more.
            raise UpdateFailed(str(err)) from err
```

with:

```text
        # The user sees our translated texts; the client's text goes only to the debug log (#37).
        try:
            charger = await self._async_read_charger()
        except AuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except RateLimitError as err:
            raise UpdateFailed(
                retry_after=err.retry_after,
                translation_domain=DOMAIN,
                translation_key="rate_limited",
            ) from err
        except NortecGoConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        except ApiError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="api_error"
            ) from err
        except ChargerNotFoundError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN, translation_key="charger_not_found"
            ) from err
        except UnexpectedResponseError as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN, translation_key="unexpected_response"
            ) from err
        except NortecGoError as err:
            # Last: the specific errors above are its subclasses. A later client version may add more.
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="read_failed"
            ) from err
```

In `_async_read_charger`, the `except NortecGoError:` block gains `as err` and a debug line first:

```text
        except NortecGoError as err:
            _LOGGER.debug("Reading the charger failed: %s", err)
            if self.data is not None:
                ...
            raise
```

In `_async_read_vehicle`, replace

```text
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
```

with

```text
        except AuthError as err:
            _LOGGER.debug("Reading the car was rejected: %s", err)
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
```

In `async_read_prices`, the `AuthError` branch becomes:

```text
        except AuthError as err:
            _LOGGER.debug("Reading the price forecast was rejected: %s", err)
            self._async_cancel_price_retry()
            if during_setup:
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN, translation_key="auth_failed"
                ) from err
            self.config_entry.async_start_reauth(self.hass)
            return
```

Leave the car and price warning logs ("Could not read the car…", "Could not read the price forecast…") as they are.

- [ ] **Step 5: Run the tests to see them pass**

Run: `uv run pytest tests/test_coordinator.py tests/test_init.py -q`
Expected: PASS, including the unchanged reauth tests listed in Review Focus 1.

- [ ] **Step 6: Check nothing still passes the client's text**

Run: `grep -n "str(err)" custom_components/nortec_go/coordinator.py`
Expected: no output.

- [ ] **Step 7: Run the gates**

Run: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95 -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: all pass.

- [ ] **Step 8: Commit**

Write the message to `/tmp/exception-translations-task-1-msg.txt` with the Write tool:

```text
feat: translated texts for setup and read errors (#37)

The coordinator raises its setup and read errors with translation keys of
its own, with unchanged exception types, and logs the client's text at
debug.

<co-author trailer from the dispatch>
```

Then: `git add custom_components/nortec_go/coordinator.py custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json tests/test_coordinator.py && git commit -F /tmp/exception-translations-task-1-msg.txt`

---

### Task 2: Docs, changelog and quality scale

**Model:** opus — a docs task (D33).
**Wave:** 1 (written against this plan's texts; re-checked against the code that lands)

**Files:**
- Modify: `docs/user/nortec_go.md` (*Troubleshooting*)
- Modify: `docs/releasing.md` (*Bumping pynortecgo* checklist)
- Modify: `CHANGELOG.md` (*Unreleased* → *Added*)
- Modify: `custom_components/nortec_go/quality_scale.yaml`

**Interfaces:**
- Consumes: the `charger_not_found` text from the Global Constraints.
- Produces: nothing code relies on.

Keep every edit to exactly what is below: a parallel branch (#11) edits the same *Troubleshooting* section, `CHANGELOG.md` and `quality_scale.yaml`.

- [ ] **Step 1: Troubleshooting heading**

In `docs/user/nortec_go.md`, replace the heading line

```text
### "The set charger was not found"
```

with

```text
### "The charger is no longer on the Nortec Go account"
```

Its paragraph stays as it is. Check nothing links to the old heading: `grep -rn --exclude-dir=superpowers "set-charger-was-not-found\|set charger was not found" docs README.md CHANGELOG.md`
gives no output (specs and plans are snapshots, so they are left out).

- [ ] **Step 2: Bump checklist**

In `docs/releasing.md`, the first checklist item under the `pynortecgo` bump ends with the sentence

```text
The integration passes them into logs and
  `ConfigEntry*` errors (`CLAUDE.md`, hard rule 5).
```

Replace that sentence with

```text
The integration passes them into its logs (`CLAUDE.md`, hard rule 5).
```

and re-wrap the item at the file's line width (about 110 characters). The rest of the item doesn't change.

- [ ] **Step 3: Changelog**

In `CHANGELOG.md`, under *Unreleased* → *Added*, replace the line

```text
- If the charger is removed from your Nortec Go account, setup stops with a "charger not found" error.
```

with

```text
- If the charger is removed from your Nortec Go account, setup stops with the error "The charger is no
  longer on the Nortec Go account".
```

and add, as the last bullet of *Added*:

```text
- Setup and read errors show the integration's own texts, not the client library's.
```

- [ ] **Step 4: Quality scale**

In `custom_components/nortec_go/quality_scale.yaml`, replace

```yaml
  exception-translations:
    status: todo
    comment: "The switch's exceptions are translated; the coordinator's UpdateFailed and ConfigEntryError texts aren't yet."
```

with

```yaml
  exception-translations: done
```

- [ ] **Step 5: Run the gates**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: all pass (`tests/test_quality_scale.py` accepts the bare `done`).

- [ ] **Step 6: Commit**

Write the message to `/tmp/exception-translations-task-2-msg.txt` with the Write tool:

```text
docs: quote the translated errors; exception-translations done (#37)

<co-author trailer from the dispatch>
```

Then: `git add docs/user/nortec_go.md docs/releasing.md CHANGELOG.md custom_components/nortec_go/quality_scale.yaml && git commit -F /tmp/exception-translations-task-2-msg.txt`
