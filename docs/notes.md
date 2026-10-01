# Notes

Small learned facts that fit no other doc, newest last. When a topic passes about three entries, propose
moving it to its own doc. Home Assistant and HACS facts live in [`ha-notes.md`](ha-notes.md).

## 2026-09-26: Interaction limit

Issues and PRs from non-collaborators are blocked by a GitHub interaction limit (collaborators only), which
expires after six months. Renew it with:

`gh api -X PUT repos/thomas3650/HA-NortecGo/interaction-limits -f limit=collaborators_only -f expiry=six_months`

Check the current limit and its expiry with `gh api repos/thomas3650/HA-NortecGo/interaction-limits`.

Set on 2026-09-26; expires 2027-03-26.

## 2026-09-26: CI images aren't pinned

The workflow actions are pinned to commit SHAs, but `hacs/action` runs the Docker image
`ghcr.io/hacs/action:main` and the hassfest action runs `ghcr.io/home-assistant/hassfest` unpinned, so their
checks can change without a change here. That's why both also run weekly. The hassfest action itself is
pinned to a `master` commit SHA, which Dependabot can't bump; refresh it by hand if the weekly run breaks.

## 2026-09-26: The push-to-`main` deny rule matches too much

`.claude/settings.json` denies `git push` commands that name `main`. In practice it also refuses a push
chained with anything that mentions `main` later (`gh pr create --base main`, `git fetch origin main:main`).
Run `git push` as its own command.

## 2026-09-28: EV Smart Charging doesn't re-send *off*

EV Smart Charging compares its schedule with its own remembered state (`auto_charging_state`), not with the
charger switch's state. If the switch goes back on after an *off*, it doesn't send *off* again until its
schedule changes, so a turn-off that fails silently isn't retried. Found while looking at #32.

## 2026-09-28: Background Claude sessions

`claude --bg` ignores agents defined inline with `--agents '<json>'` ("no agent named …"); an interactive
session accepts them. Agent files in the checkout's `.claude/agents/` work for both. A `--bg` session starts
in auto mode unless `--permission-mode` says otherwise. Found in the checks for #50.

## 2026-09-29: Workflow scripts need Python 3.14

The runner's `python3` is 3.12, but the repo is formatted for 3.14 (`ruff format` writes `except A, B:`, a
syntax error before 3.14). A repo Python script run by a workflow goes through `astral-sh/setup-uv` with
`python-version: "3.14"` and `uv run --no-project --python 3.14`, as `auto-release.yml` and
`version-check.yml` do. Found in #64.

## 2026-09-29: GitHub Actions behaviour for release workflows

- A tag or release made with `GITHUB_TOKEN` starts no other workflow, except `workflow_dispatch` and
  `repository_dispatch`; a reusable workflow called with `workflow_call` runs inside the caller's run, so
  it isn't affected.
- In a `workflow_run` run, `GITHUB_SHA` and `github.ref` are the default branch's head; the tested commit
  is `github.event.workflow_run.head_sha`.
- A called (reusable) workflow sees the caller's `github` context, so `github.ref_name` there is the
  caller's ref, not a tag; take such values from `inputs`.
- A concurrency group keeps one running and one pending run; a new run cancels the pending one.
- zizmor's `self-repository` fix (`uses: $/...`) is rejected by actionlint; keep `./` and ignore the finding
  inline.
- A `run:` step without `shell:` runs `bash -e` without `pipefail`; `shell: bash` (or
  `defaults.run.shell: bash`) adds `-o pipefail`.
- Creating a release with a new tag on a commit whose workflows differ from `main`'s head needs a permission
  `GITHUB_TOKEN` can't have: see [`releasing.md`](releasing.md#when-a-release-fails).
- A re-run replays the original run's commit and workflow files, so a fix to a workflow file never reaches
  it: see [`releasing.md`](releasing.md#when-a-release-fails).

The detail is in the [auto-release spec](superpowers/specs/2026-09-29-auto-release-design.md), *Facts used*.
Found in #64.

## 2026-09-29: zsh modifiers after `$var:`

The Bash tool's shell is zsh, where `"$r:path"` applies a `:` modifier to `$r` (`"$r:custom…"` is `$r` with
`:c` applied). Write `"${r}:path"`, for example `git show "${rev}:CHANGELOG.md"`. Found in #64.

## 2026-09-30: `pre-commit validate-config` needs the file name

Without a file name, `pre-commit validate-config` checks nothing and exits 0. Name the file:
`uv run pre-commit validate-config .pre-commit-config.yaml`. Found in #45.

## 2026-10-01: A scratch copy of the tree for a subagent

The subagent guard refuses a Bash command whose text names `.env`, even in an exclude list (a copy command
that leaves it out, say). A reviewer that tries a plan's code makes its scratch copy with `git archive HEAD`,
unpacked into a directory outside the repo: it holds only tracked files. Found in #40.

## 2026-10-01: A subagent's one-liner and guarded paths

The subagent guard refuses a subagent's `python -c` or `perl -e` command whose text names a guarded path
(`.claude/`, `.git/` or `.pre-commit-config.yaml`), even when the code only reads the file. The message
names the command as it was called, for example "python3 may write a guarded path". A reviewer reads such a
file with the Read tool or `git show`, and leaves a check that needs code (parsing an agent file's
frontmatter, say) to the controller. Found in #84.

## 2026-10-01: A piped gate hides its exit code

A gate piped through `tail` or `grep` ends with that command's exit code, so a failing gate can look green.
Run the gates unpiped, or read the gate's own status (in zsh, `${pipestatus[1]}`). Found in #40.
