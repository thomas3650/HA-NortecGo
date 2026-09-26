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
  rejected token starts reauth. Built TDD, with `pynortecgo` mocked in every test; live data only in the
  owner's manual test.

## Decisions

| Topic | Decision |
|---|---|
| Approach | Standard HA pattern: the client in `entry.runtime_data`, no coordinator until feature 2 |
| Dependency | `pynortecgo==0.1.0`, pinned exactly in `manifest.json` and in the `dev` group; bumped by PR. A test keeps the two pins equal |
| Stored in `entry.data` | Email, access token, refresh token, `expires_at` (ISO 8601), `device_id`. Never the password |
| Entry `unique_id` | The account's charger ID, from `get_charger()` in the flow |
| Charger ID in `entry.data` | Not stored. The client finds the charger itself (`get_charger()` discovers it once per client and caches it), and 0.1.0 has no way to be given a known ID. The ID lives only as the `unique_id`, used for duplicate and mismatch checks. Requested upstream as NortecGo#43; once a release has it, storing and passing the ID is a new change |
| Entry title | The charger's name (not the email, which would show in the UI and logs) |
| Session | HA's shared `aiohttp` session (`async_get_clientsession`) |
| Login | Only in the user and reauth steps, on the user's submit. Setup never logs in, and nothing retries a login |
| Car | Not checked in this feature |

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/manifest.json` | `"config_flow": true`, `"requirements": ["pynortecgo==0.1.0"]` |
| `custom_components/nortec_go/const.py` | Keys for the token fields not in `homeassistant.const` (`refresh_token`, `expires_at`) |
| `custom_components/nortec_go/entry.py` | New. `type NortecGoConfigEntry = ConfigEntry[NortecGoClient]`, and the two conversions between `Tokens` and the `entry.data` fields |
| `custom_components/nortec_go/config_flow.py` | New. User step, reauth steps |
| `custom_components/nortec_go/__init__.py` | `async_setup_entry`, `async_unload_entry`; `async_setup` and the YAML schema stay |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | Config steps, errors, aborts; `en.json` stays an exact copy |
| `custom_components/nortec_go/quality_scale.yaml` | Rules in §5 set to `done` |
| `pyproject.toml`, `uv.lock` | `pynortecgo==0.1.0` in the `dev` group |
| `tests/conftest.py` | `mock_client` and `mock_config_entry` fixtures |
| `tests/test_config_flow.py`, `tests/test_init.py`, `tests/test_manifest.py` | New or extended tests (§4) |
| `docs/user/nortec_go.md`, `CHANGELOG.md` | §6 |
| `docs/decisions.md`, `docs/way-of-working.md` | D18, D19 (§7) |

HA's own constants are used where they exist (`CONF_EMAIL`, `CONF_PASSWORD`, `CONF_ACCESS_TOKEN`,
`CONF_DEVICE_ID`).

## 2. Config flow

### 2.1 User step

1. Form: email, password.
2. On submit: a new `NortecGoClient(session)` (it generates a fresh `device_id`), `login(email, password)`,
   then `get_charger()`.
3. `async_set_unique_id(str(charger.id))` and `_abort_if_unique_id_configured()` (abort
   `already_configured`).
4. Create the entry: title `charger.name`, data as in *Decisions*, with `device_id` from the client.

### 2.2 Form errors (user and reauth steps)

| Exception | Error key | Notes |
|---|---|---|
| `AuthError` | `invalid_auth` | |
| `NortecGoConnectionError` | `cannot_connect` | |
| `RateLimitError` | `rate_limited` | Text asks the user to wait before trying again |
| `ChargerNotFoundError` | `no_charger` | |
| `MultipleChargersError` | `multiple_chargers` | Only one charger per account is supported |
| Any other exception | `unknown` | Logged with `_LOGGER.exception`, never with the email or password |

The form is shown again with the error; nothing is retried automatically.

### 2.3 Reauth

1. `async_step_reauth(entry_data)` goes to `async_step_reauth_confirm`.
2. Form: password only. The description shows the stored email as a placeholder.
3. On submit: a new client with the entry's stored `device_id` (the same device), `login(stored email,
   password)`, then `get_charger()`.
4. If the charger ID differs from the entry's `unique_id`: abort `wrong_account`.
5. On success: `async_update_reload_and_abort` with the new tokens (email and `device_id` unchanged); abort
   reason `reauth_successful`.
6. Errors as in §2.2.

## 3. Entry setup and unload

### 3.1 `async_setup_entry`

1. Rebuild `Tokens` from `entry.data`.
2. `NortecGoClient(session, tokens=…, device_id=…, on_tokens_refreshed=…)`.
3. `charger = await client.get_charger()`, mapping errors as in §3.2.
4. If `str(charger.id) != entry.unique_id`: raise `ConfigEntryError` (the account's charger has changed;
   remove and re-add the integration).
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
  - `mock_client`: patches `NortecGoClient` where `config_flow` and `__init__` import it, with
    `AsyncMock(spec=NortecGoClient)`. `login` returns a `Tokens`, `get_charger` a `Charger`, both built from
    `pynortecgo` model objects with obviously fake values (hard rule 7). `device_id` is a fake fixed string.
  - `mock_config_entry`: a `MockConfigEntry` with the fake data and `unique_id`.
- **`test_config_flow.py`** (100% of `config_flow.py`):
  - the user step creates the entry with the expected title, data and `unique_id`, and no password in the
    data;
  - each error in §2.2 shows its key, and a following submit succeeds;
  - a second setup of the same charger aborts `already_configured`;
  - reauth: success updates the tokens and keeps email and `device_id`, the stored `device_id` is passed to
    the client, `wrong_account`, and each error in §2.2;
  - the email and password never appear in the logs (`caplog`), including for `unknown`.
- **`test_init.py`:**
  - setup succeeds and `runtime_data` is the client, built with the stored tokens and `device_id`;
  - each row of §3.2 leads to the expected entry state (`SETUP_RETRY`, `SETUP_ERROR`, or `SETUP_ERROR` with
    a reauth flow in progress);
  - a charger-ID mismatch leads to `SETUP_ERROR`;
  - calling the captured `on_tokens_refreshed` updates the token fields in `entry.data`;
  - unload returns the entry to `NOT_LOADED`;
  - the existing `async_setup` tests stay.
- **`test_manifest.py`:** the `pynortecgo` pin in `manifest.json` equals the one in `pyproject.toml`.
- **Gates:** `CLAUDE.md` → Commands, including coverage ≥ 95%.

## 5. Quality scale

Set to `done`: `config-flow`, `config-flow-test-coverage`, `test-before-configure`, `test-before-setup`,
`unique-config-entry`, `runtime-data`, `config-entry-unloading`, `reauthentication-flow`, `inject-websession`,
`async-dependency`, `docs-installation-instructions`, `docs-removal-instructions`,
`docs-installation-parameters`. `dependency-transparency` stays `todo` (D15).

## 6. User docs and changelog

- `docs/user/nortec_go.md`: *Prerequisites* (one charger per account), *Configuration* (email and password;
  what is stored, and that the password isn't), *Reauthentication*, *Removal*, *Known limitations* (one
  charger per account, unofficial API that can change). Other sections stay "Not available yet".
- `CHANGELOG.md`, *Unreleased → Added*: setting up the integration from the UI, with reauthentication.

## 7. Decisions log and process

- **D18:** the config entry stores tokens and `device_id`, never the password; the charger ID is the
  `unique_id`; `pynortecgo` is pinned exactly and bumped by PR. Source: this spec.
- **D19:** GitHub issues are the backlog. Anything found that won't be fixed in the current work becomes an
  issue, or is added to an existing one. Added to `way-of-working.md` §6, with a follow-up issue in
  `NortecGo` for the sibling copy (per the sync note). Source: owner request on 2026-09-26.

## 8. Verification

- The gates pass locally and in CI (`lint`, `tests`, `hassfest`, `hacs`, `gitleaks`).
- `hassfest` accepts the manifest with `config_flow: true` and the requirement.
- Manual test by the owner (live data only here): add the integration via `scripts/develop`, restart Home
  Assistant and confirm it sets up without a new login. Nothing in this feature can start or stop a charge.
  Real-instance files stay in `config/` and `local/`.
