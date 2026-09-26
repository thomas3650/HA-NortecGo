# Way of working

A sibling copy lives in the private `NortecGo` repo. A process change in either copy gets a follow-up issue
in the other repo.

How changes are made in this repo. This is the one home for the process: `CLAUDE.md` imports it, and agents
and skills point here rather than copying it. Hard rules live in `CLAUDE.md`, and decisions in
[`decisions.md`](decisions.md).

## 1. Flow for non-trivial changes

1. **Issue:** a user story.
2. **Branch:** `<type>/<topic>`, where the type is `feat`, `fix`, `docs`, `chore` or `process`.
3. **Brainstorm:** `superpowers:brainstorming`.
4. **Spec** in `docs/superpowers/specs/`, then `full-reviewer` until Ready.
5. **Plan:** `superpowers:writing-plans`, in `docs/superpowers/plans/`, with a `Model:` tag on every task
   (and a `Guarded files:` line where needed; see §5) and a `Wave:` number on every task, written for
   parallel work (see [Parallel waves](#parallel-waves)). Then `full-reviewer` until Ready.
6. **Draft PR:** once the spec and plan are both Ready, commit them, push, and open a **draft** PR with
   `Closes #n` and links to the spec and plan. The owner reviews the spec and plan there.
7. **Execute:** `superpowers:subagent-driven-development`. For each task:
   - write the task's `Guarded files:` paths, if any, to `.git/subagent-guard-allow`;
   - dispatch `subagent_type: implementer` with the model from the tag, adding the co-author trailer line
     that names that model to the dispatch;
   - review with `task-reviewer`;
   - empty `.git/subagent-guard-allow` however the task ends, and push once it is Approved (every approved
     task is committed and pushed; for a task in a worktree: once it is cherry-picked).

   The tasks of one wave run in parallel; see [Parallel waves](#parallel-waves).
8. **Learnings:** list what the work taught us that isn't written down yet (tool quirks, safe ways of doing
   things, API facts), and propose where each goes (see [§7](#7-docs), *Learnings*), as questions to the
   owner (§6). The owner decides; the docs change in this PR, before the branch review checks them. If there
   are none, say so in the PR description.
9. **Branch review:** `full-reviewer` on the branch until Ready. A learning found during the review goes
   through step 8 too, and the next review round checks it.
10. **Ready:** update the PR description (Rulings, learnings), then `gh pr ready` only when the owner's
    review is needed, and tell the owner.
11. **Merge:** the owner merges.

### Parallel waves

**Planning.**
- Tasks in the same wave touch disjoint files and don't consume each other's output. A task's wave is one more
  than the highest wave it depends on.
- Split work so that each task owns its files: a module per feature rather than one file every task edits.
  Shared files (exports in `__init__.py`, `CHANGELOG.md`, `pyproject.toml` and `uv.lock` when a task adds a
  dependency) go in one task, usually the last.
- A task with a `Guarded files:` line gets a wave of its own and runs in the main checkout, with the controller
  session there too. The guard hook resolves paths against the main checkout, so it can't allow guarded files
  in another worktree, and doesn't protect another worktree's `.pre-commit-config.yaml` (a known limit of the
  guard hook).
- A docs task may join an early wave, written against the public names the plan fixes (see *Starting ahead
  of inputs*).

**Running a wave with more than one task.**
- Each task gets its own worktree and branch off the feature branch:
  `git worktree add ../<repo>-wt/<topic>-task-<n> -b wt/<topic>-task-<n> <feature-branch>`, then `uv sync` in it.
  `wt/*` branches are never pushed.
- The implementer and reviewer dispatches give the worktree's absolute path, and every command runs there
  (`cd <worktree> && …` or `git -C <worktree> …`). A subagent's shell starts in the main checkout.
- The controller runs the SDD scripts (brief, review package, ledger) from the main checkout, so everything
  lands in its `.superpowers/sdd/` and survives the worktree. Branch refs are shared, so
  `review-package PLAN BASE wt/<topic>-task-<n>` works there.
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

## 5. Model policy and guarded files

| Role | Model / effort |
|---|---|
| Controller (main session) | The owner's session model |
| `implementer` | Sonnet 5 / medium; Opus when tagged |
| `task-reviewer` | Opus / medium |
| `full-reviewer` | Opus / high |

- **`Model: opus`** (with a one-line reason) is for tasks that touch auth, tokens or reauth, anything near
  charge start/stop, or the mapping of `pynortecgo` models to entities; and for debugging with an unknown
  cause.

  Everything else is `Model: sonnet`. Effort can't be overridden per dispatch.
- **Guarded files:** a task that edits `.claude/` or `.pre-commit-config.yaml` lists the exact paths in a
  `Guarded files:` line.
  - Listing `.claude/settings.json` or `.claude/hooks/subagent_guard.py` needs a one-line reason.
  - The subagent guard hook (`.claude/hooks/subagent_guard.py`) refuses subagents everything else under
    `.claude`/`.git`, and hook bypasses.
  - The guard also refuses subagents' whole-tree reverts and direct `.env` reads.
  - The controller is not restricted by it.

## 6. Conventions

- **Issues:** every non-trivial change starts from an issue. The spec links it, and the PR says `Closes #n`.
- **Merging and pushing:** the owner merges. Only the controller pushes or marks a PR ready.
- **Git guards:** run `uv run pre-commit install` once per clone. The hooks refuse commits on `main` and pushes
  to `main`, and `.claude/settings.json` denies pushes to `main` and `--no-verify`. `main` is also protected
  server-side, with the required checks.
- **Questions to the owner:** plain terminal text, one at a time.
- **Delegated plan approval:** the owner may let the controller approve a plan once `full-reviewer` rates it
  Ready; the spec always needs the owner's approval.
- **Client change requests:** send them to the `nortecgo-af` session. If it isn't running, the controller
  files the issue with `gh issue create -R thomas3650/nortecgo --label ha-integration`. The issue holds no
  private data from this side.
- **Quality scale:** a PR that completes a rule sets it to `done` in `quality_scale.yaml`.
- **Devcontainer:** manual testing only, never the gate environment.

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
  aren't edited, except to change their status to `superseded by D<n>`. The format:

  ```markdown
  ### D<n>: <title>
  - **Date:** YYYY-MM-DD · **Status:** active | superseded by D<m>
  - **Decision:** one or two sentences.
  - **Why:** one or two sentences.
  - **Source:** link to the spec (and section).
  ```

  Gates: `uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
  --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`. `hassfest` and `hacs` run
  in CI only.
