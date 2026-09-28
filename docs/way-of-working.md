# Way of working

How changes are made in this repo. This is the one home for the process: `CLAUDE.md` imports it, and agents
and skills point here rather than copying it. Hard rules live in `CLAUDE.md`, and decisions in
[`decisions.md`](decisions.md).

## 1. Flow for non-trivial changes

1. **Issue:** a user story.
2. **Branch:** `<type>/<topic>`, where the type is `feat`, `fix`, `docs`, `chore` or `process`.
   Label the issue `active` (see §6 *Labels*).
3. **Brainstorm:** `superpowers:brainstorming`.
4. **Spec** in `docs/superpowers/specs/`, then `full-reviewer` until Ready.
5. **Plan:** `superpowers:writing-plans`, in `docs/superpowers/plans/`, with a `Model:` tag on every task
   (and a `Guarded files:` line where needed; see §5) and a `Wave:` number on every task, written for
   parallel work (see [Parallel waves](#parallel-waves)). Then `full-reviewer` until Ready. The `ruff-format`
   hook reformats Python blocks in Markdown, so a fragment that isn't a whole statement (parametrize rows,
   say) goes in a `text` block.
6. **Draft PR:** once the spec and plan are both Ready, commit them, push, and open a **draft** PR with
   `Closes #n` and links to the spec and plan. The owner reviews the spec and plan there.
7. **Execute:** `superpowers:subagent-driven-development`. For each task:
   - write the task's `Guarded files:` paths, if any, to the allowlist of the worktree the task runs in:
     `$(git -C <worktree> rev-parse --absolute-git-dir)/subagent-guard-allow` (in the main checkout, that is
     `.git/subagent-guard-allow`);
   - dispatch `subagent_type: implementer` with the model from the tag, adding the co-author trailer line
     that names that model to the dispatch;
   - review with `task-reviewer`;
   - empty that allowlist however the task ends, and push once it is Approved (every approved
     task is committed and pushed; for a task in a worktree: once it is cherry-picked).

   The tasks of one wave run in parallel; see [Parallel waves](#parallel-waves).
8. **Learnings:** list what the work taught us that isn't written down yet (tool quirks, safe ways of doing
   things, HA behaviour), and propose where each goes (see [§7](#7-docs), *Learnings*), as questions to the
   owner (§6). The owner decides; the docs change in this PR, before the branch review checks them. If there
   are none, say so in the PR description.
9. **Branch review:** `full-reviewer` on the branch until Ready. A learning found during the review goes
   through step 8 too, and the next review round checks it.
10. **Ready:** run `scripts/smoke` on the branch (Home Assistant must start and set up the integration with
    no errors from it; stop any running dev instance first), update the PR description (Rulings, learnings,
    the smoke result), then `gh pr ready` only when the owner's
    review is needed, and tell the owner.
11. **Merge:** the owner merges.

### Parallel waves

**Planning.**
- Tasks in the same wave touch disjoint files and don't consume each other's output. A task's wave is one more
  than the highest wave it depends on.
- Split work so that each task owns its files: a module per feature rather than one file every task edits.
  Shared files (exports in `__init__.py`, `CHANGELOG.md`, `pyproject.toml` and `uv.lock` when a task adds a
  dependency) go in one task, usually the last.
- A task with a `Guarded files:` line may run in any worktree: the guard hook reads the allowlist of the
  worktree the edited file is in (§1 step 7). One known limit stays: the hook's whole-tree revert check
  compares against the main checkout only, so a revert of a task worktree isn't caught.
- A docs task may join an early wave, written against the public names the plan fixes (see *Starting ahead
  of inputs*).

**Running a wave with more than one task.**
- Each task gets its own worktree and branch off the feature branch:
  `git worktree add ../<repo>-wt/<topic>-task-<n> -b wt/<topic>-task-<n> <feature-branch>`, then `uv sync` in it.
  Don't run `pre-commit install` there: the hooks are shared, and it points them at the worktree's `.venv`,
  which breaks every commit once the worktree is removed. If it happened, run `uv run pre-commit install`
  in the main checkout.
  `wt/*` branches are never pushed.
  (For a team lead in the PO flow: `<HA-NortecGo-wt>/<topic>-task-<n>`, by absolute path; §8.)
- The implementer and reviewer dispatches give the worktree's absolute path, and every command runs there
  (`cd <worktree> && …` or `git -C <worktree> …`). A subagent's shell starts in the main checkout.
  (For a team lead in the PO flow, its issue worktree.)
- The controller runs the SDD scripts (brief, review package, ledger) from the main checkout, so everything
  lands in its `.superpowers/sdd/` and survives the worktree. Branch refs are shared, so
  `review-package PLAN BASE wt/<topic>-task-<n>` works there. For a team lead in the PO flow (§8), "the main
  checkout" here is its issue worktree.
- Once a task is Approved, cherry-pick its commits onto the feature branch, run the gates (`CLAUDE.md` →
  Commands) and push. Tasks in one wave can be picked in any order.
- If a pick conflicts, the wave wasn't disjoint. Abort the pick. Then either re-run the task on the new head,
  or have the implementer rebase its `wt/` branch onto the feature head in its own worktree, as a fix round
  that `task-reviewer` reviews. The controller doesn't
  resolve conflicts itself.
- Remove the worktree and delete its branch (`git branch -D`) however the task ends.

**Starting ahead of inputs.** A task may start before its inputs are on the feature branch, from the
unreviewed commit of the task it depends on (only if it adds new files) or from names the plan fixes (a docs
task). Such a task:
- is reviewed with the commit it started from as its package BASE (the dependency's commit, or the feature
  head for a docs task);
- is held until its inputs are on the feature branch, then re-reviewed against that head if they changed. A
  docs task is always re-checked: its names against the code that landed;
- has only its own commits cherry-picked, never the dependency's;
- is redone if the dependency is dropped;
- never has a `Guarded files:` line.

## 2. How this maps onto the superpowers skills

Where subagent-driven-development (SDD) differs, this doc wins.

- **Workspace:** the branch from step 2, plus a worktree per task when a wave runs tasks in parallel
  ([Parallel waves](#parallel-waves)). This replaces SDD's rule that implementers never run in parallel.
- **Implementer:** `implementer` replaces SDD's `general-purpose` implementer. SDD's implementer template is
  still the dispatch prompt.
- **Model:** the plan's `Model:` tag replaces SDD's model selection.
- **Task review:** `task-reviewer` replaces SDD's spec-compliance and code-quality reviewers, and also does
  the scoped re-reviews, given the findings list and the `FIX_BASE..HEAD` package.
- **Pushes:** pushing the feature branch after an Approved task is pre-authorized. It is not an SDD stop point.
- **Final review:** `full-reviewer` is SDD's final whole-branch reviewer (and also reviews specs and plans).
  Its fix rounds follow §3, not SDD's single fix wave.
- **Finish:** step 10 replaces `superpowers:finishing-a-development-branch`.

## 3. Review rounds and escalation

- **Rounds:** after fixes, the same reviewer re-reviews, up to 5 rounds. Past that, the controller rules.
- **Rulings:** a ruling that sets a lasting rule goes in `decisions.md`. Every ruling goes in the PR
  description, because SDD's `.superpowers/sdd/` workspace is deleted.
- **Escalation:** count a task's Needs fixes verdicts (the first review plus each re-review).
  - A Sonnet task that reaches 2 gets a fresh implementer on Opus, with SDD's "you own it now" framing and
    the existing report file.
  - An Opus task resumes the same implementer until round 5, and then the controller rules.

## 4. Trivial changes

A trivial change has no behaviour change, no new decision and no new rule, for example a typo or a one-line
doc fix. It goes straight to a branch and a ready PR: no spec, no plan, no draft.

Until the first working release (the first version the owner has tested locally; the `v0.0.1` skeleton
doesn't count), the owner may rule that a small, well-scoped behaviour change skips the spec and plan (D25).
It still starts from an issue and its PR says `Closes #n`. The controller gives a short design in chat,
implements it with TDD, runs the gates and `scripts/smoke`, and opens a ready PR, with no `full-reviewer`
review.

## 5. Model policy and guarded files

| Role | Model / effort |
|---|---|
| Controller (main session) | The owner's session model |
| PO (PO flow, §8) | Opus / high |
| Team lead (PO flow, §8) | Opus / medium |
| `implementer` | Sonnet 5 / medium; Opus when tagged |
| `task-reviewer` | Opus / medium |
| `full-reviewer` | Opus / high |

- **`Model: opus`** (with a one-line reason) is for tasks that touch auth, tokens or reauth, anything near
  charge start/stop, or the mapping of `pynortecgo` models to entities; for debugging with an unknown
  cause; and for every docs task (D33).

  Everything else is `Model: sonnet`. Effort can't be overridden per dispatch.
- **Guarded files:** a task that edits `.claude/` or `.pre-commit-config.yaml` lists the exact paths in a
  `Guarded files:` line.
  - Listing `.claude/settings.json` or `.claude/hooks/subagent_guard.py` needs a one-line reason.
  - The subagent guard hook (`.claude/hooks/subagent_guard.py`) refuses subagents everything else under
    `.claude`/`.git`, and hook bypasses.
  - The guard also refuses subagents' whole-tree reverts and direct `.env` reads.
  - The allowlist covers only file-editing tools (Edit, Write, NotebookEdit). A subagent can't delete or move a guarded file (`git rm`, `rm`,
    `mv`), even an allowlisted one, so the plan gives deletes under `.claude/` to the controller.
  - The guard refuses a bare heredoc (`<<`) in Bash as unparseable. Subagents write scripts and commit messages
    with the Write tool, to a file outside the repo, and commit with `git commit -F <file>`.
  - The controller is not restricted by it.

## 6. Conventions

- **Issues:** every non-trivial change starts from an issue. The spec links it, and the PR says `Closes #n`.
- **Backlog:** GitHub issues are the backlog (D19). Anything found that won't be fixed in the current work
  becomes an issue, or is added to an existing one.
- **Labels:** each issue gets one urgency label: `v1` (needed for version 1), `v2` (can wait for version 2)
  or `v3` (nice to have, after version 2); chores may have none. Type labels come on top: `bug` for a bug,
  and `enhancement` or `documentation` where they fit. `active` marks the issues being worked on now: it goes
  on when the issue's branch is created, and comes off if the work stops before the PR is merged (a merge
  closes the issue). When in doubt, ask the owner (D30).
- **Merging and pushing:** the owner merges. Only the controller pushes or marks a PR ready; in the PO flow
  (§8) the team lead pushes and the PO marks ready.
- **Git guards:** run `uv run pre-commit install` once per clone. The hooks refuse commits on `main` and pushes
  to `main`, and `.claude/settings.json` denies pushes to `main` and `--no-verify`. `main` is also protected
  server-side, with the required checks.
- **Questions to the owner:** plain terminal text, one at a time. In the PO flow, the PO also posts them on the
  issue (§8).
- **Delegated plan approval:** the owner may let the controller approve a plan once `full-reviewer` rates it
  Ready; the spec always needs the owner's approval, except in the PO flow, where the PO approves both (D35).
- **Client change requests:** send them to the `nortecgo-af` session. If it isn't running, the controller
  files the issue with `gh issue create -R thomas3650/nortecgo --label ha-integration`. The issue holds no
  private data from this side.
- **Quality scale:** a PR that completes a rule sets it to `done` in `quality_scale.yaml`.
- **Devcontainer:** manual testing only, never the gate environment.
- **Gates:** the commands in `CLAUDE.md` → Commands; `hassfest` and `hacs` run in CI only. `scripts/smoke`
  runs before a PR is marked ready (step 10); it needs the owner's dev config in `config/`, so it runs locally,
  never in CI.

| The controller may | The controller may not |
|---|---|
| Edit anything in the repo, including `.claude/` and `.pre-commit-config.yaml`; `.claude/settings.json` only after asking the owner each time | Merge PRs |
| Create branches, commit, push feature branches | Force-push |
| Open draft PRs, update PR descriptions, `gh pr ready` | Tag releases |
| Create, comment on and label issues (for example, file deferred items) | Change GitHub repo settings, secrets or environments |
| Dispatch agents, choosing the model by the plan tag | Bypass hooks (`--no-verify`, `-n`, `SKIP=`) |
| Rule after 5 review rounds; record lasting rulings in `decisions.md` | Anything the `CLAUDE.md` hard rules forbid |
| `uv sync`, `uv lock` | Read `.env`, `local/` or `config/` |

The one-time GitHub settings applied for this repo's ground structure are an explicit exception to the
"change GitHub repo settings" rule, each step approved by the owner.

## 7. Docs

- **No duplication:** each fact lives in one place. Elsewhere, point to it.
- **General docs:** docs explain why, conventions and structure. The code is the source for specifics
  (fields, signatures, file inventories).
- **Specs and plans are snapshots:** they aren't edited after merge. A later change gets a new spec and a
  decision-log entry.
- **Same PR:** docs change in the same PR as the code they describe.
- **Learnings:** a fact we learn goes where a reader would look for it: the doc that owns the topic (a user
  facing fact in `docs/user/nortec_go.md`, a process fact in `way-of-working.md`). A small fact that fits no
  doc goes in [`notes.md`](notes.md). When a topic there passes about three entries, propose moving it to its
  own doc (and a row in the [documentation map](README.md)).
- **Decision log:** a PR that makes a lasting decision adds an entry to `decisions.md`, numbered next. Entries
  aren't edited, except to change their status to `superseded by D<n>`, or, when a later decision replaces
  only part of one, to `active; <part> superseded by D<n>` (for example `active; the polling intervals
  superseded by D29`). The format:

  ```markdown
  ### D<n>: <title>
  - **Date:** YYYY-MM-DD · **Status:** active | superseded by D<m> | active; <part> superseded by D<m>
  - **Decision:** one or two sentences.
  - **Why:** one or two sentences.
  - **Source:** link to the spec (and section).
  ```

## 8. PO flow

An alternative to running the §1 flow directly: a PO session runs the backlog through team leads, and the
owner answers escalations and merges (D35). The agent files `.claude/agents/po.md` and `team-lead.md` point
here.

### Roles and start modes

- **PO:** started by the owner with `scripts/po`, interactive, in the main checkout; its session is always
  named `po`. Picks issues, starts and resumes team leads, answers their questions or escalates, approves
  specs and plans, hands out D-numbers, runs step 10's checks and marks PRs ready. Never merges.
- **Team lead:** a background session per issue, in its own issue worktree, started by the PO and named
  `tl-<topic>`; at most 2. Runs §1 steps 3 to 9 as the controller, with the PO (addressed as `po`) in the
  owner's place. It never runs `gh pr ready`, `scripts/smoke` or `scripts/develop`, and splits a wave wider
  than 3 workers.
- **Workers:** the team lead's subagents, as in §2; at most 3 active per team lead.
- **Team lead mode**, for hard problems: the owner runs `scripts/team-lead` in the foreground in the main
  checkout (session name `team-lead`, no PO named), and is the PO. **PO mode and team lead mode never run at
  the same time:** `scripts/po` and `scripts/team-lead` refuse to start while a session named `po` or
  `team-lead` runs, or in a linked worktree, and the PO also checks at start that no session named
  `team-lead` runs.
- Owner only: merging, anything that starts or stops a real charge, the permission setup for team leads, and
  `.claude/settings.json`.

### Picking and starting an issue

When fewer than 2 team leads run, the PO picks an open issue without `active`: all `v1` first, then `v2`,
then `v3`, the most important first within a label. It skips issues without an urgency label, issues in the
same area as one in progress, and issues that depend on an unfinished one. Then it:
1. runs `git fetch`, labels the issue `active`, creates `<type>/<topic>` from `origin/main` and the issue
   worktree `../HA-NortecGo-wt/<topic>`, and runs `uv sync` there (never `pre-commit install`);
2. starts the team lead there with `claude --bg --permission-mode auto --agent team-lead -n tl-<topic>
   "<prompt>"`, run in the issue worktree, the prompt naming itself (`po`), the issue, the branch and the
   worktree;
3. records the session id, issue, branch and worktree in `.git/po-sessions.json`, and comments on the issue
   that a team lead has picked it up.

A team lead's task worktrees go next to its issue worktree, by absolute path:
`<HA-NortecGo-wt>/<topic>-task-<n>`.

### Messages

The team lead talks only to the PO, with `SendMessage`:

| Message | The PO |
|---|---|
| `hello` (first message, with the issue number) | Records its `ListAgents` name in `.git/po-sessions.json`. |
| `question` | Answers, or escalates; the team lead waits for the answer. |
| `spec ready` / `plan ready`, with the `full-reviewer` verdict | Approves or sends back with points; records the approval as an issue comment. |
| `need D-number` | Gives the next number not used on `origin/main`, on an open PR's branch, or already handed out (kept in `.git/po-sessions.json`). |
| `blocked` | Decides, or escalates. |
| `branch ready`, with `visible: yes/no` (proposed; the PO decides) | Runs *From branch ready to PR ready*. |

The PO also sends `hello` to its team leads when it starts (see *After ready, the loop, and failures*).

### Escalation

The PO escalates when it is less than 90% sure, and always for: anything near starting or stopping a charge,
or auth, tokens and reauth; a new decision or a change to a hard rule; changes to `.claude/`,
`.pre-commit-config.yaml` or `.github/workflows/`; a ruling after 5 review rounds (§3); anything that would
file an issue on the client repo.

It posts the question as an issue comment starting with `**PO question:**`, and asks the same in the terminal,
one at a time (the rest wait in a queue; on the issues they can all be up). The first answer counts; an
answer given in the terminal is copied to the issue. If the two places give different answers, the PO asks
again.

**Public text:** issue comments, PR descriptions, review comments and commit messages follow hard rule 3 and
hold no real-instance data: no smoke log lines, no values or states seen in HA, no screenshots. The visual
check is reported by what it covered, not what it saw; a defect is described in the code's terms.

### From branch ready to PR ready

One branch at a time, in the main checkout (only the PO works there, and only one Home Assistant runs):
1. The main checkout must be clean; if not, escalate. `git fetch`, `git switch --detach origin/<branch>`,
   `uv sync`. While detached, the PO starts and resumes no team leads.
2. `scripts/smoke`. A failure that comes from the shared `config/` (for example a store version another
   branch left) is escalated, not sent back.
3. **Visual check**, when the change is visible in HA (entities, names, icons, units, the options flow,
   translations, the device page): start `scripts/develop` with the Bash tool's `run_in_background` (not `&`
   in a shell: that crashes on macOS), open a new Chrome tab on `http://localhost:8123` with the owner's
   existing login, check against the spec, save screenshots to `local/screenshots/<topic>/` (the Chrome
   screenshot tool's `save_to_disk`, then `mv` into the folder without opening them), then stop HA with
   `pkill -f "hass -c config"`. Never the config flow or reauth, never credentials, never anything that calls
   an action on the charger. The screenshots are for the owner, who also cleans them up.
4. **Acceptance check:** the PR against the issue's user story and the approved spec, and the PR description
   (rulings, learnings, smoke result, which parts the visual check covered, and that the screenshots are in
   `local/screenshots/<topic>/`). Not a second code review.
5. Switch back to the branch the main checkout was on, and `uv sync`.
6. On a failure: back to the team lead with the finding. Otherwise: update the PR description, `gh pr ready`,
   tell the owner, stop the team lead (`claude stop <id>`), and remove its worktrees (`git worktree remove
   --force`: they hold `.venv` and `.superpowers/sdd/`) and `wt/` branches. The SDD workspace goes with them;
   the rulings are in the PR description.

### After ready, the loop, and failures

- A ready PR takes no slot. On changes requested or a merge conflict, the PO re-creates the issue worktree at
  the same path and resumes the team lead (`claude --bg --resume <session-id>`, run in the re-created issue
  worktree) when a slot is free. Conflicts are fixed by merging `origin/main` in, never by a force-push. A
  resumed team lead starts without its old SDD ledger.
- The PO's `/loop` (every 10 to 20 minutes) checks GitHub for merged PRs (remove `active` if still there, pick
  the next issue), answers to open `PO question`s, and review comments or conflicts on ready PRs.
- **State:** GitHub is the source of truth; `.git/po-sessions.json` maps each team lead's session id and
  `ListAgents` name to its issue, branch and worktree, and holds the D-numbers handed out.
  `claude agents --json` shows the running sessions, interactive and background; `ListAgents` the names to
  message.
- A team lead that is gone is resumed once; if that fails, the PO escalates and leaves the issue `active`.
  One with nothing new in `claude logs <id>` for 2 loops is asked for its status, then escalated.
- If the PO session ends, team leads keep running. A `SendMessage` to a PO that is down fails at once; it
  isn't queued. The team lead keeps every message whose `SendMessage` to `po` failed, and waits (it doesn't
  poll for the PO). The next `scripts/po` rebuilds its state from the above, sends `hello` to every team lead
  in `.git/po-sessions.json`, and carries on; on that `hello`, each team lead re-sends the messages that
  failed, in order.
