# Way of working

How changes are made in this repo. This is the one home for the process: `CLAUDE.md` imports it, and agents
and skills point here rather than copying it. Hard rules live in `CLAUDE.md`, and decisions in
[`decisions.md`](decisions.md).

## 1. Flow for non-trivial changes

1. **Issue:** a user story.
2. **Branch:** `<type>/<topic>`, where the type is `feat`, `fix`, `docs`, `chore` or `process`.
   The PR title's type is separate, and follows [`releasing.md`](releasing.md#pr-titles).
   Label the issue `active` (see §6 *Labels*).
3. **Brainstorm:** `superpowers:brainstorming`.
4. **Spec** in `docs/superpowers/specs/`, then `full-reviewer` until Ready.
5. **Plan:** `superpowers:writing-plans`, in `docs/superpowers/plans/`, with a `Model:` tag on every task
   (and a `Guarded files:` line where needed; see §5) and a `Wave:` number on every task, written for
   parallel work (see [Parallel waves](#parallel-waves)). Then `full-reviewer` until Ready. In a plan, a
   fragment that isn't a whole statement (parametrize rows, say) goes in a `text` block, and so do class
   methods (indented `def`s): a pre-commit hook reformats Python blocks in Markdown
   ([`ha-notes.md`](ha-notes.md#tooling)).
6. **Draft PR:** once the spec and plan are both Ready, commit them, push, and open a **draft** PR with
   `Closes #n` and links to the spec and plan. Its title follows [`releasing.md`](releasing.md#pr-titles).
   The owner reviews the spec and plan there.
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
    no errors from it; stop any running dev instance first), for a releasing title run the bump step
    ([`releasing.md`](releasing.md#a-releasing-pr)) and push, update the PR description (Rulings,
    learnings, the smoke result), then `gh pr ready` only when the owner's review is needed, and tell the
    owner.
11. **Merge:** the owner merges. In the PO flow the PO merges what §8 *Merging* allows (D45).

### Parallel waves

**Planning.**
- Tasks in the same wave touch disjoint files and don't consume each other's output. A task's wave is one more
  than the highest wave it depends on.
- Split work so that each task owns its files: a module per feature rather than one file every task edits.
  Shared files (exports in `__init__.py`, `CHANGELOG.md`, `pyproject.toml` and `uv.lock` when a task adds a
  dependency) go in one task, usually the last.
- A task with a `Guarded files:` line may run in any worktree: the guard hook reads the allowlist of the
  worktree (of this repository) the edited file is in (§1 step 7). One known limit stays: the hook's
  whole-tree revert check compares against the main checkout only, so a revert of a task worktree isn't
  caught.
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
- Don't pass `isolation: "worktree"` to these dispatches. The harness worktree it creates (under
  `.claude/worktrees/`) becomes the subagent's primary directory, and the guard hook and the isolation then
  refuse its writes to the task worktree. Subagents edit files by absolute path, with Edit and Write.
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
- **Global Constraints:** SDD's `task-brief` script extracts only the task's own text. The controller saves
  the plan's *Global Constraints* to a file in the SDD workspace and names it in both the implementer and
  the `task-reviewer` dispatches.
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

A PR opened ready with a releasing title runs the bump step ([`releasing.md`](releasing.md#a-releasing-pr))
before it is opened.

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
    with the Write tool, to a uniquely named file outside the repo (after the topic and task, for example
    `/tmp/<topic>-task-<n>-msg.txt`, or from `mktemp`), and commit with `git commit -F <file>`.
  - A task that edits the guard hook runs in a task worktree, even alone in its wave: the checkout the session
    started in holds the live hook for every subagent. After the pick, and before the next wave or the push,
    check the live hook: its tests, one subagent payload it must refuse with the Guarded-files message (not
    `guard error`), and one that goes through its git lookups and must pass.
  - The controller is not restricted by it.

## 6. Conventions

- **Issues:** every non-trivial change starts from an issue. The spec links it, and the PR says `Closes #n`.
- **Backlog:** GitHub issues are the backlog (D19). Anything found that won't be fixed in the current work
  becomes an issue, or is added to an existing one.
- **Labels:** each issue gets one urgency label: `v1` (needed for version 1), `v2` (can wait for version 2)
  or `v3` (nice to have, after version 2); chores may have none. Type labels come on top: `bug` for a bug,
  and `enhancement` or `documentation` where they fit. `active` marks the issues being worked on now: it goes
  on when the issue's branch is created, and comes off if the work stops before the PR is merged (a merge
  closes the issue). `blocked-ha` ("Waits for a Home Assistant release") goes on an issue that can't move
  until a Home Assistant release, for example #55. When in doubt, ask the owner (D30).
- **Merging and pushing:** only the owner and the PO merge: the PO in the PO flow, when §8 *Merging* allows
  it, and the owner otherwise. Only the controller pushes or marks a PR ready; in the PO flow (§8) the team
  lead pushes and the PO marks ready.
- **Git guards:** run `uv run pre-commit install` once per clone. The hooks refuse commits on `main` and pushes
  to `main`, and `.claude/settings.json` denies pushes to `main` and `--no-verify`. `main` is also protected
  server-side, with the required checks. Some hooks run a dev tool with `uv run` (ruff, `actionlint`,
  `zizmor`), so after a merge that adds such a tool, every checkout and worktree runs `uv sync` before its
  next commit.
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
| Edit anything in the repo, including `.claude/` and `.pre-commit-config.yaml`; `.claude/settings.json` only after asking the owner each time | Merge PRs (in the PO flow the PO may; §8 *Merging*) |
| Create branches, commit, push feature branches | Force-push |
| Open draft PRs, update PR descriptions, `gh pr ready` | Push a tag, or re-run a workflow run on `main` (either can publish), unless the owner says so for that release |
| Create, comment on and label issues (for example, file deferred items) | Change GitHub repo settings, secrets or environments |
| Dispatch agents, choosing the model by the plan tag | Bypass hooks (`--no-verify`, `-n`, `SKIP=`) |
| Rule after 5 review rounds; record lasting rulings in `decisions.md` | Anything the `CLAUDE.md` hard rules forbid |
| `uv sync`, `uv lock` | Read `.env`, `local/` or `config/` |
| Run the bump step in a releasing PR ([`releasing.md`](releasing.md#a-releasing-pr)) | |

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

An alternative to running the §1 flow directly: a PO session runs the backlog through team leads, makes
their PRs ready and merges them, and the owner answers escalations and merges the PRs that *Merging* leaves
to the owner (D35, D45). The agent files `.claude/agents/po.md` and `team-lead.md` point here.

### Roles and start modes

- **PO:** started by the owner with `scripts/po`, interactive, in the main checkout; its session is always
  named `po`. Picks issues, starts and resumes team leads, answers their questions or escalates, approves
  specs and plans, hands out D-numbers, runs step 10's checks, marks PRs ready, and merges them when
  *Merging* allows it.
- **Team lead:** a background session per issue, in its own issue worktree, started by the PO and named
  `tl-<topic>`; at most 2. Runs §1 steps 3 to 9 as the controller, with the PO (addressed as `po`) in the
  owner's place. For a releasing title it then runs the bump step
  ([`releasing.md`](releasing.md#a-releasing-pr)), as its last step before `branch ready`. It never merges
  and never runs `gh pr ready`, `scripts/smoke` or `scripts/develop`, and it splits a wave wider than 3
  workers.
- **Workers:** the team lead's subagents, as in §2; at most 3 active per team lead.
- **Team lead mode**, for hard problems: the owner runs `scripts/team-lead` in the foreground in the main
  checkout (session name `team-lead`, no PO named), and is the PO. **PO mode and team lead mode never run at
  the same time:** `scripts/po` and `scripts/team-lead` refuse to start while a session named `po` or
  `team-lead` runs, or in a linked worktree, and the PO also checks at start that no session named
  `team-lead` runs. Team leads (`tl-*`) still running while the PO is down count as PO mode: the owner
  doesn't start `scripts/team-lead` then.
- Owner only: merging what *Merging* doesn't give the PO, anything that starts or stops a real charge,
  pushing a tag, re-running a workflow run on `main`, the permission setup for team leads, and
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
1. The main checkout must be clean; if not, escalate. `git fetch`. If `origin/main` isn't merged into the
   branch (`git merge-base --is-ancestor origin/main origin/<branch>` fails), it goes back to the team lead
   with that finding, before any smoke test. Otherwise `git switch --detach origin/<branch>`, `uv sync`.
   While detached, the PO starts and resumes no team leads.
2. `scripts/smoke`. A failure that comes from the shared `config/` (for example a store version another
   branch left) is escalated, not sent back.
3. **Visual check**, when the change is visible in HA (entities, names, icons, units, the options flow,
   translations, the device page): start `scripts/develop` with the Bash tool's `run_in_background` (not `&`
   in a shell: that crashes on macOS), open a new Chrome tab on `http://localhost:8123` with the owner's
   existing login, check against the spec (what to look at, and that an agent operates no control, are in
   [`manual-testing.md`](manual-testing.md)), save screenshots to `local/screenshots/<topic>/` (the Chrome
   screenshot tool's `save_to_disk`, then `mv` into the folder without opening them), then stop HA with
   `pkill -f "hass -c config"`. Never the config flow or reauth, never credentials, never anything that calls
   an action on the charger. The screenshots are for the owner, who also cleans them up.
4. **Acceptance check:** the PR against the issue's user story and the approved spec, the title's type and
   release level ([`releasing.md`](releasing.md#pr-titles)), and the PR description (rulings, learnings,
   smoke result, which parts the visual check covered, and that the screenshots are in
   `local/screenshots/<topic>/`). Not a second code review. The PO also decides here who merges the PR
   (*Merging*, **Owner-merge PRs**), and the PR description says so in one line: the PO, or the owner and
   why.
5. Switch back to the branch the main checkout was on, and `uv sync`.
6. On a failure: back to the team lead with the finding. Otherwise: update the PR description, `gh pr ready`,
   record the PR (*Merging*, **What the PO records**), tell the owner (for an owner-merge PR: that it is
   theirs to merge, and why), stop the team lead (`claude stop <id>`), and remove its worktrees (`git
   worktree remove --force`: they hold `.venv` and `.superpowers/sdd/`) and `wt/` branches. The SDD workspace
   goes with them; the rulings are in the PR description. Then, for a PR the PO may merge: *Merging*.

### Merging

Only the PO and the owner merge (D45). The PO merges a PR when it took the PR through *From branch ready to
PR ready* and marked it ready, in this or an earlier session, the PR is not owner-merge, and nothing on it
waits for the owner (step 3 of the merge, below). Every other PR is the owner's to merge, also
Dependabot's, the owner's own and trivial ones (§4).

**Owner-merge PRs.** A PR is owner-merge when its diff touches something *Escalation* always escalates for
(the part of that list a diff can touch): charge start or stop (the code that calls them, or what decides
when they are called); auth, tokens or reauth; a hard rule; or one of the paths *Escalation* names. A new
decision alone doesn't make a PR owner-merge: the owner approved it in the spec. The PO decides from the
changed files (`gh pr diff <n> --name-only`) and the spec; a plan task tagged `Model: opus` for charge or
auth (§5) is a sign. Below 90% sure, the PR is owner-merge.

**What the PO records.** When it marks a PR ready, the PO writes to the PR's entry in
`.git/po-sessions.json`: that it is ready, who merges it (`po` or `owner`), the *checked head* (the head
commit the smoke test ran on), the *cleared time*, and what the PR waits for, if anything (the owner's
go-ahead, or a team lead's fix and for which comment or check). A later session reads it there. If the entry
or the checked head is missing, or the PR's head is a different commit, the PR goes through *From branch
ready to PR ready* again before any merge.

The merge, after a `git fetch`:
1. **Up to date:** `origin/main` is merged into the PR's head (the test in *From branch ready to PR ready*,
   step 1). If not: **Behind `main`**, which covers a merge conflict too.
2. **The required checks have run and passed on the checked head:**
   `gh pr checks <n> --required --json name,bucket` shows every required check in bucket `pass`. The PO
   waits while any is `pending`, and while `version-check` is `skipping`: on a draft it is skipped, GitHub
   counts a skipped check as passed, and its real run starts only after `gh pr ready`. A failed check goes
   back to the resumed team lead with the finding.
3. **Nothing waits for the owner:**
   - the head is still the checked head, and no review has the state `CHANGES_REQUESTED`
     (`gh pr view <n> --json headRefOid,reviews,comments`);
   - no review thread is unresolved (`gh api graphql`, the PR's `reviewThreads { isResolved }`; threads from
     the owner's review of the spec and plan on the draft count too);
   - no review, PR comment or reply in a review thread is newer than the cleared time (the same query gives
     each thread's latest comment time).

   Otherwise the PO doesn't merge, and the merge waits for the owner's go-ahead. A comment that asks for a
   change goes to the resumed team lead (*After ready*); after the fix the PR goes through *From branch
   ready to PR ready* again, as in **Behind `main`**, and the PO then asks the owner for a go-ahead, naming
   the comment and the fix. Anything else, or a comment the PO can't place, is escalated at once. The PO
   resolves no thread and dismisses no review: a thread stops the merge until the owner resolves it, and a
   `CHANGES_REQUESTED` review until the owner dismisses it. The PO writes nothing on a PR after ready except
   its description. PRs in the PO flow are opened under the owner's account, so the owner can't request
   changes on them: a comment is the owner's way to stop a merge.
4. **Merge the checked head:** `gh pr merge <n> --squash --match-head-commit <checked head>`; never `--admin`,
   never `--auto`. If GitHub refuses, start once more with the `git fetch` and step 1 (`main` may have moved
   during the wait); a second refusal is escalated.

Then *After a merge*.

**The cleared time** is in UTC and ISO 8601, as GitHub's timestamps are: first the time the PO marked the PR
ready. When the owner gives a go-ahead in step 3 of the merge, the PO sets it to the time of that answer, so
the comments the owner has dealt with no longer stop the merge. Nothing else moves it: not a new checked
head, and not a team lead's fix alone.

**Behind `main`.** The PO resumes the team lead (*After ready*). The team lead merges `origin/main` in, for a
releasing PR runs the bump step again ([`releasing.md`](releasing.md#two-releasing-prs-at-once)), pushes, and
reports `branch ready`. The PO repeats *From branch ready to PR ready* on the new head, with these
differences: the visual check only if `main` brought a visible change; the acceptance check only for the
title, the bump and the PR description; no `gh pr ready`. The clean-up in step 6 of *From branch ready to PR
ready* runs again. The PO records the new checked head and starts the merge again with the `git fetch` and
step 1.

**The queue.** The PRs the PO may merge form a queue, in the order they became ready. The PO merges one at a
time: the first, then *After a merge* including its release check, and only then the next. Only the next PR
in the queue is brought up to date; the ones behind it wait, since the next merge would leave them behind
again. A PR that waits for the owner's answer or for a team lead's fix steps out of the queue, and rejoins it
at the front: after the owner's go-ahead (step 3 of the merge, or a refusal in its step 4), or once the fix
for a failed required check (step 2 of the merge) has been through *From branch ready to PR ready* again. A
resume for a PR that is first in the queue, or has stepped out of it, takes a free team-lead slot before a
new issue is picked.

Owner-merge PRs are not in the queue and block nothing. One that falls behind `main` stays as it is until
the owner says they are about to merge it; the PO then brings it up to date (**Behind `main`**, without the
merge) and tells the owner.

### After a merge

For every merged PR of the PO flow, whether the PO or the owner merged it (the loop finds the owner's
merges):
1. **`main` is green:** watch the required workflows on `main` for the merge commit, and the `auto-release`
   runs ([`releasing.md`](releasing.md#what-happens-on-merge)). For a merge the PO made, the merge commit's
   title is the PR title followed by ` (#<n>)`; if not, escalate.
2. **The release, for a releasing PR:** the tag `vX.Y.Z` is on the merge commit, and the release exists with
   the changelog section as its notes. That HACS offers the version is left to the owner; the PO says so in
   its message.
3. **On a failure in 1 or 2:** escalate, and merge nothing more until the owner has answered. The PO never
   re-runs a workflow run on `main` and never pushes a tag
   ([`releasing.md`](releasing.md#when-a-release-fails)).
4. **Labels:** `Closes #n` closes the issue; remove `active` if it is still there.
5. **The main checkout:** `git fetch --prune`; when it is on `main`, `git pull --ff-only`; then `uv sync` (§6
   *Git guards*). Delete the merged local branch (`git branch -D <type>/<topic>`), and mark the PR's entry in
   `.git/po-sessions.json` as merged; its D-numbers stay recorded.
6. **Tell the owner** in the terminal: which PR merged, and the version it released, if any.
7. **The next PR in the queue** (*Merging*), if there is one; it is now behind `main`. Owner-merge PRs that
   are behind stay as they are.
8. **Pick the next issue** (*Picking and starting an issue*).

### After ready, the loop, and failures

- A ready PR takes no slot. The PO re-creates the issue worktree at the same path, runs `uv sync` in it, and
  resumes the team lead (`claude --bg --permission-mode auto --resume <session-id>`, run in the re-created
  issue worktree) when a slot is free, for:
  - changes requested (a comment that asks for a change), or a failed required check; the merge then follows
    *Merging*, step 3 or step 2;
  - a branch that `origin/main` isn't merged into, which includes a merge conflict and a stale bump (a
    releasing PR behind `main` after another release;
    [`releasing.md`](releasing.md#two-releasing-prs-at-once)): only for the first PR in the queue, and for an
    owner-merge PR once the owner says they are about to merge it (*Merging*, **The queue**).

  Conflicts are fixed by merging `origin/main` in, never by a force-push. A resumed team lead starts without
  its old SDD ledger.
- The PO's `/loop` (every 10 to 20 minutes) checks GitHub for merged PRs (*After a merge*), ready PRs the PO
  may merge that aren't merged yet (*Merging*: checks still running when a session ended, an escalation since
  answered, a PR waiting for its turn), answers to open `PO question`s, and review comments or conflicts on
  ready PRs.
- **State:** GitHub is the source of truth; `.git/po-sessions.json` maps each team lead's session id and
  `ListAgents` name to its issue, branch and worktree, and holds the D-numbers handed out and each ready PR's
  record (*Merging*, **What the PO records**). `claude agents --json` shows the running sessions, interactive
  and background; `ListAgents` the names to message.
- A team lead that is gone is resumed once; if that fails, the PO escalates and leaves the issue `active`.
  One with nothing new in `claude logs <id>` for 2 loops is asked for its status, then escalated.
- If the PO session ends, team leads keep running. A `SendMessage` to a PO that is down fails at once; it
  isn't queued. The team lead keeps every message whose `SendMessage` to `po` failed, and waits (it doesn't
  poll for the PO). The next `scripts/po` rebuilds its state from the above, sends `hello` to every team lead
  in `.git/po-sessions.json`, and carries on; on that `hello`, each team lead re-sends the messages that
  failed, in order.
