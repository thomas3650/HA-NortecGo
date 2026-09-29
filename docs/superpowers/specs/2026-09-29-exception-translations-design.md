# Translated errors for setup and reads — design

Date: 2026-09-29 · Branch: `feat/exception-translations` · Issue: #37

## Goal

- **What:** the errors that setup and the charger, car and price reads raise to Home Assistant carry a
  `translation_key` of our own, not `pynortecgo`'s message. The client's message is no longer the error
  text; it is logged at debug (and stays chained to our exception, so HA's tracebacks still show it).
- **Why:** today the coordinator passes `str(err)` into `ConfigEntryAuthFailed`, `ConfigEntryError` and
  `UpdateFailed`, so the UI shows the client's English. A client release that rewords a message changes the
  UI and silently breaks the user docs, which quote one of them.
- **Not in this work:** the warning logs of a failed car read ("Could not read the car…") and of a failed
  price read (D37's log run). They keep the client's text: they are logs, not error texts shown in the UI,
  and `docs/releasing.md` checks the client's messages on every bump. Diagnostics (#11) aren't touched.
- **Done when:** no `pynortecgo` message is shown to the user as the error text; built TDD with
  `pynortecgo` mocked; the gates pass; user docs, `docs/releasing.md`, changelog and quality scale updated.

## Decisions

Proposed by the team lead and approved through the PO (issue #37, 2026-09-29).

| Topic | Decision |
|---|---|
| Exception types | Unchanged at every site: `AuthError` → `ConfigEntryAuthFailed`, `RateLimitError` → `UpdateFailed` with `retry_after`, connection and API errors → `UpdateFailed`, `ChargerNotFoundError` and `UnexpectedResponseError` → `ConfigEntryError`, any other `NortecGoError` → `UpdateFailed`, caught last. Only the message changes, so reauth behaves exactly as before (hard rule 6) |
| Keys | One per client error class (§2), in the `exceptions` section of `strings.json`. The `AuthError` sites reuse the existing `auth_failed` key |
| Placeholders | None: the client's text would bring back what this change removes |
| Client's text | A debug log line at each raise site (§3) |
| Car and price warning logs | Unchanged (see *Not in this work*) |
| Decision log | No new entry: this follows HA's `exception-translations` rule and makes no decision of ours |
| Process | Full path (spec, plan, `full-reviewer`) |

Facts used, public-safe (Home Assistant 2026.9):

- `HomeAssistantError` and its subclasses (`ConfigEntryAuthFailed`, `ConfigEntryError`, `UpdateFailed`)
  take `translation_domain` and `translation_key`. Without a message, `str()` renders the English text
  from the integration's translations, with its final period stripped (`async_get_exception_message` calls
  `rstrip(".")`). `UpdateFailed` still takes `retry_after` with them.
- A failed first refresh re-raises as `ConfigEntryNotReady` with the cause's translation domain, key and
  placeholders, so a setup retry shows our text too.
- A config entry whose setup fails or retries (`ConfigEntryError`, `ConfigEntryAuthFailed`,
  `ConfigEntryNotReady`) stores the exception's translation domain and key as its error reason. The
  frontend shows that text in the user's language.
- The coordinator's failure log lines ("Error fetching nortec_go data: …" for `UpdateFailed`, "Config
  entry setup failed while fetching …" for `ConfigEntryError`, "Authentication failed while fetching …" for
  `ConfigEntryAuthFailed`) end with the exception's text, so they show our text from now on.

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/coordinator.py` | The raise sites (7 today, 9 after the split) and the debug lines (§3) |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | The new keys (§2), identical in both |
| `custom_components/nortec_go/quality_scale.yaml` | `exception-translations: done` (§4) |
| `docs/user/nortec_go.md` | One *Troubleshooting* heading (§4) |
| `docs/releasing.md` | The bump checklist's wording (§4) |
| `CHANGELOG.md` | Two lines (§4) |
| `tests/test_coordinator.py`, `tests/test_init.py` | §5 |

Every other `HomeAssistantError` the integration raises (the charge control's, the repairs') already has a
translation key, and the config flow shows its own error keys. So these 7 sites are all that's left.
They become 9, because both two-class branches split (§3).

## 2. Keys and texts

New keys under `exceptions` (the texts are fixed here; the docs quote them):

| Key | Client error | Text |
|---|---|---|
| `rate_limited` | `RateLimitError` | The Nortec Go service is limiting requests. Home Assistant will read again later. |
| `cannot_connect` | `NortecGoConnectionError` | Can't reach the Nortec Go service. Home Assistant will try again. |
| `api_error` | `ApiError` | The Nortec Go service returned an error. Home Assistant will try again. |
| `charger_not_found` | `ChargerNotFoundError` | The charger is no longer on the Nortec Go account. Remove the integration and add it again. |
| `unexpected_response` | `UnexpectedResponseError` | The Nortec Go service sent an answer this integration doesn't understand. Check for an update of the integration. |
| `read_failed` | any other `NortecGoError` | Reading the charger failed. Home Assistant will try again. |

`auth_failed` (existing, already used by the *Charge* switch): "The Nortec Go session was rejected. Sign in
again from the repair notice." Its text doesn't change.

## 3. Raise sites

| Site | Raise | Key |
|---|---|---|
| Charger read, `AuthError` | `ConfigEntryAuthFailed` | `auth_failed` |
| Charger read, `RateLimitError` | `UpdateFailed(…, retry_after=err.retry_after)` | `rate_limited` |
| Charger read, `NortecGoConnectionError` | `UpdateFailed` | `cannot_connect` |
| Charger read, `ApiError` | `UpdateFailed` | `api_error` |
| Charger read, `ChargerNotFoundError` | `ConfigEntryError` | `charger_not_found` |
| Charger read, `UnexpectedResponseError` | `ConfigEntryError` | `unexpected_response` |
| Charger read, other `NortecGoError` | `UpdateFailed` | `read_failed` |
| Car read, `AuthError` | `ConfigEntryAuthFailed` | `auth_failed` |
| Setup price read, `AuthError` | `ConfigEntryAuthFailed` | `auth_failed` |

Both two-class branches split in two, one per key: `(NortecGoConnectionError, ApiError)` and
`(ChargerNotFoundError, UnexpectedResponseError)`. The client's error classes are all direct subclasses of
`NortecGoError`, so only the catch-all has to stay last. Each raise is
`raise X(translation_domain=DOMAIN, translation_key=…) from err`, so the client's exception stays chained.

Debug lines, each with the client's text as `%s`:

- **Charger read:** one line in `_async_read_charger`'s existing `except NortecGoError` block (which gains
  `as err`), "Reading the charger failed: %s". It covers every charger branch.
- **Car read, `AuthError`:** "Reading the car was rejected: %s".
- **Price read, `AuthError`:** "Reading the price forecast was rejected: %s", before the `during_setup`
  test, so it covers the later-read path too.

The comment above the charger `try` ("pynortecgo's messages hold no tokens, emails or IDs, so they may be
passed on") becomes one that says the client's text goes only to the debug log.

## 4. Docs and quality scale

- **`docs/user/nortec_go.md`:** in *Troubleshooting*, the heading `"The set charger was not found"` becomes
  `"The charger is no longer on the Nortec Go account"`. Its paragraph and the rest of the section don't
  change (#11 edits the same section).
- **`docs/releasing.md`:** the first bump checklist item's last sentence becomes "The integration passes them
  into its logs (`CLAUDE.md`, hard rule 5)." The item stays.
- **`CHANGELOG.md`:** the integration is unreleased, so everything stays under *Unreleased* → *Added*.
  - The existing line "If the charger is removed from your Nortec Go account, setup stops with a "charger
    not found" error." becomes "If the charger is removed from your Nortec Go account, setup stops with the
    error "The charger is no longer on the Nortec Go account"."
  - One new line at the end of *Added*: "Setup and read errors show the integration's own texts, not the
    client library's."
- **`quality_scale.yaml`:** `exception-translations: done`, a bare scalar with its comment removed.

## 5. Tests

`pynortecgo` is mocked in every test (hard rule 7).

- **Charger read, after setup:** for each client error in §3, `coordinator.last_exception` is the
  expected type with `translation_domain == DOMAIN` and the expected key. `str()` equals the §2 text
  without its final period, which also proves the key exists in the translations. The client's message
  isn't in `str()`, and it is in the debug log (`caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")`).
  `RateLimitError` keeps its `retry_after`.
- **Charger read, at setup:** the entry's state is as today (`SETUP_RETRY` or `SETUP_ERROR`), and its
  `error_reason_translation_key` is the expected key. `test_first_refresh_charger_errors`'
  `reason == str(error)` assertion changes: the reason is now our text.
- **Car and setup price `AuthError`:** the raised `ConfigEntryAuthFailed` has key `auth_failed`, the
  client's text is in the debug log, and reauth starts. The existing reauth tests pass unchanged:
  `test_first_refresh_auth_error_starts_reauth`, `test_later_auth_error_starts_reauth`,
  `test_later_price_auth_error_starts_reauth` and the price retry `AuthError` tests. None logs in.
- `test_translations_match_strings` keeps `strings.json` and `en.json` identical.
