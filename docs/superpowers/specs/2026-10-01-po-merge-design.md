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
  all say the same thing about who merges, when and how, and what the PO does after a merge; the search in
  *Execution shape* finds only the hits listed there. The gates pass.

## Decisions

Proposed by the team lead and ruled by the owner through the PO (issue #84, 2026-10-01).

| Topic | Decision |
|---|---|
| Who merges | Only the PO and the owner. The PO merges when the rules below allow it; otherwise the owner does. A team lead, the controller of the direct flow and a subagent never merge |
| Releasing PRs | The PO may merge them (`feat`, `fix`, `perf`), and so publish a release |
| Owner-merge PRs | A PR stays the owner's to merge when it touches charge start or stop; auth, tokens or reauth; a hard rule (`CLAUDE.md` → *Hard rules*); `.claude/`; `.pre-commit-config.yaml`; or `.github/workflows/`. A PR that only adds a decision the owner approved in its spec does not count |
| When | Right away, once the PR is ready and the required checks are green on the head commit the PO checked |
| How | `gh pr merge <n> --squash --match-head-commit <sha>`; never `--admin`, never `--auto`. An open review thread, a changes-requested review or a comment made after ready stops the merge until the owner gives a go-ahead (a comment asking for a change goes to the team lead first); the PO resolves no thread to get a merge through |
| A PR behind `main` | The resumed team lead updates it (merging `origin/main` in, and for a releasing PR the bump step again). The PO then re-runs `scripts/smoke` on the new head before it merges |
| Proposed; the owner's approval of this spec confirms them | A PR comment or review made after ready stops the PO's merge until the owner gives a go-ahead, also after the team lead has fixed what the comment asked for (stricter than the ruling, which named an open thread and changes requested). An owner-merge PR that is behind `main` is brought up to date only when the owner says they are about to merge it |
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
- `version-check` runs only on a PR that isn't a draft. On a draft its job is skipped, the check shows as
  `skipping`, and GitHub counts a skipped required check as passed. Its first real run starts after
  `gh pr ready`, so right after ready the required checks can look green before `version-check` has run.
- With no required approvals, GitHub may not refuse a merge for a changes-requested review, and `gh`'s
  refusal doesn't always say why. So the PO checks reviews, threads and comments itself before it merges
  (§2).
- GitHub titles a squash commit with the PR title followed by ` (#<PR number>)`, as on `main` today.
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
- nothing on the PR waits for the owner (§2, step 3).

A PR is **owner-merge** when its diff touches something §8 *Escalation* always escalates for and a diff can
touch. *Merging* points at that list rather than repeating it, and names the one exception:
- charge start or stop (the code that calls them, or what decides when they are called);
- auth, tokens or reauth;
- a hard rule (`CLAUDE.md` → *Hard rules*);
- `.claude/`, `.pre-commit-config.yaml` or `.github/workflows/`;
- but not a new decision alone: the owner approved it in the spec.

The PO decides this in the acceptance check (step 4 of *From branch ready to PR ready*), from the PR's
changed files and its spec. The path cases are read from `gh pr diff <n> --name-only`. For charge and auth,
a plan task tagged `Model: opus` for that reason (§5) is a sign. When the PO is less than 90% sure, the PR
is owner-merge.

For an owner-merge PR the PO does what it does today: marks it ready, tells the owner that it is theirs to
merge and why, and goes on. The PR description gets one line saying who merges it (the PO, or the owner and
why).

**What the PO records.** When it marks a PR ready, the PO writes to the PR's entry in
`.git/po-sessions.json`: that it is ready, who merges it (`po` or `owner`), the head commit the smoke
test ran on (the *checked head*), and the *cleared time* (§2). A later session reads it there. If the entry
or the checked head is missing, or the PR's head is a different commit, the PR goes through *From branch
ready to PR ready* again before any merge.

### 2. The merge

After `gh pr ready` (§8 *From branch ready to PR ready*, step 6), for a PR the PO may merge, after a
`git fetch`:

1. **Up to date.** `origin/main` is merged into the PR's head
   (`git merge-base --is-ancestor origin/main origin/<branch>`). If not, go to *Behind `main`* below; that
   covers a branch with a merge conflict too.
2. **The required checks have run and passed on the checked head.**
   `gh pr checks <n> --required --json name,bucket` shows all six in bucket `pass`. The PO waits while any is
   `pending`, and while `version-check` is `skipping`: on a draft it is skipped, a skipped check counts as
   green for GitHub, and its real run starts only after `gh pr ready`. A failed check goes back to the team
   lead with the finding (resumed, as in *After ready*).
3. **Nothing waits for the owner.** All of these hold:
   - the head is still the checked head, and no review has the state `CHANGES_REQUESTED`
     (`gh pr view <n> --json headRefOid,reviews,comments`);
   - no review thread is unresolved (`gh api graphql`, the PR's `reviewThreads { isResolved }`; threads from
     the owner's review of the spec and plan on the draft count too);
   - no review, PR comment or reply in a review thread is newer than the PR's *cleared time* (below; the
     same GraphQL query gives each thread's latest comment time).

   Otherwise the PO doesn't merge, and the merge waits for the owner's go-ahead:
   - a comment that asks for a change goes to the resumed team lead, as *After ready* does today ("changes
     requested" there means such a comment). After the fix the PR goes through *From branch ready to PR
     ready* again, and the PO then asks the owner for a go-ahead, naming the comment and the fix;
   - anything else, or a comment the PO can't place, is escalated to the owner at once.

   The PO resolves no thread and dismisses no review: a review in the state `CHANGES_REQUESTED` stops the
   merge until the owner dismisses it. (PRs in the PO flow are opened under the owner's account, so the
   owner can't request changes on them; a comment is the owner's way to stop a merge. The PO itself writes
   nothing on a PR after ready except its description.)
4. **Merge the checked head:** `gh pr merge <n> --squash --match-head-commit <checked head>`. Never `--admin`
   and never `--auto`. If GitHub refuses, the PO starts once more with the `git fetch` and step 1 (`main` may
   have moved during the wait in step 2); a second refusal is escalated.

**The cleared time** is part of what the PO records (§1), in UTC and ISO 8601 as GitHub's timestamps are:
first the time it marked the PR ready. When the owner gives a go-ahead in step 3 (to an escalation, or
after a team lead's fix), the PO sets it to the time of that answer, so the comments the owner has dealt
with no longer stop the merge; an unresolved thread still does, until the owner resolves it. Nothing else
moves it: not a new checked head, and not the team lead's fix alone.

**Behind `main`.** The PO resumes the team lead (*After ready*: the issue worktree is re-created). The team
lead merges `origin/main` in, for a releasing PR runs the bump step again (`releasing.md` → *Two releasing
PRs at once*), pushes, and reports `branch ready`. The PO then repeats *From branch ready to PR ready* on the
new head, with these differences: the visual check only if `main` brought a visible change; the acceptance
check only for the title, the bump and the PR description; no `gh pr ready` (it is ready already). Step 6's
clean-up runs again: the team lead is stopped and its worktrees and `wt/` branches are removed. The PO
records the new checked head and starts again with the `git fetch` and step 1.

To save a wasted smoke run, step 1 of *From branch ready to PR ready* gains the same test: a branch that
`origin/main` isn't merged into goes back to the team lead before the smoke test.

**One merge at a time, in order.** The PRs the PO may merge form a queue, in the order they became ready.
The PO merges the first, finishes §3 including the release check, and only then turns to the next. Only the
next PR in the queue is brought up to date; the ones behind it wait, since the next merge would leave them
behind again. A PR that waits for the owner's answer or for a team lead's fix (step 3, or a refusal in
step 4) steps out of the queue until the owner's go-ahead comes, and then rejoins it at the front. A resume
for the first PR in the queue takes a free team-lead slot before a new issue is picked.

**Owner-merge PRs** are not in the queue and block nothing. One that falls behind `main` stays as it is
until the owner says they are about to merge it; the PO then brings it up to date (*Behind `main`*, without
the merge) and tells the owner. Updating it after every PO merge would cost a team-lead resume and a smoke
run each time.

The loop also picks up a ready PR the PO may merge that isn't merged yet (checks still running when a session
ended, an escalation since answered, a PR waiting for its turn), and carries on here.

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
5. **The main checkout:** `git fetch --prune`; when it is on `main`, `git pull --ff-only`; then `uv sync`
   (§6 *Git guards*). Delete the merged local branch (`git branch -D <type>/<topic>`; its worktrees went at
   ready). Mark the PR's entry in `.git/po-sessions.json` as merged; its D-numbers stay recorded.
6. **Tell the owner** in the terminal: which PR merged, and the version it released, if any.
7. **The next PR in the queue** (§2), if there is one; it is now behind `main`. Owner-merge PRs that are
   behind stay as they are (§2, *Owner-merge PRs*).
8. **Pick the next issue** (*Picking and starting an issue*).

### 4. Where the rule changes

| File | Change |
|---|---|
| `CLAUDE.md` | Hard rule 1 names who merges: only the PO and the owner; the PO when `way-of-working.md` §8 *Merging* allows it, the owner otherwise; a team lead, the controller and a subagent never. The `scripts/po` line under *Commands* is unchanged |
| `docs/way-of-working.md` §1 | Step 11: the owner merges; in the PO flow the PO merges what §8 *Merging* allows |
| `docs/way-of-working.md` §6 | *Merging and pushing* says the same and points to §8. In the may/may-not table, "Merge PRs" stays in the controller's *may not* column, with a pointer that the PO may (§8) |
| `docs/way-of-working.md` §8 | The intro and *Roles* (the PO no longer "never merges"; the team lead and workers still never do); the owner-only list (merging whatever *Merging* doesn't give the PO; re-running and tagging unchanged); *From branch ready to PR ready*: step 1 sends back a branch that `origin/main` isn't merged into, step 4 gains the owner-merge decision and the PR description's who-merges line, step 6 records the entry in `.git/po-sessions.json` and leads into *Merging*; *State* names what that file now holds per PR; the new *Merging* and *After a merge* subsections; *After ready*: changes requested (a comment asking for a change) still resume the team lead when a slot is free, and the merge then waits for the owner's go-ahead; a branch that `origin/main` isn't merged into (a merge conflict and a stale bump included) resumes it only for the first PR in the queue, and for an owner-merge PR once the owner says they are about to merge it, followed by the repeat of *From branch ready to PR ready*; such a resume takes a free slot before a new issue; the loop's merged-PR check runs *After a merge*, and the loop carries on *Merging* for a ready PR that isn't merged yet |
| `.claude/agents/po.md` | The description and the intro no longer say "the owner merges". In *Never*: "Merge a PR" becomes merging an owner-merge PR, merging with `--admin` or `--auto`, and resolving a review thread or dismissing a review to get a merge through. Force-push, tags, re-runs on `main` and GitHub settings stay |
| `docs/releasing.md` | "the owner may merge days after the bump" no longer names the owner; *What happens on merge* says that in the PO flow the PO does the check afterwards (pointing to §8 *After a merge*); *Two releasing PRs at once* points to §8 for the merge order |
| `docs/decisions.md` | The new entry D45, and D35's status |

Not changed: `.claude/agents/team-lead.md`, `.claude/settings.json`, `scripts/po`, `scripts/team-lead`,
`docs/README.md`, `.claude/agents/implementer.md`. D35's *Decision* and *Why* and D39's *Why* still mention
the owner merging: entries aren't edited beyond D35's status, and D45 is the one that changes who merges.

The decision-log entry:

```markdown
### D45: The PO merges ready PRs
- **Date:** 2026-10-01 · **Status:** active
- **Decision:** In the PO flow the PO squash-merges a PR it has made ready, releasing PRs included, once
  the required checks are green on the head it checked, and then checks `main` and the release. PRs that
  touch charge start or stop, auth, tokens or reauth, a hard rule, `.claude/`, `.pre-commit-config.yaml` or
  `.github/workflows/` stay the owner's to merge, and nobody else merges.
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
- `gh pr merge` in the PO session asks the owner for permission unless the owner's own permission setup
  allows it. That setup is the owner's and outside this PR (§8 *Roles*, owner only).
- Team leads that are running need nothing: their rule doesn't change.

The PR description says this too, so the owner sees it at merge time.

## Execution shape

Docs only: no code and no tests change, and every task is a docs task, so `Model: opus` (D33). The branch
has `origin/main` merged in first (D42 and D43 are on it).

| Task | Wave | Files | Guarded files |
|---|---|---|---|
| 1 | 1 | `docs/way-of-working.md` | none |
| 2 | 2 | `CLAUDE.md`, `.claude/agents/po.md` | `.claude/agents/po.md` |
| 3 | 2 | `docs/releasing.md`, `docs/decisions.md` | none |

Tasks 2 and 3 point at Task 1's new subsections, so they start once Task 1 is on the feature branch (a task
with a `Guarded files:` line never starts ahead of its inputs).

Checks, per task and on the branch: the gates (`CLAUDE.md` → *Commands*), and this search, every hit read:

```bash
git grep -niE 'merg' -- . ':!docs/superpowers' ':!uv.lock' ':!custom_components' ':!tests' ':!scripts' ':!.github'
```

Hits about who merges that are right to stay:
- `docs/decisions.md`: D35's *Decision* and *Why*, and D39's *Why* (history; D35's status points to D45);
- `.claude/agents/team-lead.md` and `.claude/agents/implementer.md`: their own "never merge" lines;
- `docs/way-of-working.md` §6: "Merge PRs" in the controller's *may not* column.

Every other hit either isn't about who merges, or says what this spec says.

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
- **`gh pr merge --squash` takes its commit title and body from the repo's defaults.** After its first
  merge the PO checks that the merge commit's title is the PR title followed by ` (#<PR number>)`, and
  escalates if it isn't.
