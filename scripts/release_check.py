"""Release rules for the release workflows and the bump step (docs/releasing.md).

Stdlib only. The workflows run it with `uv run --no-project --python 3.14`.
"""

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

MANIFEST = "custom_components/nortec_go/manifest.json"
CHANGELOG = "CHANGELOG.md"
REQUIRED_WORKFLOWS: tuple[str, ...] = ("lint", "tests", "hassfest", "hacs", "gitleaks")
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

_VERSION = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)
_PLAIN_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
_TITLE = re.compile(r"(?P<type>[a-z]+)(?:\((?P<scope>[^()\s]+)\))?(?P<bang>!)?: \S.*")
_HEADING = re.compile(r"## \[(?P<name>[^\]]+)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?")
_MANIFEST_VERSION = re.compile(r'("version"\s*:\s*")[^"]*(")')


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
        "pr-check", help="Do the PR's title, version and changelog agree?"
    )
    pr_check.add_argument("--title", required=True)
    pr_check.add_argument("base")
    pr_check.add_argument("head")
    commands.add_parser(
        "release-pr", help="The bump step: bump the version and move Unreleased."
    ).add_argument("--title", required=True)
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
