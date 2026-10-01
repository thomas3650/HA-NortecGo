# Quality scale statuses in line with the code — design

Date: 2026-09-30 · Branch: `chore/quality-scale-status` · Issue: #36 (part of #12)

## Goal

- **What:** every rule in `custom_components/nortec_go/quality_scale.yaml` has the status that the current
  rule text and the code on `main` support. A rule that stays `todo` says what is missing.
- **Why:** the owner wants to see a clear path to Silver (#12). Some statuses are out of date today
  (`test-coverage`, `action-setup`), and one claims more than the code does (`action-exceptions`, #40).
- **Not in this work:**
  - Fixing #40. The *Refresh* button keeps its silent press. `action-exceptions` goes back to `todo` and
    points at #40. #40 stays open: the PR says `Closes #36` only.
  - Any behaviour change. Every entity keeps its registry default.
- **Done when:** each of the 54 rules was checked against its rule text (fetched from
  developers.home-assistant.io on 2026-09-30) and the code. The statuses and comments below are in the file,
  `tests/test_quality_scale.py` passes with the new assertions (§3), and the gates pass.

## Decisions

Proposed by the team lead and approved through the PO (issue #36, 2026-09-30).

| Topic | Decision |
|---|---|
| `entity-disabled-by-default` | `done`. *Last read* and *Last seen* stay enabled (owner's answer) |
| Rules for things the integration doesn't register | `exempt`, with a comment: `action-setup`, `docs-actions`, `docs-conditions`, `docs-triggers` |
| `action-exceptions` | `todo`, pointing at #40 |
| `strict-typing` | `done`, after one type annotation in `repairs.py` (§2) |
| `discovery`, `discovery-update-info` | `exempt`: the integration reaches the charger only through the cloud account (§1) |
| `entity-unavailable` | Stays `done`, with today's comment unchanged (owner's answer). After a failed read the *Charge* switch stays available and shows the last read's state, on purpose: `turn_off` must still reach the charger during an outage. The comment names this deviation and why |
| `todo` rules | Each gets a comment on what is missing |
| Release level | Non-releasing: the title is `chore: …`, with no CHANGELOG entry and no bump. The only code change is a type annotation |
| Decision log | No new entry. These are readings of HA's rules, and no lasting rule of ours changes |

Facts used, public-safe:

- **Rule texts:** most rules say "There are no exceptions to this rule". Core integrations still mark a rule
  `exempt` with a comment when the thing it governs doesn't exist, for example `action-setup` for an
  integration without service actions.
- **hassfest:** its quality-scale check (`script/hassfest/quality_scale.py`, `validate_iqs_file`) returns
  at once for an integration that isn't in core. So `tests/test_quality_scale.py` is this file's only
  check. hassfest's schema needs a comment whenever the status is written as a mapping, and allows a
  comment on `todo` and `done` too.
- **Release rules:** `scripts/release_check.py` goes only by the PR title, never by the paths changed
  (`docs/releasing.md`).

## 1. The statuses

Only the rules that change are listed. Every other rule was checked and keeps its status and comment as
they are today.

| Rule | Today | New | Evidence |
|---|---|---|---|
| `action-setup` | `todo` | `exempt` | `async_setup` registers nothing; the integration has no service actions |
| `docs-actions` | `todo` | `exempt` | Same. The user docs say so under *Actions, conditions and triggers* |
| `docs-conditions` | `todo` | `exempt` | The integration provides no conditions |
| `docs-triggers` | `todo` | `exempt` | The integration provides no triggers |
| `action-exceptions` | `done` | `todo` | The *Charge* switch raises translated `ServiceValidationError` and `HomeAssistantError`. The rule covers platform actions too, and the *Refresh* button's press raises nothing when its read fails (#40) |
| `test-coverage` | `todo` | `done` | Every module is at 98% or more. CI's `tests` workflow fails below 95% |
| `discovery` | `todo` | `exempt` | Cloud only (`iot_class: cloud_polling`): the integration reaches the charger only through the Nortec Go account and never on the local network |
| `discovery-update-info` | `todo` | `exempt` | Same: no discovery, and no network address to keep up to date |
| `entity-disabled-by-default` | `todo` | `done` | Every entity is enabled on purpose (see its comment) |
| `strict-typing` | `todo` | `done` | mypy runs with `strict = true` on the integration and tests, in CI's `lint` workflow. `pynortecgo` ships `py.typed`. `NortecGoConfigEntry` is used throughout once §2 is in |
| `dynamic-devices` | `todo` | `todo`, with a comment | Whether the account has a car is fixed at setup, so a car added later shows up only after a reload |
| `stale-devices` | `todo` | `todo`, with a comment | The car device is removed at setup when the account has no car. A car removed while the integration runs keeps its last data until a reload. `async_remove_config_entry_device` isn't implemented |
| `icon-translations` | `todo` | `todo`, with a comment | There is no `icons.json`. The *Charge* switch, the *Refresh* button and the *Current price*, *Charge status* and *Charge limit* sensors get no icon from a device class and have none of their own |
| `reconfiguration-flow` | `todo` | `todo`, with a comment | The config flow has only `user` and `reauth_confirm` steps |

The comments, word for word. Every comment is a double-quoted YAML string, so a `#` in it isn't read as a YAML
comment:

```yaml
action-setup:
  status: exempt
  comment: "The integration registers no service actions."
docs-actions:
  status: exempt
  comment: "The integration registers no service actions."
docs-conditions:
  status: exempt
  comment: "The integration provides no conditions."
docs-triggers:
  status: exempt
  comment: "The integration provides no triggers."
action-exceptions:
  status: todo
  comment: "The Charge switch raises translated errors; the Refresh button's press raises nothing when its read fails (#40)."
test-coverage:
  status: done
  comment: "CI fails below 95% in total; every module is above it."
discovery:
  status: exempt
  comment: "Cloud only (cloud_polling): the integration reaches the charger only through the Nortec Go account, never on the local network."
discovery-update-info:
  status: exempt
  comment: "No discovery: the integration reaches the charger only through the cloud account and stores no network address."
entity-disabled-by-default:
  status: done
  comment: "Every entity is enabled: Last read and Last seen are the only signs of how old the charger and car data are, and they change only once per read (D29)."
strict-typing:
  status: done
  comment: "mypy runs strict on the integration and its tests in CI; pynortecgo ships py.typed; NortecGoConfigEntry is used throughout."
dynamic-devices:
  status: todo
  comment: "Whether the account has a car is fixed at setup; a car added later shows up only after a reload."
stale-devices:
  status: todo
  comment: "A car removed while running keeps its last data until a reload, which removes its device; no async_remove_config_entry_device."
icon-translations:
  status: todo
  comment: "No icons.json yet; the Charge switch, the Refresh button and the Current price, Charge status and Charge limit sensors have no icon of their own."
reconfiguration-flow:
  status: todo
  comment: "No reconfigure step; the config flow has only the user and reauth steps."
```

The rules keep their order and their tier headings (`# Bronze` … `# Platinum`) in the file.

## 2. The `repairs.py` annotation

`StartBlockedRepairFlow.async_step_confirm` gets the entry with `self.hass.config_entries.async_get_entry`,
which returns an untyped `ConfigEntry`, so `entry.runtime_data` is `Any` there. The `strict-typing` rule
says the custom typed entry "must be used throughout". The fix annotates the local variable:

```python
entry: NortecGoConfigEntry | None = self.hass.config_entries.async_get_entry(
    self._entry_id
)
```

with `from .entry import NortecGoConfigEntry`. Behaviour doesn't change, and the existing repairs tests
cover the lines. mypy must pass with the annotation.

## 3. Tests

In `tests/test_quality_scale.py`:

- A test that pins the new statuses: a table of the 14 rules in §1 and their new status, checked against
  the file. It fails before the change.
- A test that the `action-exceptions` comment ends with `(#40).`, like the existing
  `test_dependency_transparency_comment`. This catches a comment cut short at the `#`.
- `test_quality_scale_statuses` is extended to mirror hassfest's schema: every rule written as a mapping
  has a non-empty `comment`, whatever its status (today it checks this only for `exempt`). So none of the
  `todo` and `done` comments in §1 can be dropped by accident.

The other existing tests (known statuses, 54 rules) stay as they are.

## 4. Files

| File | Change |
|---|---|
| `custom_components/nortec_go/quality_scale.yaml` | §1 |
| `custom_components/nortec_go/repairs.py` | §2 |
| `tests/test_quality_scale.py` | §3 |

No user docs change: the user docs describe no quality-scale status, and they already say the integration
has no actions, conditions or triggers.
