# Session names that collide across projects — design

Date: 2026-10-02 · Branch: `process/session-names` · Issue: #53

## Goal

- **What:** the PO flow tells this repo's sessions from another project's by the directory a session runs
  in, not by its name alone. A new read-only script, `scripts/sessions.py`, answers two questions: which
  running sessions belong to this repo, and whether a name can be messaged safely. The start scripts, the
  PO's start check and the team lead's sends to `po` use it. The session names don't change.
- **Why:** the flow names its sessions `po`, `team-lead` and `tl-<topic>`, and `claude agents --json` and
  `ListAgents` list the sessions of every project on the machine (#53). So a session named `po` or
  `team-lead` in another repo makes `scripts/po` and `scripts/team-lead` refuse to start, and a team
  lead's `SendMessage` to `po` can reach another repo's PO.
- **Not in this work:**
  - new session names (a repo prefix): see *Decisions*, and *Known limit*;
  - two repos that run a PO flow with the same names at the same time: messages are held, not
    misdelivered, and that is all (*Known limit*);
  - the PO's sends to `tl-<topic>`: the issue names the send to `po`, a topic name is specific to one
    issue, and the same limit covers a clash;
  - `.claude/settings.json`, the guard hook, `.pre-commit-config.yaml`, `.github/workflows/` and the hard
    rules in `CLAUDE.md`. If the work turns out to need one of them, it stops and goes to the PO as
    `blocked`;
  - `CLAUDE.md`: its *Layout* line on `scripts/` names examples, not an inventory.
- **Done when:** the script and its tests are in, the two start scripts use it, §8 and the two agent files
  hold the text in *Design*, D49 is in `decisions.md`, and the gates pass.

## Decisions

Proposed by the team lead; the PO chose option A on 2026-10-02, **for the owner's review** on the PR (the
owner is away, and this PR is owner-merge: it edits `.claude/agents/`).

| Topic | Decision |
|---|---|
| How sessions are told apart | By the `cwd` in `claude agents --json`: a session belongs to this repo when its `cwd` is inside a checkout of this repository (option A). The names stay `po`, `team-lead` and `tl-<topic>` |
| "Inside a checkout of this repository" | The session's `cwd` and the script's own directory have the same git common directory. This covers the main checkout and every linked worktree, wherever it is on disk. A path prefix doesn't: the issue worktrees are not under the main checkout, and the two directory names share a prefix |
| One home for the rule | `scripts/sessions.py`. The start scripts and the agents call it; none of them repeats the rule |
| The start scripts | Refuse only for a session named `po` or `team-lead` *of this repo* |
| The team lead's send to `po` | Before each `SendMessage` to `po`, the team lead checks that exactly one running session on the machine is named `po` and that it is this repo's. If not, the message counts as failed: keep it and wait, as for a PO that is down |
| The PO's start | The `team-lead` check uses the script instead of `ListAgents`. The PO also checks that its own name can be messaged, and tells the owner if another project's `po` is in the way |
| Decision log | D49, last in `decisions.md` |
| Title | `process: the PO flow tells its sessions from other projects' (#53)`; non-releasing, so no `CHANGELOG.md` entry and no bump |

Options that were not chosen:

| Option | Why not |
|---|---|
| B. A repo prefix on the names (`ha-po`, `ha-team-lead`, `ha-tl-<topic>`) | It fixes both problems and lets two repos run a PO flow at once. But every name in §8, both agent files and both scripts change, and the sessions running at merge time keep their old names, so it needs a transition: the scripts know both sets of names, the team lead takes the PO's address from its start prompt, and `.git/po-sessions.json` holds old names. A prefix is also only a convention: another project can pick the same one |
| C. Both A and B | The most robust, and the most change: B's cost plus A's script |

**Known limit.** Two projects on one machine can't both run a PO flow with these names at the same time.
While another project's session named `po` runs, this repo's team leads hold their messages; none is
delivered to the wrong PO. The PO sees this at its start and tells the owner. A repo prefix (option B) is
the next step if two flows at once are ever wanted.

## Facts used

Checked on 2026-10-02, read-only: no session was started, stopped or renamed.

- `claude agents --json` prints an array of the running sessions, interactive and background, of every
  project on the machine. Each row has `name`, `cwd`, `kind`, `sessionId`, `pid`, `status` and
  `startedAt`.
- `ListAgents` shows a name and a `[ref]` per session, and no directory. The ref is not part of the
  `sessionId`. So an agent can't learn from `ListAgents` which project a session belongs to.
- `SendMessage` addresses a session by name. When one running session has the name, the message is
  delivered. When two have it, the bare name is not enough and the send asks for a ref.
- So the wrong delivery happens when this repo's PO is down and another project's `po` runs: the send
  succeeds, and the team lead's keep-and-wait rule never starts. With both running, the send fails, and
  the team lead can't pick the right ref.
- `claude agents --cwd <path>` is documented for background sessions only. The script filters the JSON
  itself.
- Neither `.claude/settings.json` nor the guard hook names a session.
- The two start scripts hold the same inline Python that collects every `name` in the JSON. They have no
  tests.
- `uv run python` in a directory without a project still gives the project's Python version (3.14) on
  this setup, under `uv run pytest` and outside it. So a test can run a copy of the scripts in a temporary
  repository.
- `scripts/release_check.py` is the precedent for a Python script: listed in mypy's `files` in
  `pyproject.toml`, linted by ruff, imported by its tests (`pythonpath = ["scripts"]`).

## Design

### `scripts/sessions.py`

Standard library only, read-only: it runs `claude agents --json` and `git rev-parse`, and writes nothing.
It is run as `uv run python scripts/sessions.py <command>`, from any directory.

- **This repo** is the git common directory of the script's own directory:
  `git -C <script dir> rev-parse --path-format=absolute --git-common-dir`.
- **A session is ours** when the same command, run with `-C <the session's cwd>`, gives the same
  directory (both resolved, so a symlink doesn't matter). A session whose `cwd` is missing from the row,
  no longer exists, or is not in a git repository, is not ours; none of these is an error.

| Command | Prints | Exit code |
|---|---|---|
| `running [NAME…]` | The names of this repo's running sessions, one per line, sorted. With names given, only those of them that run | 0 |
| `reachable NAME` | Nothing on stdout. On exit 1, one line on stderr with the reason | 0 when exactly one running session on the machine has the name and it is ours; 1 otherwise |

Reasons for `reachable` exit 1: no session has the name; the one that has it belongs to another project;
more than one has it.

Exit 2, with one line on stderr, when `claude agents --json` fails or doesn't print a JSON array of
objects, or when the script's own directory is not in a git repository. A session without a `name` is
skipped.

The script never prints a `cwd` or a session id: its output can end up in a PR or an issue (hard rule 3).

### `scripts/po` and `scripts/team-lead`

The inline Python goes. Both scripts ask
`uv run python scripts/sessions.py running po team-lead` (after their `cd` to the repo root) and refuse,
with today's message and exit code 2, when it prints a name. Under `set -e`, an exit 2 of the script stops
the start, as a failing `claude agents --json` does today. The worktree check and the `exec` line don't
change.

### `.claude/agents/team-lead.md`

In *Your mode*, **PO mode**, the sentence on a failed send becomes (the plan fixes the line breaks):

```text
Before each `SendMessage` to `po`, run `uv run python scripts/sessions.py reachable po`; if it fails, don't
send: the message counts as failed. If a `SendMessage` to `po` fails, keep that message and wait (don't
poll for the PO); when the PO's `hello` arrives, re-send every message that failed, in order, with the
same check.
```

### `.claude/agents/po.md`

Start step 2 becomes:

```text
2. Run `uv run python scripts/sessions.py running team-lead`. If it prints `team-lead`, the owner is in
   team lead mode: say so and do nothing else. Then run `uv run python scripts/sessions.py reachable po`.
   If it fails, tell the owner why: until it passes, team leads hold their messages (§8, *Sessions of this
   repo*).
```

### `docs/way-of-working.md` §8

Four edits; the plan fixes the line breaks.

1. *Roles and start modes*, **Team lead mode**: "refuse to start while a session named `po` or `team-lead`
   runs" becomes "refuse to start while a session of this repo named `po` or `team-lead` runs", and "no
   session named `team-lead` runs" becomes "no session of this repo named `team-lead` runs".
2. A new bullet in *Roles and start modes*, after **Team lead mode**:

   ```text
   - **Sessions of this repo:** the session names are not unique on the machine: `claude agents --json` and
     `ListAgents` list the sessions of every project. A session is this repo's when it runs in the main
     checkout or one of its worktrees; `scripts/sessions.py` is the one place that decides it (D49). The
     start scripts count only this repo's sessions. A team lead sends to `po` only when
     `scripts/sessions.py reachable po` passes (exactly one running session is named `po`, and it is this
     repo's); otherwise the message counts as failed. So while another project's session named `po` runs,
     team leads hold their messages, and the PO tells the owner at its start. Two projects can't both run a
     PO flow with these names at once.
   ```
3. *After ready, the loop, and failures*, **State**: "`claude agents --json` shows the running sessions,
   interactive and background" becomes "`claude agents --json` shows the running sessions of every
   project, interactive and background (`scripts/sessions.py running` those of this repo)".
4. The same section's last bullet: after "A `SendMessage` to a PO that is down fails at once; it isn't
   queued.", add "One that the check in *Sessions of this repo* stops counts as failed too."

PR #103, not merged yet, edits the same section. Edits 3 and 4 touch sentences near its changes, so a
merge of `origin/main` can conflict there; it is resolved by keeping both texts.

### `docs/decisions.md`

```markdown
### D49: The PO flow's sessions are told apart by their directory
- **Date:** 2026-10-02 · **Status:** active
- **Decision:** A session belongs to this repo when its `cwd` is in the main checkout or one of its
  worktrees; `scripts/sessions.py` decides it. The start scripts count only this repo's sessions, and a
  team lead sends to `po` only when exactly one running session has that name and it is this repo's. The
  session names stay `po`, `team-lead` and `tl-<topic>`.
- **Why:** The names are not unique on the machine (#53). Filtering by directory changes no name, so
  running sessions keep working; a repo prefix needs a transition and is the next step if two projects
  ever run a PO flow at once.
- **Source:** [session names spec](superpowers/specs/2026-10-02-session-names-design.md), Decisions
```

D48 is taken by PR #103. D49 goes last, and the merge of `origin/main` brings D48 in before it.

### Tests

`tests/test_sessions.py`. Nothing calls the real `claude`: every test either passes the JSON in, or puts a
stub `claude` first on `PATH`. The repositories are made with `git init` under `tmp_path`, and the session
names and paths in the tests are invented.

- **The rule**, on `sessions.py` imported as a module, with two temporary repositories, a linked worktree
  of the first, and a plain directory:
  - a session in the main checkout, in a linked worktree, and in a subdirectory of either is ours;
  - a session in the other repository, in the plain directory, in a directory that doesn't exist, and one
    with no `cwd` is not ours;
  - `running` with and without names; a row without a `name` is skipped;
  - `reachable`: exit 0 for one session of ours; exit 1 for none, for one of another project, and for two
    with the name (ours and another's), each with its reason;
  - exit 2 when the stub `claude` fails, and when it prints something that isn't a JSON array.
- **The start scripts**, for both `scripts/po` and `scripts/team-lead`, as copies in a temporary
  repository (in the real checkout a test may itself run in a linked worktree, which the scripts refuse):
  - a `po` or `team-lead` session of that repository: exit 2, the message names it, and the stub records
    no start;
  - the same names in another repository only: the stub records the start, with the arguments the script's
    `exec` line gives;
  - a linked worktree of the temporary repository: exit 2, as today.

The stub prints canned JSON for `agents --json` and records any other call's arguments to a file.

## Execution shape

| Task | Wave | Model | Files | Guarded files |
|---|---|---|---|---|
| 1 | 1 | sonnet | `scripts/sessions.py`, `tests/test_sessions.py`, `scripts/po`, `scripts/team-lead`, `pyproject.toml` (mypy's `files`) | none |
| 2 | 2 | opus (docs, D33) | `docs/way-of-working.md`, `docs/decisions.md`, `.claude/agents/po.md`, `.claude/agents/team-lead.md` | `.claude/agents/po.md`, `.claude/agents/team-lead.md` |

Task 2 is in wave 2, not ahead of its inputs: a task with a `Guarded files:` line never starts ahead
(§1, *Starting ahead of inputs*). Each wave has one task, so both run in the issue worktree,
`<HA-NortecGo-wt>/session-names`.

Checks on the branch: the gates (`CLAUDE.md` → *Commands*), and the script run once for real, read-only,
by the team lead: `running` and `reachable po` from the issue worktree. What they print is not copied into
the PR (hard rule 3, §8 *Public text*); the PR says only that they ran and whether they agreed with the
sessions the team lead knew of.

`visible: no` (nothing changes in Home Assistant).

## Risks

- **The live sessions.** The PO and the team leads running at merge time have the old agent files in
  their context. Nothing they rely on changes: the names, the messages and `.git/po-sessions.json` stay.
  They get the new checks at their next start.
- **A resumed session in a worktree that is gone.** Its `cwd` no longer exists, so it is not counted as
  ours. The PO re-creates the issue worktree before it resumes a team lead (§8), so a running team lead's
  directory exists.
- **`cwd` is the session's start directory or its current one.** Either is inside a checkout of this repo
  for the flow's sessions: the PO works in the main checkout, a team lead in its issue worktree and its
  task worktrees.
- **Both POs run.** Team leads hold every message until the other project's `po` stops (*Known limit*).
  The PO's start check makes it visible; nothing resolves it automatically.
- **The check and the send are two steps.** A session named `po` can start or stop between them. The gap
  is a moment, and the failure it leaves is the one that exists today.
- **`claude agents --json` changes shape.** The script exits 2, the start scripts refuse to start, and a
  team lead holds its message. The tests pin the shape the script reads.
