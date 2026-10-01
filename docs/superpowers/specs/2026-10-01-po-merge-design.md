# The PO merges ready PRs — design

Date: 2026-10-01 · Branch: `process/po-merge` · Issue: #84

## Goal

- **What:** in the PO flow, the PO merges a PR once it has made it ready and the required checks are green,
  and then runs the steps that follow a merge. Some PRs stay the owner's to merge.
- **Why:** today only the owner merges, so a finished PR waits for the owner to press merge, and every other
  ready PR waits behind it (#84).
- **Not in this work:**
  - merging in the direct flow or in team lead mode (the owner is at the terminal there);
  - PRs the PO didn't take through *From branch ready to PR ready*: Dependabot's, the owner's own, trivial
    ones (`way-of-working.md` §4);
  - GitHub's auto-merge (it is off, and turning it on is a GitHub settings change);
  - re-running a failed release or pushing a tag, which stay the owner's (`releasing.md` → *When a release
    fails*);
  - `.claude/settings.json` and `scripts/po` (see *Facts used*).
- **Done when:** `CLAUDE.md`, `way-of-working.md`, `releasing.md`, `.claude/agents/po.md` and `decisions.md`
  all say the same thing about who merges, when and how, and what the PO does after a merge; no place still
  says that only the owner merges. The gates pass.

## Decisions

Proposed by the team lead and ruled by the owner through the PO (issue #84, 2026-10-01).

| Topic | Decision |
|---|---|
| Who merges | Only the PO and the owner. The PO merges when the rules below allow it; otherwise the owner does. A team lead, the controller of the direct flow and a subagent never merge |
| Releasing PRs | The PO may merge them (`feat`, `fix`, `perf`), and so publish a release |
| Owner-merge PRs | A PR stays the owner's to merge when it touches charge start or stop; auth, tokens or reauth; a hard rule (`CLAUDE.md` → *Hard rules*); `.claude/`; `.pre-commit-config.yaml`; or `.github/workflows/`. A PR that only adds a decision the owner approved in its spec does not count |
| When | Right away, once the PR is ready and the required checks are green on the head commit the PO checked |
| How | `gh pr merge <n> --squash --match-head-commit <sha>`; never `--admin`, never `--auto`. An open review thread or a changes-requested review goes to the owner; the PO resolves no thread to get a merge through |
| A PR behind `main` | The resumed team lead updates it (merging `origin/main` in, and for a releasing PR the bump step again). The PO then re-runs `scripts/smoke` on the new head before it merges |
| Hard rule 1 | It names who merges |
| Decision log | D45: *The PO merges ready PRs*. D35's status becomes `active; the owner merges superseded by D45` |
| Title | `process: the PO merges ready PRs (#84)`; non-releasing, so no `CHANGELOG.md` entry and no bump |
| Rejected | The PO updating a branch itself with `gh pr update-branch` (only the team lead pushes to a feature branch); a waiting time before the merge (the owner asked for none); the team lead proposing `merge: po/owner` in `branch ready` (the PO reads it from the diff, so the message stays as it is) |

Facts used:

- `main`'s branch protection (read on 2026-10-01): six required checks (`lint`, `tests`, `hassfest`, `hacs`,
  `gitleaks`, `version-check`), strict mode (the branch must be up to date with `main`), conversations must
  be resolved, no required approvals, and it binds admins. So GitHub itself refuses a merge with a red
  check, a branch behind `main` or an open review thread.
- The repo allows squash merges only, with the PR title and body as the commit message, and deletes the head
  branch on merge (D5). Auto-merge is off.
- `version-check` runs only on a PR that isn't a draft, so it first runs after `gh pr ready`.
- `.claude/settings.json` denies pushes to `main` and `--no-verify`. It has no rule on `gh pr merge`, so it
  needs no change. It applies to every session alike, so a rule there couldn't tell the PO from a team lead.
- `scripts/po` passes no prompt of its own (`exec claude --agent po -n po "$@"`). The PO's standing
  instructions are `.claude/agents/po.md` only, so the script needs no change.
- `.claude/agents/team-lead.md` says a team lead never merges. That stays true, so the file doesn't change.
- No test reads the text of the docs or the agent files (`tests/test_subagent_guard.py` uses `po.md` only as
  a path).
- Each merge leaves every other ready PR behind `main` (strict mode). For a releasing PR the bump is then
  stale as well (`releasing.md` → *Two releasing PRs at once*).

## Design

### 1. Who merges, and which PRs stay the owner's

A new subsection **Merging** in `way-of-working.md` §8, after *From branch ready to PR ready*, owns the
rule. Other places point to it.

The PO merges a PR when all of these hold:
- the PO took it through *From branch ready to PR ready* in this or an earlier session, and marked it ready;
- it is not an owner-merge PR;
- it has no open review thread and no changes-requested review.

A PR is **owner-merge** when its diff touches any of:
- charge start or stop (the code that calls them, or what decides when they are called);
- auth, tokens or reauth;
- a hard rule (`CLAUDE.md` → *Hard rules*);
- `.claude/`, `.pre-commit-config.yaml` or `.github/workflows/`.

The PO decides this in the acceptance check, from the PR's changed files and its spec. The path cases are
read from `gh pr diff <n> --name-only`. For charge and auth, a plan task tagged `Model: opus` for that reason
(§5) is a sign. When the PO is less than 90% sure, the PR is owner-merge.

A new decision alone doesn't make a PR owner-merge: the owner approved it in the spec (the escalation list
in §8 already sends every new decision to the owner).

For an owner-merge PR the PO does what it does today: marks it ready, tells the owner that it is theirs to
merge and why, and goes on. The PR description says which of the two it is.

### 2. The merge

After `gh pr ready` (§8 *From branch ready to PR ready*, step 6), for a PR the PO may merge:

1. Wait for the required checks on the PR: `gh pr checks <n> --required --watch`. A failed check goes back
   to the team lead with the finding (resumed, as in *After ready*).
2. Merge the commit the PO checked: `gh pr merge <n> --squash --match-head-commit <sha>`, where `<sha>` is
   the head the smoke test ran on. Never `--admin` and never `--auto`.
3. If GitHub refuses the merge:
   - **behind `main`:** resume the team lead, which merges `origin/main` in (and for a releasing PR runs the
     bump step again, `releasing.md` → *Two releasing PRs at once*) and reports `branch ready`. The PO then
     runs `scripts/smoke` on the new head, repeats the visual check only if `main` brought a visible change,
     and starts again at step 1;
   - **an open review thread, or changes requested:** escalate to the owner. The PO resolves no thread and
     dismisses no review;
   - **anything else:** escalate.

**One merge at a time.** The PO finishes the steps in §3, including the release check, before it merges the
next PR. Two ready PRs merge in the order they became ready. When the PO knows before the merge that the PR
is behind `main` (another PR merged since its smoke run), it goes straight to *behind `main`* above.

The team lead is stopped and its worktrees removed at ready, as today; a PR that needs the team lead again
gets it back through the resume in *After ready*.

### 3. After a merge

A new subsection **After a merge** in §8. The PO runs it for every merged PR of the PO flow, whether the PO
or the owner merged it (the loop finds the owner's merges, as today).

1. **`main` is green:** watch the required workflows on `main` for the merge commit, and the `auto-release`
   runs (`releasing.md` → *What happens on merge*).
2. **The release, for a releasing PR:** the tag `vX.Y.Z` is on the merge commit, and the release exists with
   the changelog section as its notes. That HACS offers the version is left to the owner; the PO says so in
   its message.
3. **On a failure in 1 or 2:** escalate, and merge nothing more until the owner has answered. The PO never
   re-runs a workflow run on `main` and never pushes a tag (`releasing.md` → *When a release fails*).
4. **Labels:** the issue is closed by `Closes #n`; remove `active` if it is still there.
5. **The main checkout:** `git fetch`; when it is on `main`, `git pull --ff-only`; then `uv sync` (§6
   *Git guards*). Delete the merged local branch (`git branch -D <type>/<topic>`).
6. **Tell the owner** in the terminal: which PR merged, and the version it released, if any.
7. **Other ready PRs** are now behind `main`: each goes through *behind `main`* in §2, one at a time, in the
   order they became ready.
8. **Pick the next issue** (*Picking and starting an issue*).

### 4. Where the rule changes

| File | Change |
|---|---|
| `CLAUDE.md` | Hard rule 1 names who merges: only the PO and the owner; the PO when `way-of-working.md` §8 *Merging* allows it, the owner otherwise; a team lead, the controller and a subagent never. The `scripts/po` line under *Commands* is unchanged |
| `docs/way-of-working.md` §1 | Step 11: the owner merges; in the PO flow the PO merges what §8 *Merging* allows |
| `docs/way-of-working.md` §6 | *Merging and pushing* says the same and points to §8. In the may/may-not table, "Merge PRs" stays in the controller's *may not* column, with a pointer that the PO may (§8) |
| `docs/way-of-working.md` §8 | The intro and *Roles* (the PO no longer "never merges"; the team lead and workers still never do); the owner-only list (merging only owner-merge PRs; re-running and tagging unchanged); *From branch ready to PR ready* step 6 leads into *Merging*; the new *Merging* and *After a merge* subsections; *After ready* (a branch behind `main` joins the reasons to resume a team lead, with the smoke re-run); the loop's merged-PR check runs *After a merge* |
| `.claude/agents/po.md` | The description and the intro no longer say "the owner merges". In *Never*: "Merge a PR" becomes merging an owner-merge PR, merging with `--admin` or `--auto`, and resolving a review thread or dismissing a review to get a merge through. Force-push, tags, re-runs on `main` and GitHub settings stay |
| `docs/releasing.md` | "the owner may merge days after the bump" no longer names the owner; *What happens on merge* says that in the PO flow the PO does the check afterwards (pointing to §8 *After a merge*); *Two releasing PRs at once* points to §8 for the merge order |
| `docs/decisions.md` | The new entry D45, and D35's status |

Not changed: `.claude/agents/team-lead.md`, `.claude/settings.json`, `scripts/po`, `scripts/team-lead`,
`docs/README.md`. D39 and D40 mention the owner merging only in their *Why*; entries aren't edited, and D45
is the one that changes who merges.

The decision-log entry:

```markdown
### D45: The PO merges ready PRs
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** In the PO flow the PO squash-merges a PR it has made ready, once the required checks are
  green on the head it checked, releasing PRs included, and then checks `main` and the release. PRs that
  touch charge start or stop, auth, tokens or reauth, a hard rule, `.claude/`, `.pre-commit-config.yaml` or
  `.github/workflows/` stay the owner's to merge. Nobody else merges.
- **Why:** The owner's ruling (#84): a finished PR shouldn't wait for the owner to press merge, while the
  changes that can cost money, lock the account or weaken the process keep the owner's eye.
- **Source:** [PO merge spec](superpowers/specs/2026-10-01-po-merge-design.md), Decisions
```

### 5. When the new rule starts to apply

- This PR changes a hard rule and `.claude/`, so it is itself owner-merge.
- A running PO session keeps the instructions it started with (`.claude/agents/po.md` is read when the
  session starts, from the main checkout's working tree). After the owner merges this PR, the owner updates
  the main checkout to the new `main`, ends the running `po` session and starts a fresh `scripts/po`. Only
  that session merges. A PO started from a main checkout that is behind `main` still has the old rule.
- Team leads that are running need nothing: their rule doesn't change.

The PR description says this too, so the owner sees it at merge time.

## Execution shape

Docs only: no code and no tests change, and every task is a docs task, so `Model: opus` (D33). One wave of
three tasks with disjoint files, written against the names this spec fixes (the §8 subsections *Merging* and
*After a merge*, and D45):

| Task | Files | Guarded files |
|---|---|---|
| 1 | `docs/way-of-working.md` | none |
| 2 | `CLAUDE.md`, `.claude/agents/po.md` | `.claude/agents/po.md` |
| 3 | `docs/releasing.md`, `docs/decisions.md` | none |

Checks, per task and on the branch: the gates (`CLAUDE.md` → *Commands*), and a search of the repo outside
`docs/superpowers/` for places that still say only the owner merges or that the PO never merges.

`visible: no` (nothing changes in Home Assistant).

## Risks

- **A release goes out with nobody watching.** The PO checks `main`, the tag and the release after every
  merge, merges nothing more on a failure, and tells the owner each time.
- **The PO misjudges an owner-merge PR.** The path cases are read from the changed files; for charge and
  auth the PO takes the owner-merge side when it is under 90% sure.
- **A workflow PR merged between a releasing merge and its tag** gives the HTTP 403 case in `releasing.md`.
  Workflow PRs are owner-merge, and the PO merges nothing until the release check is done; the owner still
  has to avoid that window, as today.
- **The merged commit differs from what the PO tested.** `--match-head-commit` refuses a head that moved,
  and strict mode refuses a branch behind `main`, which sends the PR back through smoke.
- **`gh pr merge --squash` takes its commit title and body from the repo's defaults** (the PR title and
  body). The PO checks the merge commit's title against the PR title after its first merge, and escalates
  if they differ.
