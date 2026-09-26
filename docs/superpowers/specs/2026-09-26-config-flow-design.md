# Config flow, reauth and entry setup — design

Date: 2026-09-26 · Branch: `feat/config-flow` · Issue: #7

## Goal

- **What:** the first feature. A user adds Nortec Go from the Home Assistant UI with their Nortec Go login.
  Home Assistant stores session tokens (never the password), sets the entry up with a `pynortecgo` client,
  stays connected across restarts without a new login, and asks for the password again (reauth) when the
  tokens are rejected.
- **Why:** the foundation for using the integration with
  [EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging). The work is split into three
  features, each with its own spec, plan and PR: this one (#7), read-only entities (#8), charge control (#9).
- **Not in this work:** entities, a `DataUpdateCoordinator`, diagnostics (#11), anything that starts or stops
  a charge, a reconfigure flow, the car (only feature 2 needs it).
- **Done when:** the integration can be added in the UI, survives a restart without a new login, and a
  rejected token starts reauth. In this feature only setup calls the client, so a rejected token is noticed
  at setup (a start, restart or reload); feature 2's polling notices it at any time. Built TDD, with
  `pynortecgo` mocked in every test; live data only in the owner's manual test.

## Decisions

| Topic | Decision |
|---|---|
| Approach | Standard HA pattern: the client in `entry.runtime_data`, no coordinator until feature 2 |
| Dependency | `pynortecgo==0.1.0` (exact pin per D7), in `manifest.json` and in the `dev` group; bumped by PR. A test keeps the two pins equal |
| Stored in `entry.data` | Email, access token, refresh token, `expires_at` (ISO 8601), `device_id`. Never the password |
| Entry `unique_id` | The account's charger ID, from `get_charger()` in the flow |
| Charger ID in `entry.data` | Not stored. The client finds the charger itself (`get_charger()` discovers it once per client and caches it), and 0.1.0 has no way to be given a known ID. The ID lives only as the `unique_id`, used for duplicate and mismatch checks. Requested upstream as NortecGo#43; once a release has it, storing and passing the ID is a new change |
| Entry title | The charger's name (not the email, which would show in the UI and logs). HA puts entry titles in its setup log lines; the charger name is the one the owner chose in the app |
| Session | HA's shared `aiohttp` session (`async_get_clientsession`) |
| Login | Only in the user and reauth steps, once per submit. Setup never logs in, and nothing retries a login (hard rule 6; tested, §4) |
| Messages | No email, password, token, charger ID or `device_id` in any log line or exception message, including `ConfigEntry*` exceptions (hard rule 5). pynortecgo's own exception texts carry none, so they may be included |
| Stored tokens | Always `client.tokens` read after `get_charger()`, not the value `login()` returned, so a refresh during `get_charger()` can't leave stale tokens |
| Car | Not checked in this feature |

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/manifest.json` | `"config_flow": true`, `"requirements": ["pynortecgo==0.1.0"]` |
| `custom_components/nortec_go/const.py` | Keys for the token fields not in `homeassistant.const` (`refresh_token`, `expires_at`) |
| `custom_components/nortec_go/entry.py` | New. `type NortecGoConfigEntry = ConfigEntry[NortecGoClient]`, and the two conversions between `Tokens` and the `entry.data` fields |
| `custom_components/nortec_go/config_flow.py` | New. User step, reauth steps |
| `custom_components/nortec_go/__init__.py` | `async_setup_entry`, `async_unload_entry`; `async_setup` and the YAML schema stay |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | Config steps with `data` and `data_description` for every field, errors, aborts (`already_configured`, `already_in_progress`, `reauth_successful`, `wrong_account`). Literal text only, no `[%key:…%]` references: only core's build resolves those, and a custom integration's `en.json` is served as-is. `en.json` stays an exact copy |
| `custom_components/nortec_go/quality_scale.yaml` | Rules set as in §5 |
| `pyproject.toml`, `uv.lock` | `pynortecgo==0.1.0` in the `dev` group |
| `tests/conftest.py` | `mock_client` and `mock_config_entry` fixtures |
| `tests/test_config_flow.py`, `tests/test_init.py`, `tests/test_manifest.py` | New or extended tests (§4) |
| `docs/user/nortec_go.md`, `CHANGELOG.md` | §6 |
| `docs/decisions.md`, `docs/way-of-working.md` | D18, D19, D20; D8 superseded (§7) |

HA's own constants are used where they exist (`CONF_EMAIL`, `CONF_PASSWORD`, `CONF_ACCESS_TOKEN`,
`CONF_DEVICE_ID`).

## 2. Config flow

### 2.1 User step

1. Form: email, password. After an error the form is shown again with the typed email kept
   (`add_suggested_values_to_schema`), never the password.
2. On submit: a new `NortecGoClient(session)` (it generates a fresh `device_id`), `login(email, password)`,
   then `get_charger()`.
3. `async_set_unique_id(str(charger.id))` and `_abort_if_unique_id_configured()` (abort
   `already_configured`, also while a reauth for that charger is open, since HA leaves reauth flows out of
   the in-progress check; `already_in_progress` when two add flows for one charger overlap).
4. Create the entry: title `charger.name`, data as in *Decisions*: tokens from `client.tokens`, `device_id`
   from `client.device_id`.

### 2.2 Form errors (user and reauth steps)

| Exception | Error key | Notes |
|---|---|---|
| `AuthError` | `invalid_auth` | |
| `NortecGoConnectionError`, `ApiError` | `cannot_connect` | `ApiError` is transient, as in setup (§3.2) |
| `RateLimitError` | `rate_limited` | Text asks the user to wait before trying again |
| `ChargerNotFoundError` | `no_charger` | |
| `MultipleChargersError` | `multiple_chargers` | Only one charger per account is supported |
| `UnexpectedResponseError` and any other exception | `unknown` | Logged with `_LOGGER.exception`; the message never holds the email or password |

The form is shown again with the error; nothing is retried automatically.

### 2.3 Reauth

1. `async_step_reauth(entry_data)` goes to `async_step_reauth_confirm`.
2. Form: password only. The description shows the stored email as a placeholder.
3. On submit: a new client with the entry's stored `device_id` (the same device), `login(stored email,
   password)`, then `get_charger()`.
4. `async_set_unique_id(str(charger.id))` then `_abort_if_unique_id_mismatch(reason="wrong_account")`.
5. On success: `async_update_reload_and_abort(entry, data_updates=…)` with the new tokens from
   `client.tokens` (email and `device_id` unchanged); abort reason `reauth_successful`.
6. Errors as in §2.2.

## 3. Entry setup and unload

### 3.1 `async_setup_entry`

1. Rebuild `Tokens` from `entry.data`.
2. `NortecGoClient(session, tokens=…, device_id=…, on_tokens_refreshed=…)`.
3. `charger = await client.get_charger()`, mapping errors as in §3.2.
4. If `str(charger.id) != entry.unique_id`: raise `ConfigEntryError` with a message that says the
   account's charger has changed and to remove and re-add the integration, without either ID.
5. `entry.runtime_data = client`; forward to no platforms yet.

### 3.2 Setup errors

| Exception | Raised as | Effect |
|---|---|---|
| `AuthError` | `ConfigEntryAuthFailed` | HA starts the reauth flow |
| `NortecGoConnectionError`, `RateLimitError`, `ApiError` | `ConfigEntryNotReady` | HA retries setup with backoff; a retry only reads with the stored tokens |
| `UnexpectedResponseError`, `ChargerNotFoundError`, `MultipleChargersError` | `ConfigEntryError` | Permanent until the user acts |

### 3.3 Token refresh

The client refreshes tokens itself and then awaits `on_tokens_refreshed(tokens)`. The callback writes the new
token fields into `entry.data` with `hass.config_entries.async_update_entry`. It doesn't call the client (the
client forbids it during a refresh) and doesn't reload the entry. That is what lets a restart start from the
newest tokens without a login.

### 3.4 Unload

`async_unload_entry` unloads the (empty) platform list and returns the result. The session is HA's shared
one, so nothing is closed.

## 4. Tests

TDD: each behaviour gets a failing test first. `pynortecgo` is always mocked; no test reaches the network.

- **Fixtures (`conftest.py`):**
  - `mock_client`: patches the `NortecGoClient` class where `config_flow` and `__init__` import it
    (`autospec=True`). Both patches return the same instance, an `AsyncMock(spec=NortecGoClient)`: `login`
    returns a `Tokens`, `get_charger` a `Charger`, `tokens` is a `Tokens` and `device_id` a fixed fake
    string, all built from `pynortecgo` model objects with obviously fake values (hard rule 7). The fixture
    exposes the class mock too, so tests can assert constructor kwargs and capture `on_tokens_refreshed`.
  - `mock_config_entry`: a `MockConfigEntry` with the fake data and `unique_id`.
- **`test_config_flow.py`** (100% of `config_flow.py`):
  - the user step creates the entry with the expected title, data and `unique_id`, and no password in the
    data;
  - each error in §2.2 shows its key, and a following submit succeeds;
  - a second setup of the same charger aborts `already_configured`;
  - reauth: success updates the tokens and keeps email and `device_id`, the stored `device_id` is passed to
    the client, `wrong_account`, and each error in §2.2 followed by a submit that ends in
    `reauth_successful`;
  - the typed email is kept after an error;
  - every submit, including the error cases, awaits `login` exactly once;
  - the email and password never appear in the logs (`caplog`), including for `unknown`.
- **`test_init.py`:**
  - setup succeeds and `runtime_data` is the client, built with the stored tokens and `device_id`;
  - each row of §3.2 leads to the expected entry state (`SETUP_RETRY`, `SETUP_ERROR`, or `SETUP_ERROR` with
    a reauth flow in progress);
  - a charger-ID mismatch leads to `SETUP_ERROR`, and neither ID appears in the logs;
  - no setup path, including `AuthError`, awaits `login`;
  - calling the captured `on_tokens_refreshed` updates the token fields in `entry.data`;
  - unload returns the entry to `NOT_LOADED`;
  - the existing `async_setup` tests stay.
- **`test_manifest.py`:** the `pynortecgo` pin in `manifest.json` equals the one in `pyproject.toml`.
- **Gates:** `CLAUDE.md` → Commands, including coverage ≥ 95%.

## 5. Quality scale

Set to `done`: `config-flow`, `config-flow-test-coverage`, `test-before-configure`, `test-before-setup`,
`unique-config-entry`, `runtime-data`, `config-entry-unloading`, `reauthentication-flow`, `inject-websession`,
`async-dependency`, `docs-installation-instructions`, `docs-removal-instructions`,
`docs-installation-parameters`, `docs-known-limitations` (§6), `docs-high-level-description` (the intro
exists), `integration-owner` (codeowners set). `docs-configuration-parameters` becomes `exempt` (no options
flow). `dependency-transparency` stays `todo` (D15).

## 6. User docs and changelog

- `docs/user/nortec_go.md`: *Prerequisites* (keeps exactly one charger and one car per account: the car
  isn't checked yet but features 2 and 3 need it), *Configuration* (email and password;
  what is stored, and that the password isn't), *Reauthentication*, *Removal*, *Known limitations* (one
  charger per account, unofficial API that can change). Other sections stay "Not available yet".
- `CHANGELOG.md`, *Unreleased → Added*: setting up the integration from the UI, with reauthentication.

## 7. Decisions log and process

- **D18:** the config entry stores tokens and `device_id`, never the password; the charger ID is the
  `unique_id`; pin bumps (D7) come as PRs, with the manifest and dev pins kept equal by a test. Source: this
  spec.
- **D19:** GitHub issues are the backlog. Anything found that won't be fixed in the current work becomes an
  issue, or is added to an existing one. Added to `way-of-working.md` §6. Source: owner request on
  2026-09-26.
- **D20:** each repo owns its way of working; there is no sync duty with `NortecGo`. A learning that clearly
  helps the other repo may be sent there as an issue. D8 becomes `superseded by D20` (its client
  change-request route stays, and moves into D20's text), and the sync note at the top of
  `way-of-working.md` is removed. Source: owner decision on 2026-09-26 (see NortecGo#41).

## 8. Follow-ups (issues, per D19)

- D17 says to revisit CodeQL as a required check once auth code lands: #14, the owner's decision.
- A refresh the API rejects with a status other than 401 would reach setup as `ApiError` and retry forever
  instead of starting reauth. Only a 401 has been observed. Fixed in the client, not guarded here (setup
  can't tell a rejected refresh from another 400/403): NortecGo#44. The integration picks it up with a pin
  bump.
- Passing a known charger ID to the client: NortecGo#43.

## 9. Verification

- The gates pass locally and in CI (`lint`, `tests`, `hassfest`, `hacs`, `gitleaks`).
- `hassfest` accepts the manifest with `config_flow: true` and the requirement.
- Manual test by the owner (live data only here): add the integration via `scripts/develop`, restart Home
  Assistant and confirm it sets up without a new login. Nothing in this feature can start or stop a charge.
  Real-instance files stay in `config/` and `local/`.
