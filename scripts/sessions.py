"""Tell this repository's running Claude sessions from other projects' (docs/way-of-working.md §8, D49).

Read-only: it runs `claude agents --json` and `git rev-parse`, and writes nothing. It never prints a
session's directory or id, on stdout or stderr.
"""

import argparse
from collections.abc import Sequence
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
DROPPED_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")


class SessionsError(Exception):
    """The sessions can't be listed. The message is the script's own text and safe to print."""


def common_dir(directory: Path) -> Path | None:
    """Return the git common directory of the repository `directory` is in, or None if it is in none."""
    env = {
        key: value for key, value in os.environ.items() if key not in DROPPED_GIT_ENV
    }
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(directory),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    except OSError:
        return None
    path = result.stdout.strip()
    if result.returncode != 0 or not path:
        return None
    return Path(path).resolve()


def repo_of(anchor: Path) -> Path:
    """Return the git common directory that stands for this repository."""
    repo = common_dir(anchor)
    if repo is None:
        raise SessionsError("sessions: this script is not in a git repository.")
    return repo


def parse_sessions(text: str) -> list[dict[str, Any]]:
    """Parse the output of `claude agents --json`."""
    try:
        rows = json.loads(text)
    except ValueError as err:
        raise SessionsError(
            "sessions: `claude agents --json` did not print JSON."
        ) from err
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise SessionsError(
            "sessions: `claude agents --json` did not print an array of objects."
        )
    return rows


def load_sessions() -> list[dict[str, Any]]:
    """Run `claude agents --json` and return its rows. Its stderr is captured and never passed on."""
    try:
        result = subprocess.run(
            ["claude", "agents", "--json"], capture_output=True, text=True, check=False
        )
    except OSError as err:
        raise SessionsError(
            "sessions: `claude agents --json` could not be run."
        ) from err
    if result.returncode != 0:
        raise SessionsError("sessions: `claude agents --json` failed.")
    return parse_sessions(result.stdout)


def is_ours(row: dict[str, Any], repo: Path) -> bool:
    """Say whether the session in `row` runs in a checkout of the repository `repo` stands for."""
    cwd = row.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return False
    return common_dir(Path(cwd)) == repo


def running(
    rows: Sequence[dict[str, Any]], names: Sequence[str] = (), anchor: Path = HERE
) -> list[str]:
    """Return the names of this repository's sessions, sorted, each once; only `names` if any are given."""
    repo = repo_of(anchor)
    ours = {
        row["name"]
        for row in rows
        if isinstance(row.get("name"), str) and is_ours(row, repo)
    }
    if names:
        ours &= set(names)
    return sorted(ours)


def unreachable_reason(
    rows: Sequence[dict[str, Any]], name: str, anchor: Path = HERE
) -> str | None:
    """Return why `name` can't be messaged safely, or None when exactly one session has it and it is ours."""
    repo = repo_of(anchor)
    named = [row for row in rows if row.get("name") == name]
    if not named:
        return f"sessions: no running session is named {name}."
    if len(named) > 1:
        return f"sessions: {len(named)} running sessions are named {name}."
    if not is_ours(named[0], repo):
        return f"sessions: the session named {name} belongs to another project."
    return None


def main(argv: Sequence[str] | None = None, anchor: Path = HERE) -> int:
    """Run a command; return 0, 1 (`reachable` says no) or 2 (the sessions can't be listed)."""
    parser = argparse.ArgumentParser(prog="sessions", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    running_parser = commands.add_parser(
        "running", help="print the names of this repo's running sessions"
    )
    running_parser.add_argument(
        "names", nargs="*", help="print only these names, if they run"
    )
    reachable_parser = commands.add_parser(
        "reachable", help="exit 0 if exactly one session has the name and it is ours"
    )
    reachable_parser.add_argument("name")
    args = parser.parse_args(argv)
    try:
        rows = load_sessions()
        if args.command == "running":
            for name in running(rows, args.names, anchor):
                print(name)
            return 0
        reason = unreachable_reason(rows, args.name, anchor)
    except SessionsError as err:
        print(err, file=sys.stderr)
        return 2
    if reason is not None:
        print(reason, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
