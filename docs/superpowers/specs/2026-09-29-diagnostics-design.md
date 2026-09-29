# Diagnostics with redaction — design

Date: 2026-09-29 · Branch: `feat/diagnostics` · Issue: #11

## Goal

- **What:** a diagnostics download for the config entry that shows what the integration last read and how its
  reads are going, with the sign-in secrets redacted (quality scale rule `diagnostics`).
- **Why:** so a problem can be investigated from one file the user downloads, without sharing their email,
  password, session tokens or the client's device ID.
- **Not in this work:** device diagnostics (the issue asks for the config entry only); any change to what the
  integration reads or stores.
- **Done when:** built TDD with `pynortecgo` mocked in every test; the gates pass; `diagnostics: done` in
  `quality_scale.yaml`; the user docs point to diagnostics from *Troubleshooting* (scope added from #38);
  hard rule 5, changelog and decision log updated.

## Decisions

The owner's ruling through the PO (issue #11, 2026-09-29), which replaced the team lead's first proposal
(redact the charger's and car's IDs and names too).

| Topic | Decision |
|---|---|
| Scope | Config entry diagnostics only |
| Redacted | Only `email`, `password`, `access_token`, `refresh_token` and `device_id` (§3) |
| Kept | Everything else: the charger's `id`, `name` and `charge_id`, the car's `id` and `name`, the entry's title and unique ID, the car's brand and model, the `*_raw` states, `expires_at`, the prices' currency |
| Hard rule 5 | Reworded to that list; IDs and location drop out (§6) |
| Prices | A summary, no per-slot prices (§2) |
| New client fields | A test pins the fields of `pynortecgo`'s `Charger` and `Vehicle`, to catch a new field that might be a secret (§4) |
| Decision log | D38: the redaction rule and the field pin (§7) |

Facts used, public-safe:

- `pynortecgo` 0.5.0: `Charger` and `Vehicle` are frozen dataclasses of plain values, datetimes and
  `StrEnum`s; the integration's own `ChargeControlState` (`charge_control.py`) is a frozen dataclass of four
  bools. The client's models hold no secrets.
- `entry.data` holds `email`, `device_id`, `access_token`, `refresh_token` and `expires_at`; the password is
  never stored, and the entry has no options (no options flow).
- The client's device ID is sent at sign-in, so it counts as a sign-in secret here.
- Home Assistant's `async_redact_data` leaves `None` and empty strings as they are and redacts every other
  value of a listed key, in nested dicts too.
- Home Assistant's download wraps the integration's data with system info (versions, the time zone and
  more), the manifest, setup times and the integration's repair issues; it serializes with
  `ExtendedJSONEncoder`, and a value it can't serialize fails the download.
- A non-persistent repair issue (the *Starts are blocked* issue is one) appears in the download as its ID
  (`start_blocked_<entry_id>`), domain, creation time and flags only.
- The download handler doesn't check the entry's state, so it can be asked for an entry that isn't loaded
  (setup failed or retrying). `runtime_data` is set only after the first refresh succeeded and is removed at
  unload, so a loaded entry always has coordinator data; a later failed read keeps the previous data.
- `DataUpdateCoordinator` never clears `last_exception` after a successful read.
- A failed first read becomes a `ConfigEntryNotReady` with no message, so `entry.reason` is `None` in
  `setup_retry`. A `ChargerNotFoundError` or `UnexpectedResponseError` becomes `ConfigEntryError(str(err))`:
  state `setup_error`, with the error's message as the reason.
- `hass_client` signs its requests with an access token made at fixture setup. Home Assistant checks the
  token's issue time and 30-minute expiry with 10 s leeway, so a request after the clock is moved back before
  the token's issue time, or more than 30 minutes forward, gets a 401.
- `pynortecgo`'s error messages hold no email, password, tokens or device ID (the device ID goes only in a
  request header, and transport errors carry exception type names, not requests); some name the endpoint's
  path template (for example the method and path of a rejected request). The logs already carry them.

## 1. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/diagnostics.py` | New: `async_get_config_entry_diagnostics` (§2, §3) |
| `custom_components/nortec_go/coordinator.py` | Read-only properties `car_read_failing`, `price_read_failing` and `price_retry_pending` (§2); the comment on `pynortecgo`'s messages (§6) |
| `custom_components/nortec_go/quality_scale.yaml` | `diagnostics: done` |
| `tests/test_diagnostics.py` | New (§8) |
| `docs/user/nortec_go.md` | A *Diagnostics* subsection in *Troubleshooting*, and one sentence in *Reporting a problem* (§5) |
| `CLAUDE.md` | Hard rule 5 (§6) |
| `docs/releasing.md` | The client-bump checklist (§6) |
| `docs/manual-testing.md` | A *Diagnostics (#11)* checklist (§5) |
| `.github/ISSUE_TEMPLATE/bug.yml` | The *Diagnostics / logs* field mentions the diagnostics file (§5) |
| `docs/decisions.md` | D38 (§7) |
| `CHANGELOG.md` | One line under *Unreleased* → *Added* |

The three properties expose the coordinator's `_car_failing`, `_prices_failing` and
`_price_retry is not None`, because ruff's `SLF` rule refuses private access from `diagnostics.py`.

## 2. The output

`async_get_config_entry_diagnostics(hass, entry)` returns, with the §3 redaction applied to the whole dict:

```text
{
  "entry": {
    "title": str,
    "unique_id": str | None,
    "data": dict(entry.data),
    "options": dict(entry.options),
  },
  "loaded": true,
  "coordinator": {
    "last_update_success": bool,
    "last_exception": str | None,        # str() of the last failure; None while last_update_success
    "update_interval_seconds": float | None,
    "has_car": bool,
    "car_read_failing": bool,
    "price_read_failing": bool,
    "price_retry_pending": bool,
  },
  "data": {
    "read_at": datetime,
    "charger": dataclasses.asdict(charger),
    "vehicle": None | dataclasses.asdict(vehicle),
    "control": dataclasses.asdict(control),
  },
  "prices": {
    "currency": str | None,
    "slot_count": int,
    "first_slot_start": datetime | None,
    "last_slot_start": datetime | None,
  },
}
```

- **Not loaded:** when `entry.state is not ConfigEntryState.LOADED` (as `repairs.py` checks), the output is
  `entry`, `"loaded": false`, `"state"` (the state's value, for example `setup_retry`) and `"reason"`
  (`entry.reason`: `None` for a failed first read, the error's message for a setup error; Facts used). It keeps
  a request for an entry that isn't loaded (through the API) from failing with an error; the frontend may
  offer the download only for a loaded entry, so neither the user docs nor the design rely on it. On the
  loaded path `runtime_data` and `coordinator.data` are always set (Facts used), so there is no `None` case
  for `data`.
- **Last exception:** `None` while `last_update_success` is true, because the coordinator keeps an old error
  after a recovery, which would read as a current one.
- **Serializable:** datetimes and `StrEnum`s serialize with Home Assistant's encoder; the interval is given
  in seconds, not as a `timedelta`; the known price slots (keyed by datetime) aren't dumped.
- **Messages:** `last_exception` and `reason` are messages of `pynortecgo` errors or the integration's own:
  no email, password, tokens or device ID (Facts used).

## 3. Redaction

One module-level set, `TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN,
CONF_DEVICE_ID}` (the first, second, third and fifth from `homeassistant.const`, `CONF_REFRESH_TOKEN` from
`const.py`), applied with `async_redact_data` to the whole output, loaded or not.

- **Password:** never stored, but on the list as a safeguard, so a later bug that stores it doesn't reach a
  download.
- **Whole output:** a later `pynortecgo` field or `entry.data` key with one of these names is redacted too.
- **Kept:** everything else (the Decisions table). `expires_at` helps with sign-in problems. The IDs and names
  help match a download to an issue and to the Home Assistant devices.

## 4. New client fields

`dataclasses.asdict` puts every field of the model in the output, so a field that a later `pynortecgo` adds
would be shown, and it might be a secret. A test pins the exact field names of `Charger` and `Vehicle`
(`dataclasses.fields`). When a client bump adds, removes or renames a field, that test fails; whoever bumps
the client then decides whether the field is a secret, adds it to `TO_REDACT` if so, updates the pinned list,
and the tests pass again. `Tokens` never reaches the output (the tokens in `entry.data` are strings, redacted
by key), so it isn't pinned.

## 5. User docs

The rule for users is stated once, in a new *Diagnostics* subsection of *Troubleshooting*, placed after
*Debug logging* and before *Reporting a problem* (another branch, #37, edits the same section: the edit stays
small). It says:

- how to download them: **Settings** > **Devices & services** > **Nortec Go**, the entry's menu (⋮) >
  **Download diagnostics**;
- what they hold: the last read of the charger and the car, and how the reads are going;
- what is removed: your email, the session tokens and the device ID the integration signs in with (your
  password is never stored);
- what stays: your charger's and car's names and IDs, and Home Assistant's own information (versions,
  installed custom integrations, the time zone). So check the file before you share it, and remove what you
  don't want public.

*Reporting a problem* gains one sentence: you can attach the diagnostics file, pointing to *Diagnostics* for
what it holds. Its existing advice (remove your email, your charger's and car's names, and anything else that
identifies you) is about pasted log lines, and stays.

The bug report template's *Diagnostics / logs* field gains: you can also attach the diagnostics file (see the
docs' *Diagnostics*).

`docs/manual-testing.md` gains a short `### Diagnostics (#11)` checklist, marked **Owner** (the entry's ⋮
menu is owner-only there): download the diagnostics from the entry's menu, save the file in `local/`, and
check that the email, both tokens and the device ID show as `**REDACTED**` and the charger's and car's data
are there. Agents never open the file (hard rule 9).

## 6. Hard rule 5 and the release checklist

`CLAUDE.md` hard rule 5 today:

> 5. Diagnostics and logs redact tokens, email, IDs and location (`async_redact_data`), and credentials and
>    usernames are never logged, even wrong ones. Anything taken from a real instance (diagnostics downloads,
>    logs, dumps) goes in `local/` and is never committed.

New wording (for the owner's approval with the spec):

> 5. Diagnostics and logs redact the email, the password, the access and refresh tokens and the client's
>    device ID (`async_redact_data`; D38), and credentials and usernames are never logged, even wrong ones.
>    Anything taken from a real instance (diagnostics downloads, logs, dumps) goes in `local/` and is never
>    committed.

Hard rule 3 (nothing private in this public repo, IDs included) doesn't change: it is about what is committed
here, not about what a user's download holds.

`docs/releasing.md`, the client-bump checklist, today asks to confirm that exception messages "hold no email,
password, token, IDs or request bodies" and cites hard rule 5. It becomes "hold no email, password, tokens,
device ID or request bodies", in line with the rule. It also gains one item: when the diagnostics field-pin
test fails, decide for each new field whether it is a secret (D38).

Other docs checked for the old list: `docs/way-of-working.md`, `docs/ha-notes.md`, `docs/manual-testing.md`,
`docs/notes.md`, the agents in `.claude/agents/` and the bug report template don't repeat it. The PR
template's "No private data: IDs, …" line is hard rule 3's, and stays. The coordinator's comment that
`pynortecgo`'s messages "hold no tokens, emails or IDs, so they may be passed on" becomes "hold no email,
password, tokens or device ID, so they may be passed on": the release checklist no longer checks IDs, and the
device ID now matters.

## 7. Decision log

D38, *Diagnostics redact only the sign-in secrets*:

```markdown
### D38: Diagnostics redact only the sign-in secrets
- **Date:** 2026-09-29 · **Status:** active
- **Decision:** Diagnostics and logs redact only the email, the password, the access and refresh tokens and
  the client's device ID, with `async_redact_data` over the whole diagnostics output; the charger's and car's
  IDs and names and the entry's title and unique ID stay. A test pins the `pynortecgo` model fields the
  output dumps, so a client bump that adds a field fails the tests until someone decides whether it is a
  secret.
- **Why:** The owner's ruling (issue #11): the IDs and names help match a download to an issue and to the
  devices, and aren't secrets. `asdict` shows every field, and Dependabot bumps the client; a new secret key
  in `entry.data` under another name still needs adding to the list by hand.
- **Source:** [diagnostics spec](superpowers/specs/2026-09-29-diagnostics-design.md), §3, §4 and §6
```

## 8. Tests

`tests/test_diagnostics.py`, with fixtures from `pynortecgo` model objects (`conftest.py`'s `make_charger`
and `make_vehicle`, hard rule 7), through Home Assistant's real endpoint, so serialization is tested too.
Every download in the test file goes through one helper, used instead of
`pytest_homeassistant_custom_component`'s `get_diagnostics_for_config_entry` (which returns only `data` and
uses the fixture's token): it sets up the `diagnostics` component, GETs
`/api/diagnostics/config_entry/<entry_id>` with `hass_client` and a fresh access token, asserts 200, and
returns the whole body. Tests read `["data"]` from it; test 2 uses the whole body. Tests 1, 2 and 4 run with time frozen (`freezer`, as `test_coordinator.py` does): `read_at` comes from
`utcnow()`, the price store prunes past slots, and a price retry is only scheduled when it falls before the
next price read. The token is fresh because `hass_client`'s own is made at fixture setup (Facts used): the
helper makes one after the last clock move, from a refresh token for `hass_admin_user` created with
`CLIENT_ID` (from `pytest_homeassistant_custom_component.common`; a normal refresh token needs a client ID),
then `hass.auth.async_create_access_token`, passed to `hass_client`. Expected error messages come from fake exception strings in the test, never from copied
client messages (hard rule 3).

1. **The whole output, exactly:** a set-up entry with a charge open (so `charge_id` is set) and a car, with
   known prices: the returned `data` equals the expected dict, the four stored secrets (`email`, both tokens,
   `device_id`) as `**REDACTED**`, and the kept
   fields with their fake values (the charger's and car's IDs and names, the charge ID, the title and unique
   ID).
2. **Secrets never appear:** an entry whose `data` also holds a `password` key (`FAKE_PASSWORD`; the
   safeguard), with a charge open, a car, and starts blocked (so the repair issue is in the download): the
   whole response body holds none of `FAKE_EMAIL`, `FAKE_PASSWORD`, the `FAKE_TOKENS` and `NEW_TOKENS`
   strings, `FAKE_DEVICE_ID`; and the kept fields do appear (`FAKE_CHARGER_NAME`, `FAKE_VEHICLE_NAME`, the
   charger's ID, the charge ID). The charger's ID also appears as the entry's unique ID; test 1 covers the
   model fields themselves.
3. **No car:** `vehicle` is `None`.
4. **Failing reads:** after a failed charger read, `last_update_success` is false and `last_exception` holds
   the error's message; after a later good read, `last_exception` is `None` again. A failed car read shows
   `car_read_failing`; a failed scheduled price read with a retry pending shows `price_read_failing` and
   `price_retry_pending`.
5. **Not loaded:** for an entry whose first read failed, the output is `entry` (secrets redacted),
   `"loaded": false`, `"state": "setup_retry"` and `"reason": None`; for one whose setup raised a
   `ChargerNotFoundError` with a fake message, `"state": "setup_error"` and that message as the reason.
6. **Field pin (§4):** `{f.name for f in fields(Charger)}` and the same for `Vehicle` equal the pinned sets.
