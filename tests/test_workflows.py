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


def test_release_workflows_run_bash_with_pipefail() -> None:
    """`shell: bash` makes run steps use -eo pipefail, so a failed git ls-remote in a pipe fails the step."""
    for name in ("auto-release.yml", "release.yml", "version-check.yml"):
        assert _load(name)["defaults"] == {"run": {"shell": "bash"}}, name
