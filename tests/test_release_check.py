"""Tests for the release rules in scripts/release_check.py."""

import io
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
from typing import Any

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
    """A malformed title is an error: exit 2, files untouched."""
    before = _read(work)
    assert main(["release-pr", "--title=Bump the uv group"]) == 2
    assert _read(work) == before


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


@pytest.mark.parametrize("missing", ["CHANGELOG.md", str(MANIFEST_PATH)])
def test_release_pr_missing_file(
    work: Path, missing: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing file is an error (exit 2), and the other file is left as it was."""
    (work / missing).unlink()
    other = work / (str(MANIFEST_PATH) if missing == "CHANGELOG.md" else "CHANGELOG.md")
    before = other.read_text(encoding="utf-8")
    assert main(["release-pr", "--title=fix: a fix"]) == 2
    assert f"error: Can't read {missing}" in capsys.readouterr().err
    assert other.read_text(encoding="utf-8") == before


def test_release_pr_unwritable_manifest(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file that can't be written is an error (exit 2); the manifest is written first, so nothing changes."""
    manifest = work / MANIFEST_PATH
    manifest.chmod(0o444)
    before = _read(work)
    try:
        assert main(["release-pr", "--title=fix: a fix"]) == 2
    finally:
        manifest.chmod(0o644)
    assert f"error: Can't write {MANIFEST_PATH}" in capsys.readouterr().err
    assert _read(work) == before


def test_release_pr_without_a_repository_root(
    work: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When git can't name the repository root, the bump is an error and writes nothing."""
    real_run = subprocess.run

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(args, 128, "", "fatal: no root")
        return real_run(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    before = _read(work)
    assert main(["release-pr", "--title=fix: a fix"]) == 2
    assert (
        "error: Can't find the repository root: fatal: no root"
        in capsys.readouterr().err
    )
    assert _read(work) == before


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
