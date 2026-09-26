# Config flow, reauth and entry setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Let a user add Nortec Go from the UI with their login, keep the session across restarts with stored
tokens (never the password), and ask for the password again when the tokens are rejected.

**Architecture:** `entry.py` owns the config entry's shape: the typed entry (`ConfigEntry[NortecGoClient]`),
the token ↔ `entry.data` conversions and `create_client`, the one place a `NortecGoClient` is built.
`__init__.py` sets the entry up with a client from the stored tokens and checks it with one `get_charger()`.
`config_flow.py` has the user and reauth steps. No entities and no coordinator yet.

**Tech Stack:** Python 3.14, Home Assistant 2026.9.3 (via `pytest-homeassistant-custom-component==0.13.366`),
`pynortecgo==0.1.0`, uv, ruff, mypy (strict), pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-config-flow-design.md`. Read it with this plan; every § refers to
it.

## Global Constraints

- `pynortecgo==0.1.0`, pinned exactly, in `manifest.json` `requirements` and in the `dev` dependency group.
- Stored in `entry.data`: `email`, `access_token`, `refresh_token`, `expires_at` (ISO 8601), `device_id`.
  Never the password.
- The entry's `unique_id` is `str(charger.id)`; its title is the charger's name.
- Login happens only in the user and reauth steps, once per submit. Setup never logs in; nothing retries a
  login (hard rule 6).
- No email, password, token, charger ID or `device_id` in any log line or exception message, including
  `ConfigEntry*` exceptions (hard rule 5). `pynortecgo`'s own exception texts carry none and may be included.
- Stored tokens are always `client.tokens` read after `get_charger()`.
- `strings.json` has literal text only, no `[%key:…%]` references; `translations/en.json` is an exact copy.
- Tests always mock `pynortecgo`; fixtures are built from `pynortecgo` model objects with obviously fake
  values (hard rule 7). Nothing in the repo holds real IDs, emails, tokens or raw API endpoints (hard rule 3).
- Subagents never read `.env`, `local/` or `config/`.
- TDD: every behaviour gets a failing test first.
- Gates before every commit, in the task's working directory:
  `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`.
- Commit messages are written with the Write tool to a file outside the repo and committed with
  `git commit -F <file>` (the subagent guard refuses heredocs). They end with the co-author trailer given in
  the dispatch.
- Docs: plain, short sentences; lines ≤ 120 characters in `.md` files.

## Review Focus

- Email typed with spaces around it (a common paste): the stored and sent email is stripped. The password is
  sent exactly as typed, never stripped. Pinned in Task 3.
- A user starts "Add integration" for a charger while its reauth is open: abort `already_configured` (HA
  leaves reauth flows out of `already_in_progress`); two overlapping add flows for one charger abort
  `already_in_progress` with readable text, not a raw key. Both pinned in Task 3.
- A charger whose name is empty: the entry title falls back to `Nortec Go` instead of an empty title. Pinned
  in Task 3.
- `expires_at` keeps its UTC offset through the `entry.data` round trip, so a restart doesn't read a naive
  time. Pinned in Task 1.
- A setup retry after `ConfigEntryNotReady` reuses the stored tokens and never logs in. Pinned in Task 2.

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | 1, 4 | Disjoint files. Task 4 (docs) starts ahead of inputs, from the names this plan fixes, and is re-checked against the code that lands |
| 2 | 2 | Needs Task 1's `entry.py`, fixtures and `config_flow.py` stub (HA imports the `config_flow` platform to set up any entry) |
| 3 | 3 | Needs Task 2's `async_setup_entry`: a created or reauthed entry is set up for real (with the mocked client), and the AuthError → reauth test needs both |

No task has guarded files.

## File map

| File | Task | Responsibility |
|---|---|---|
| `pyproject.toml`, `uv.lock` | 1 | `pynortecgo==0.1.0` in the `dev` group |
| `custom_components/nortec_go/manifest.json` | 1 | `config_flow: true`, the requirement |
| `custom_components/nortec_go/const.py` | 1 | `CONF_REFRESH_TOKEN`, `CONF_EXPIRES_AT` |
| `custom_components/nortec_go/entry.py` | 1 | `NortecGoConfigEntry`, `tokens_to_data`, `tokens_from_data`, `create_client` |
| `tests/conftest.py` | 1 | Fake values, `mock_client_class`, `mock_client`, `mock_config_entry` |
| `tests/test_entry.py`, `tests/test_manifest.py` | 1 | Tests for `entry.py` and the pins |
| `custom_components/nortec_go/__init__.py` | 2 | `async_setup_entry`, `async_unload_entry` |
| `tests/test_init.py` | 2 | Setup, errors, token refresh, unload |
| `custom_components/nortec_go/config_flow.py` | 3 | User and reauth steps |
| `custom_components/nortec_go/strings.json`, `translations/en.json` | 3 | Flow text |
| `tests/test_config_flow.py` | 3 | Flow tests |
| `custom_components/nortec_go/quality_scale.yaml` | 4 | Rule statuses (§5) |
| `docs/user/nortec_go.md`, `CHANGELOG.md` | 4 | §6 |
| `docs/decisions.md`, `docs/way-of-working.md` | 4 | D18–D20, D8 superseded, backlog convention, sync note removed |

The spec's §4 says the fixture patches `NortecGoClient` "where `config_flow` and `__init__` import it". This
plan routes both through `entry.create_client`, so there is one patch site
(`custom_components.nortec_go.entry.NortecGoClient`). The intent is kept: one shared mocked instance, and the
class mock is exposed for constructor kwargs and `on_tokens_refreshed`.

The spec's §6 names a *Reauthentication* section in the user docs. This plan puts it under *Troubleshooting*
("Asked to sign in again"), which fits the home-assistant.io template (D9) better; the content is the same.

---

### Task 1: Dependency, entry helpers and test fixtures

**Model:** opus (token storage and the client construction every auth path uses) · **Wave:** 1

**Files:**
- Modify: `pyproject.toml` (the `dev` group), `uv.lock` (via `uv add`)
- Modify: `custom_components/nortec_go/manifest.json`
- Modify: `custom_components/nortec_go/const.py`
- Create: `custom_components/nortec_go/entry.py`
- Create: `custom_components/nortec_go/config_flow.py` (a stub; Task 3 replaces it)
- Modify: `tests/conftest.py`
- Create: `tests/test_entry.py`, `tests/test_manifest.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `custom_components.nortec_go.const`: `CONF_REFRESH_TOKEN: Final = "refresh_token"`,
    `CONF_EXPIRES_AT: Final = "expires_at"`.
  - `custom_components.nortec_go.entry`:
    - `type NortecGoConfigEntry = ConfigEntry[NortecGoClient]`
    - `def tokens_to_data(tokens: Tokens) -> dict[str, str]`
    - `def tokens_from_data(data: Mapping[str, Any]) -> Tokens`
    - `def create_client(hass: HomeAssistant, *, tokens: Tokens | None = None, device_id: str | None = None, on_tokens_refreshed: Callable[[Tokens], Awaitable[None]] | None = None) -> NortecGoClient`
  - `tests/conftest.py`: `FAKE_EMAIL`, `FAKE_PASSWORD`, `FAKE_DEVICE_ID`, `FAKE_CHARGER_ID`,
    `OTHER_CHARGER_ID`, `FAKE_CHARGER_NAME`, `FAKE_TOKENS`, `NEW_TOKENS`, `make_charger(charger_id: int = FAKE_CHARGER_ID, name: str = FAKE_CHARGER_NAME) -> Charger`,
    fixtures `mock_client_class`, `mock_client`, `mock_config_entry`.

- [ ] **Step 1: Add the dependency**

Run: `uv add --group dev pynortecgo==0.1.0`
Expected: `pyproject.toml`'s `dev` group gains `"pynortecgo==0.1.0"` and `uv.lock` gains `pynortecgo 0.1.0`.
If `uv add` writes the entry in another form (for example `>=`), edit it to `"pynortecgo==0.1.0"` and run
`uv lock`.

- [ ] **Step 2: Write the failing pin test**

Create `tests/test_manifest.py`:

```python
"""Tests for the integration manifest."""

import json
from pathlib import Path
import tomllib

from custom_components.nortec_go.const import DOMAIN

ROOT = Path(__file__).parent.parent
MANIFEST = ROOT / "custom_components" / DOMAIN / "manifest.json"
PYPROJECT = ROOT / "pyproject.toml"


def _pins(requirements: list[str]) -> list[str]:
    return [req for req in requirements if req.startswith("pynortecgo")]


def test_pynortecgo_pins_match() -> None:
    """The manifest and the dev group pin the same exact pynortecgo version."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    manifest_pins = _pins(manifest["requirements"])
    dev_pins = _pins(pyproject["dependency-groups"]["dev"])
    assert len(manifest_pins) == 1
    assert manifest_pins[0].startswith("pynortecgo==")
    assert manifest_pins == dev_pins


def test_config_flow_enabled() -> None:
    """The integration is set up from the UI."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["config_flow"] is True
```

- [ ] **Step 3: Run it to see it fail**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: both tests FAIL (`requirements` is empty, `config_flow` is false).

- [ ] **Step 4: Update the manifest**

In `custom_components/nortec_go/manifest.json` set `"config_flow": true` and
`"requirements": ["pynortecgo==0.1.0"]`. Keep every other key and the key order.

- [ ] **Step 5: Run it to see it pass**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: PASS.

- [ ] **Step 5a: Add the config flow stub**

With `config_flow: true`, HA imports the `config_flow` platform to set up any config entry (see
`docs/notes.md`), and hassfest expects the file. Create `custom_components/nortec_go/config_flow.py`:

```python
"""Config flow for Nortec Go."""

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class NortecGoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nortec Go. The steps come in a later task."""
```

- [ ] **Step 6: Add the fixtures**

Replace `tests/conftest.py` with:

```python
"""Fixtures for the Nortec Go tests."""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL
from pynortecgo import Charger, ChargerState, NortecGoClient, Tokens
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nortec_go.const import DOMAIN
from custom_components.nortec_go.entry import tokens_to_data

# Obviously fake values; nothing here comes from a real account (hard rules 3 and 7).
FAKE_EMAIL = "user@example.com"
FAKE_PASSWORD = "fake-password-123"
FAKE_DEVICE_ID = "00000000-0000-4000-8000-000000000000"
FAKE_CHARGER_ID = 918273645
OTHER_CHARGER_ID = 564738291
FAKE_CHARGER_NAME = "Garage charger"
FAKE_TOKENS = Tokens(
    access_token="fake-access-token",
    refresh_token="fake-refresh-token",
    expires_at=datetime(2030, 1, 1, 12, 0, tzinfo=UTC),
)
NEW_TOKENS = Tokens(
    access_token="new-fake-access-token",
    refresh_token="new-fake-refresh-token",
    expires_at=datetime(2030, 1, 2, 12, 0, tzinfo=UTC),
)


def make_charger(
    charger_id: int = FAKE_CHARGER_ID, name: str = FAKE_CHARGER_NAME
) -> Charger:
    """Return an idle charger with no open charge."""
    return Charger(
        id=charger_id,
        name=name,
        max_kw=11.0,
        state=ChargerState.AVAILABLE,
        state_raw="available",
        is_connected=False,
        charge_state=None,
        charge_state_raw=None,
        charge_id=None,
        can_stop=None,
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from custom_components in every test."""


@pytest.fixture
def mock_client_class() -> Generator[MagicMock]:
    """Patch the client class; every construction returns the same mocked client."""
    with patch(
        "custom_components.nortec_go.entry.NortecGoClient", autospec=True
    ) as client_class:
        client = AsyncMock(spec=NortecGoClient)
        client.login.return_value = FAKE_TOKENS
        client.get_charger.return_value = make_charger()
        client.tokens = FAKE_TOKENS
        client.device_id = FAKE_DEVICE_ID
        client_class.return_value = client
        yield client_class


@pytest.fixture
def mock_client(mock_client_class: MagicMock) -> AsyncMock:
    """The mocked client instance."""
    client: AsyncMock = mock_client_class.return_value
    return client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A config entry as the user step creates it."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=FAKE_CHARGER_NAME,
        unique_id=str(FAKE_CHARGER_ID),
        data={
            CONF_EMAIL: FAKE_EMAIL,
            CONF_DEVICE_ID: FAKE_DEVICE_ID,
            **tokens_to_data(FAKE_TOKENS),
        },
    )
```

- [ ] **Step 7: Write the failing `entry.py` tests**

Create `tests/test_entry.py`:

```python
"""Tests for the config entry helpers."""

import json
from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.nortec_go.const import CONF_EXPIRES_AT, CONF_REFRESH_TOKEN
from custom_components.nortec_go.entry import (
    create_client,
    tokens_from_data,
    tokens_to_data,
)

from .conftest import FAKE_DEVICE_ID, FAKE_TOKENS


def test_tokens_to_data() -> None:
    """Tokens become three JSON-safe strings."""
    data = tokens_to_data(FAKE_TOKENS)
    assert data == {
        CONF_ACCESS_TOKEN: "fake-access-token",
        CONF_REFRESH_TOKEN: "fake-refresh-token",
        CONF_EXPIRES_AT: "2030-01-01T12:00:00+00:00",
    }
    assert json.loads(json.dumps(data)) == data


def test_tokens_round_trip() -> None:
    """Tokens survive the round trip, and expires_at keeps its UTC offset."""
    tokens = tokens_from_data(tokens_to_data(FAKE_TOKENS))
    assert tokens == FAKE_TOKENS
    assert tokens.expires_at.utcoffset() is not None


def test_tokens_from_data_ignores_other_keys() -> None:
    """Other entry data (email, device_id) doesn't disturb the conversion."""
    data = {"email": "x", "device_id": "y", **tokens_to_data(FAKE_TOKENS)}
    assert tokens_from_data(data) == FAKE_TOKENS


async def test_create_client(hass: HomeAssistant, mock_client_class: MagicMock) -> None:
    """The client gets HA's shared session and the given keyword arguments."""
    callback = AsyncMock()
    client = create_client(
        hass,
        tokens=FAKE_TOKENS,
        device_id=FAKE_DEVICE_ID,
        on_tokens_refreshed=callback,
    )
    assert client is mock_client_class.return_value
    mock_client_class.assert_called_once_with(
        async_get_clientsession(hass),
        tokens=FAKE_TOKENS,
        device_id=FAKE_DEVICE_ID,
        on_tokens_refreshed=callback,
    )


async def test_create_client_defaults(
    hass: HomeAssistant, mock_client_class: MagicMock
) -> None:
    """Without arguments the client starts with no tokens and makes its own device_id."""
    create_client(hass)
    mock_client_class.assert_called_once_with(
        async_get_clientsession(hass),
        tokens=None,
        device_id=None,
        on_tokens_refreshed=None,
    )
```

- [ ] **Step 8: Run them to see them fail**

Run: `uv run pytest tests/test_entry.py -v`
Expected: collection error, `custom_components.nortec_go.entry` does not exist (and the conftest import fails
the same way).

- [ ] **Step 9: Add the constants**

Append to `custom_components/nortec_go/const.py`:

```python
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_EXPIRES_AT: Final = "expires_at"
```

- [ ] **Step 10: Write `entry.py`**

Create `custom_components/nortec_go/entry.py`:

```python
"""The Nortec Go config entry: its type, its stored tokens and its client."""

from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pynortecgo import NortecGoClient, Tokens

from .const import CONF_EXPIRES_AT, CONF_REFRESH_TOKEN

type NortecGoConfigEntry = ConfigEntry[NortecGoClient]


def tokens_to_data(tokens: Tokens) -> dict[str, str]:
    """Return the entry.data fields that store the tokens."""
    return {
        CONF_ACCESS_TOKEN: tokens.access_token,
        CONF_REFRESH_TOKEN: tokens.refresh_token,
        CONF_EXPIRES_AT: tokens.expires_at.isoformat(),
    }


def tokens_from_data(data: Mapping[str, Any]) -> Tokens:
    """Rebuild the tokens from entry.data."""
    return Tokens(
        access_token=data[CONF_ACCESS_TOKEN],
        refresh_token=data[CONF_REFRESH_TOKEN],
        expires_at=datetime.fromisoformat(data[CONF_EXPIRES_AT]),
    )


def create_client(
    hass: HomeAssistant,
    *,
    tokens: Tokens | None = None,
    device_id: str | None = None,
    on_tokens_refreshed: Callable[[Tokens], Awaitable[None]] | None = None,
) -> NortecGoClient:
    """Build a client on Home Assistant's shared aiohttp session."""
    return NortecGoClient(
        async_get_clientsession(hass),
        tokens=tokens,
        device_id=device_id,
        on_tokens_refreshed=on_tokens_refreshed,
    )
```

- [ ] **Step 11: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: all tests PASS, including the existing `test_init.py` and `test_quality_scale.py`.

- [ ] **Step 12: Run the gates and commit**

Run the gates (Global Constraints). Then write the message file (outside the repo) with the Write tool:

```
feat: add pynortecgo, entry helpers and test fixtures (#7)

<co-author trailer from the dispatch>
```

Run: `git add pyproject.toml uv.lock custom_components/nortec_go/manifest.json custom_components/nortec_go/const.py custom_components/nortec_go/entry.py custom_components/nortec_go/config_flow.py tests/conftest.py tests/test_entry.py tests/test_manifest.py && git commit -F <message file>`

---

### Task 2: Entry setup, token refresh and unload

**Model:** opus (reauth trigger and token persistence) · **Wave:** 2

**Files:**
- Modify: `custom_components/nortec_go/__init__.py`
- Modify: `tests/test_init.py`

**Interfaces:**
- Consumes (Task 1): `create_client`, `tokens_from_data`, `tokens_to_data`, `NortecGoConfigEntry`; fixtures
  `mock_client_class`, `mock_client`, `mock_config_entry`; `FAKE_*`, `NEW_TOKENS`, `OTHER_CHARGER_ID`,
  `make_charger`.
- Produces: `custom_components.nortec_go.async_setup_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> bool`
  and `async_unload_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> bool`. After setup,
  `entry.runtime_data` is the client.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_init.py` (keep the existing tests and imports; merge these imports into the existing
import block so ruff's isort order holds):

```python
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL
from pynortecgo import (
    ApiError,
    AuthError,
    ChargerNotFoundError,
    MultipleChargersError,
    NortecGoConnectionError,
    RateLimitError,
    UnexpectedResponseError,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nortec_go.entry import tokens_from_data

from .conftest import (
    FAKE_CHARGER_ID,
    FAKE_DEVICE_ID,
    FAKE_EMAIL,
    FAKE_TOKENS,
    NEW_TOKENS,
    OTHER_CHARGER_ID,
    make_charger,
)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    mock_client: AsyncMock,
) -> None:
    """Setup builds the client from the stored tokens and device_id, reads the charger once."""
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data is mock_client
    kwargs = mock_client_class.call_args.kwargs
    assert kwargs["tokens"] == FAKE_TOKENS
    assert kwargs["device_id"] == FAKE_DEVICE_ID
    assert kwargs["on_tokens_refreshed"] is not None
    mock_client.get_charger.assert_awaited_once()
    mock_client.login.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (NortecGoConnectionError("network down"), ConfigEntryState.SETUP_RETRY),
        (RateLimitError("too many requests"), ConfigEntryState.SETUP_RETRY),
        (ApiError("GET /example", 500), ConfigEntryState.SETUP_RETRY),
        (
            UnexpectedResponseError("GET /example", "bad shape"),
            ConfigEntryState.SETUP_ERROR,
        ),
        (ChargerNotFoundError("no charger"), ConfigEntryState.SETUP_ERROR),
        (MultipleChargersError("two chargers"), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_setup_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    error: Exception,
    state: ConfigEntryState,
) -> None:
    """Transient errors retry setup, permanent ones stop it; neither logs in."""
    mock_client.get_charger.side_effect = error
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is state
    mock_client.login.assert_not_awaited()


async def test_setup_retry_reuses_stored_tokens(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    mock_client: AsyncMock,
) -> None:
    """A retry after a transient error reads with the stored tokens and never logs in."""
    mock_client.get_charger.side_effect = NortecGoConnectionError("network down")
    await _setup(hass, mock_config_entry)
    state = mock_config_entry.state  # a local, so mypy doesn't keep the narrowing
    assert state is ConfigEntryState.SETUP_RETRY

    mock_client.get_charger.side_effect = None
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_client_class.call_count == 2
    assert mock_client_class.call_args.kwargs["tokens"] == FAKE_TOKENS
    mock_client.login.assert_not_awaited()


async def test_setup_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
) -> None:
    """A rejected token stops setup and asks HA for reauth, without logging in."""
    mock_client.get_charger.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth_if_available") as start_reauth:
        await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    start_reauth.assert_called_once()
    mock_client.login.assert_not_awaited()


async def test_setup_charger_changed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Another charger on the account stops setup, and neither ID is logged."""
    mock_client.get_charger.return_value = make_charger(OTHER_CHARGER_ID)
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    assert "charger has changed" in caplog.text
    assert str(FAKE_CHARGER_ID) not in caplog.text
    assert str(OTHER_CHARGER_ID) not in caplog.text


async def test_setup_logs_no_credentials(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Setup failures never log the email, tokens or device_id."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    mock_client.get_charger.side_effect = AuthError("token rejected")
    with patch.object(ConfigEntry, "async_start_reauth_if_available"):
        await _setup(hass, mock_config_entry)

    assert "could not authenticate" in caplog.text
    for secret in (
        FAKE_EMAIL,
        FAKE_DEVICE_ID,
        FAKE_TOKENS.access_token,
        FAKE_TOKENS.refresh_token,
    ):
        assert secret not in caplog.text


async def test_tokens_refreshed_are_stored(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
) -> None:
    """New tokens from a refresh go into entry.data; email and device_id stay; no reload."""
    await _setup(hass, mock_config_entry)
    on_tokens_refreshed = mock_client_class.call_args.kwargs["on_tokens_refreshed"]

    await on_tokens_refreshed(NEW_TOKENS)
    await hass.async_block_till_done()

    assert tokens_from_data(mock_config_entry.data) == NEW_TOKENS
    assert mock_config_entry.data[CONF_EMAIL] == FAKE_EMAIL
    assert mock_config_entry.data[CONF_DEVICE_ID] == FAKE_DEVICE_ID
    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_client_class.call_count == 1


async def test_unload_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Unload returns the entry to NOT_LOADED."""
    await _setup(hass, mock_config_entry)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_init.py -v`
Expected: the new tests FAIL (the integration has no `async_setup_entry`, so the entry ends in
`SETUP_ERROR` or setup returns False); the four existing tests PASS.

- [ ] **Step 3: Implement setup and unload**

Replace `custom_components/nortec_go/__init__.py` with:

```python
"""The Nortec Go integration."""

from homeassistant.const import CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from pynortecgo import (
    ApiError,
    AuthError,
    ChargerNotFoundError,
    MultipleChargersError,
    NortecGoConnectionError,
    RateLimitError,
    Tokens,
    UnexpectedResponseError,
)

from .const import DOMAIN
from .entry import NortecGoConfigEntry, create_client, tokens_from_data, tokens_to_data

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = []


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Nortec Go integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> bool:
    """Set up Nortec Go from a config entry, with the stored tokens."""

    async def _async_store_tokens(tokens: Tokens) -> None:
        # Runs inside the client's refresh: must not call the client.
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, **tokens_to_data(tokens)}
        )

    client = create_client(
        hass,
        tokens=tokens_from_data(entry.data),
        device_id=entry.data[CONF_DEVICE_ID],
        on_tokens_refreshed=_async_store_tokens,
    )
    # pynortecgo's messages hold no tokens, emails or IDs, so they may be passed on.
    try:
        charger = await client.get_charger()
    except AuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (NortecGoConnectionError, RateLimitError, ApiError) as err:
        raise ConfigEntryNotReady(str(err)) from err
    except (
        UnexpectedResponseError,
        ChargerNotFoundError,
        MultipleChargersError,
    ) as err:
        raise ConfigEntryError(str(err)) from err

    if str(charger.id) != entry.unique_id:
        raise ConfigEntryError(
            "The account's charger has changed; remove the integration and add it again"
        )

    entry.runtime_data = client
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NortecGoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest tests/test_init.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the gates and commit**

Run the gates. Message file:

```
feat: set up the config entry with stored tokens (#7)

<co-author trailer from the dispatch>
```

Run: `git add custom_components/nortec_go/__init__.py tests/test_init.py && git commit -F <message file>`

---

### Task 3: Config flow (user and reauth steps) and strings

**Model:** opus (login, token storage and reauth) · **Wave:** 3

**Files:**
- Modify: `custom_components/nortec_go/config_flow.py` (replace Task 1's stub)
- Modify: `custom_components/nortec_go/strings.json`, `custom_components/nortec_go/translations/en.json`
- Create: `tests/test_config_flow.py`

**Interfaces:**
- Consumes (Task 1): `create_client`, `tokens_to_data`, `tokens_from_data`; fixtures and fakes from
  `tests/conftest.py`. (Task 2): `async_setup_entry`, so a created or reloaded entry sets up with the mocked
  client.
- Produces: `NortecGoConfigFlow` (domain `nortec_go`, `VERSION = 1`), steps `user`, `reauth`,
  `reauth_confirm`; error keys `invalid_auth`, `cannot_connect`, `rate_limited`, `no_charger`,
  `multiple_chargers`, `unknown`; abort reasons `already_configured`, `already_in_progress`,
  `reauth_successful`, `wrong_account`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_flow.py`:

```python
"""Tests for the Nortec Go config flow."""

from collections.abc import Mapping
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_USER,
    ConfigEntryState,
    ConfigFlow,
)
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pynortecgo import (
    ApiError,
    AuthError,
    ChargerNotFoundError,
    MultipleChargersError,
    NortecGoConnectionError,
    RateLimitError,
    UnexpectedResponseError,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nortec_go.const import DOMAIN
from custom_components.nortec_go.entry import tokens_from_data, tokens_to_data

from .conftest import (
    FAKE_CHARGER_ID,
    FAKE_CHARGER_NAME,
    FAKE_DEVICE_ID,
    FAKE_EMAIL,
    FAKE_PASSWORD,
    FAKE_TOKENS,
    NEW_TOKENS,
    OTHER_CHARGER_ID,
    make_charger,
)

USER_INPUT = {CONF_EMAIL: FAKE_EMAIL, CONF_PASSWORD: FAKE_PASSWORD}

# (method that raises, exception, error key)
FLOW_ERRORS = [
    ("login", AuthError("rejected"), "invalid_auth"),
    ("login", NortecGoConnectionError("network down"), "cannot_connect"),
    ("login", ApiError("POST /example", 500), "cannot_connect"),
    ("login", RateLimitError("too many requests"), "rate_limited"),
    ("get_charger", ChargerNotFoundError("no charger"), "no_charger"),
    ("get_charger", MultipleChargersError("two chargers"), "multiple_chargers"),
    ("get_charger", UnexpectedResponseError("GET /example", "bad shape"), "unknown"),
    ("login", RuntimeError("boom"), "unknown"),
]


def _suggested(result: Mapping[str, Any], key: str) -> Any:
    for marker in result["data_schema"].schema:
        if marker == key:
            return (marker.description or {}).get("suggested_value")
    raise AssertionError(key)


async def test_user_flow(
    hass: HomeAssistant, mock_client_class: MagicMock, mock_client: AsyncMock
) -> None:
    """A login creates the entry with tokens and device_id, never the password."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == FAKE_CHARGER_NAME
    assert result["data"] == {
        CONF_EMAIL: FAKE_EMAIL,
        CONF_DEVICE_ID: FAKE_DEVICE_ID,
        **tokens_to_data(FAKE_TOKENS),
    }
    assert CONF_PASSWORD not in result["data"]
    assert result["result"].unique_id == str(FAKE_CHARGER_ID)
    assert result["result"].state is ConfigEntryState.LOADED
    assert mock_client_class.call_args_list[0].kwargs["device_id"] is None
    mock_client.login.assert_awaited_once_with(FAKE_EMAIL, FAKE_PASSWORD)


async def test_user_flow_stores_client_tokens(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """The stored tokens are client.tokens after get_charger, not login's return value."""
    mock_client.tokens = NEW_TOKENS
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert tokens_from_data(result["data"]) == NEW_TOKENS


async def test_user_flow_strips_email_not_password(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """Spaces around the email are dropped; the password is sent as typed."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: f"  {FAKE_EMAIL} ", CONF_PASSWORD: " pass word "},
    )
    await hass.async_block_till_done()

    assert result["data"][CONF_EMAIL] == FAKE_EMAIL
    mock_client.login.assert_awaited_once_with(FAKE_EMAIL, " pass word ")


async def test_user_flow_empty_charger_name(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """A charger without a name gets the title 'Nortec Go'."""
    mock_client.get_charger.return_value = make_charger(name="")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["title"] == "Nortec Go"


@pytest.mark.parametrize(("method", "error", "key"), FLOW_ERRORS)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    method: str,
    error: Exception,
    key: str,
) -> None:
    """Each error shows its key, keeps the email, logs in once, and a retry succeeds."""
    getattr(mock_client, method).side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": key}
    assert _suggested(result, CONF_EMAIL) == FAKE_EMAIL
    assert _suggested(result, CONF_PASSWORD) is None
    assert mock_client.login.await_count == 1

    getattr(mock_client, method).side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_client.login.await_count == 2


async def test_user_flow_logs_no_credentials(
    hass: HomeAssistant, mock_client: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    """An unexpected error is logged without the email or password."""
    caplog.set_level(logging.DEBUG, logger="custom_components.nortec_go")
    mock_client.login.side_effect = RuntimeError("boom")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert "Unexpected error" in caplog.text
    assert FAKE_EMAIL not in caplog.text
    assert FAKE_PASSWORD not in caplog.text


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """The same charger can't be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_while_reauth_in_progress(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Adding a charger whose reauth is open aborts as already configured.

    HA leaves reauth flows out of its already_in_progress check, so the entry check decides.
    """
    mock_config_entry.add_to_hass(hass)
    await mock_config_entry.start_reauth_flow(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_parallel_for_same_charger(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """A second add flow for a charger another add flow has claimed aborts with readable text."""
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    flow = hass.config_entries.flow._progress[first["flow_id"]]  # noqa: SLF001
    assert isinstance(flow, ConfigFlow)
    await flow.async_set_unique_id(str(FAKE_CHARGER_ID))

    result = await hass.config_entries.flow.async_configure(
        second["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"


async def test_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client_class: MagicMock,
    mock_client: AsyncMock,
) -> None:
    """Reauth logs in with the stored email and device_id and stores the new tokens."""
    mock_config_entry.add_to_hass(hass)
    mock_client.tokens = NEW_TOKENS
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    # HA adds {"name": entry.title} to reauth placeholders itself.
    assert result["description_placeholders"] == {
        "email": FAKE_EMAIL,
        "name": FAKE_CHARGER_NAME,
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: FAKE_PASSWORD}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert tokens_from_data(mock_config_entry.data) == NEW_TOKENS
    assert mock_config_entry.data[CONF_EMAIL] == FAKE_EMAIL
    assert mock_config_entry.data[CONF_DEVICE_ID] == FAKE_DEVICE_ID
    assert CONF_PASSWORD not in mock_config_entry.data
    assert mock_client_class.call_args_list[0].kwargs["device_id"] == FAKE_DEVICE_ID
    mock_client.login.assert_awaited_once_with(FAKE_EMAIL, FAKE_PASSWORD)


async def test_reauth_wrong_account(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """Signing in to an account with another charger aborts and keeps the old data."""
    mock_config_entry.add_to_hass(hass)
    mock_client.get_charger.return_value = make_charger(OTHER_CHARGER_ID)
    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: FAKE_PASSWORD}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert tokens_from_data(mock_config_entry.data) == FAKE_TOKENS


@pytest.mark.parametrize(("method", "error", "key"), FLOW_ERRORS)
async def test_reauth_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    method: str,
    error: Exception,
    key: str,
) -> None:
    """Each reauth error shows its key, logs in once, and a retry succeeds."""
    mock_config_entry.add_to_hass(hass)
    getattr(mock_client, method).side_effect = error
    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: FAKE_PASSWORD}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": key}
    assert mock_client.login.await_count == 1

    getattr(mock_client, method).side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: FAKE_PASSWORD}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_client.login.await_count == 2


async def test_setup_auth_error_opens_reauth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    """A token rejected at setup opens the reauth form."""
    mock_client.get_charger.side_effect = AuthError("token rejected")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    assert flows[0]["step_id"] == "reauth_confirm"
    mock_client.login.assert_not_awaited()
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_config_flow.py -v`
Expected: FAIL; the stub flow has no `user` step (the flow aborts or errors with an unknown step).

- [ ] **Step 3: Write the config flow**

Replace `custom_components/nortec_go/config_flow.py` with:

```python
"""Config flow for Nortec Go."""

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE_ID, CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from pynortecgo import (
    ApiError,
    AuthError,
    Charger,
    ChargerNotFoundError,
    MultipleChargersError,
    NortecGoClient,
    NortecGoConnectionError,
    RateLimitError,
    Tokens,
)
import voluptuous as vol  # noqa: TID251  (HA 2026.9.3's flow API is typed for voluptuous schemas)

from .const import DOMAIN
from .entry import create_client, tokens_to_data

_LOGGER = logging.getLogger(__name__)

DEFAULT_TITLE = "Nortec Go"

EMAIL_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
)
PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)
USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): EMAIL_SELECTOR,
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR})


async def _async_sign_in(
    client: NortecGoClient, email: str, password: str
) -> tuple[Charger, Tokens] | str:
    """Log in once and read the charger; return them, or the error key for the form."""
    try:
        await client.login(email, password)
        charger = await client.get_charger()
    except AuthError:
        return "invalid_auth"
    except NortecGoConnectionError, ApiError:
        return "cannot_connect"
    except RateLimitError:
        return "rate_limited"
    except ChargerNotFoundError:
        return "no_charger"
    except MultipleChargersError:
        return "multiple_chargers"
    except Exception:
        # Never log the email or password; pynortecgo's messages hold neither.
        _LOGGER.exception("Unexpected error while signing in to Nortec Go")
        return "unknown"
    tokens = client.tokens
    assert tokens is not None  # login() sets them
    return charger, tokens


class NortecGoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nortec Go."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the email and password, then create the entry."""
        errors: dict[str, str] = {}
        suggested: dict[str, Any] | None = None
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            client = create_client(self.hass)
            result = await _async_sign_in(client, email, user_input[CONF_PASSWORD])
            if isinstance(result, str):
                errors["base"] = result
                suggested = {CONF_EMAIL: email}
            else:
                charger, tokens = result
                await self.async_set_unique_id(str(charger.id))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=charger.name or DEFAULT_TITLE,
                    data={
                        CONF_EMAIL: email,
                        CONF_DEVICE_ID: client.device_id,
                        **tokens_to_data(tokens),
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, suggested),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth when the stored tokens are rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the password again and store the new tokens."""
        entry = self._get_reauth_entry()
        email: str = entry.data[CONF_EMAIL]
        errors: dict[str, str] = {}
        if user_input is not None:
            client = create_client(self.hass, device_id=entry.data[CONF_DEVICE_ID])
            result = await _async_sign_in(client, email, user_input[CONF_PASSWORD])
            if isinstance(result, str):
                errors["base"] = result
            else:
                charger, tokens = result
                await self.async_set_unique_id(str(charger.id))
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates=tokens_to_data(tokens)
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"email": email},
            errors=errors,
        )
```

The `voluptuous` import keeps its `noqa`: ruff's config (copied from HA core dev) bans it in favour of
`probatio`, but HA 2026.9.3's `add_suggested_values_to_schema` and `async_show_form` are typed for voluptuous
schemas, so `probatio` fails mypy strict (HA aliases one to the other at runtime).

- [ ] **Step 4: Write the strings**

Replace `custom_components/nortec_go/strings.json` with the following, and write the identical content to
`custom_components/nortec_go/translations/en.json`:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Sign in to Nortec Go",
        "description": "Sign in with the email and password you use in the Nortec Go app.",
        "data": {
          "email": "Email",
          "password": "Password"
        },
        "data_description": {
          "email": "The email address of your Nortec Go account.",
          "password": "Your Nortec Go password. It is used once to sign in and is not stored."
        }
      },
      "reauth_confirm": {
        "title": "Sign in to Nortec Go again",
        "description": "The Nortec Go session for {email} was rejected. Enter your password to sign in again.",
        "data": {
          "password": "Password"
        },
        "data_description": {
          "password": "Your Nortec Go password. It is used once to sign in and is not stored."
        }
      }
    },
    "error": {
      "invalid_auth": "The email or password is wrong.",
      "cannot_connect": "Can't reach the Nortec Go service. Check your connection and try again.",
      "rate_limited": "Too many sign-in attempts. Wait a while before you try again.",
      "no_charger": "This account has no charger.",
      "multiple_chargers": "This account has more than one charger. Only one charger per account is supported.",
      "unknown": "Unexpected error. Check the Home Assistant logs."
    },
    "abort": {
      "already_configured": "This charger is already set up.",
      "already_in_progress": "This charger is already being set up or signed in again.",
      "reauth_successful": "Signed in again.",
      "wrong_account": "This account's charger isn't the one this integration was set up for. Sign in with the same account."
    }
  }
}
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: all PASS, including `test_translations_match_strings`.

- [ ] **Step 6: Check coverage of the flow**

Run: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing -q`
Expected: `config_flow.py` at 100% (`config-flow-test-coverage`). If a line is missed, add the test that
reaches it; don't add `pragma: no cover`.

- [ ] **Step 7: Run the gates and commit**

Run the gates. Message file:

```
feat: config flow with login and reauth (#7)

<co-author trailer from the dispatch>
```

Run: `git add custom_components/nortec_go/config_flow.py custom_components/nortec_go/strings.json custom_components/nortec_go/translations/en.json tests/test_config_flow.py && git commit -F <message file>`

---

### Task 4: Quality scale, user docs, changelog, decisions and process

**Model:** sonnet · **Wave:** 1 (docs, starting ahead of inputs from the names this plan fixes)

**Files:**
- Modify: `custom_components/nortec_go/quality_scale.yaml`
- Modify: `docs/user/nortec_go.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/decisions.md`
- Modify: `docs/way-of-working.md`

**Interfaces:**
- Consumes: the names fixed in this plan (steps `user` and `reauth_confirm`, the form fields Email and
  Password, the error and abort texts in Task 3 Step 4, title fallback `Nortec Go`).
- Produces: docs only.

- [ ] **Step 1: Quality scale**

In `custom_components/nortec_go/quality_scale.yaml`, change these rules from `todo` to `done` (plain string
form, `rule: done`): `config-flow`, `config-flow-test-coverage`, `test-before-configure`, `test-before-setup`,
`unique-config-entry`, `runtime-data`, `config-entry-unloading`, `reauthentication-flow`, `inject-websession`,
`async-dependency`, `docs-installation-instructions`, `docs-removal-instructions`,
`docs-installation-parameters`, `docs-known-limitations`, `docs-high-level-description`, `integration-owner`.

Change `docs-configuration-parameters` to:

```yaml
  docs-configuration-parameters:
    status: exempt
    comment: "The integration has no options flow."
```

Leave every other rule, including `dependency-transparency`, as it is. Run `uv run pytest tests/test_quality_scale.py -q`
(54 rules, every exemption has a comment): PASS.

- [ ] **Step 2: User docs**

In `docs/user/nortec_go.md`:

- *Prerequisites*: keep the text (exactly one charger and one car). Add one sentence: "The car isn't checked
  when you add the integration, but later features need it."
- After *Installation*, add a new section:

  ```markdown
  ## Configuration

  1. Go to **Settings** > **Devices & services** and select **Add integration**.
  2. Search for **Nortec Go** and select it.
  3. Enter the email and password you use in the Nortec Go app.

  Email
  : The email address of your Nortec Go account.

  Password
  : Your Nortec Go password. It is used once to sign in and is not stored.

  Home Assistant stores only the session that the sign-in returns, and renews it by itself. The integration
  is named after your charger.
  ```

- *Configuration options*: replace "Not available yet." with "The integration has no options to change after
  setup."
- *Known limitations*: replace "Not available yet." with:

  ```markdown
  - One charger per account. An account with no charger or with more than one can't be added.
  - Unofficial: the integration uses the same private API as the app, which can change without notice.
  - No entities yet. The integration only signs in and checks the charger; sensors and charge control come
    in later releases.
  ```

- *Troubleshooting*: replace "Not available yet." with:

  ```markdown
  ### Asked to sign in again

  When the stored session is rejected, Home Assistant shows a **Reauthentication required** notice for Nortec
  Go. Select it and enter your password. You sign in to the same account; signing in to an account with
  another charger is refused.

  ### "Too many sign-in attempts"

  The Nortec Go service limits sign-ins. Wait a while before you try again.
  ```

- *Removing the integration*: replace the text with:

  ```markdown
  1. Go to **Settings** > **Devices & services** and select **Nortec Go**.
  2. Open the menu (⋮) and select **Delete**.
  3. To remove the files as well, remove **Nortec Go** in HACS and restart Home Assistant.
  ```

- [ ] **Step 3: Changelog**

Under `## [Unreleased]` in `CHANGELOG.md`, add:

```markdown
### Added

- Add the integration from the UI with your Nortec Go email and password. Only the session is stored, never
  the password.
- Reauthentication: when the session is rejected, Home Assistant asks for the password again.
```

- [ ] **Step 4: Decisions**

In `docs/decisions.md`:

- In D8, change only the status: `**Status:** superseded by D20`.
- Append:

  ```markdown
  ### D18: Config entry holds tokens and device_id; charger ID is the unique ID
  - **Date:** 2026-09-26 · **Status:** active
  - **Decision:** The config entry stores the email, the session tokens and the client's `device_id`, never the
    password. The account's charger ID is the entry's `unique_id`; it isn't stored in the entry data, since
    the client finds the charger itself. Pin bumps (D7) come as PRs, with a test keeping the manifest and dev
    pins equal.
  - **Why:** Login is rate-limited and the password shouldn't sit in Home Assistant's storage; the charger ID
    stops the same charger being added twice and catches a changed account at setup.
  - **Source:** [config-flow spec](superpowers/specs/2026-09-26-config-flow-design.md), Decisions

  ### D19: GitHub issues are the backlog
  - **Date:** 2026-09-26 · **Status:** active
  - **Decision:** Anything found that won't be fixed in the current work becomes a GitHub issue, or is added
    to an existing one.
  - **Why:** One place for everything still to do, instead of notes scattered over specs and PRs.
  - **Source:** owner request on 2026-09-26; [config-flow spec](superpowers/specs/2026-09-26-config-flow-design.md), §7

  ### D20: Each repo owns its way of working
  - **Date:** 2026-09-26 · **Status:** active
  - **Decision:** This repo's `docs/way-of-working.md` is its own, with no duty to keep it in step with
    `NortecGo`'s. A learning that clearly helps the other repo may be sent there as an issue. Anything the
    client needs still goes to `NortecGo` as a change request, sent to the `nortecgo-af` session or filed
    with `gh issue create -R thomas3650/nortecgo --label ha-integration`. Supersedes D8.
  - **Why:** The repos do different jobs; a sync duty costs an issue for every process change, most of
    which don't apply to the other repo.
  - **Source:** owner decision on 2026-09-26 (NortecGo#41 closed);
    [config-flow spec](superpowers/specs/2026-09-26-config-flow-design.md), §7
  ```

- [ ] **Step 5: Way of working**

In `docs/way-of-working.md`:

- Delete the first paragraph after the title ("A sibling copy lives in the private `NortecGo` repo. A process
  change in either copy gets a follow-up issue in the other repo.") and the blank line after it.
- In §6 *Conventions*, after the **Issues** bullet, add:

  ```markdown
  - **Backlog:** GitHub issues are the backlog (D19). Anything found that won't be fixed in the current work
    becomes an issue, or is added to an existing one.
  ```

Check nothing else in the repo still mentions the sync note: `grep -rn -i "sibling copy\|sync note" docs CLAUDE.md README.md`.
Expected hits: D8 (superseded) in `docs/decisions.md`, and the specs and plans under `docs/superpowers/`
(snapshots, never edited). `docs/way-of-working.md` must no longer appear. Report any other hit to the
controller.

- [ ] **Step 6: Run the gates and commit**

Run the gates. Check `.md` lines are ≤ 120 characters in the files you changed. Message file:

```
docs: quality scale, user docs, changelog and decisions D18-D20 (#7)

<co-author trailer from the dispatch>
```

Run: `git add custom_components/nortec_go/quality_scale.yaml docs/user/nortec_go.md CHANGELOG.md docs/decisions.md docs/way-of-working.md && git commit -F <message file>`
