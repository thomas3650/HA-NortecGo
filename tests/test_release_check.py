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
