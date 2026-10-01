# Quality scale statuses in line with the code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** Every rule in `custom_components/nortec_go/quality_scale.yaml` has the status the rule text and the code support, and every rule written as a mapping carries a comment.

**Architecture:** One task. It pins the 14 new statuses and the comment rules in `tests/test_quality_scale.py`, edits the 14 rules in `quality_scale.yaml`, and annotates the entry in `repairs.py` with `NortecGoConfigEntry` so `strict-typing` holds.

**Tech Stack:** Python 3.14, Home Assistant 2026.9 custom integration, pytest with `pytest-homeassistant-custom-component`, mypy strict, uv.

**Spec:** `docs/superpowers/specs/2026-09-30-quality-scale-status-design.md` (issue #36).

## Global Constraints

- TDD: write the failing test, see it fail, then change the file.
- No behaviour change. The only code change is the type annotation in `repairs.py`. No CHANGELOG entry, no version bump: the PR title is non-releasing (`chore: …`).
- In `quality_scale.yaml`, every comment is a double-quoted YAML string, word for word as in Task 1 Step 3. The rules keep their order and the tier headings (`# Bronze`, `# Silver`, `# Gold`, `# Platinum`). Only the 14 rules listed change; every other line stays as it is.
- #40 isn't fixed here: `button.py` and `tests/test_button.py` don't change.
- Nothing private (hard rule 3): no IDs, tokens, emails, captures or raw endpoints.
- Gates before every commit (`CLAUDE.md` → Commands): `uv run pytest -q`, then `uv run ruff check && uv run ruff format --check && uv run mypy`. The coverage gate (`uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`) passes at the end of the task.
- Subagents write commit messages with the Write tool to a file outside the repo (for example `/tmp/quality-scale-status-task-1-msg.txt`), and commit with `git commit -F <file>` (no heredocs). End the message with the co-author trailer given in the dispatch.
- Match the surrounding code: one-line docstrings ending in a period.

## Review Focus

- A `#` inside a comment that isn't quoted: YAML cuts the comment short silently. The `(#40).` test pins `action-exceptions`; the reviewer checks every new comment is double-quoted.
- A rule written as a mapping without a comment (hassfest's schema needs one, and hassfest doesn't check custom integrations): the extended `test_quality_scale_statuses` pins it.
- A rule accidentally renamed, dropped or duplicated while editing: `test_rule_count` (54) and the status table pin it.
- The annotation in `repairs.py` changing behaviour: it must be a type annotation only, and `tests/test_repairs.py` stays green unchanged.

---

### Task 1: Statuses, comment checks and the typed repairs entry

**Model:** sonnet — status and test changes, plus a type-only annotation in the start-block repair flow with no runtime change; no auth, entity mapping or docs work.
**Wave:** 1

**Files:**
- Modify: `tests/test_quality_scale.py`
- Modify: `custom_components/nortec_go/quality_scale.yaml`
- Modify: `custom_components/nortec_go/repairs.py`

**Interfaces:**
- Consumes: `NortecGoConfigEntry` from `custom_components/nortec_go/entry.py` (`type NortecGoConfigEntry = ConfigEntry[NortecGoCoordinator]`).
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the failing tests**

In `tests/test_quality_scale.py`, replace `test_quality_scale_statuses` with this version (a comment on every mapping, whatever its status, as hassfest's schema requires):

```python
def test_quality_scale_statuses() -> None:
    """Every rule has a known status, and every rule written as a mapping says why."""
    rules = load_yaml_dict(QUALITY_SCALE)["rules"]
    assert rules
    for name, value in rules.items():
        if isinstance(value, str):
            assert value in STATUSES, name
            assert value != "exempt", f"{name}: exempt needs a comment"
        else:
            assert value["status"] in STATUSES, name
            assert value.get("comment"), name
```

Then add, after `test_dependency_transparency_comment`:

```python
CHECKED_STATUSES = {
    "action-setup": "exempt",
    "docs-actions": "exempt",
    "docs-conditions": "exempt",
    "docs-triggers": "exempt",
    "action-exceptions": "todo",
    "test-coverage": "done",
    "discovery": "exempt",
    "discovery-update-info": "exempt",
    "entity-disabled-by-default": "done",
    "strict-typing": "done",
    "dynamic-devices": "todo",
    "stale-devices": "todo",
    "icon-translations": "todo",
    "reconfiguration-flow": "todo",
}


def _status(value: str | dict[str, str]) -> str:
    """A rule's status, from either form."""
    return value if isinstance(value, str) else value["status"]


def test_checked_statuses() -> None:
    """The statuses checked against the rule texts and the code (issue #36)."""
    rules = load_yaml_dict(QUALITY_SCALE)["rules"]
    for name, status in CHECKED_STATUSES.items():
        assert _status(rules[name]) == status, name
        assert rules[name]["comment"], name


def test_action_exceptions_comment() -> None:
    """The comment isn't cut short by a YAML '#' comment marker."""
    rule = load_yaml_dict(QUALITY_SCALE)["rules"]["action-exceptions"]
    assert rule["comment"].endswith("(#40).")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_quality_scale.py -q`
Expected: `test_checked_statuses` and `test_action_exceptions_comment` FAIL (today `action-setup` is `todo`, and `action-exceptions` is the bare string `done`, so its test fails with `TypeError: string indices must be integers`). `test_quality_scale_statuses` and `test_rule_count` pass.

- [ ] **Step 3: Update `quality_scale.yaml`**

Replace each of these 14 rules in place (each is a one-line `rule: status` today), keeping its position and its tier. The rest of the file doesn't change.

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

(In the file the rules are indented two spaces under `rules:`, and `status`/`comment` four.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_quality_scale.py -q`
Expected: all 5 pass.

- [ ] **Step 5: Annotate the entry in `repairs.py`**

In `custom_components/nortec_go/repairs.py`, add the import after the Home Assistant imports:

```python
from .entry import NortecGoConfigEntry
```

and in `StartBlockedRepairFlow.async_step_confirm` replace

```text
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
```

with

```text
        entry: NortecGoConfigEntry | None = self.hass.config_entries.async_get_entry(
            self._entry_id
        )
```

(let `uv run ruff format` settle the line breaks). Nothing else in the file changes.

- [ ] **Step 6: Run the gates**

Run: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`
Expected: all pass, total at or above 95%.

Run: `uv run ruff check && uv run ruff format --check && uv run mypy`
Expected: no issues. (mypy now types `entry.runtime_data.charge_control` in `repairs.py`.)

- [ ] **Step 7: Commit**

Write the message to `/tmp/quality-scale-status-task-1-msg.txt` with the Write tool:

```text
chore: bring quality_scale.yaml statuses in line with the code (#36)

Exempt the rules for actions, conditions, triggers and discovery; set
test-coverage, entity-disabled-by-default and strict-typing to done;
move action-exceptions back to todo (#40); comment every todo. Type the
repairs flow's entry as NortecGoConfigEntry.

<co-author trailer from the dispatch>
```

```bash
git add tests/test_quality_scale.py custom_components/nortec_go/quality_scale.yaml custom_components/nortec_go/repairs.py
git commit -F /tmp/quality-scale-status-task-1-msg.txt
```
