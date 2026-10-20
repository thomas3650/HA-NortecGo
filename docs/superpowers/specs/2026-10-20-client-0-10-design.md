# Update pynortecgo to 0.10.0 — design

Date: 2026-10-20 · Branch: `feat/client-0-10` · Issue: #111

## Goal

- **What:** pin `pynortecgo==0.10.0` (from `0.8.0`) in `manifest.json` and `pyproject.toml`, update the lock
  with `uv lock --upgrade-package pynortecgo` ([`releasing.md`](../../releasing.md#bumping-pynortecgo)), and
  make the tests and the diagnostics expectations fit the client's models.
- **Why:** 0.9.0, 0.9.1 and 0.10.0 bring fixes that users see:
  - two car power-delivery values (*Unplugged*, *PluggedInComplete*) were logged as unknown at every
    restart; they are now known;
  - a reply time that doesn't fit a date (year 1 or 9999) used to raise a bare `OverflowError`, which none
    of the integration's handlers caught. Now it raises `UnexpectedResponseError`, or, in the charge
    history, gives no last charge.
- **Not in this work:**
  - a new entity for a charge's start time (`started_at`). It's a new feature, and gets its own issue if
    it's wanted;
  - automatic bumps of the pin (#49);
  - any change to `ChargerState` or `ChargeState` handling. The client adds no members there.
- **Done when:**
  - both pins say `0.10.0` (`tests/test_manifest.py::test_pynortecgo_pins_match` checks they match);
  - `uv.lock` holds 0.10.0;
  - the gates pass, including the coverage gate;
  - `scripts/smoke` passes;
  - `CHANGELOG.md` has the entries below under *Unreleased*;
  - the PR description holds the results of the *Bumping `pynortecgo`* checklist (*Checklist* below).

## What changes in the client (0.8.0 → 0.10.0)

Checked against the published wheels of both versions:

| Change | Version | Effect here |
|---|---|---|
| `ActiveCharge.started_at: datetime \| None`, required | 0.9.0 | The test factory `make_charger` builds an `ActiveCharge` and must pass it. The integration's code builds no models |
| `CompletedCharge.started_at: datetime`, required | 0.9.0 | The test factory `make_completed_charge` must pass it |
| The history reads a charge's start time strictly | 0.9.0 | A newest completed charge without a start time fails the history read. `last_charge` is then None, with a client warning. That reaches the *Last charge cost* sensor, `costs.py` and the energy ledger's settling (`energy.py`), all of which already handle `last_charge` None. This is a known effect, and needs no code change |
| A WARNING, once per client, for an open charge without a start time (`started_at` None), then DEBUG | 0.9.0 | A log line from `pynortecgo`, holding no value or secret. No code change, and no changelog entry: the integration's behaviour doesn't change |
| A time in year 1 or 9999 raises `UnexpectedResponseError`; in the history it gives `last_charge` None | 0.9.1 | See *Out-of-range times* below |
| `PowerDeliveryState.UNPLUGGED`, `PLUGGED_IN_COMPLETE` | 0.10.0 | None in the code: only diagnostics reads `power_delivery_state`, as a value |

The `NortecGoClient` method signatures, the public names (`__all__`) and `exceptions.py` are the same in
both versions.

### Out-of-range times

The client reads times strictly in the token's expiry (login and every refresh), the car's `last_seen`, the
history's times, and the price slots. The open charge's start time is read leniently: an out-of-range one
becomes None. Each path the integration already handles, with no code change:

| Path | Now (0.10.0) | Before (bare `OverflowError`) | Existing test |
|---|---|---|---|
| Charger read, with a token refresh inside it | The `unexpected_response` error, a `ConfigEntryError` (`coordinator.py`) | Got past `except NortecGoError`: HA's "Unexpected error fetching" | `test_first_refresh_charger_errors` (its `UnexpectedResponseError` row) and `test_later_permanent_charger_errors`, in `tests/test_coordinator.py` |
| Car read at setup | `UpdateFailed` with `unexpected_response` | As above | `test_car_error_at_setup_retries` |
| Car read while running | A warning, and the car keeps its last data | Failed the whole update | `test_later_car_error_keeps_car_data`. It raises `ApiError`, but the catch is `except NortecGoError`, so it covers this path too |
| Price read | A warning, and the D37 retry; the *Refresh* button raises `price_read_failed` | Got past the price read, also at setup (`__init__.py`) | `test_failed_price_read_keeps_slots`, and `test_press_raises_when_only_the_price_read_fails` in `tests/test_button.py`. They raise other client errors, but the price read catches any `NortecGoError`, so they cover this path too |
| Config flow, reauth and reconfigure sign-in | `unknown`, through `except Exception` | The same | The `unknown` cases in `tests/test_config_flow.py` |
| Charge history | `last_charge` None | Failed the charger read | `test_last_charge_reads_without_a_last_charge` in `tests/test_costs.py` |

## Decisions

Approved by the controller on 2026-10-20, under the owner's delegation for this issue.

| Topic | Decision |
|---|---|
| `started_at` in diagnostics | Shown, not redacted: like `completed_at`, it's a charge time, not a sign-in secret (D38). The download dumps the models with `asdict`, so it appears in `active_charge` and `last_charge` with no code change. No changelog entry (D46): what the user docs say the download keeps, the last charge's ID, cost, energy and time, stays true |
| The field pins | `ACTIVE_CHARGE_FIELDS` and `COMPLETED_CHARGE_FIELDS` in `tests/test_diagnostics.py` gain `started_at`, so `test_client_model_fields_are_pinned` passes again |
| Test factories | `make_charger` gains a keyword `started_at: datetime \| None = FAKE_STARTED_AT`, passed to the `ActiveCharge`; `None` stays possible. `make_completed_charge` gains `started_at: datetime = FAKE_LAST_STARTED_AT`. The new constants in `tests/conftest.py` are `FAKE_STARTED_AT = datetime(2026, 9, 27, 9, 30, tzinfo=UTC)` and `FAKE_LAST_STARTED_AT = datetime(2026, 9, 25, 3, 45, tzinfo=UTC)`, the latter before `FAKE_COMPLETED_AT`. Both are fake values (hard rule 7) |
| Diagnostics expectations | `test_diagnostics_output` is the only test that dumps a charge. Its expected `active_charge` gains `"started_at": "2026-09-27T09:30:00+00:00"`, and its `last_charge` gains `"started_at": "2026-09-25T03:45:00+00:00"` |
| Title | `fix: update pynortecgo to 0.10.0 (#111)`. The fixes are user-visible, so it's a patch release, with the bump step |
| Docs | `docs/user/nortec_go.md` and `quality_scale.yaml` don't change, because no entity, option or behaviour of the integration does |
| Decision log | No entry: a dependency bump sets no lasting rule |

## CHANGELOG entries

Under `## [Unreleased]`, `### Fixed`:

- The log no longer warns at every restart that the car's power-delivery state is unknown when the car is
  unplugged or done charging.
- A time out of range in a reply from the service no longer causes an unhandled error:
  - a failed charger read shows the "unexpected reply" error;
  - a failed car or price read keeps its last values and is tried again (a failed car read at setup retries
    the setup);
  - in the charge history, it means no last charge.

## Checklist

The *Bumping `pynortecgo`* checklist ([`releasing.md`](../../releasing.md#bumping-pynortecgo)), with its
results. The PR description repeats them:

- **Exception messages:** the only new text is `UnexpectedResponseError(endpoint, "wrong type for field
  '<where>'")`, for an out-of-range time. It holds no value, email, password, token, device ID or request
  body.
- **Diagnostics fields:** the one new field is `started_at` on `ActiveCharge` and `CompletedCharge`. It's
  not a secret, so `TO_REDACT` doesn't change; the pinned sets are updated.
- **New exception classes:** none (`exceptions.py` and `__all__` are unchanged).
- **Breaking model changes:** only the new required `started_at` fields. The integration builds no models,
  and its entities don't read the field.

## Testing

- TDD: bumping the pin first makes the factory calls and `test_client_model_fields_are_pinned` fail; the
  factory and pin changes make them pass.
- One new test builds a charger whose open charge has `started_at=None`, and checks that the charge sensors
  still read it, because the client allows a charge with no start time.
- `tests/test_manifest.py::test_pynortecgo_pins_match` checks that the two pins match.
- The coverage gate stays at 95% or above.
- `scripts/smoke` runs before the PR is ready.

## Execution shape

One task, `Model: opus`, because it touches the mapping of `pynortecgo` models and diagnostics (§5). It
covers the pins, the lock, the factories, the diagnostics tests, the `None` test and the CHANGELOG entries.
