# A merged PR releases itself, by its title — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** A PR's title decides whether it releases and at which level. A releasing PR carries its own bump, made by `release_check.py release-pr`. `version-check` checks that the title, version and changelog agree, and a merged PR is the only way a release happens.

**Architecture:**
- Task 1 adds the title, version and changelog rules, the widened `pr-check`, and the new `release-pr` to `scripts/release_check.py`, with tests.
- Task 2 changes the workflows and Dependabot:
  - `version-check.yml` passes the title;
  - `auto-release.yml` loses `workflow_dispatch`;
  - `release.yml` loses `push: tags` and its pre-release marking;
  - `dependabot.yml` gets `chore(deps)` titles;
  - `tests/test_workflows.py` pins all of it.
- Task 3 writes the docs, the decision log, the PR template and the agent files, against the code that landed.
- Task 4 runs the pre-merge checks.

**Tech Stack:** Python 3.14 (stdlib only for the script), pytest, PyYAML, GitHub Actions, uv, actionlint, zizmor.

**Spec:** `docs/superpowers/specs/2026-09-29-release-model-design.md` (issues #68, #67).

## Global Constraints

- **Nothing private (hard rule 3):** no IDs, tokens or emails, and no links to the private client repo. Say "the owner's client library repo" if needed. Commit SHAs of this public repo are fine.
- **Gates before every commit** (`CLAUDE.md` → Commands): `uv run pytest -q`, then `uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`. The coverage gate (`--cov-fail-under=95`) passes at the end of each task.
- **Commit messages:** subagents write them with the Write tool to `/tmp/release-model-task-<n>-msg.txt` and commit with `git commit -F <file>`. No heredocs. End each message with the co-author trailer given in the dispatch.
- **Python style:** 3.14, like the rest of the repo. One-line docstrings end in a period. `scripts/release_check.py` stays stdlib only.
- **Title types and levels** (spec §2):

  | Type | Release |
  |---|---|
  | `fix`, `perf` | patch |
  | `feat` | minor |
  | `feat!`, `fix!`, `perf!` | minor while the major version is 0, major from 1.0 |
  | `refactor`, `docs`, `chore`, `ci`, `test`, `process` | none |

- **Title grammar:** `type(scope)!: text`, as the regex `(?P<type>[a-z]+)(?:\((?P<scope>[^()\s]+)\))?(?P<bang>!)?: \S.*` with `fullmatch`.
- **Fixed names in `scripts/release_check.py`:**
  - `RELEASING`, `NON_RELEASING`, `UNRELEASED = "Unreleased"`;
  - `Title(kind, scope, breaking)` with `.releasing`, and `parse_title`;
  - `next_version(base: Version, title: Title) -> str`;
  - `Section`, `Changelog` with `.versions()`, `parse_changelog`, `render_changelog`, `merge_bodies`;
  - `bump_changelog(text, main_versions, version, date)`, `set_manifest_version(manifest, version)`, `pr_problems(title, *, base_manifest, head_manifest, base_changelog, head_changelog)`, `_today()`;
  - the subcommands `pr-check --title=TITLE BASE HEAD` and `release-pr --title=TITLE`;
  - the existing `bump`, `runs-green`, `tag-commit` and their functions stay unchanged.
- **Exit codes:**
  - `pr-check`: 0 clean, 1 with problems (printed on stdout), 2 on an error.
  - `release-pr`: 0 bumped, 1 refused (non-releasing title, or `origin/main` not merged in; on stderr), 2 on an error.
- **Workflows:**
  - actions stay pinned to the SHAs already in the files;
  - no `${{` inside a `run:` block;
  - never `pull_request_target`;
  - top-level `permissions: {}`;
  - the job ids and names `version-check`, `decide`, `release` stay.
- **Decision number:** D40. D39's status becomes `active; the bump PR and the fallbacks superseded by D40`, and D10's becomes `superseded by D40`.
- **What agents may not do:** push tags, dispatch or re-run workflows, or change GitHub settings.

## Review Focus

1. **A breaking title, or one that starts with `-`, through the workflow.** `version-check.yml` passes `--title="$PR_TITLE"` with `=`. Task 2's `test_version_check_passes_the_title_through_env` pins it, and Task 1's `test_cli_pr_check` runs a title starting with `-`.
2. **Rerunning the bump after `main` was merged in.** The branch's own section is gone (the recipe put its entries back under *Unreleased*), and `main`'s section with the same version is kept. Task 1's `test_release_pr_two_releasing_prs` covers it.
3. **The real `manifest.json` formatting.** The bump changes only the `version` value, so the key order, the indentation and `requirements` stay. Task 1's `test_release_pr_bumps` compares the whole file.
4. **The recovery path.** A tag the owner pushed by hand on the releasing commit, then a re-run, must still publish. `auto-release.yml`'s *The tag* step goes on when the tag points at the commit. The reviewer of Task 2 reads that step: only a tag on *another* commit fails it.
5. **Dependabot's new titles.** `chore(deps): bump the uv group with 3 updates` must parse as non-releasing. Task 1's `test_parse_title` has it.

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (`release_check.py`), Task 2 (workflows) | Disjoint files, two worktrees off the feature branch. Task 2 uses only the CLI shape this plan fixes (`pr-check --title=…`), not Task 1's code |
| 2 | Task 3 (docs) | After Tasks 1 and 2 are on the feature branch |
| 3 | Task 4 (pre-merge checks) | After the draft PR exists and the branch is pushed |

Guarded files: Task 3 only. It is alone in wave 2, so it runs in the main checkout (in the PO flow, the team
lead's issue worktree). Before its dispatch the controller writes `.claude/agents/po.md` and
`.claude/agents/team-lead.md` to `$(git -C <that checkout> rev-parse --absolute-git-dir)/subagent-guard-allow`,
and empties it however the task ends.

---

### Task 1: The release rules and the bump step in `scripts/release_check.py`

**Model:** opus — the release rules, near tagging and publishing.
**Wave:** 1

**Files:**
- Modify: `scripts/release_check.py`
- Modify: `tests/test_release_check.py`

**Interfaces:**
- Consumes: the existing `Version`, `parse_version`, `manifest_version`, `ReleaseCheckError`, `MANIFEST`, `CHANGELOG`, `_git_show`, `main`, `_run` in `scripts/release_check.py`.
- Produces (used by Task 2's workflow and Task 3's docs):
  - `python scripts/release_check.py pr-check --title=TITLE BASE HEAD`, which prints each problem on stdout (or `Title, version and changelog agree`) and exits 0/1/2;
  - `python scripts/release_check.py release-pr --title=TITLE`, which prints the new version and exits 0/1/2.

- [ ] **Step 1: Write the failing tests for titles and next versions**

In `tests/test_release_check.py`, change the imports at the top to:

```python
"""Tests for the release rules in scripts/release_check.py."""

import io
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys

import pytest

import release_check
from release_check import (
    REQUIRED_WORKFLOWS,
    UNRELEASED,
    ReleaseCheckError,
    Title,
    Verdict,
    bump_changelog,
    bump_verdict,
    changelog_section,
    has_heading,
    main,
    manifest_version,
    merge_bodies,
    next_version,
    parse_changelog,
    parse_title,
    parse_version,
    pr_problems,
    render_changelog,
    runs_problems,
    set_manifest_version,
    tag_commit,
)

ROOT = Path(__file__).parent.parent
```

Then, after the existing `test_has_heading` test (before `# Bump` / `_verdict`), add:

````python
# Titles


@pytest.mark.parametrize(
    ("title", "kind", "scope", "breaking"),
    [
        ("feat: a thing", "feat", None, False),
        ("fix(price): one retry (#39)", "fix", "price", False),
        ("perf!: faster reads", "perf", None, True),
        ("feat(api)!: a new model", "feat", "api", True),
        ("docs(changelog): fix a typo", "docs", "changelog", False),
        ("process: release model (#68, #67) (#69)", "process", None, False),
        ("chore(deps): bump the uv group with 3 updates", "chore", "deps", False),
        ("refactor: split a module", "refactor", None, False),
        ("ci: pin an action", "ci", None, False),
        ("test: a missing case", "test", None, False),
    ],
)
def test_parse_title(title: str, kind: str, scope: str | None, breaking: bool) -> None:
    """A title parses into its type, scope and breaking mark."""
    assert parse_title(title) == Title(kind, scope, breaking)


@pytest.mark.parametrize(
    "title",
    [
        "Feat: a thing",
        "feat:a thing",
        "feat:  a thing",
        "feat: ",
        "feat",
        "feat(): a thing",
        "feat(a b): a thing",
        "feat!(api): a thing",
        'Revert "feat: a thing"',
        "Bump the uv group with 3 updates",
    ],
)
def test_malformed_title(title: str) -> None:
    """A title that isn't `type(scope)!: text` is refused."""
    with pytest.raises(
        ReleaseCheckError, match=re.escape("isn't 'type(scope)!: text'")
    ):
        parse_title(title)


@pytest.mark.parametrize("title", ["feature: a thing", "build: a thing"])
def test_unknown_title_type(title: str) -> None:
    """A type outside the table is refused."""
    with pytest.raises(ReleaseCheckError, match="isn't one of"):
        parse_title(title)


@pytest.mark.parametrize("title", ["docs!: a thing", "chore(deps)!: a thing"])
def test_breaking_mark_on_a_non_releasing_type(title: str) -> None:
    """`!` is only for feat, fix and perf."""
    with pytest.raises(ReleaseCheckError, match="marks a breaking change"):
        parse_title(title)


@pytest.mark.parametrize(
    ("title", "releasing"),
    [
        ("feat: x", True),
        ("fix: x", True),
        ("perf: x", True),
        ("refactor: x", False),
        ("docs: x", False),
        ("chore: x", False),
        ("ci: x", False),
        ("test: x", False),
        ("process: x", False),
    ],
)
def test_title_releasing(title: str, releasing: bool) -> None:
    """Only feat, fix and perf release."""
    assert parse_title(title).releasing is releasing


# Next version


@pytest.mark.parametrize(
    ("base", "title", "expected"),
    [
        ("0.1.0", "fix: x", "0.1.1"),
        ("0.1.0", "perf: x", "0.1.1"),
        ("0.1.0", "feat: x", "0.2.0"),
        ("0.1.3", "feat!: x", "0.2.0"),
        ("0.1.3", "fix!: x", "0.2.0"),
        ("1.2.3", "feat: x", "1.3.0"),
        ("1.2.3", "fix!: x", "2.0.0"),
        ("1.2.3", "feat!: x", "2.0.0"),
    ],
)
def test_next_version(base: str, title: str, expected: str) -> None:
    """The title's level bumps the base; `!` is minor on 0.x and major from 1.0."""
    assert next_version(parse_version(base), parse_title(title)) == expected


def test_next_version_from_a_pre_release() -> None:
    """A pre-release base is an error."""
    with pytest.raises(ReleaseCheckError, match="pre-release"):
        next_version(parse_version("1.0.0-beta.1"), parse_title("fix: x"))


def test_next_version_for_a_non_releasing_title() -> None:
    """A non-releasing title has no next version."""
    with pytest.raises(ReleaseCheckError, match="doesn't release"):
        next_version(parse_version("0.1.0"), parse_title("docs: x"))
````

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_release_check.py -q`
Expected: collection error, `ImportError: cannot import name 'UNRELEASED'` (and the other new names).

- [ ] **Step 3: Add titles and next versions to the script**

In `scripts/release_check.py`:

Replace the module docstring with:

```python
"""Release rules for the release workflows and the bump step (docs/releasing.md).

Stdlib only. The workflows run it with `uv run --no-project --python 3.14`.
"""
```

Add `from collections.abc import Collection, Sequence` and `from datetime import UTC, datetime` to the imports. Keep the existing isort order, which is `force-sort-within-sections`:

```python
import argparse
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
```

After `REQUIRED_WORKFLOWS`, add:

```python
RELEASING: dict[str, str] = {"feat": "minor", "fix": "patch", "perf": "patch"}
NON_RELEASING: frozenset[str] = frozenset(
    {"refactor", "docs", "chore", "ci", "test", "process"}
)
GROUP_ORDER: tuple[str, ...] = (
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
)
UNRELEASED = "Unreleased"
DOCS = "docs/releasing.md"
```

After the existing `_VERSION` regex, add:

```python
_PLAIN_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
_TITLE = re.compile(r"(?P<type>[a-z]+)(?:\((?P<scope>[^()\s]+)\))?(?P<bang>!)?: \S.*")
_HEADING = re.compile(r"## \[(?P<name>[^\]]+)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?")
_MANIFEST_VERSION = re.compile(r'("version"\s*:\s*")[^"]*(")')
```

After `manifest_version`, add:

```python
@dataclass(frozen=True, slots=True)
class Title:
    """A PR title's type, scope and breaking mark."""

    kind: str
    scope: str | None
    breaking: bool

    @property
    def releasing(self) -> bool:
        """Whether a PR with this title is a release."""
        return self.kind in RELEASING


def parse_title(title: str) -> Title:
    """Parse a PR title, `type(scope)!: text`."""
    match = _TITLE.fullmatch(title)
    if match is None:
        raise ReleaseCheckError(
            f"PR title {title!r} isn't 'type(scope)!: text' (see {DOCS})"
        )
    kind = match["type"]
    if kind not in RELEASING and kind not in NON_RELEASING:
        allowed = ", ".join(sorted([*RELEASING, *NON_RELEASING]))
        raise ReleaseCheckError(
            f"PR title type {kind!r} isn't one of: {allowed} (see {DOCS})"
        )
    breaking = match["bang"] is not None
    if breaking and kind not in RELEASING:
        raise ReleaseCheckError(
            f"'!' marks a breaking change, which is a feat, fix or perf, not a {kind} (see {DOCS})"
        )
    return Title(kind, match["scope"], breaking)


def next_version(base: Version, title: Title) -> str:
    """The version a releasing PR with this title bumps the base to."""
    if not title.releasing:
        raise ReleaseCheckError(f"A {title.kind} PR doesn't release")
    if not base.is_release:
        raise ReleaseCheckError(f"The base version {base.text} is a pre-release")
    level = RELEASING[title.kind]
    if title.breaking:
        level = "minor" if base.major == 0 else "major"
    if level == "major":
        return f"{base.major + 1}.0.0"
    if level == "minor":
        return f"{base.major}.{base.minor + 1}.0"
    return f"{base.major}.{base.minor}.{base.patch + 1}"
```

The imports that aren't used yet make `ruff check` fail for a while: `Collection` and `Sequence` until Step 7, `UTC` and `datetime` until Step 11. Run only pytest until then.

- [ ] **Step 4: Go on to the changelog tests**

The test file imports names that Step 7 adds (`bump_changelog` and the others), so it can't be collected yet.
The first green run is Step 8. Don't add stubs.

- [ ] **Step 5: Write the failing tests for the changelog**

After the next-version tests, add:

````python
# The changelog

MAIN_LOG = (
    "# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-09-29\n\n### Added\n\n- Old.\n"
)
UNRELEASED_LOG = (
    "# Changelog\n\n## [Unreleased]\n\n### Fixed\n\n- A fix.\n\n"
    "## [0.1.0] - 2026-09-29\n\n### Added\n\n- Old.\n"
)
BUMPED_LOG = (
    "# Changelog\n\n## [Unreleased]\n\n## [0.1.1] - 2026-10-01\n\n### Fixed\n\n- A fix.\n\n"
    "## [0.1.0] - 2026-09-29\n\n### Added\n\n- Old.\n"
)


def test_the_real_changelog_round_trips() -> None:
    """Parsing and rendering CHANGELOG.md gives back the same text."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert render_changelog(parse_changelog(text)) == text


def test_parse_changelog() -> None:
    """Sections come in file order, with names, dates and bodies."""
    changelog = parse_changelog(BUMPED_LOG)
    assert changelog.preamble == "# Changelog"
    assert [(s.name, s.date) for s in changelog.sections] == [
        (UNRELEASED, None),
        ("0.1.1", "2026-10-01"),
        ("0.1.0", "2026-09-29"),
    ]
    assert changelog.sections[1].body == "### Fixed\n\n- A fix."
    assert list(changelog.versions()) == ["0.1.1", "0.1.0"]


@pytest.mark.parametrize(
    "heading",
    [
        "## [0.2.0]",
        "## [Unreleased] - 2026-09-29",
        "## [0.2.0] - 29-09-2026",
        "## [1.0.0-beta.1] - 2026-09-29",
        "## Unreleased",
    ],
)
def test_bad_changelog_heading(heading: str) -> None:
    """A heading that isn't [Unreleased] or a dated X.Y.Z is refused."""
    with pytest.raises(ReleaseCheckError, match=re.escape("isn't '## [Unreleased]'")):
        parse_changelog(f"# Changelog\n\n{heading}\n\n- A thing.\n")


def test_duplicate_changelog_section() -> None:
    """A section name that appears twice is refused, naming the recipe."""
    text = BUMPED_LOG.replace("## [0.1.0] - 2026-09-29", "## [0.1.1] - 2026-09-29")
    with pytest.raises(ReleaseCheckError, match="Two releasing PRs at once"):
        parse_changelog(text)


def test_bump_from_unreleased() -> None:
    """The bump moves Unreleased under the new version and leaves Unreleased empty."""
    assert (
        bump_changelog(UNRELEASED_LOG, {"0.1.0"}, "0.1.1", "2026-10-01") == BUMPED_LOG
    )


def test_bump_folds_the_branchs_own_section_back() -> None:
    """The branch's earlier bump is folded back: groups in Keep a Changelog order, its entries first."""
    text = (
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n\n- Newer fix.\n\n### Added\n\n- Newer thing.\n\n"
        "## [0.1.1] - 2026-09-30\n\n### Fixed\n\n- Older fix.\n\n"
        "## [0.1.0] - 2026-09-29\n\n### Added\n\n- Old.\n"
    )
    assert bump_changelog(text, {"0.1.0"}, "0.2.0", "2026-10-01") == (
        "# Changelog\n\n## [Unreleased]\n\n"
        "## [0.2.0] - 2026-10-01\n\n### Added\n\n- Newer thing.\n\n### Fixed\n\n- Older fix.\n- Newer fix.\n\n"
        "## [0.1.0] - 2026-09-29\n\n### Added\n\n- Old.\n"
    )


def test_bump_is_the_same_when_rerun() -> None:
    """Rerunning the bump on its own result changes nothing."""
    assert bump_changelog(BUMPED_LOG, {"0.1.0"}, "0.1.1", "2026-10-01") == BUMPED_LOG


def test_bump_without_entries() -> None:
    """Nothing under Unreleased is an error."""
    with pytest.raises(ReleaseCheckError, match="no entries"):
        bump_changelog(MAIN_LOG, {"0.1.0"}, "0.1.1", "2026-10-01")


def test_merge_bodies() -> None:
    """Free text first, then the groups in Keep a Changelog order, then other groups as first seen."""
    bodies = [
        "Intro.\n\n### Removed\n\n- X.",
        "### Custom\n\n- Y.\n\n### Added\n\n- Z.\n\n### Empty",
    ]
    assert merge_bodies(bodies) == (
        "Intro.\n\n### Added\n\n- Z.\n\n### Removed\n\n- X.\n\n### Custom\n\n- Y."
    )


def test_set_manifest_version() -> None:
    """Only the version value changes."""
    manifest = '{\n  "requirements": ["pynortecgo==0.5.0"],\n  "version": "0.1.0"\n}\n'
    assert set_manifest_version(manifest, "0.1.1") == manifest.replace("0.1.0", "0.1.1")


def test_set_manifest_version_without_version() -> None:
    """A manifest without a version is an error."""
    with pytest.raises(ReleaseCheckError, match="no version"):
        set_manifest_version("{}\n", "0.1.1")


# The PR check


def _problems(
    title: str,
    head_version: str,
    head_log: str,
    base_version: str = "0.1.0",
    base_log: str = MAIN_LOG,
) -> list[str]:
    return pr_problems(
        title,
        base_manifest=_manifest(base_version),
        head_manifest=_manifest(head_version),
        base_changelog=base_log,
        head_changelog=head_log,
    )


def test_pr_check_clean() -> None:
    """A bumped releasing PR, an untouched non-releasing PR and a docs(changelog) fix pass."""
    assert _problems("fix: a fix (#70)", "0.1.1", BUMPED_LOG) == []
    assert _problems("chore: tidy up", "0.1.0", MAIN_LOG) == []
    assert (
        _problems(
            "docs(changelog): fix a typo",
            "0.1.0",
            MAIN_LOG.replace("- Old.", "- Older."),
        )
        == []
    )


NO_UNRELEASED = BUMPED_LOG.replace("## [Unreleased]\n\n", "")
LEFT_OVER = BUMPED_LOG.replace("## [Unreleased]\n\n", "## [Unreleased]\n\n- Left.\n\n")
EMPTY_SECTION = BUMPED_LOG.replace("### Fixed\n\n- A fix.\n\n", "")
EXTRA_SECTION = BUMPED_LOG.replace(
    "## [0.1.0] - 2026-09-29",
    "## [0.0.9] - 2026-09-28\n\n- Odd.\n\n## [0.1.0] - 2026-09-29",
)
RELEASED_REMOVED = (
    "# Changelog\n\n## [Unreleased]\n\n## [0.1.1] - 2026-10-01\n\n- A fix.\n"
)
RELEASED_HEADING = BUMPED_LOG.replace(
    "## [0.1.0] - 2026-09-29", "## [0.1.0] - 2026-09-28"
)
RELEASED_BODY = BUMPED_LOG.replace("- Old.", "- Older.")
BAD_DATE = BUMPED_LOG.replace("2026-10-01", "1-10-2026")
UNRELEASED_ENTRY = MAIN_LOG.replace(
    "## [Unreleased]\n\n", "## [Unreleased]\n\n- New.\n\n"
)
NEW_SECTION = MAIN_LOG.replace(
    "## [0.1.0]", "## [0.1.1] - 2026-10-01\n\n- A fix.\n\n## [0.1.0]"
)


@pytest.mark.parametrize(
    ("title", "head_version", "head_log", "expected"),
    [
        ("feat: x", "0.1.1", BUMPED_LOG, "version is 0.1.1, expected 0.2.0"),
        ("fix: x", "0.1.0", MAIN_LOG, "version is 0.1.0, expected 0.1.1"),
        ("fix: x", "0.1.1", MAIN_LOG, "must be ## [0.1.1] - YYYY-MM-DD"),
        ("fix: x", "0.1.1", NO_UNRELEASED, "the first section must be ## [Unreleased]"),
        ("fix: x", "0.1.1", LEFT_OVER, "[Unreleased] must be empty after the bump"),
        ("fix: x", "0.1.1", EMPTY_SECTION, "[0.1.1] has no entries"),
        ("fix: x", "0.1.1", EXTRA_SECTION, "unexpected new section [0.0.9]"),
        ("fix: x", "0.1.1", RELEASED_REMOVED, "released section [0.1.0] was removed"),
        (
            "fix: x",
            "0.1.1",
            RELEASED_HEADING,
            "heading of the released section [0.1.0] changed",
        ),
        ("fix: x", "0.1.1", RELEASED_BODY, "released section [0.1.0] changed"),
        ("fix: x", "0.1.1", BAD_DATE, "isn't '## [Unreleased]'"),
        ("chore: x", "0.1.1", MAIN_LOG, "a chore PR doesn't change the version"),
        (
            "docs: x",
            "0.1.0",
            UNRELEASED_ENTRY,
            "a docs PR doesn't change the changelog",
        ),
        ("docs(changelog): x", "0.1.0", NEW_SECTION, "unexpected new section [0.1.1]"),
        ("docs(changelog): x", "0.1.0", UNRELEASED_ENTRY, "not [Unreleased]"),
        (
            "docs(changelog): x",
            "0.1.0",
            RELEASED_HEADING.replace(
                "## [0.1.1] - 2026-10-01\n\n### Fixed\n\n- A fix.\n\n", ""
            ),
            "heading of the released section [0.1.0] changed",
        ),
        (
            "docs(changelog): x",
            "0.1.0",
            "# Changelog\n\n## [Unreleased]\n",
            "released section [0.1.0] was removed",
        ),
        (
            "docs(changelog): x",
            "0.1.1",
            MAIN_LOG,
            "a docs PR doesn't change the version",
        ),
        ("Bump the uv group", "0.1.0", MAIN_LOG, "isn't 'type(scope)!: text'"),
    ],
)
def test_pr_check_problems(
    title: str, head_version: str, head_log: str, expected: str
) -> None:
    """Each broken rule is reported."""
    problems = _problems(title, head_version, head_log)
    assert any(expected in problem for problem in problems), problems


def test_pr_check_stale_bump() -> None:
    """After main released 0.1.1 and was merged in, a bump still at 0.1.1 is stale."""
    problems = _problems(
        "fix: x", "0.1.1", BUMPED_LOG, base_version="0.1.1", base_log=BUMPED_LOG
    )
    assert any("version is 0.1.1, expected 0.1.2" in problem for problem in problems)


def test_pr_check_pre_release_base() -> None:
    """A releasing PR on a pre-release base is a problem."""
    problems = _problems("fix: x", "1.0.0", BUMPED_LOG, base_version="1.0.0-beta.1")
    assert any("pre-release" in problem for problem in problems)
````

`_manifest` is the existing helper in the file (`json.dumps({"domain": "nortec_go", "version": version})`). `MAIN_LOG` and the other constants sit next to the existing `HEADER`, `OLD` and `NEW`. Keep both sets; they don't clash.

- [ ] **Step 6: Run them to see them fail**

Run: `uv run pytest tests/test_release_check.py -q`
Expected: collection error on the missing names (`bump_changelog`, `merge_bodies`, `parse_changelog`, `pr_problems`, `render_changelog`, `set_manifest_version`, `UNRELEASED` is there now).

- [ ] **Step 7: Add the changelog, the manifest version and the PR check to the script**

After `next_version`, add:

```python
@dataclass(frozen=True, slots=True)
class Section:
    """One `## [...]` section of the changelog; the body has no surrounding blank lines."""

    name: str
    date: str | None
    heading: str
    body: str


@dataclass(frozen=True, slots=True)
class Changelog:
    """The text before the first section, and the sections in file order."""

    preamble: str
    sections: tuple[Section, ...]

    def versions(self) -> dict[str, Section]:
        """The version sections by name, in file order."""
        return {s.name: s for s in self.sections if s.name != UNRELEASED}


def _section(heading: str, body: list[str]) -> Section:
    match = _HEADING.fullmatch(heading)
    if match is None or not (
        (match["name"] == UNRELEASED and match["date"] is None)
        or (_PLAIN_VERSION.fullmatch(match["name"]) and match["date"] is not None)
    ):
        raise ReleaseCheckError(
            f"CHANGELOG.md heading {heading!r} isn't '## [Unreleased]' or '## [X.Y.Z] - YYYY-MM-DD'"
        )
    return Section(match["name"], match["date"], heading, "\n".join(body).strip("\n"))


def parse_changelog(text: str) -> Changelog:
    """Split a changelog into its preamble and `## ` sections."""
    preamble: list[str] = []
    sections: list[Section] = []
    heading: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections.append(_section(heading, body))
            heading, body = line, []
        elif heading is None:
            preamble.append(line)
        else:
            body.append(line)
    if heading is not None:
        sections.append(_section(heading, body))
    seen: set[str] = set()
    for section in sections:
        if section.name in seen:
            raise ReleaseCheckError(
                f"CHANGELOG.md has [{section.name}] twice (see {DOCS}, Two releasing PRs at once)"
            )
        seen.add(section.name)
    return Changelog("\n".join(preamble).strip("\n"), tuple(sections))


def render_changelog(changelog: Changelog) -> str:
    """The changelog text: blocks separated by one blank line, ending in a newline."""
    parts = [changelog.preamble]
    parts += [
        f"{s.heading}\n\n{s.body}" if s.body else s.heading for s in changelog.sections
    ]
    return "\n\n".join(parts) + "\n"


def _split_body(body: str) -> tuple[str, list[tuple[str, str]]]:
    free: list[str] = []
    groups: list[tuple[str, list[str]]] = []
    for line in body.splitlines():
        if line.startswith("### "):
            groups.append((line[4:].strip(), []))
        elif groups:
            groups[-1][1].append(line)
        else:
            free.append(line)
    return "\n".join(free).strip("\n"), [
        (name, "\n".join(lines).strip("\n")) for name, lines in groups
    ]


def merge_bodies(bodies: Sequence[str]) -> str:
    """Merge section bodies into one.

    Free text comes first, then the `###` groups in Keep a Changelog order, then any other group in
    the order first seen. Within each, earlier bodies come first. Empty groups are dropped.
    """
    free: list[str] = []
    groups: dict[str, list[str]] = {}
    for body in bodies:
        text, subsections = _split_body(body)
        if text:
            free.append(text)
        for name, entries in subsections:
            chunks = groups.setdefault(name, [])
            if entries:
                chunks.append(entries)
    order = [name for name in GROUP_ORDER if name in groups]
    order += [name for name in groups if name not in GROUP_ORDER]
    parts = ["\n\n".join(free)] if free else []
    parts += [
        f"### {name}\n\n" + "\n".join(groups[name]) for name in order if groups[name]
    ]
    return "\n\n".join(parts)


def bump_changelog(
    text: str, main_versions: Collection[str], version: str, date: str
) -> str:
    """Fold the branch's own version sections back, then move Unreleased under the version.

    The branch's own sections are those whose name isn't in main's changelog; they come first,
    oldest (lowest in the file) first, then Unreleased.
    """
    changelog = parse_changelog(text)
    own = [
        s
        for s in changelog.sections
        if s.name != UNRELEASED and s.name not in main_versions
    ]
    unreleased = [s for s in changelog.sections if s.name == UNRELEASED]
    body = merge_bodies([s.body for s in [*reversed(own), *unreleased]])
    if not body.strip():
        raise ReleaseCheckError(
            "CHANGELOG.md has no entries under [Unreleased] to release"
        )
    kept = [s for s in changelog.sections if s.name in main_versions]
    sections = (
        Section(UNRELEASED, None, f"## [{UNRELEASED}]", ""),
        Section(version, date, f"## [{version}] - {date}", body),
        *kept,
    )
    return render_changelog(Changelog(changelog.preamble, sections))


def set_manifest_version(manifest: str, version: str) -> str:
    """The manifest.json text with only the version value changed."""
    updated, count = _MANIFEST_VERSION.subn(rf"\g<1>{version}\g<2>", manifest, count=1)
    if count != 1:
        raise ReleaseCheckError("manifest.json has no version to set")
    return updated


def _unreleased(changelog: Changelog) -> str | None:
    return next((s.body for s in changelog.sections if s.name == UNRELEASED), None)


def _released_problems(
    base: Changelog, head: Changelog, *, fixing_old: bool
) -> list[str]:
    problems: list[str] = []
    head_sections = head.versions()
    for name, section in base.versions().items():
        now = head_sections.get(name)
        if now is None:
            problems.append(f"CHANGELOG.md: the released section [{name}] was removed")
        elif now.heading != section.heading:
            problems.append(
                f"CHANGELOG.md: the heading of the released section [{name}] changed"
            )
        elif now.body != section.body and not fixing_old:
            problems.append(
                f"CHANGELOG.md: the released section [{name}] changed "
                "(only a 'docs(changelog): …' PR may fix old entries)"
            )
    return problems


def _releasing_problems(
    head: Changelog, version: str, expected: str, added: list[str]
) -> list[str]:
    problems: list[str] = []
    if version != expected:
        problems.append(
            f"manifest.json: version is {version}, expected {expected} "
            f"(run the bump step, see {DOCS})"
        )
    first = head.sections[0] if head.sections else None
    second = head.sections[1] if len(head.sections) > 1 else None
    if first is None or first.name != UNRELEASED:
        problems.append("CHANGELOG.md: the first section must be ## [Unreleased]")
    elif first.body.strip():
        problems.append("CHANGELOG.md: [Unreleased] must be empty after the bump")
    if second is None or second.name != expected:
        problems.append(
            f"CHANGELOG.md: the section under [Unreleased] must be ## [{expected}] - YYYY-MM-DD"
        )
    elif not second.body.strip():
        problems.append(f"CHANGELOG.md: [{expected}] has no entries")
    problems += [
        f"CHANGELOG.md: unexpected new section [{name}]"
        for name in added
        if name != expected
    ]
    return problems


def pr_problems(
    title: str,
    *,
    base_manifest: str,
    head_manifest: str,
    base_changelog: str,
    head_changelog: str,
) -> list[str]:
    """What breaks the release rules for a PR against its merge base; [] when nothing does."""
    try:
        parsed = parse_title(title)
        base_version = manifest_version(base_manifest)
        head_version = manifest_version(head_manifest)
        base = parse_changelog(base_changelog)
        head = parse_changelog(head_changelog)
        expected = next_version(base_version, parsed) if parsed.releasing else None
    except ReleaseCheckError as err:
        return [str(err)]
    fixing_old = parsed.kind == "docs" and parsed.scope == "changelog"
    problems = _released_problems(base, head, fixing_old=fixing_old)
    added = [name for name in head.versions() if name not in base.versions()]
    if expected is not None:
        return problems + _releasing_problems(head, head_version.text, expected, added)
    if head_version.text != base_version.text:
        problems.append(
            f"manifest.json: a {parsed.kind} PR doesn't change the version (see {DOCS})"
        )
    if fixing_old:
        problems += [f"CHANGELOG.md: unexpected new section [{name}]" for name in added]
        if _unreleased(head) != _unreleased(base):
            problems.append(
                "CHANGELOG.md: a docs(changelog) PR may fix released sections only, not [Unreleased]"
            )
    elif head_changelog != base_changelog:
        problems.append(
            f"CHANGELOG.md: a {parsed.kind} PR doesn't change the changelog "
            f"(a user-visible change is a feat, fix or perf PR, see {DOCS})"
        )
    return problems
```

`ruff format` may rewrap some of these lines; let it.

- [ ] **Step 8: Run the tests**

Run: `uv run pytest tests/test_release_check.py -q`
Expected: all pass, including the existing `test_cli_pr_check`, which still uses the old `pr-check BASE HEAD`. Steps 9 to 11 replace it and the subcommand.

- [ ] **Step 9: Write the failing CLI tests**

Replace the existing `test_cli_pr_check` with:

```python
def test_cli_pr_check(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """pr-check exits 0 when the title, version and changelog agree, 1 with the problems, 2 on an error."""
    base = _commit(repo, "0.1.0", MAIN_LOG)
    bumped = _commit(repo, "0.1.1", BUMPED_LOG)
    assert main(["pr-check", "--title=fix: a fix", base, bumped]) == 0
    assert "Title, version and changelog agree" in capsys.readouterr().out
    assert main(["pr-check", "--title=feat: a thing", base, bumped]) == 1
    assert "expected 0.2.0" in capsys.readouterr().out
    assert (
        main(
            ["pr-check", "--title=-x: a title that looks like an option", base, bumped]
        )
        == 1
    )
    assert "isn't 'type(scope)!: text'" in capsys.readouterr().out
    assert main(["pr-check", "--title=fix: a fix", "no-such-commit", bumped]) == 2
```

After `test_cli_tag_commit` (before `test_tag_commit_skips_other_lines`), add the `release-pr` tests:

```python
# release-pr, with an origin

REAL_MANIFEST = (
    '{\n  "domain": "nortec_go",\n  "requirements": ["pynortecgo==0.5.0"],\n'
    '  "version": "0.1.0"\n}\n'
)
MANIFEST_PATH = Path("custom_components") / "nortec_go" / "manifest.json"


def _write(repo: Path, manifest: str, changelog: str) -> None:
    (repo / MANIFEST_PATH).parent.mkdir(parents=True, exist_ok=True)
    (repo / MANIFEST_PATH).write_text(manifest, encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(changelog, encoding="utf-8")


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-q",
        "-m",
        message,
    )


def _read(repo: Path) -> tuple[str, str]:
    return (
        (repo / MANIFEST_PATH).read_text(encoding="utf-8"),
        (repo / "CHANGELOG.md").read_text(encoding="utf-8"),
    )


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A clone of an origin whose main is at 0.1.0, on a branch with a fix under Unreleased."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _write(origin, REAL_MANIFEST, MAIN_LOG)
    _commit_all(origin, "0.1.0")
    clone = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    _git(clone, "switch", "-q", "-c", "fix/topic")
    _write(clone, REAL_MANIFEST, UNRELEASED_LOG)
    _commit_all(clone, "fix: a fix")
    monkeypatch.chdir(clone)
    monkeypatch.setattr(release_check, "_today", lambda: "2026-10-01")
    return clone


def test_release_pr_bumps(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The bump writes the next version (only that value) and the moved changelog, and commits nothing."""
    assert main(["release-pr", "--title=fix: a fix"]) == 0
    assert capsys.readouterr().out == "0.1.1\n"
    assert _read(work) == (REAL_MANIFEST.replace('"0.1.0"', '"0.1.1"'), BUMPED_LOG)
    assert _git(work, "diff", "--name-only").splitlines() == [
        "CHANGELOG.md",
        "custom_components/nortec_go/manifest.json",
    ]
    assert _git(work, "log", "-1", "--format=%s") == "fix: a fix"


def test_release_pr_rerun_and_retitle(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A rerun changes nothing; a rerun after a retitle to feat bumps from main again."""
    assert main(["release-pr", "--title=fix: a fix"]) == 0
    _commit_all(work, "chore: release 0.1.1")
    assert main(["release-pr", "--title=fix: a fix"]) == 0
    assert _read(work)[1] == BUMPED_LOG
    assert main(["release-pr", "--title=feat: a thing"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "0.2.0"
    assert _read(work) == (
        REAL_MANIFEST.replace('"0.1.0"', '"0.2.0"'),
        BUMPED_LOG.replace("## [0.1.1] - 2026-10-01", "## [0.2.0] - 2026-10-01"),
    )


def test_release_pr_non_releasing_title(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-releasing title has nothing to bump: exit 1, files untouched."""
    before = _read(work)
    assert main(["release-pr", "--title=chore: tidy up"]) == 1
    assert "nothing to bump" in capsys.readouterr().err
    assert _read(work) == before


def test_release_pr_malformed_title(work: Path) -> None:
    """A malformed title is an error."""
    assert main(["release-pr", "--title=Bump the uv group"]) == 2


def test_release_pr_refuses_without_main_merged_in(
    work: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When main has moved on and isn't merged in, the bump refuses: exit 1, files untouched."""
    origin = tmp_path / "origin"
    _write(origin, REAL_MANIFEST.replace('"0.1.0"', '"0.1.1"'), BUMPED_LOG)
    _commit_all(origin, "fix: main's fix")
    before = _read(work)
    assert main(["release-pr", "--title=fix: a fix"]) == 1
    assert "merge origin/main into this branch first" in capsys.readouterr().err
    assert _read(work) == before


def test_release_pr_two_releasing_prs(
    work: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The recipe: merge main, take main's files with this branch's entries under Unreleased, rerun."""
    assert main(["release-pr", "--title=fix: a fix"]) == 0
    _commit_all(work, "chore: release 0.1.1")
    origin = tmp_path / "origin"
    main_log = BUMPED_LOG.replace("- A fix.", "- Main's fix.")
    _write(origin, REAL_MANIFEST.replace('"0.1.0"', '"0.1.1"'), main_log)
    _commit_all(origin, "fix: main's fix")
    _git(work, "fetch", "-q", "origin")
    # The two changelogs conflict (spec, Facts), so check=False; the recipe below resolves it.
    merge = subprocess.run(
        [
            "git",
            "-C",
            str(work),
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "merge",
            "-q",
            "--no-edit",
            "origin/main",
        ],
        check=False,
        capture_output=True,
    )
    assert merge.returncode != 0
    assert (work / ".git" / "MERGE_HEAD").exists()
    recipe_log = main_log.replace(
        "## [Unreleased]\n\n", "## [Unreleased]\n\n### Fixed\n\n- A fix.\n\n"
    )
    _write(work, REAL_MANIFEST.replace('"0.1.0"', '"0.1.1"'), recipe_log)
    _commit_all(work, "Merge origin/main")
    capsys.readouterr()
    assert main(["release-pr", "--title=fix: a fix"]) == 0
    assert capsys.readouterr().out == "0.1.2\n"
    assert _read(work) == (
        REAL_MANIFEST.replace('"0.1.0"', '"0.1.2"'),
        "# Changelog\n\n## [Unreleased]\n\n## [0.1.2] - 2026-10-01\n\n### Fixed\n\n- A fix.\n\n"
        "## [0.1.1] - 2026-10-01\n\n### Fixed\n\n- Main's fix.\n\n"
        "## [0.1.0] - 2026-09-29\n\n### Added\n\n- Old.\n",
    )


def test_release_pr_without_origin(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without an origin the fetch fails: exit 2."""
    _commit(repo, "0.1.0", UNRELEASED_LOG)
    assert main(["release-pr", "--title=fix: a fix"]) == 2
    assert "git fetch origin main failed" in capsys.readouterr().err
```

Note: the `work` fixture's commits use `_git`, which runs with `core.hooksPath=/dev/null`, so the repo's pre-commit hooks never run in the temporary repositories.

- [ ] **Step 10: Run them to see them fail**

Run: `uv run pytest tests/test_release_check.py -q -k "cli_pr_check or release_pr"`
Expected: FAIL. argparse exits 2 on `--title` for `pr-check`, and on the unknown subcommand `release-pr`.

- [ ] **Step 11: Wire the subcommands**

In `scripts/release_check.py`, before `_verdict`, add:

```python
def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], check=False, capture_output=True, text=True)


def _release_pr(title_text: str) -> int:
    title = parse_title(title_text)
    if not title.releasing:
        print(
            f"A {title.kind} PR doesn't release: nothing to bump (see {DOCS})",
            file=sys.stderr,
        )
        return 1
    fetch = _git("fetch", "-q", "origin", "main")
    if fetch.returncode != 0:
        raise ReleaseCheckError(f"git fetch origin main failed: {fetch.stderr.strip()}")
    if _git("merge-base", "--is-ancestor", "origin/main", "HEAD").returncode != 0:
        print(
            "origin/main isn't in this branch: merge origin/main into this branch first "
            f"(see {DOCS}, Two releasing PRs at once)",
            file=sys.stderr,
        )
        return 1
    version = next_version(manifest_version(_git_show("origin/main", MANIFEST)), title)
    main_versions = parse_changelog(_git_show("origin/main", CHANGELOG)).versions()
    root = Path(_git("rev-parse", "--show-toplevel").stdout.strip())
    changelog_path, manifest_path = root / CHANGELOG, root / MANIFEST
    changelog = bump_changelog(
        changelog_path.read_text(encoding="utf-8"), main_versions, version, _today()
    )
    manifest = set_manifest_version(manifest_path.read_text(encoding="utf-8"), version)
    manifest_path.write_text(manifest, encoding="utf-8")
    changelog_path.write_text(changelog, encoding="utf-8")
    print(version)
    return 0
```

In `_run`, replace the `pr-check` branch with:

```text
    if args.command == "pr-check":
        problems = pr_problems(
            args.title,
            base_manifest=_git_show(args.base, MANIFEST),
            head_manifest=_git_show(args.head, MANIFEST),
            base_changelog=_git_show(args.base, CHANGELOG),
            head_changelog=_git_show(args.head, CHANGELOG),
        )
        for problem in problems:
            print(problem)
        if not problems:
            print("Title, version and changelog agree")
        return 1 if problems else 0
    if args.command == "release-pr":
        return _release_pr(args.title)
```

In `main`, replace the `pr-check` parser lines with:

```text
    pr_check = commands.add_parser(
        "pr-check", help="Do the PR's title, version and changelog agree?"
    )
    pr_check.add_argument("--title", required=True)
    pr_check.add_argument("base")
    pr_check.add_argument("head")
    commands.add_parser(
        "release-pr", help="The bump step: bump the version and move Unreleased."
    ).add_argument("--title", required=True)
```

- [ ] **Step 12: Run the whole file, then the gates**

Run: `uv run pytest tests/test_release_check.py -q`
Expected: all pass.
Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`
Expected: all pass. If `ruff format --check` fails, run `uv run ruff format scripts tests` and check the diff.
Run: `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95 -q`
Expected: pass.

- [ ] **Step 13: Commit**

Write `/tmp/release-model-task-1-msg.txt` with the Write tool:

```text
feat(release): title rules, pr-check with the title, and release-pr (#68)

<co-author trailer from the dispatch>
```

Then run `git add scripts/release_check.py tests/test_release_check.py && git commit -F /tmp/release-model-task-1-msg.txt`.

---

### Task 2: The workflows and Dependabot

**Model:** opus — `.github/workflows/`, tagging and publishing.
**Wave:** 1

**Files:**
- Modify: `.github/workflows/version-check.yml`
- Modify: `.github/workflows/auto-release.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `.github/dependabot.yml`
- Modify: `tests/test_workflows.py`

**Interfaces:**
- Consumes: the CLI shape `scripts/release_check.py pr-check --title=TITLE BASE HEAD` (Task 1; not needed to run this task's tests).
- Produces: workflows that Task 3's docs describe. `auto-release` is triggered only by `workflow_run`. `release` is only `workflow_call` with the inputs `tag` and `sha`. `version-check` passes `PR_TITLE`.

- [ ] **Step 1: Write the failing workflow tests**

In `tests/test_workflows.py`:

Replace `test_auto_release_triggers_and_permissions` with:

```python
def test_auto_release_triggers_and_permissions() -> None:
    """auto-release runs only after CI on main, never by hand or for a PR, and only the release job can write."""
    workflow = _load("auto-release.yml")
    on = _on(workflow)
    assert set(on) == {"workflow_run"}
    assert on["workflow_run"]["branches"] == ["main"]
    assert workflow["permissions"] == {}
    writers = [
        name
        for name, job in workflow["jobs"].items()
        if job.get("permissions", {}).get("contents") == "write"
    ]
    assert writers == ["release"]
    assert workflow["jobs"]["release"]["uses"] == "./.github/workflows/release.yml"


def test_auto_release_guard() -> None:
    """The decide job goes on only for a successful push run on main from this repository."""
    guard = _load("auto-release.yml")["jobs"]["decide"]["if"]
    for condition in (
        "github.event.workflow_run.conclusion == 'success'",
        "github.event.workflow_run.event == 'push'",
        "github.event.workflow_run.head_branch == 'main'",
        "github.event.workflow_run.head_repository.full_name == github.repository",
    ):
        assert condition in guard
    assert "workflow_dispatch" not in guard


def test_no_dry_run_or_dispatch_left() -> None:
    """No release workflow has a dry run or a sha input any more."""
    for name in ("auto-release.yml", "release.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "dry_run" not in text
        assert "workflow_dispatch" not in text
        assert "inputs.sha ||" not in text
```

Replace `test_release_triggers_and_permissions` and `test_release_takes_the_tag_from_inputs` with:

```python
def test_release_triggers_and_permissions() -> None:
    """Release runs only when auto-release calls it, with a tag and a commit."""
    workflow = _load("release.yml")
    on = _on(workflow)
    assert set(on) == {"workflow_call"}
    assert set(on["workflow_call"]["inputs"]) == {"tag", "sha"}
    assert workflow["permissions"] == {}
    assert workflow["jobs"]["release"]["permissions"] == {"contents": "write"}


def test_release_takes_the_tag_from_inputs() -> None:
    """The tag and the commit come from the inputs only; every release is a full one."""
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert "ref: ${{ inputs.sha }}" in text
    assert "inputs.tag" in text
    assert "github.ref" not in text
    assert "--prerelease" not in text
```

Replace `test_version_check` with:

```python
def test_version_check() -> None:
    """version-check runs on pull_request only, with one job named version-check, against the merge base."""
    workflow = _load("version-check.yml")
    on = _on(workflow)
    assert set(on) == {"pull_request"}
    assert "edited" in on["pull_request"]["types"]
    assert workflow["permissions"] == {}
    assert list(workflow["jobs"]) == ["version-check"]
    assert "git merge-base" in (WORKFLOWS / "version-check.yml").read_text(
        encoding="utf-8"
    )


def test_version_check_passes_the_title_through_env() -> None:
    """The PR title reaches the script through env and --title=, never inside run."""
    steps = _load("version-check.yml")["jobs"]["version-check"]["steps"]
    [step] = [s for s in steps if "release_check.py" in s.get("run", "")]
    assert step["env"]["PR_TITLE"] == "${{ github.event.pull_request.title }}"
    assert '--title="$PR_TITLE"' in step["run"]
    assert "pull_request.title" not in step["run"]


def test_dependabot_titles_are_chore() -> None:
    """Dependabot's PR titles are chore(deps): … or chore(deps-dev): …, a non-releasing type."""
    config = yaml.safe_load(
        (WORKFLOWS.parent / "dependabot.yml").read_text(encoding="utf-8")
    )
    for update in config["updates"]:
        assert update["commit-message"] == {"prefix": "chore", "include": "scope"}
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/test_workflows.py -q`
Expected: FAIL in the tests just written (`workflow_dispatch` is still in `on`, `push` in release, no `PR_TITLE`, no `commit-message`).

- [ ] **Step 3: Change `version-check.yml`**

Replace the last step (from `- name: A version change must be a bump` to the end of the file) with:

```yaml
      - name: Title, version and changelog agree
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
          PR_TITLE: ${{ github.event.pull_request.title }}
        run: |
          # Against the merge base: what this PR changes, even if main has a newer release.
          # --title= so a title that starts with - isn't read as an option (docs/releasing.md).
          base="$(git merge-base "$BASE_SHA" "$HEAD_SHA")"
          uv run --no-project --python 3.14 python scripts/release_check.py pr-check --title="$PR_TITLE" "$base" "$HEAD_SHA"
```

- [ ] **Step 4: Change `auto-release.yml`**

Make these changes and leave everything else as it is.
1. In `on:`, delete the whole `workflow_dispatch:` block (from `workflow_dispatch:` through `default: true`).
2. Set the concurrency group to:

```yaml
concurrency:
  group: auto-release-${{ github.event.workflow_run.event }}-${{ github.event.workflow_run.head_sha }}
  cancel-in-progress: false
```

3. Set the `decide` job's `if:` to:

```yaml
    if: >-
      github.event.workflow_run.conclusion == 'success' &&
      github.event.workflow_run.event == 'push' &&
      github.event.workflow_run.head_branch == 'main' &&
      github.event.workflow_run.head_repository.full_name == github.repository
```

4. Replace *The commit* step with:

```yaml
      - name: The commit
        id: commit
        env:
          RUN_SHA: ${{ github.event.workflow_run.head_sha }}
        run: |
          sha="$(git rev-parse --verify --quiet "${RUN_SHA}^{commit}")" || { echo "Not a commit: ${RUN_SHA}"; exit 1; }
          git merge-base --is-ancestor "$sha" origin/main || { echo "${sha} is not on main"; exit 1; }
          echo "sha=${sha}" >> "$GITHUB_OUTPUT"
```

5. In *The tag* step, remove `DRY_RUN: ${{ inputs.dry_run }}` from `env:` and the `if [ "$DRY_RUN" = true ]; then … fi` block. The step's `run:` becomes:

```yaml
        run: |
          # The repo is public, so ls-remote works without credentials (persist-credentials: false).
          # A tag already on this commit is fine: the owner's recovery for the workflow-scope limit
          # (docs/releasing.md, When a release fails) pushes it by hand and re-runs this run.
          tagged="$(git ls-remote origin "refs/tags/${TAG}" "refs/tags/${TAG}^{}" \
            | uv run --no-project --python 3.14 python scripts/release_check.py tag-commit "$TAG")"
          if [ -n "$tagged" ] && [ "$tagged" != "$SHA" ]; then
            echo "Tag ${TAG} points at ${tagged}, not ${SHA}"
            exit 1
          fi
          echo "release=true" >> "$GITHUB_OUTPUT"
```

- [ ] **Step 5: Change `release.yml`**

1. Delete `push:` and `tags: ["v*"]` from `on:`, so `on:` holds only `workflow_call:` with its two inputs.
2. In the checkout, set `ref: ${{ inputs.sha }}`.
3. Replace *The tag and the commit* step with:

```yaml
      - name: The tag and the commit
        env:
          INPUT_TAG: ${{ inputs.tag }}
        run: |
          # The tag is an input: a called workflow sees the caller's github context.
          echo "TAG=${INPUT_TAG}" >> "$GITHUB_ENV"
          echo "COMMIT=$(git rev-parse HEAD)" >> "$GITHUB_ENV"
```

4. In *Create the GitHub release*, replace the `run:` with:

```yaml
        run: |
          gh release create "$TAG" --target "$COMMIT" --title "$TAG" --notes-file notes.md
```

- [ ] **Step 6: Change `.github/dependabot.yml`**

Add to each of the two entries (`github-actions` and `uv`), after `directory: /`:

```yaml
    commit-message:
      prefix: chore
      include: scope
```

- [ ] **Step 7: Run the tests and the gates**

Run: `uv run pytest tests/test_workflows.py -q`
Expected: all pass.
Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`
Expected: all pass. If `zizmor` flags something new, fix it in the workflow. Don't add an ignore without a comment saying why.

- [ ] **Step 8: Commit**

Write `/tmp/release-model-task-2-msg.txt` with the Write tool:

```text
ci: release only through merged PRs; version-check reads the title; chore(deps) titles (#68, #67)

<co-author trailer from the dispatch>
```

Then run `git add .github tests/test_workflows.py && git commit -F /tmp/release-model-task-2-msg.txt`.

---

### Task 3: Docs, decision log, PR template and agents

**Model:** opus — a docs task (D33), and the agents' rules.
**Wave:** 2
**Guarded files:** `.claude/agents/po.md`, `.claude/agents/team-lead.md`

**Files:**
- Modify: `docs/releasing.md` (rewrite)
- Modify: `docs/way-of-working.md`
- Modify: `docs/decisions.md`
- Modify: `docs/README.md`
- Modify: `docs/notes.md`
- Modify: `CLAUDE.md`
- Modify: `.github/pull_request_template.md`
- Modify: `.claude/agents/po.md`, `.claude/agents/team-lead.md`

**Interfaces:**
- Consumes: Task 1's CLI (`release-pr --title=…`, `pr-check --title=…`) and Task 2's workflows. Check every name against the files on the branch.
- Produces: nothing code uses.

- [ ] **Step 1: Rewrite `docs/releasing.md`**

Replace the whole file with the text below. Keep the two sections marked "unchanged" as they are in the current file, apart from the one added paragraph each:

````markdown
# Releasing

## Versioning

This project uses [Semantic Versioning](https://semver.org/). Every release is a full release of an
`X.Y.Z` version; there are no pre-releases. While the major version is 0, a minor release may break
something; its changelog entries say so.

A merged PR is the only way a release happens (D40). Its title decides whether it releases and at which
level, a releasing PR carries its own version bump, and merging it publishes the release. Neither release
workflow can be started by hand, and a pushed tag publishes nothing on its own.

## PR titles

Every PR title is `type(scope)!: text`. The `version-check` check reads it on every PR that isn't a draft.
- `type` is lowercase, and one of the types in the table.
- `(scope)` is optional: one or more characters other than brackets and whitespace.
- `!` is optional, comes right before the colon, and marks a breaking change.
- Then a colon, one space, and the text. The text may hold `(#n)` references.

| Type | Release |
|---|---|
| `fix`, `perf` | patch |
| `feat` | minor |
| `feat!`, `fix!`, `perf!` (breaking) | minor while the major version is 0, major from 1.0 |
| `refactor`, `docs`, `chore`, `ci`, `test`, `process` | none |

- `!` on a non-releasing type is invalid: a breaking change is a `feat`, `fix` or `perf`.
- A user-visible change is a `feat`, `fix` or `perf`, with a `CHANGELOG.md` entry. A change that isn't
  user-visible has a non-releasing type.
- GitHub's *Revert* button titles a PR `Revert "…"`. Retitle it, for example `fix: revert …`.
- Only `!` marks a breaking change; a `BREAKING CHANGE:` footer isn't read.
- Dependabot's titles are `chore(deps): …`, or `chore(deps-dev): …` for development dependencies. For one
  that users should get, retitle it `feat` or `fix` and
  run the bump step on its branch. Dependabot then stops rebasing it, which is fine for a PR about to merge.
- The title's type is separate from the branch's type (`way-of-working.md` §1 step 2).

## A releasing PR

1. Write the changelog entries under `## [Unreleased]`, as for any user-visible change.
2. **The bump step** comes last, just before the PR is marked ready. In the PO flow it comes before the team
   lead's `branch ready`.

   ```bash
   uv run python scripts/release_check.py release-pr --title="$(gh pr view --json title -q .title)"
   ```

   Before the PR exists (a trivial or D25 PR, opened ready), give the title in single quotes instead, for
   example `--title='fix: …'`. In double quotes, an interactive shell breaks on the `!` of a breaking title.

   The command fetches `origin/main` and sets `version` in `manifest.json` to the next version after
   `main`'s. Then it moves *Unreleased* under `## [X.Y.Z] - <today, UTC>` and prints the version. It commits
   nothing: commit `chore: release X.Y.Z` and push. It refuses a non-releasing title, and a branch that
   `origin/main` isn't merged into.
3. After the bump:
   - **A changelog change:** put it under *Unreleased* and rerun the bump step. It first folds the branch's
     earlier bump back.
   - **A retitle to another releasing type:** rerun the bump step.
   - **A retitle to a non-releasing type:** if `main` has moved, merge `origin/main` in first. Then set
     `version` in `manifest.json` back to `origin/main`'s, changing only that value (a `pynortecgo` bump also
     changes the file). Set `CHANGELOG.md` back to `origin/main`'s too, and commit.

`version-check` compares the PR with its merge base. A releasing PR must have:
- a `version` that is exactly the next one;
- an empty *Unreleased*;
- below it, a `## [X.Y.Z] - YYYY-MM-DD` section with entries. Only the date's format is checked, not its
  value, since the owner may merge days after the bump.

A non-releasing PR changes neither `version` nor `CHANGELOG.md`. The rules live in
`scripts/release_check.py`.

## Two releasing PRs at once

`main` requires a PR to be up to date before it merges. This is strict mode, and it binds admins too. Once
one releasing PR merges, the other can't merge until it takes in `main`, and then its bump is stale and
`version-check` fails.

1. Merge `origin/main` into the branch: `git merge origin/main`, or GitHub's *Update branch* with its merge
   option. Never rebase: that needs a force-push.
2. Whether or not git reports a conflict:
   - take `main`'s `CHANGELOG.md`, and put this branch's entries back under its `## [Unreleased]`;
   - take `main`'s `version` in `manifest.json`.
3. Commit the merge, rerun the bump step, commit and push.

In the PO flow the team lead does this after the PO resumes it (`way-of-working.md` §8).

## Fixing an old changelog entry

Released sections never change, except in a PR titled `docs(changelog): …`. Such a PR may fix their text.
It may not:
- add or remove a section;
- change a heading;
- change *Unreleased*;
- change `version`.

## What happens on merge

`auto-release.yml` waits until the five required workflows (`lint`, `tests`, `hassfest`, `hacs`,
`gitleaks`) have passed on `main` for the merge commit. Then it checks whether the commit is a bump,
compared with the commit before it:
- the version is higher (semver);
- the same commit adds the `## [X.Y.Z]` heading to `CHANGELOG.md`;
- that section has entries.

If so, it tags the commit `vX.Y.Z` and publishes the release through `release.yml`. Any other merge
releases nothing, and the `auto-release` run says why.

Afterwards, check the `auto-release` runs for the merge commit. There are up to five, one per required
workflow. Some show as cancelled, and the one that runs after the last workflow does the work. Then check:
- the tag;
- the release, with the changelog section as its notes;
- that HACS offers the version.

## When a release fails

Re-running a run can publish, and so can pushing a tag, so every step here is the owner's. The controller
takes one only when the owner says so for that release.

- **A required workflow failed on `main`.**
  - If it's flaky, re-run it: *Re-run failed jobs*, or `gh run rerun <id> --failed`. When it passes,
    `auto-release` runs again.
  - A real break is fixed in a PR. The version it would have released may never be published. Its
    `CHANGELOG.md` section stays as history, and the next releasing PR carries only its own entries.
- **`auto-release` or `release` failed.** If the cause is in the repo, fix it in a PR first. Then re-run the
  failed `auto-release` run. A re-run acts on the same commit, and neither a release that already exists
  nor a tag already on that commit gets in the way.
- **`HTTP 403: Resource not accessible by integration` when the release is created.**
  - Why: GitHub needs the `workflows` permission to create a release with a new tag on a commit whose
    `.github/workflows/` differ from `main`'s head, and a workflow's `GITHUB_TOKEN` can't have that
    permission
    ([GitHub changelog](https://github.blog/changelog/2023-11-02-github-actions-enforcing-workflow-scope-when-creating-a-release/)).
  - When: a PR that changes the workflows merged after the releasing PR, but before its release was tagged.
    A re-run fails the same way.
  - Fix: the owner pushes the tag on the releasing commit by hand, then re-runs the failed `auto-release`
    run. The re-run finds the tag on that commit and publishes. `0.1.0` was released this way.

  ```bash
  git fetch origin
  git tag vX.Y.Z <releasing commit>
  git push origin vX.Y.Z
  ```

## What `release.yml` checks

`auto-release.yml` calls it with the tag and the commit; it has no other trigger.

- The tag equals `v` followed by the `version` in `manifest.json`. If it doesn't match, the release fails.
- The `CHANGELOG.md` has a `## [X.Y.Z]` section for that version, and it is not empty. If it's missing or
  empty, the release fails.
- A release that exists already means there is nothing to do: the run ends with no second release.
- A tag that exists must point at the commit being released, or the release fails.
- If the checks pass, it runs `gh release create`, using that changelog section as the release notes.

## Required workflows

(unchanged: copy the current section as it is)

## Bumping `pynortecgo`

(unchanged: copy the current section as it is, and add this paragraph after its first paragraph:)

Title such a PR by what it changes for users (*PR titles*). If users see a difference, it's a `feat` or
`fix` with a changelog entry and the bump step. If they don't, it's `chore(deps): …`.

## Bumping Home Assistant

(unchanged: copy the current section as it is, and add:)

Title such a PR by what it changes for users (*PR titles*). A higher minimum Home Assistant version is
something users see, so that PR is a `feat` or `fix` with a changelog entry and the bump step.

## Once, after the release model PR merges

1. Every checkout and worktree runs `uv sync`: the `actionlint` and `zizmor` pre-commit hooks need the
   tools.
2. The owner adds `version-check` to `main`'s required status checks (a GitHub setting).
3. Any PR still open then gets a title by these rules and, if the title releases, the bump step.

The first PR after these are done removes this section.
````

The three "(unchanged …)" lines are instructions, not text. The finished file has the real sections there.

- [ ] **Step 2: `docs/way-of-working.md`**

Make these changes. Keep each bullet's existing wording otherwise.
1. §1 step 2, after "…`chore` or `process`.": add "The PR title's type is separate, and follows [`releasing.md`](releasing.md#pr-titles)."
2. §1 step 6, before "The owner reviews the spec and plan there.": add "Its title follows [`releasing.md`](releasing.md#pr-titles)."
3. §1 step 10: after "(…; stop any running dev instance first)" and before "update the PR description", insert ", for a releasing title run the bump step ([`releasing.md`](releasing.md#a-releasing-pr)) and push". Adjust the punctuation so the sentence reads: run smoke, then the bump step, then update the description, then `gh pr ready`.
4. §4: after the D25 paragraph, add a paragraph: "A PR opened ready with a releasing title runs the bump step ([`releasing.md`](releasing.md#a-releasing-pr)) before it is opened; give the title in single quotes."
5. §6 table:
   - the *may not* cell "Tag releases" becomes "Push a tag, or re-run a workflow run on `main` (either can publish), unless the owner says so for that release";
   - add a row "| Run the bump step in a releasing PR ([`releasing.md`](releasing.md#a-releasing-pr)) | |".
6. §8 *Roles and start modes*, the team lead bullet: after "…with the PO (addressed as `po`) in the owner's place.", add "For a releasing title it then runs the bump step ([`releasing.md`](releasing.md#a-releasing-pr)), as its last step before `branch ready`."
7. §8, the "Owner only:" bullet becomes: "Owner only: merging, anything that starts or stops a real charge, pushing a tag, re-running a workflow run on `main`, the permission setup for team leads, and `.claude/settings.json`."
8. §8 *From branch ready to PR ready*, step 4: after "the PR against the issue's user story and the approved spec,", insert " the title's type and release level ([`releasing.md`](releasing.md#pr-titles)),".
9. §8 *After ready…*, first bullet: "On changes requested or a merge conflict" becomes "On changes requested, a merge conflict, or a stale bump (a releasing PR behind `main` after another release; [`releasing.md`](releasing.md#two-releasing-prs-at-once))".

- [ ] **Step 3: `docs/decisions.md`**

1. D10's status line becomes `- **Date:** 2026-09-26 · **Status:** superseded by D40`.
2. D39's status line becomes `- **Date:** 2026-09-29 · **Status:** active; the bump PR and the fallbacks superseded by D40`.
3. Append at the end:

```markdown
### D40: A merged PR releases itself, by its title
- **Date:** 2026-09-29 · **Status:** active
- **Decision:** The PR title's type decides the release (`fix`/`perf` patch, `feat` minor, `!` minor on 0.x
  and major from 1.0, other types none). A releasing PR carries its own bump from `release_check.py
  release-pr`, run before it is marked ready; `auto-release.yml` publishes it on merge, as D39 set up. A
  merged PR is the only way to release: no dispatch, and a pushed tag publishes nothing on its own. A failed
  release is re-run by the owner; when the workflow-scope limit blocks the tag, the owner pushes it by hand
  first.
- **Why:** a separate bump PR was a manual step that left changes waiting under *Unreleased*, and every
  release should come from a reviewed, merged PR; a stale bump between two ready PRs is accepted as the
  price.
- **Source:** [release model spec](superpowers/specs/2026-09-29-release-model-design.md), Decisions
```

- [ ] **Step 4: The other docs**

1. `docs/README.md`, the `releasing.md` row's middle cell: `PR titles, the bump step, the automatic release, when a release fails, what `release.yml` checks`. The last cell stays `Cutting a release`.
2. `docs/notes.md`, section *2026-09-29: GitHub Actions behaviour for release workflows*: add a last bullet: "- Creating a release with a new tag on a commit whose workflows differ from `main`'s head needs a permission `GITHUB_TOKEN` can't have: see [`releasing.md`](releasing.md#when-a-release-fails)."
3. `CLAUDE.md`:
   - "- Add a `CHANGELOG.md` entry under *Unreleased* for user-visible changes." becomes "- Add a `CHANGELOG.md` entry under *Unreleased* for user-visible changes, and title the PR `feat`, `fix` or `perf` (`docs/releasing.md`).";
   - in the layout, "`release_check.py`, the release rules the workflows run" becomes "`release_check.py`, the release rules and the bump step". Keep the line wrapping at 110 characters.
4. `.github/pull_request_template.md`: replace the line `- [ ] \`CHANGELOG.md\` updated under *Unreleased* (user-visible changes)` with two lines:

```markdown
- [ ] Title type per `docs/releasing.md` (user-visible → `feat`, `fix` or `perf`, with a `CHANGELOG.md` entry)
- [ ] Releasing title → the bump step run last (`docs/releasing.md`)
```

- [ ] **Step 5: The agent files**

1. `.claude/agents/team-lead.md`:
   - "The PO takes the owner's place in §1 steps 3 to 8; step 10 is the PO's." becomes "The PO takes the owner's place in §1 steps 3 to 8; step 10 is the PO's, except the bump step (`docs/releasing.md`), which you run before `branch ready`.";
   - in *Never*, "- Merge a PR, force-push, tag a release, or change GitHub settings." becomes "- Merge a PR, force-push, push a tag, re-run a workflow run on `main`, or change GitHub settings.".
2. `.claude/agents/po.md`, in *Never*: the same replacement of "- Merge a PR, force-push, tag a release, or change GitHub settings.".

- [ ] **Step 6: Check the names and leftovers**

Run: `git grep -n -e "bump PR" -e "dry_run" -e "Tagging by hand" -e "Fallbacks" -e "pr-check [^-]" -- ':!docs/superpowers' ':!CHANGELOG.md' ':!docs/decisions.md' ':!tests'`
Expected: no output. (Decision entries aren't edited apart from their status, and the tests name `dry_run` on purpose.) Also check every command and name in the docs against `scripts/release_check.py` (`release-pr --title=`, `pr-check --title=`) and the workflows. For any hit, fix the doc, or say in the report why it stays.
Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`
Expected: all pass. (`ruff format` also checks Python blocks in Markdown; the docs here have none.)

- [ ] **Step 7: Commit**

Write `/tmp/release-model-task-3-msg.txt` with the Write tool:

```text
docs: release by PR title, D40, and the flow around the bump step (#68, #67)

<co-author trailer from the dispatch>
```

Then run `git add docs CLAUDE.md .github/pull_request_template.md .claude/agents/po.md .claude/agents/team-lead.md && git commit -F /tmp/release-model-task-3-msg.txt`.

---

### Task 4: Pre-merge checks

**Model:** sonnet — read-only checks and a throwaway clone; nothing is committed or pushed.
**Wave:** 3 (after Tasks 1 to 3 are on the pushed feature branch and the draft PR exists)

**Files:** none. The report lists each command's result.

**Interfaces:**
- Consumes: the pushed branch `process/release-model`, its draft PR, and Task 1's CLI.
- Produces: a report. The controller copies it into the PR description.

- [ ] **Step 1: 0.1.0 is still released on `9441abd`**

Run: `gh release view v0.1.0 --json tagName,isPrerelease,isDraft && git ls-remote origin refs/tags/v0.1.0`
Expected: `v0.1.0`, `isPrerelease` false, `isDraft` false; the tag points at `9441abd728348e85de63f04245d80be76f11bbc0`.

- [ ] **Step 2: This PR passes its own check**

Run, in the main checkout of the feature branch:

```bash
git fetch -q origin
base="$(git merge-base origin/main origin/process/release-model)"
uv run --no-project --python 3.14 python scripts/release_check.py pr-check --title="$(gh pr view process/release-model --json title -q .title)" "$base" origin/process/release-model
```

Expected: `Title, version and changelog agree`, exit 0. The title is `process: …`, so the version and `CHANGELOG.md` are unchanged.

- [ ] **Step 3: A bump in a throwaway clone**

Run it as one Bash call: a subagent's shell doesn't keep the `cd` between calls.

```bash
d="$(mktemp -d)"
git clone -q --branch process/release-model https://github.com/thomas3650/HA-NortecGo.git "$d/c"
cd "$d/c"
git -c user.name=Test -c user.email=test@example.invalid -c commit.gpgsign=false merge -q --no-edit origin/main
perl -0pi -e 's/## \[Unreleased\]\n/## [Unreleased]\n\n### Fixed\n\n- A test entry.\n/' CHANGELOG.md
git -c user.name=Test -c user.email=test@example.invalid -c commit.gpgsign=false commit -qam "fix: test entry"
uv run --no-project --python 3.14 python scripts/release_check.py release-pr --title='fix: test'
git -c user.name=Test -c user.email=test@example.invalid -c commit.gpgsign=false commit -qam "chore: release"
uv run --no-project --python 3.14 python scripts/release_check.py pr-check --title='fix: test' "$(git merge-base origin/main HEAD)" HEAD
cd - && rm -rf "$d"
```

Expected:
- the merge says "Already up to date" or merges cleanly;
- `release-pr` prints the next patch version after `main`'s (`0.1.1` while `main` is at `0.1.0`);
- `pr-check` prints `Title, version and changelog agree` and exits 0;
- the directory is removed.

Nothing is pushed: the clone has no credentials helper set up for pushing, and the steps never push.

- [ ] **Step 4: Report**

Report each step's command and output. Don't commit anything. The controller then checks that the PR
description says `Closes #68` and `Closes #67`.
