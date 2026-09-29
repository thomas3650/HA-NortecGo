# Tag and publish a release when a merged PR bumps the version Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** Once CI passes on `main` for a commit that bumps the version, `auto-release.yml` tags it and publishes the release through `release.yml`; `version-check.yml` checks on each PR that a version change is such a bump.

**Architecture:**
- Task 1 adds the workflow linters (`actionlint` with ShellCheck, `zizmor`) to the dev group, `lint.yml`, pre-commit and `CLAUDE.md`, and fixes what they find in the existing workflows.
- Task 2 writes `scripts/release_check.py`, the stdlib rules (versions, changelog section, bump, required runs, tag commit) and their tests.
- Task 3 writes `auto-release.yml` and `version-check.yml`, gives `release.yml` its `workflow_call` path, and adds `tests/test_workflows.py`.
- Task 4 writes the docs (`releasing.md`, D39, the docs map row), in wave 1, against the names this plan fixes.

**Tech Stack:** GitHub Actions, Python 3.14 (stdlib only for the script), pytest, PyYAML (already in the dev env through Home Assistant), uv, actionlint, ShellCheck, zizmor.

**Spec:** `docs/superpowers/specs/2026-09-29-auto-release-design.md` (issue #64).

## Global Constraints

- **Nothing private (hard rule 3):** no IDs, tokens, emails, or links to the private client repo. Commit SHAs of this public repo (`9441abd`, `db53bf7`) are fine.
- **Gates before every commit** (`CLAUDE.md` → Commands):
  - run `uv run pytest -q`;
  - then `uv run ruff check && uv run ruff format --check && uv run mypy`;
  - from Task 1 on, also `uv run actionlint && uv run zizmor --offline .github/workflows`;
  - the coverage gate (`--cov-fail-under=95`) passes at the end of each task.
- **Commit messages:** subagents write them with the Write tool to a uniquely named file outside the repo (`/tmp/auto-release-task-<n>-msg.txt`) and commit with `git commit -F <file>`. No heredocs. End each message with the co-author trailer given in the dispatch.
- **Python style:** 3.14, like the rest of the repo. Exception tuples without `as` use the 3.14 form `except A, B:`, and `ruff format` writes it. One-line docstrings end in a period.
- **Actions:** pinned to the SHAs the repo already uses:
  - `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1`
  - `astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7  # v10.2.0`
  - Every checkout has `persist-credentials: false`.
- **Workflow values:** every `${{ }}` value used in a `run:` script reaches it through `env:`. No `${{` inside a `run:` block.
- **Which commit:** `auto-release.yml` and `release.yml` never use `github.sha` or `GITHUB_SHA`. The commit is `github.event.workflow_run.head_sha`, or the resolved `sha` input.
- **Triggers and permissions:** never `pull_request_target`. Top-level `permissions: {}` in `auto-release.yml`, `release.yml` and `version-check.yml`. Each job states its own.
- **Fixed names:**
  - the script `scripts/release_check.py`, with `REQUIRED_WORKFLOWS = ("lint", "tests", "hassfest", "hacs", "gitleaks")` and the subcommands `bump`, `pr-check`, `runs-green` and `tag-commit`;
  - the workflows `auto-release` (jobs `decide`, `release`), `version-check` (job `version-check`) and `release` (job `release`);
  - the `release.yml` `workflow_call` inputs `tag` and `sha`;
  - the `auto-release.yml` dispatch inputs `sha` and `dry_run`.
- **Script runs in workflows:** `uv run --no-project --python 3.14 python scripts/release_check.py ...`, after `setup-uv` with `python-version: "3.14"` and `enable-cache: false`.
- **Decision number:** D39. D10's status becomes `active; the manual tag superseded by D39`.
- **What agents may not do:** tag, push tags, dispatch workflows, or change GitHub settings.

## Review Focus

1. **A `workflow_run` run while `main` has moved on.** `GITHUB_SHA` is then main's newer head. Everything must use `head_sha`. Task 3's `test_no_github_sha_in_release_workflows` pins the text; the reviewer also reads every step's commit source.
2. **`release.yml` called from `auto-release.yml`.** The `github` context is the caller's, so `github.ref_name` is `main`. The tag must come from `inputs.tag` and the checkout from `inputs.sha || github.ref`, pinned by Task 3's `test_release_takes_the_tag_from_inputs`.
3. **The `0.1.0` dispatch on `9441abd`.** The checked-out commit has no script, so `release.yml` must stay shell only (Task 3's `test_release_is_shell_only`). `bump` must say bump for a commit that is not main's head (Task 2's `test_cli_bump_on_an_older_commit`).
4. **A scheduled `hassfest`/`hacs` run on the bump commit.** It must not cancel the waiting push run, so the concurrency group includes the event (Task 3's `test_concurrency_group_per_event_and_commit`). It must not count as green or red, because the runs list asks for `event=push` (the reviewer reads the `gh api` line).
5. **Injection through branch names or inputs.** No `${{` inside a `run:` block in any workflow (Task 3's `test_no_expressions_inside_run_blocks`).

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (linters), Task 4 (docs) | Disjoint files, two worktrees off the feature branch. Task 4 is written against this plan's names and re-checked against the code that lands |
| 2 | Task 2 (`release_check.py`) | Edits `pyproject.toml` after Task 1 (same file, so not in wave 1) |
| 3 | Task 3 (workflows) | Uses Task 2's script and `REQUIRED_WORKFLOWS`, and Task 1's linters |

Guarded files: Task 1 only. Before its dispatch the controller writes `.pre-commit-config.yaml` to
`$(git -C <task-1 worktree> rev-parse --absolute-git-dir)/subagent-guard-allow`, and empties it however the task ends.

---

### Task 1: Workflow linters in the gates

**Model:** opus — it changes `.github/workflows/` and the pre-commit config.
**Wave:** 1
**Guarded files:** `.pre-commit-config.yaml` — the `actionlint` and `zizmor` pre-commit hooks (spec §7).

**Files:**
- Modify: `pyproject.toml` (dev group only), `uv.lock`
- Modify: `.pre-commit-config.yaml`
- Modify: `.github/workflows/lint.yml`
- Modify: `CLAUDE.md` (*Commands*, the lint line)
- Modify, only if a linter finds something: `.github/workflows/release.yml`, `tests.yml`, `hassfest.yml`, `hacs.yml`, `gitleaks.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: `uv run actionlint` (ShellCheck on the `PATH` through `shellcheck-py`) and `uv run zizmor --offline .github/workflows` pass on the repo. Tasks 2 and 3 run them as gates.

- [ ] **Step 1: Add the dev dependencies**

In `pyproject.toml`, `[dependency-groups] dev`, add these four lines after `"pre-commit",`:

```text
  "actionlint-py",
  "shellcheck-py",
  "zizmor",
  "types-PyYAML",
```

Run: `uv lock && uv sync`
Expected: all four installed; `uv run actionlint -version`, `uv run shellcheck --version` and `uv run zizmor --version` each print a version.

- [ ] **Step 2: See what the linters find today**

Run: `uv run actionlint; uv run zizmor --offline .github/workflows`
Expected: actionlint clean; zizmor's `artipacked` findings on the five checkouts without `persist-credentials: false` (gitleaks, hassfest, lint, release, tests). Note every finding.

Run: `uv run actionlint -verbose 2>&1 | grep 'Rule "shellcheck" was disabled'`
Expected: no output (ShellCheck is on the `PATH`, so actionlint runs it).

- [ ] **Step 3: Fix the findings**

- Add `persist-credentials: false` under `with:` of every `actions/checkout` step (in `gitleaks.yml`, next to `fetch-depth: 0`). None of these workflows pushes with git.
- In `release.yml`'s *Create the GitHub release* step, replace the `flags` string with an array:

```bash
prerelease=()
case "$VERSION" in 0.0.*|*-*) prerelease=(--prerelease) ;; esac
gh release create "$GITHUB_REF_NAME" --title "$GITHUB_REF_NAME" --notes-file notes.md "${prerelease[@]}"
```

- **Anything else:** fix it if the fix is small and changes no behaviour. Otherwise add an inline `# zizmor: ignore[<rule>]` with a one-line reason, and list it in the report. Don't change triggers, job names or permissions. The job names are required checks on `main`.

Run: `uv run actionlint && uv run zizmor --offline .github/workflows`
Expected: both exit 0 with no findings.

- [ ] **Step 4: Run them in CI**

In `.github/workflows/lint.yml`, after `- run: uv run mypy`, add:

```yaml
      - run: uv run actionlint
      - run: uv run zizmor --offline .github/workflows
```

- [ ] **Step 5: Pre-commit hooks**

In `.pre-commit-config.yaml`, in the `- repo: local` block, add these hooks before `no-push-to-main`:

```yaml
      - id: actionlint
        name: actionlint (GitHub workflows)
        entry: uv run actionlint
        language: system
        files: ^\.github/workflows/
      - id: zizmor
        name: zizmor (GitHub workflows)
        entry: uv run zizmor --offline
        language: system
        files: ^\.github/workflows/
```

Run: `uv run pre-commit run actionlint --all-files && uv run pre-commit run zizmor --all-files`
Expected: both Passed.

- [ ] **Step 6: `CLAUDE.md`**

In *Commands*, replace the line

```text
uv run ruff check && uv run ruff format --check && uv run mypy
```

with

```text
uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows
```

- [ ] **Step 7: Gates and commit**

Run the gates in the Global Constraints (the full set, with the coverage gate).
Commit message:

```text
process: actionlint and zizmor in the gates (#64)
```

---

### Task 2: `scripts/release_check.py`

**Model:** opus — the release rules, near tagging (the PO's ruling for this issue).
**Wave:** 2

**Files:**
- Create: `scripts/release_check.py`
- Create: `tests/test_release_check.py`
- Modify: `pyproject.toml` (pytest `pythonpath`, mypy `mypy_path` and `files`, ruff per-file ignores)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces (for Task 3), in module `release_check` (importable in tests through `pythonpath = ["scripts"]`):
  - `REQUIRED_WORKFLOWS: tuple[str, ...] = ("lint", "tests", "hassfest", "hacs", "gitleaks")`
  - `MANIFEST = "custom_components/nortec_go/manifest.json"`, `CHANGELOG = "CHANGELOG.md"`
  - `class ReleaseCheckError(Exception)`
  - `@dataclass(frozen=True, order=True, slots=True) class Version` with `parse_version(text: str) -> Version`
  - `manifest_version(manifest: str) -> Version`
  - `changelog_section(changelog: str, version: str) -> str | None`, `has_heading(changelog: str, version: str) -> bool`
  - `@dataclass(frozen=True, slots=True) class Verdict(changed: bool, bump: bool, version: str, reason: str)`
  - `bump_verdict(*, base_manifest: str, head_manifest: str, base_changelog: str, head_changelog: str) -> Verdict`
  - `runs_problems(payload: dict[str, Any], required: tuple[str, ...] = REQUIRED_WORKFLOWS) -> list[str]`
  - `tag_commit(ls_remote: str, tag: str) -> str | None`
  - `main(argv: list[str] | None = None) -> int`
  - CLI:
    - `bump <commit>` writes `version`, `tag` and `bump` to `$GITHUB_OUTPUT`, and exits 0 unless there is an error;
    - `pr-check <base> <head>` exits 0 or 1;
    - `runs-green` reads JSON on stdin and exits 0 or 1;
    - `tag-commit <tag>` reads `git ls-remote` output on stdin and prints the commit or nothing;
    - an error exits 2.

- [ ] **Step 1: Configure pytest, mypy and ruff for the script**

In `pyproject.toml`:
- `[tool.pytest.ini_options]`: add `pythonpath = ["scripts"]`.
- `[tool.ruff.lint.isort]`: `known-first-party` becomes `["custom_components.nortec_go", "tests", "release_check"]`.
- `[tool.mypy]`: change `files` to `["custom_components", "tests", "scripts/release_check.py"]` and add `mypy_path = "scripts"`.
- Add, after `[tool.ruff.lint.pydocstyle]`:

```toml
[tool.ruff.lint.per-file-ignores]
# A script run by the workflows, not a package; it prints its verdicts.
"scripts/*.py" = ["INP001", "T201"]
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_release_check.py`:

```python
"""Tests for the release rules in scripts/release_check.py."""

import io
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

from release_check import (
    REQUIRED_WORKFLOWS,
    ReleaseCheckError,
    Verdict,
    bump_verdict,
    changelog_section,
    has_heading,
    main,
    manifest_version,
    parse_version,
    runs_problems,
    tag_commit,
)

HEADER = "# Changelog\n\n## [Unreleased]\n"
OLD = HEADER + "\n## [0.0.1] - 2026-09-26\n\n- The skeleton.\n"
NEW = (
    HEADER
    + "\n## [0.1.0] - 2026-09-29\n\n### Added\n\n- A thing.\n\n## [0.0.1] - 2026-09-26\n\n- The skeleton.\n"
)
NEW_EMPTY = (
    HEADER
    + "\n## [0.1.0] - 2026-09-29\n\n\n## [0.0.1] - 2026-09-26\n\n- The skeleton.\n"
)


def _manifest(version: str) -> str:
    return json.dumps({"domain": "nortec_go", "version": version})


# Versions


@pytest.mark.parametrize(
    ("lower", "higher"),
    [
        ("0.0.1", "0.1.0"),
        ("0.9.9", "1.0.0"),
        ("1.0.0", "1.0.1"),
        ("1.0.0-beta.1", "1.0.0"),
        ("1.0.0-alpha", "1.0.0-beta"),
        ("1.0.0-beta.2", "1.0.0-beta.11"),
        ("1.0.0-1", "1.0.0-alpha"),
        ("1.0.0-alpha", "1.0.0-alpha.1"),
    ],
)
def test_version_precedence(lower: str, higher: str) -> None:
    """Versions compare by semver precedence."""
    assert parse_version(lower) < parse_version(higher)


def test_equal_versions() -> None:
    """The same version compares equal."""
    assert parse_version("1.2.3") == parse_version("1.2.3")


@pytest.mark.parametrize(
    "text", ["", "1.2", "v1.2.3", "1.2.3.4", "01.2.3", "1.2.3-", "1.2.3+build"]
)
def test_bad_version(text: str) -> None:
    """A version that isn't X.Y.Z with an optional pre-release is an error."""
    with pytest.raises(ReleaseCheckError):
        parse_version(text)


def test_manifest_version() -> None:
    """The manifest's version is read and parsed."""
    assert manifest_version(_manifest("0.1.0")).text == "0.1.0"


@pytest.mark.parametrize(
    "manifest", ["not json", "[]", '{"domain": "nortec_go"}', '{"version": 1}']
)
def test_manifest_without_version(manifest: str) -> None:
    """A manifest without a string version is an error."""
    with pytest.raises(ReleaseCheckError):
        manifest_version(manifest)


# The changelog section


def test_changelog_section() -> None:
    """The section runs from its heading to the next one."""
    assert changelog_section(NEW, "0.1.0") == "### Added\n\n- A thing."


def test_changelog_last_section() -> None:
    """The last section in the file runs to the end."""
    assert changelog_section(NEW, "0.0.1") == "- The skeleton."


def test_changelog_section_missing_or_blank() -> None:
    """A missing section and a blank one are both no section."""
    assert changelog_section(OLD, "0.1.0") is None
    assert changelog_section(NEW_EMPTY, "0.1.0") is None


def test_has_heading() -> None:
    """The heading counts even when its section is blank."""
    assert has_heading(NEW_EMPTY, "0.1.0")
    assert not has_heading(OLD, "0.1.0")


# Bump


def _verdict(base: str, head: str, base_log: str, head_log: str) -> Verdict:
    return bump_verdict(
        base_manifest=_manifest(base),
        head_manifest=_manifest(head),
        base_changelog=base_log,
        head_changelog=head_log,
    )


def test_bump() -> None:
    """A higher version with a new, non-empty section is a bump."""
    verdict = _verdict("0.0.1", "0.1.0", OLD, NEW)
    assert (verdict.changed, verdict.bump, verdict.version) == (True, True, "0.1.0")
    assert verdict.reason == "0.0.1 -> 0.1.0: a bump, release v0.1.0"


def test_unchanged_is_no_bump() -> None:
    """An unchanged version is no bump, and no change."""
    verdict = _verdict("0.1.0", "0.1.0", NEW, NEW)
    assert (verdict.changed, verdict.bump) == (False, False)
    assert verdict.reason == "0.1.0 unchanged: nothing to release"


def test_lower_is_no_bump() -> None:
    """A lower version, a revert of a bump included, is no bump."""
    verdict = _verdict("0.1.0", "0.0.1", NEW, OLD)
    assert (verdict.changed, verdict.bump) == (True, False)
    assert verdict.reason == "0.0.1 is lower than 0.1.0: not a bump"


def test_heading_already_in_base_is_no_bump() -> None:
    """A version whose heading the base already had is no bump."""
    verdict = _verdict("0.0.1", "0.1.0", NEW, NEW)
    assert (verdict.changed, verdict.bump) == (True, False)
    assert (
        verdict.reason
        == "CHANGELOG.md already has ## [0.1.0] before this change: not a bump"
    )


def test_raised_without_section_is_no_bump() -> None:
    """A higher version without a section, or with a blank one, is no bump."""
    for head_log in (OLD, NEW_EMPTY):
        verdict = _verdict("0.0.1", "0.1.0", OLD, head_log)
        assert (verdict.changed, verdict.bump) == (True, False)
        assert (
            verdict.reason
            == "CHANGELOG.md has no ## [0.1.0] section with entries: not a bump"
        )


# Required runs


def _run(
    name: str, conclusion: str | None, created_at: str = "2026-09-29T10:00:00Z"
) -> dict[str, object]:
    return {
        "name": name,
        "conclusion": conclusion,
        "status": "completed" if conclusion else "in_progress",
        "created_at": created_at,
    }


def _green() -> list[dict[str, object]]:
    return [_run(name, "success") for name in REQUIRED_WORKFLOWS]


def test_runs_all_green() -> None:
    """All five workflows passed."""
    assert runs_problems({"workflow_runs": _green()}) == []


def test_runs_one_missing() -> None:
    """A workflow without a push run is a problem."""
    runs = [run for run in _green() if run["name"] != "hacs"]
    assert runs_problems({"workflow_runs": runs}) == ["hacs: no push run"]


def test_runs_one_failed_or_running() -> None:
    """A failed or still running workflow is a problem."""
    runs = [*_green()[:3], _run("hacs", "failure"), _run("gitleaks", None)]
    assert runs_problems({"workflow_runs": runs}) == [
        "hacs: failure",
        "gitleaks: in_progress",
    ]


def test_runs_newest_counts() -> None:
    """Only the newest run of a workflow counts."""
    older_failed = [*_green(), _run("tests", "failure", "2026-09-29T09:00:00Z")]
    assert runs_problems({"workflow_runs": older_failed}) == []
    newer_failed = [*_green(), _run("tests", "failure", "2026-09-29T11:00:00Z")]
    assert runs_problems({"workflow_runs": newer_failed}) == ["tests: failure"]


def test_runs_other_workflows_ignored() -> None:
    """Runs of workflows that aren't required don't count."""
    runs = [*_green(), _run("CodeQL", "failure")]
    assert runs_problems({"workflow_runs": runs}) == []


# Tag commit

LIGHT = "1111111111111111111111111111111111111111\trefs/tags/v0.1.0\n"
ANNOTATED = (
    "2222222222222222222222222222222222222222\trefs/tags/v0.1.0\n"
    "3333333333333333333333333333333333333333\trefs/tags/v0.1.0^{}\n"
)


def test_tag_commit() -> None:
    """A lightweight tag is its line; an annotated tag is its peeled line; a missing tag is None."""
    assert tag_commit(LIGHT, "v0.1.0") == "1111111111111111111111111111111111111111"
    assert tag_commit(ANNOTATED, "v0.1.0") == "3333333333333333333333333333333333333333"
    assert tag_commit("", "v0.1.0") is None
    assert tag_commit(LIGHT, "v0.1.1") is None


# The CLI, with git in a temporary repository


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, version: str, changelog: str) -> str:
    manifest = repo / "custom_components" / "nortec_go" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(_manifest(version), encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (repo / "other.txt").write_text(f"{version} {len(changelog)}\n", encoding="utf-8")
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
        version,
    )
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty git repository as the working directory, with no GITHUB_OUTPUT."""
    _git(tmp_path, "init", "-q", "-b", "main")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    return tmp_path


def test_cli_bump_on_an_older_commit(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The 0.1.0 case: the bump commit is a bump though main has moved on; the later commit isn't."""
    _commit(repo, "0.0.1", OLD)
    bump = _commit(repo, "0.1.0", NEW)
    later = _commit(repo, "0.1.0", NEW + "\n")
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert main(["bump", bump]) == 0
    assert "0.0.1 -> 0.1.0: a bump, release v0.1.0" in capsys.readouterr().out
    assert output.read_text(encoding="utf-8").splitlines() == [
        "version=0.1.0",
        "tag=v0.1.0",
        "bump=true",
    ]

    output.unlink()
    assert main(["bump", later]) == 0
    assert "0.1.0 unchanged: nothing to release" in capsys.readouterr().out
    assert output.read_text(encoding="utf-8").splitlines() == [
        "version=0.1.0",
        "tag=v0.1.0",
        "bump=false",
    ]


def test_cli_bump_without_github_output(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without GITHUB_OUTPUT the verdict is only printed."""
    _commit(repo, "0.0.1", OLD)
    bump = _commit(repo, "0.1.0", NEW)
    assert main(["bump", bump]) == 0
    assert "a bump" in capsys.readouterr().out


def test_cli_bump_error(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A commit without a parent can't be read: exit 2."""
    first = _commit(repo, "0.0.1", OLD)
    assert main(["bump", first]) == 2
    assert capsys.readouterr().err.startswith("error: ")


def test_cli_pr_check(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A PR passes with the version unchanged or bumped, and fails with any other version change."""
    base = _commit(repo, "0.0.1", OLD)
    unchanged = _commit(repo, "0.0.1", OLD + "\n")
    assert main(["pr-check", base, unchanged]) == 0
    bumped = _commit(repo, "0.1.0", NEW)
    assert main(["pr-check", base, bumped]) == 0
    no_section = _commit(repo, "0.2.0", NEW)
    assert main(["pr-check", bumped, no_section]) == 1
    assert "no ## [0.2.0] section" in capsys.readouterr().out


def test_cli_runs_green(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """runs-green exits 0 when all passed and 1 with the problems listed."""
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"workflow_runs": _green()}))
    )
    assert main(["runs-green"]) == 0
    assert "All required workflows passed" in capsys.readouterr().out
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"workflow_runs": _green()[1:]}))
    )
    assert main(["runs-green"]) == 1
    assert "lint: no push run" in capsys.readouterr().out


@pytest.mark.parametrize("stdin", ["not json", "[]"])
def test_cli_runs_green_bad_input(stdin: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A runs list that isn't a JSON object is an error."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    assert main(["runs-green"]) == 2


def test_cli_tag_commit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """tag-commit prints the commit, or nothing for a missing tag, and exits 0."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(ANNOTATED))
    assert main(["tag-commit", "v0.1.0"]) == 0
    assert capsys.readouterr().out == "3333333333333333333333333333333333333333\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert main(["tag-commit", "v0.1.0"]) == 0
    assert capsys.readouterr().out == ""


def test_tag_commit_skips_other_lines() -> None:
    """Lines that aren't a SHA and a ref are skipped."""
    assert (
        tag_commit("warning: something odd\n" + LIGHT, "v0.1.0")
        == "1111111111111111111111111111111111111111"
    )


def test_script_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run as a script, it exits with main()'s code."""
    script = Path(__file__).parent.parent / "scripts" / "release_check.py"
    monkeypatch.setattr(sys, "argv", [str(script), "tag-commit", "v0.1.0"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(script), run_name="__main__")
    assert exit_info.value.code == 0
```

Let `ruff format` wrap the long lines; mypy runs strict on tests.

Run: `uv run pytest tests/test_release_check.py -q`
Expected: collection fails with `ModuleNotFoundError: No module named 'release_check'`.

- [ ] **Step 3: Write the script**

Create `scripts/release_check.py`:

```python
"""Release rules for the auto-release and version-check workflows.

Stdlib only. The workflows run it with `uv run --no-project --python 3.14`.
"""

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

MANIFEST = "custom_components/nortec_go/manifest.json"
CHANGELOG = "CHANGELOG.md"
REQUIRED_WORKFLOWS: tuple[str, ...] = ("lint", "tests", "hassfest", "hacs", "gitleaks")

_VERSION = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)


class ReleaseCheckError(Exception):
    """A file can't be read, or a version can't be parsed."""


@dataclass(frozen=True, order=True, slots=True)
class Version:
    """A version, ordered by semver precedence."""

    major: int
    minor: int
    patch: int
    is_release: bool
    pre: tuple[tuple[int, int, str], ...]
    text: str = field(compare=False)


def parse_version(text: str) -> Version:
    """Parse `X.Y.Z` with an optional `-<pre-release>` suffix."""
    match = _VERSION.fullmatch(text)
    if match is None:
        raise ReleaseCheckError(f"Not a version: {text!r}")
    major, minor, patch, pre = match.groups()
    parts = pre.split(".") if pre else []
    identifiers = tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part) for part in parts
    )
    return Version(int(major), int(minor), int(patch), pre is None, identifiers, text)


def manifest_version(manifest: str) -> Version:
    """The version in a manifest.json text."""
    try:
        version = json.loads(manifest)["version"]
    except (json.JSONDecodeError, KeyError, TypeError) as err:
        raise ReleaseCheckError("manifest.json has no version") from err
    if not isinstance(version, str):
        raise ReleaseCheckError("manifest.json's version isn't a string")
    return parse_version(version)


def has_heading(changelog: str, version: str) -> bool:
    """Whether the changelog has a `## [X.Y.Z]` heading for the version."""
    heading = f"## [{version}]"
    return any(line.startswith(heading) for line in changelog.splitlines())


def changelog_section(changelog: str, version: str) -> str | None:
    """The version's changelog section without its heading, or None if missing or blank."""
    heading = f"## [{version}]"
    lines = changelog.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(heading):
            body: list[str] = []
            for rest in lines[index + 1 :]:
                if rest.startswith("## ["):
                    break
                body.append(rest)
            return "\n".join(body).strip() or None
    return None


@dataclass(frozen=True, slots=True)
class Verdict:
    """Whether a change of the version is a bump, and why."""

    changed: bool
    bump: bool
    version: str
    reason: str


def bump_verdict(
    *, base_manifest: str, head_manifest: str, base_changelog: str, head_changelog: str
) -> Verdict:
    """Whether the head is a bump of the base (spec §3)."""
    base = manifest_version(base_manifest)
    head = manifest_version(head_manifest)
    version = head.text
    if head == base:
        return Verdict(
            False, False, version, f"{version} unchanged: nothing to release"
        )
    if head < base:
        return Verdict(
            True, False, version, f"{version} is lower than {base.text}: not a bump"
        )
    if has_heading(base_changelog, version):
        return Verdict(
            True,
            False,
            version,
            f"CHANGELOG.md already has ## [{version}] before this change: not a bump",
        )
    if changelog_section(head_changelog, version) is None:
        return Verdict(
            True,
            False,
            version,
            f"CHANGELOG.md has no ## [{version}] section with entries: not a bump",
        )
    return Verdict(
        True, True, version, f"{base.text} -> {version}: a bump, release v{version}"
    )


def runs_problems(
    payload: dict[str, Any], required: tuple[str, ...] = REQUIRED_WORKFLOWS
) -> list[str]:
    """What keeps the required workflows' newest push runs from all having passed."""
    newest: dict[str, dict[str, Any]] = {}
    for run in payload.get("workflow_runs", []):
        name = run.get("name")
        if name in required and (
            name not in newest or run["created_at"] > newest[name]["created_at"]
        ):
            newest[name] = run
    problems: list[str] = []
    for name in required:
        run = newest.get(name)
        if run is None:
            problems.append(f"{name}: no push run")
        elif run.get("conclusion") != "success":
            problems.append(f"{name}: {run.get('conclusion') or run.get('status')}")
    return problems


def tag_commit(ls_remote: str, tag: str) -> str | None:
    """The commit a tag points at, from `git ls-remote` output; None if the tag is missing."""
    plain = peeled = None
    for line in ls_remote.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, ref = parts
        if ref == f"refs/tags/{tag}^{{}}":
            peeled = sha
        elif ref == f"refs/tags/{tag}":
            plain = sha
    return peeled or plain


def _git_show(rev: str, path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "show", f"{rev}:{path}"], check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as err:
        raise ReleaseCheckError(
            f"Can't read {path} at {rev}: {err.stderr.strip()}"
        ) from err
    return result.stdout


def _verdict(base: str, head: str) -> Verdict:
    return bump_verdict(
        base_manifest=_git_show(base, MANIFEST),
        head_manifest=_git_show(head, MANIFEST),
        base_changelog=_git_show(base, CHANGELOG),
        head_changelog=_git_show(head, CHANGELOG),
    )


def _write_outputs(values: dict[str, str]) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with Path(path).open("a", encoding="utf-8") as output:
            output.writelines(f"{key}={value}\n" for key, value in values.items())


def _run(args: argparse.Namespace) -> int:
    if args.command == "bump":
        verdict = _verdict(f"{args.commit}^1", args.commit)
        print(verdict.reason)
        _write_outputs(
            {
                "version": verdict.version,
                "tag": f"v{verdict.version}",
                "bump": "true" if verdict.bump else "false",
            }
        )
        return 0
    if args.command == "pr-check":
        verdict = _verdict(args.base, args.head)
        print(verdict.reason)
        return 0 if verdict.bump or not verdict.changed else 1
    if args.command == "runs-green":
        try:
            payload = json.loads(sys.stdin.read())
        except json.JSONDecodeError as err:
            raise ReleaseCheckError("The runs list isn't JSON") from err
        if not isinstance(payload, dict):
            raise ReleaseCheckError("The runs list isn't a JSON object")
        problems = runs_problems(payload)
        for problem in problems:
            print(problem)
        if not problems:
            print("All required workflows passed: " + ", ".join(REQUIRED_WORKFLOWS))
        return 1 if problems else 0
    commit = tag_commit(sys.stdin.read(), args.tag)
    if commit:
        print(commit)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run one subcommand; exit 2 on an error."""
    parser = argparse.ArgumentParser(
        description="Release rules for the release workflows."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "bump", help="Is the commit a bump of its first parent?"
    ).add_argument("commit")
    pr_check = commands.add_parser(
        "pr-check", help="Is a version change from base to head a bump?"
    )
    pr_check.add_argument("base")
    pr_check.add_argument("head")
    commands.add_parser(
        "runs-green", help="Did every required workflow pass? Runs JSON on stdin."
    )
    commands.add_parser(
        "tag-commit", help="The commit a tag points at. git ls-remote on stdin."
    ).add_argument("tag")
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except ReleaseCheckError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```


- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_release_check.py -q`
Expected: all pass.

Run: `uv run pytest tests/test_release_check.py -q --cov=release_check --cov-branch --cov-report=term-missing`
Expected: 100 % of lines and branches in `release_check.py`. This is a local check, not a gate. If something is missed, add a test for it; don't add a `pragma`.

- [ ] **Step 5: Gates and commit**

Run the gates in the Global Constraints.
Commit message:

```text
process: release rules for the release workflows (#64)
```

---

### Task 3: The workflows

**Model:** opus — `.github/workflows/`, tagging and the write token.
**Wave:** 3

**Files:**
- Create: `.github/workflows/auto-release.yml`
- Create: `.github/workflows/version-check.yml`
- Modify: `.github/workflows/release.yml`
- Create: `tests/test_workflows.py`

**Interfaces:**
- Consumes: `release_check.REQUIRED_WORKFLOWS` and the CLI from Task 2; `uv run actionlint` and `uv run zizmor --offline .github/workflows` from Task 1.
- Produces: the workflows named in the Global Constraints.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_workflows.py`:

```python
"""Tests for the structure of the GitHub workflows."""

from pathlib import Path
import re
from typing import Any

import yaml

from release_check import REQUIRED_WORKFLOWS

WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"


def _load(name: str) -> dict[Any, Any]:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _on(workflow: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML reads the key `on:` as the boolean True.
    on = workflow[True]
    assert isinstance(on, dict)
    return on


def _all() -> dict[str, dict[Any, Any]]:
    return {path.name: _load(path.name) for path in sorted(WORKFLOWS.glob("*.yml"))}


def _runs_on_push_to_main(workflow: dict[Any, Any]) -> bool:
    push = _on(workflow).get("push")
    return isinstance(push, dict) and "main" in push.get("branches", [])


def test_required_workflows_match() -> None:
    """The workflows run on a push to main are the ones auto-release waits for."""
    names = sorted(wf["name"] for wf in _all().values() if _runs_on_push_to_main(wf))
    assert names == sorted(REQUIRED_WORKFLOWS)
    assert sorted(_on(_load("auto-release.yml"))["workflow_run"]["workflows"]) == names


def test_required_workflows_have_one_job_named_like_them() -> None:
    """Each required workflow has one job with its name: the required check names on main."""
    for workflow in _all().values():
        if _runs_on_push_to_main(workflow):
            assert list(workflow["jobs"]) == [workflow["name"]]


def test_auto_release_triggers_and_permissions() -> None:
    """auto-release never runs for a PR, and only the release job can write."""
    workflow = _load("auto-release.yml")
    on = _on(workflow)
    assert set(on) == {"workflow_run", "workflow_dispatch"}
    assert on["workflow_run"]["branches"] == ["main"]
    assert set(on["workflow_dispatch"]["inputs"]) == {"sha", "dry_run"}
    assert workflow["permissions"] == {}
    writers = [
        name
        for name, job in workflow["jobs"].items()
        if job.get("permissions", {}).get("contents") == "write"
    ]
    assert writers == ["release"]
    assert workflow["jobs"]["release"]["uses"] == "./.github/workflows/release.yml"


def test_concurrency_group_per_event_and_commit() -> None:
    """One group per event and commit, at workflow level, never cancelling a running release."""
    concurrency = _load("auto-release.yml")["concurrency"]
    assert "github.event.workflow_run.event" in concurrency["group"]
    assert "github.event.workflow_run.head_sha" in concurrency["group"]
    assert concurrency["cancel-in-progress"] is False


def test_release_triggers_and_permissions() -> None:
    """Release runs on a tag push or a call with a tag and a commit."""
    workflow = _load("release.yml")
    on = _on(workflow)
    assert on["push"] == {"tags": ["v*"]}
    assert set(on["workflow_call"]["inputs"]) == {"tag", "sha"}
    assert workflow["permissions"] == {}
    assert workflow["jobs"]["release"]["permissions"] == {"contents": "write"}


def test_release_takes_the_tag_from_inputs() -> None:
    """A called release takes its tag and commit from the inputs, not from the caller's github context."""
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert "inputs.sha || github.ref" in text
    assert "inputs.tag" in text


def test_release_is_shell_only() -> None:
    """release.yml runs no script from the checked-out commit, which may predate it."""
    assert "release_check" not in (WORKFLOWS / "release.yml").read_text(
        encoding="utf-8"
    )


def test_no_github_sha_in_release_workflows() -> None:
    """The release workflows never use the default branch's head as the commit."""
    for name in ("auto-release.yml", "release.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "github.sha" not in text
        assert "GITHUB_SHA" not in text


def test_version_check() -> None:
    """version-check runs on pull_request only, with one job named version-check, against the merge base."""
    workflow = _load("version-check.yml")
    on = _on(workflow)
    assert set(on) == {"pull_request"}
    assert workflow["permissions"] == {}
    assert list(workflow["jobs"]) == ["version-check"]
    assert "git merge-base" in (WORKFLOWS / "version-check.yml").read_text(
        encoding="utf-8"
    )


def test_no_pull_request_target() -> None:
    """No workflow uses pull_request_target."""
    for workflow in _all().values():
        assert "pull_request_target" not in _on(workflow)


def test_no_expressions_inside_run_blocks() -> None:
    """Values reach run: scripts through env:, never as ${{ }} inside the script."""
    for name, workflow in _all().items():
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                assert not re.search(r"\$\{\{", step.get("run", "")), (
                    f"{name}: {step.get('name', step['run'])}"
                )
```

Run: `uv run pytest tests/test_workflows.py -q`
Expected: FAIL. `auto-release.yml` and `version-check.yml` don't exist yet (`FileNotFoundError`), and the other `release.yml` tests fail. `test_required_workflows_have_one_job_named_like_them`, `test_no_pull_request_target`, `test_no_expressions_inside_run_blocks` and `test_release_is_shell_only` may already pass.

- [ ] **Step 2: `release.yml`**

Replace `.github/workflows/release.yml` with:

```yaml
name: release
on:
  push:
    tags: ["v*"]
  workflow_call:
    inputs:
      tag:
        description: The tag to release, v<version>
        required: true
        type: string
      sha:
        description: The commit to release
        required: true
        type: string

permissions: {}

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          ref: ${{ inputs.sha || github.ref }}
          persist-credentials: false
      - name: The tag and the commit
        env:
          INPUT_TAG: ${{ inputs.tag }}
          REF_NAME: ${{ github.ref_name }}
        run: |
          # Called: the tag is an input (a called workflow sees the caller's github context).
          # Pushed: the tag is the pushed ref.
          if [ -n "$INPUT_TAG" ]; then tag="$INPUT_TAG"; else tag="$REF_NAME"; fi
          echo "TAG=${tag}" >> "$GITHUB_ENV"
          echo "COMMIT=$(git rev-parse HEAD)" >> "$GITHUB_ENV"
      - name: Tag must match manifest.json version
        run: |
          version="$(python3 -c 'import json; print(json.load(open("custom_components/nortec_go/manifest.json"))["version"])')"
          test "${TAG}" = "v${version}" || { echo "Tag ${TAG} != v${version}"; exit 1; }
          echo "VERSION=${version}" >> "$GITHUB_ENV"
      - name: Extract release notes from CHANGELOG.md
        run: |
          awk -v v="$VERSION" '
            $0 ~ "^## \\[" v "\\]" {found=1; next}
            found && /^## \[/ {exit}
            found {print}
          ' CHANGELOG.md > notes.md
          grep -q '[^[:space:]]' notes.md || { echo "No CHANGELOG section for $VERSION"; exit 1; }
      - name: Skip a release that exists
        id: existing
        env:
          GH_TOKEN: ${{ github.token }}
          GH_REPO: ${{ github.repository }}
        run: |
          if gh release view "$TAG" > /dev/null 2>&1; then
            echo "Release ${TAG} already exists: nothing to do"
            echo "exists=true" >> "$GITHUB_OUTPUT"
          fi
      - name: The tag must point at the commit
        if: steps.existing.outputs.exists != 'true'
        run: |
          # The repo is public, so ls-remote works without credentials (persist-credentials: false).
          tagged="$(git ls-remote origin "refs/tags/${TAG}" "refs/tags/${TAG}^{}" \
            | awk -v t="refs/tags/${TAG}" '$2 == t "^{}" {p=$1} $2 == t {l=$1} END {print (p != "" ? p : l)}')"
          if [ -n "$tagged" ] && [ "$tagged" != "$COMMIT" ]; then
            echo "Tag ${TAG} points at ${tagged}, not ${COMMIT}"
            exit 1
          fi
      - name: Create the GitHub release
        if: steps.existing.outputs.exists != 'true'
        env:
          GH_TOKEN: ${{ github.token }}
          GH_REPO: ${{ github.repository }}
        run: |
          prerelease=()
          case "$VERSION" in 0.0.*|*-*) prerelease=(--prerelease) ;; esac
          gh release create "$TAG" --target "$COMMIT" --title "$TAG" --notes-file notes.md "${prerelease[@]}"
```

The `python3` in the manifest step is the runner's 3.12. The one-liner is valid there, and it's the same one as today.

- [ ] **Step 3: `auto-release.yml`**

Create `.github/workflows/auto-release.yml`:

```yaml
name: auto-release
on:
  # zizmor: ignore[dangerous-triggers] only successful push runs on main from this repo go on (the decide
  # job's if:), and no PR code runs; see docs/superpowers/specs/2026-09-29-auto-release-design.md §2.1.
  workflow_run:
    workflows: [lint, tests, hassfest, hacs, gitleaks]
    types: [completed]
    branches: [main]
  workflow_dispatch:
    inputs:
      sha:
        description: A commit on main that bumps the version
        required: true
        type: string
      dry_run:
        description: Only log what would happen
        type: boolean
        default: true

permissions: {}

concurrency:
  group: auto-release-${{ github.event.workflow_run.event || 'dispatch' }}-${{ github.event.workflow_run.head_sha || inputs.sha }}
  cancel-in-progress: false

jobs:
  decide:
    if: >-
      (github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main') ||
      (github.event_name == 'workflow_run' &&
       github.event.workflow_run.conclusion == 'success' &&
       github.event.workflow_run.event == 'push' &&
       github.event.workflow_run.head_branch == 'main' &&
       github.event.workflow_run.head_repository.full_name == github.repository)
    runs-on: ubuntu-latest
    permissions:
      contents: read
      actions: read
    outputs:
      version: ${{ steps.bump.outputs.version }}
      tag: ${{ steps.bump.outputs.tag }}
      sha: ${{ steps.commit.outputs.sha }}
      release: ${{ steps.tag.outputs.release }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          ref: main
          fetch-depth: 0
          persist-credentials: false
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7  # v10.2.0
        with:
          python-version: "3.14"
          enable-cache: false
      - name: The commit
        id: commit
        env:
          EVENT_NAME: ${{ github.event_name }}
          RUN_SHA: ${{ github.event.workflow_run.head_sha }}
          INPUT_SHA: ${{ inputs.sha }}
        run: |
          if [ "$EVENT_NAME" = workflow_dispatch ]; then raw="$INPUT_SHA"; else raw="$RUN_SHA"; fi
          sha="$(git rev-parse --verify --quiet "${raw}^{commit}")" || { echo "Not a commit: ${raw}"; exit 1; }
          git merge-base --is-ancestor "$sha" origin/main || { echo "${sha} is not on main"; exit 1; }
          echo "sha=${sha}" >> "$GITHUB_OUTPUT"
      - name: Is it a bump?
        id: bump
        env:
          SHA: ${{ steps.commit.outputs.sha }}
        run: uv run --no-project --python 3.14 python scripts/release_check.py bump "$SHA"
      - name: Did the required workflows pass?
        id: runs
        if: steps.bump.outputs.bump == 'true'
        env:
          GH_TOKEN: ${{ github.token }}
          REPO: ${{ github.repository }}
          SHA: ${{ steps.commit.outputs.sha }}
        run: |
          gh api "repos/${REPO}/actions/runs?head_sha=${SHA}&event=push&per_page=100" > "${RUNNER_TEMP}/runs.json"
          rc=0
          uv run --no-project --python 3.14 python scripts/release_check.py runs-green < "${RUNNER_TEMP}/runs.json" || rc=$?
          case "$rc" in
            0) echo "green=true" >> "$GITHUB_OUTPUT" ;;
            1) echo "Not all required workflows have passed yet: nothing to release in this run" ;;
            *) exit "$rc" ;;
          esac
      - name: The tag
        id: tag
        if: steps.runs.outputs.green == 'true'
        env:
          TAG: ${{ steps.bump.outputs.tag }}
          SHA: ${{ steps.commit.outputs.sha }}
          DRY_RUN: ${{ inputs.dry_run }}
        run: |
          # The repo is public, so ls-remote works without credentials (persist-credentials: false).
          tagged="$(git ls-remote origin "refs/tags/${TAG}" "refs/tags/${TAG}^{}" \
            | uv run --no-project --python 3.14 python scripts/release_check.py tag-commit "$TAG")"
          if [ -n "$tagged" ] && [ "$tagged" != "$SHA" ]; then
            echo "Tag ${TAG} points at ${tagged}, not ${SHA}"
            exit 1
          fi
          if [ "$DRY_RUN" = true ]; then
            echo "Dry run: would release ${TAG} on ${SHA}"
            exit 0
          fi
          echo "release=true" >> "$GITHUB_OUTPUT"

  release:
    needs: decide
    if: needs.decide.outputs.release == 'true'
    permissions:
      contents: write
    uses: ./.github/workflows/release.yml  # zizmor: ignore[self-repository] actionlint and GitHub's documented syntax take ./ (spec §2.3)
    with:
      tag: ${{ needs.decide.outputs.tag }}
      sha: ${{ needs.decide.outputs.sha }}
```

- **`self-repository`:** zizmor suggests `$/.github/workflows/release.yml` for the `uses:` line. Never apply that fix: actionlint rejects it, and the spec and `test_auto_release_triggers_and_permissions` fix `./`. The inline ignore above stays.
- **The zizmor comment:** if zizmor wants the ignore comment on the `workflow_run:` line itself, move it there and keep the reason as a comment above. The same goes for any other finding: fix it where the fix is small; otherwise ignore it inline with a reason and list it in the report.
- **`test_concurrency_group_per_event_and_commit`:** the test looks for the `head_sha` expression in the group, which is there. Don't change the test to fit a different group.

- [ ] **Step 4: `version-check.yml`**

Create `.github/workflows/version-check.yml`:

```yaml
name: version-check
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review, edited]

permissions: {}

jobs:
  version-check:
    if: github.event.pull_request.draft == false
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
        with:
          ref: ${{ github.event.pull_request.head.sha }}
          fetch-depth: 0
          persist-credentials: false
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7  # v10.2.0
        with:
          python-version: "3.14"
          enable-cache: false
      - name: A version change must be a bump
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
        run: |
          # Against the merge base: what this PR changes, even if main has a newer release.
          base="$(git merge-base "$BASE_SHA" "$HEAD_SHA")"
          uv run --no-project --python 3.14 python scripts/release_check.py pr-check "$base" "$HEAD_SHA"
```

- [ ] **Step 5: Tests and linters pass**

Run: `uv run pytest tests/test_workflows.py -q`
Expected: all pass.

Run: `uv run actionlint && uv run zizmor --offline .github/workflows`
Expected: actionlint exits 0; zizmor says `No findings to report` with 2 ignored (`dangerous-triggers`, `self-repository`).

- [ ] **Step 6: The checks before the merge (spec §9)**

Run in the worktree, which has full history:

```bash
uv run --no-project --python 3.14 python scripts/release_check.py bump 9441abd
uv run --no-project --python 3.14 python scripts/release_check.py bump db53bf7
gh api "repos/thomas3650/HA-NortecGo/actions/runs?head_sha=$(git rev-parse 9441abd)&event=push&per_page=100" \
  | uv run --no-project --python 3.14 python scripts/release_check.py runs-green
```

Expected:
1. `0.0.1 -> 0.1.0: a bump, release v0.1.0`.
2. A "not a bump" or "unchanged" line; `db53bf7` has version `0.0.1` like its parent, so `0.0.1 unchanged: nothing to release`.
3. `All required workflows passed: lint, tests, hassfest, hacs, gitleaks`.

Put the three outputs in the report. The `gh api` call is read-only. Tag nothing, dispatch nothing.

- [ ] **Step 7: Gates and commit**

Run the gates in the Global Constraints (the full set, with the coverage gate).
Commit message:

```text
process: tag and publish a release when a merged PR bumps the version (#64)
```

---

### Task 4: Docs and decision log

**Model:** opus — a docs task (D33).
**Wave:** 1 (written against this plan's names; re-checked against the workflows that land)

**Files:**
- Modify: `docs/releasing.md`
- Modify: `docs/decisions.md` (D10's status; append D39)
- Modify: `docs/README.md` (the `releasing.md` row)
- Modify: `docs/way-of-working.md` (§6, *Labels*: the `blocked-ha` label, an owner ruling relayed by the PO)

**Interfaces:**
- Consumes: the names in the Global Constraints, and spec §2 to §6 and §8.
- Produces: docs only.

- [ ] **Step 1: `docs/releasing.md`**

Keep *Versioning*, *Bumping `pynortecgo`* and *Bumping Home Assistant* as they are. Rewrite the middle of the file so that it has these sections, in this order. Match the file's style: short paragraphs and lists, about 110 characters a line, and "the owner" for the person who merges.

1. **`## The bump PR`:** the three steps as today. Then: merging it is the release, and nothing else is needed. Once the five required workflows (`lint`, `tests`, `hassfest`, `hacs`, `gitleaks`) have passed on `main` for the merge commit, `auto-release.yml` tags that commit `vX.Y.Z` and publishes the release through `release.yml`. The `version-check` check on the PR fails if the version changes in a way that wouldn't be released.
2. **`## What counts as a bump`:** in words, spec §3's rule:
   - the version is higher (semver) than in the commit before;
   - the same commit adds the `## [X.Y.Z]` heading;
   - the section has entries.
   Anything else, a revert to an older version included, releases nothing, and the `auto-release` run says why.
3. **`## After a merge`:** check the `auto-release` runs for the merge commit. There are up to five, one per required workflow. Some show as cancelled, and the one that runs after the last workflow does the work. Then check the tag, the release with the changelog section as its notes, and that HACS offers the version.
4. **`## Once, after the auto-release PR merges`:**
   - First, the owner adds `version-check` to `main`'s required status checks (a GitHub setting).
   - Then, to release `0.1.0`, whose bump (`9441abd`) merged before the automation: the owner runs `auto-release` from the Actions tab on `main` with `sha` `9441abd` and `dry_run` on, reads the log, then runs it again with `dry_run` off.
   - Last, the owner checks the tag `v0.1.0` on `9441abd`, the release, and HACS.
   - End with the sentence: "The next bump PR removes this section."
5. **`## Fallbacks`:**
   - A run of `auto-release` from the Actions tab on `main`, with the commit's `sha`, `dry_run` on first. It takes any bump commit on `main` whose required workflows passed, also one merged before the automation. Without the dry run, it tags a release, so it is the owner's action, like a tag by hand.
   - `### Tagging by hand` (renamed from *Tagging (owner only)*; spec §5's *Tagging by hand (fallback)*, shortened because it sits under *Fallbacks*; same commands): for a commit the rule doesn't count as a bump. The pushed tag starts `release.yml`.
6. **`## What release.yml checks`:**
   - It starts in two ways: a pushed `v*` tag, or a call from `auto-release.yml` with the tag and the commit.
   - Keep the two checks and the pre-release rule.
   - Add: a release that exists already means nothing to do, and a tag that exists must point at the commit being released.
7. **`## Required workflows`** (a short paragraph):
   - `auto-release.yml`'s trigger list and `REQUIRED_WORKFLOWS` in `scripts/release_check.py` follow the required status checks on `main`. Each required workflow has one job with the workflow's name, and those names are the checks.
   - `tests/test_workflows.py` fails if a workflow that runs on a push to `main` is added or renamed without them. It doesn't see a change made only in GitHub's settings.

Don't repeat the details that live in the workflows or the script (step names, API paths). Point to the files.

- [ ] **Step 2: `docs/decisions.md`**

In D10, change `**Status:** active` to `**Status:** active; the manual tag superseded by D39`. Change nothing else in D10.

Append after D38:

```markdown
### D39: A merged bump PR is the release
- **Date:** 2026-09-29 · **Status:** active
- **Decision:** When CI passes on `main` for a commit that raises the version and adds its changelog
  section, `auto-release.yml` tags that commit and publishes the release through `release.yml`. A dispatch
  of `auto-release.yml` is the fallback, also for a bump merged before it; tagging by hand is the last one.
- **Why:** The bump PR already holds everything a release needs; the owner still decides when a release goes
  out by merging it.
- **Source:** [auto-release spec](superpowers/specs/2026-09-29-auto-release-design.md), Decisions and §2
```

- [ ] **Step 3: `docs/README.md`**

In the map, the `releasing.md` row's *Contents* cell becomes:

```text
The bump PR, the automatic release, fallbacks and tagging by hand, what `release.yml` checks
```

- [ ] **Step 4: `docs/way-of-working.md`, the `blocked-ha` label**

The owner's ruling (relayed by the PO on 2026-09-29; not in the spec). In §6, the *Labels* bullet, insert this
sentence after the one that ends "…(a merge closes the issue).", before "When in doubt, ask the owner (D30).":

```text
`blocked-ha` ("Waits for a Home Assistant release") goes on an issue that can't move until a Home Assistant
release, for example #55.
```

Re-wrap the bullet to the file's line length.

- [ ] **Step 5: Check and commit**

Run: `uv run pre-commit run --files docs/releasing.md docs/decisions.md docs/README.md docs/way-of-working.md`
Expected: Passed.
Commit message:

```text
docs: the bump PR is the release, and the blocked-ha label (#64)
```
