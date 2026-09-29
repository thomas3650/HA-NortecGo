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
