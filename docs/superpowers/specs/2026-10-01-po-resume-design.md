# Resuming a team lead keeps its name, and a waiting lead that exited — design

Date: 2026-10-01 · Branch: `docs/po-resume` · Issue: #89

## Goal

- **What:** `way-of-working.md` §8 records two things learned while running the PO flow: the resume command
  needs `-n tl-<topic>` to keep the team lead's name, and a background team lead that is idle while it waits
  for the PO's reply can exit and is then resumed with that reply.
- **Why:** both were found by running the flow and are not written down (#89). Without the first, a resumed
  team lead can't be messaged under its name. Without the second, a PO reads a waiting team lead that exited
  as a failed one and spends the one resume §8 allows.
- **Not in this work:**
  - the line on a team lead with nothing new in `claude logs <id>` for 2 loops (it can also hit a team lead
    that only waits, or one that has exited; named in the learnings step, for the PO to file as an issue);
  - which goes first when a slot frees, the resume of a waiting team lead or a new issue: §8 orders only
    the resumes for ready PRs (*Merging*, **The queue**). An ordering here is a new rule and the owner's to
    decide (the PO's ruling on #89), so it goes in the same follow-up issue;
  - a team lead that exits while it waits for the PO's `hello` after a PO restart (the same follow-up
    issue);
  - `.claude/agents/`, `scripts/`, `CLAUDE.md` and `decisions.md` (see *Facts used*);
  - any new rule beyond the two points in the issue.
- **Done when:** §8 *After ready, the loop, and failures* holds the two edits in *Design*, the search in
  *Execution shape* gives the one hit named there, and the gates pass.

## Decisions

Proposed by the team lead and approved by the PO (issue #89, 2026-10-01).

| Topic | Decision |
|---|---|
| Where | Only `docs/way-of-working.md` §8, *After ready, the loop, and failures* |
| The resume command | It gets `-n tl-<topic>`, as the start command in *Picking and starting an issue* has |
| Which reply | The PO's reply to any of the team lead's messages (§8 *Messages*): an answer, an approval or points sent back, a D-number, a decision or a finding, whoever gave it (the owner's, relayed, or the PO's own) |
| The one resume | Resuming a waiting team lead that exited is not the "resumed once" of a team lead that is gone |
| The cap | The resume waits for a free slot, as the resume for a ready PR does. This restates "at most 2" team leads; it is no new rule. Which goes first when a slot frees is left open (*Not in this work*) |
| One command | Every resume in the section uses the one resume command, with `-n`, also the "resumed once" resume, whose bullet names no command today |
| Decision log | No entry: both points record how the tools behave and what worked, and the issue scopes them. No lasting decision is made |
| Title | `process: a resumed team lead keeps its name (#89)` (the type earlier PO-flow changes used; the branch name stays); non-releasing, so no `CHANGELOG.md` entry and no bump |

Facts used:

- From the issue, seen while running the PO flow on 2026-09-30 and 2026-10-01: a team lead resumed without
  `-n` came back under a generated `ListAgents` name, and messages to `tl-<topic>` stopped reaching it;
  resuming with `-n tl-<topic>` kept the name (confirmed twice). A background team lead that was idle,
  waiting for an owner answer, exited; nothing was lost, and resuming it with the answer in the prompt
  worked.
- What keeps a waiting team lead's work is its issue worktree, not a push: before the draft PR (§1 step 6)
  the spec and plan are not pushed, and may not be committed.
- `claude --help` gives the usage as `claude [options] [command] [prompt]`, so a resume takes a prompt after
  its options.
- The resume command is written in one place in the repo, outside `docs/superpowers/`: §8 *After ready, the
  loop, and failures*. `.claude/agents/po.md` and `team-lead.md`, `scripts/po`, `scripts/team-lead` and
  `docs/notes.md` don't hold it, so none of them changes.
- The issue worktree of a team lead that waits is in place: before `gh pr ready` the PO hasn't removed it,
  and for a team lead resumed after ready the PO re-created it for that resume.
- `claude --help` says `--bg` with `--resume` starts a copy when the session is already running. So the PO
  resumes only a team lead that `claude agents --json` no longer shows (§8 *State* names that command).
- A team lead that exited doesn't run, so *Picking and starting an issue* ("when fewer than 2 team leads
  run") lets the PO start another one in the meantime.
- No test reads the text of `way-of-working.md`.

## Design

Both edits are in `way-of-working.md` §8, *After ready, the loop, and failures*. The wording below is the
text to land; the task may change line breaks only.

### 1. The resume command keeps the name

In the first bullet, the command becomes:

```text
claude --bg --permission-mode auto --resume <session-id> -n tl-<topic>
```

The paragraph that closes that bullet ("Conflicts are fixed by merging `origin/main` in, … A resumed team
lead starts without its old SDD ledger.") gets one more sentence:

```text
The `-n` keeps its name: without it the resumed session gets a generated `ListAgents` name, and messages to
`tl-<topic>` no longer reach it. Every resume in this section uses this resume command, run in the team
lead's issue worktree.
```

### 2. A waiting team lead that exited

A new bullet, right after the bullet "A team lead that is gone is resumed once; …", which itself doesn't
change:

```text
- A background team lead that is idle while it waits for the PO's reply to one of its messages can exit
  (`claude agents --json` no longer shows it). Nothing is lost: its issue worktree is still in place. When
  the reply is there and a slot is free, the PO resumes it with the resume command, the reply as the prompt
  after the options. This is not the one resume of a team lead that is gone: that one is still there if the
  team lead fails later.
```

The resume command itself is written once, in the first bullet (§7, *No duplication*).

## Execution shape

Docs only: no code and no tests change. One docs task, so `Model: opus` (D33).

| Task | Wave | Files | Guarded files |
|---|---|---|---|
| 1 | 1 | `docs/way-of-working.md` | none |

It runs in the issue worktree; a wave of one task needs no task worktree.

Checks, on the task and on the branch: the gates (`CLAUDE.md` → *Commands*), and this search:

```bash
git grep -n -A1 -e '--resume' -- . ':!docs/superpowers' ':!uv.lock'
```

It gives one hit, in `docs/way-of-working.md`, and one of the two lines it prints holds `-n tl-<topic>`.

`visible: no` (nothing changes in Home Assistant).

## Risks

- **A later `claude` version changes how `--resume` and `-n` work together.** The doc states what was seen;
  a PO that finds otherwise raises it as a learning (§1 step 8).
- **The new bullet is read as a way around "resumed once".** It covers only a team lead that was waiting
  for the PO's reply when it exited (it has a message the PO hasn't replied to); one that is gone in the
  middle of its work is still the failure case.
