# The PO flow's open points: a moved head, free slots, and a team lead that exited — design

Date: 2026-10-02 · Branch: `process/po-open-points` · Issues: #90, #97

## Goal

- **What:** `way-of-working.md` §8 gets one instruction for each of five cases it leaves open today: a ready
  PR whose head moved after it was checked, a resume slot for an owner-merge PR, what takes a free slot
  first, the "nothing new for 2 loops" check on a team lead that only waits, and a team lead that exited
  while the PO was down.
- **Why:** each case has two instructions or none (#90, #97), so the PO has to guess. They were left out of
  #88 and #89 because each one needs a decision, not a wording fix.
- **Not in this work:**
  - `CLAUDE.md`, `.claude/`, `scripts/`, `.pre-commit-config.yaml` and `.github/workflows/` (see *Facts
    used*: none of them needs a change);
  - new state in `.git/po-sessions.json`, or any new message between the PO and a team lead;
  - the order among several resumes for ready PRs that wait for a slot at the same time (not asked in
    either issue; the PO takes them as they come up);
  - any rule beyond the five points in the two issues.
- **Done when:** §8 holds edits 1 to 5 in *Design*, `decisions.md` holds D48 (edit 6), the checks in *Execution
  shape* give what is named there, and the gates pass.

## Decisions

**These are proposals for the owner's review.** The owner is away; the team lead proposed each one and the
PO chose it (2026-10-02), preferring the option that keeps the owner in control and adds the least new
machinery. The PR is the owner's to merge (it changes §8, and the PO was told so), and its description lists
every point with the alternatives, so the owner can change any of them before merging.

| # | Point | Proposed decision | Alternatives not chosen |
|---|---|---|---|
| 1 | #90: a ready PR's head is no longer the checked head | A push the PO asked for (a resume it started) follows that resume's rule, and the PO records the new checked head. Any other moved head is escalated at once, on an owner-merge PR too; the PO checks nothing until the owner answers, and after the go-ahead the PR goes through *From branch ready to PR ready* again on the new head. Said once, in a paragraph the PO applies before step 1 of the merge; step 3 keeps its head test as the last check and points there | Re-check only, then merge without asking (the PO would merge commits nobody in the flow asked for). Re-check and always ask for a go-ahead (adds a go-ahead to every **Behind `main`** round, which D45 doesn't have) |
| 2 | #90: a resume slot for an owner-merge PR the owner is about to merge | The same priority as the resumes for the queue: it takes a free slot before a new issue is picked, as every resume for a ready PR does | No priority (the owner, who has said they are about to merge, waits behind new work) |
| 3 | #97: which goes first when a slot frees | One order, in one place: a resume for a ready PR, then a team lead that isn't running and is to be resumed (gone, or exited while waiting with its reply there, or found exited at the PO's start), then a new issue. *Picking and starting an issue* still lets the PO start a new issue while an exited team lead waits for its reply | The exited team lead keeps its slot (changes what "fewer than 2 team leads run" means, and a slot stays empty for as long as an owner answer takes). A new issue first (a half-done issue can wait behind any number of new ones) |
| 4 | #97: the "nothing new in `claude logs <id>` for 2 loops" line | It applies to a running team lead only, and not to one that waits for the PO's reply to one of its messages | Exclude only the one that exited (a running, waiting one is still escalated, with an answer the PO already knows). No change |
| 5 | #97: an exit while waiting for the PO's `hello` | At its start the PO resumes a team lead that is in `.git/po-sessions.json`, is no longer running and whose issue worktree is still in place, with `hello` as the prompt; the team lead then re-sends its kept messages as today. The PO can't tell an exit while waiting from a failure, so this is the one resume of a team lead that is gone | It doesn't count as the one resume (a team lead that really failed gets two automatic resumes). It counts only if the team lead re-sends nothing (the most exact, but a new conditional rule to track) |

Other decisions:

| Topic | Decision |
|---|---|
| Where | `docs/way-of-working.md` §8 (*Picking and starting an issue*, *Merging*, *After ready, the loop, and failures*) and `docs/decisions.md` |
| Decision log | One entry, D48 (number given by the PO). D35 and D45 keep their status: nothing they say is replaced |
| When the reply is known to be open | Point 5 leaves out a team lead with an open `PO question` on its issue: the PO knows it waits for a reply, so #89's bullet holds (resume with the reply, not the one resume) |
| Running sessions | Only a team lead `claude agents --json` no longer shows is resumed; said once, with the resume command |
| Title | `process: settle the PO flow's open points (#90, #97)`; non-releasing, so no `CHANGELOG.md` entry and no bump |

Facts used:

- `claude --help` (checked 2026-10-02): `--bg` with `--resume <session-id>` "continues that session in the
  background under the same ID, or starts a copy and says so when the session is already running". Found in
  #89's work and noted on #97.
- After each push the PO asks for, §8 already has the PR go through *From branch ready to PR ready* again:
  **Behind `main`** (which also says the PO records the new checked head), a failed required check (**The
  queue**), and a requested change (step 3 of the merge, "as in **Behind `main`**"). So a head that isn't
  the checked head, with no such resume open, moved without the PO asking.
- PRs in the PO flow are opened under the owner's account, and only the team lead pushes (§6), so an
  unasked push is the owner's own, or something went wrong. Both are the owner's to judge.
- At its start the PO already runs `claude agents --json` and reads `.git/po-sessions.json`
  (`.claude/agents/po.md`, start steps 1 and 3), so finding a team lead that exited needs no new state.
- A resume brings the team lead's transcript back, and the kept messages are in it. `team-lead.md` says
  the team lead re-sends them "when the PO's `hello` arrives"; a `hello` that arrives as the resume prompt
  meets that. `po.md` start step 4 ("Send `hello` to every team lead in `.git/po-sessions.json`") stays
  true: the `hello` reaches a running team lead by `SendMessage` and one that exited as its resume prompt,
  and step 1 tells the PO to follow §8. So neither agent file changes.
- A team lead whose PR is ready was stopped by the PO, and its issue worktree removed (*From branch ready to
  PR ready*, step 6). It is in `.git/po-sessions.json` and not running, and it must not be resumed at the
  PO's start. For a resume after ready the PO re-creates the worktree (*After ready*, first bullet), so a
  team lead that isn't running and whose issue worktree is in place exited; the PO didn't stop it.
- No test reads the text of `way-of-working.md` or `decisions.md`.

## Design

The wording below is the text to land; the task may change line breaks only, except that `**Free slots**`
and `**A moved head**` each stay on one line (the checks search for them). Edits 1 to 5 are in
`docs/way-of-working.md` §8; edit 6 is in `docs/decisions.md`.

### 1. A moved head: one rule, ahead of the merge (point 1)

In *Merging*, **What the PO records**, the last sentence

```text
If the entry
or the checked head is missing, or the PR's head is a different commit, the PR goes through *From branch
ready to PR ready* again before any merge.
```

becomes

```text
If the entry
or the checked head is missing, the PR goes through *From branch ready to PR ready* again before any merge.
```

and a new paragraph follows it:

```text
**A moved head.** The PO compares a ready PR's head with its checked head before it does anything else with
the PR: before step 1 of the merge, before it resumes a team lead for it, and for an owner-merge PR before
it brings it up to date. A head moves with a push the PO asked for, in a resume it started (**Behind
`main`**, a failed required check, a requested change); that push follows the resume's rule, which ends with
a new checked head. A later session sees that such a resume is open by the team lead's issue worktree, which
is in place only then. Any other moved head is escalated at once, on an owner-merge PR too, and until the
owner answers the PO checks nothing on the PR and resumes no team lead for it. After the owner's go-ahead
the PR goes through *From branch ready to PR ready* again on the new head (without `gh pr ready`), and the
PO records the new checked head; a PR the PO may merge then rejoins the queue at the front.
```

In step 3 of the merge, the first bullet

```text
   - the head is still the checked head, and no review has the state `CHANGES_REQUESTED`
     (`gh pr view <n> --json headRefOid,reviews,comments`);
```

becomes

```text
   - the head is still the checked head (if not: **A moved head**), and no review has the state
     `CHANGES_REQUESTED` (`gh pr view <n> --json headRefOid,reviews,comments`);
```

It stays as the last test before the merge. The rest of step 3 doesn't change.

In **The cleared time**, the sentence

```text
When the owner gives a go-ahead in step 3 of the merge, the PO sets it to the time of that answer, so
the comments the owner has dealt with no longer stop the merge.
```

becomes

```text
When the owner gives a go-ahead in step 3 of the merge, or for a moved head, the PO sets it to the time of
that answer, so the comments the owner has dealt with no longer stop the merge.
```

### 2. Free slots: one order (points 2 and 3)

In *Merging*, **The queue**, the last sentence of the first paragraph is removed:

```text
A
resume for a PR that is first in the queue, or has stepped out of it, takes a free team-lead slot before a
new issue is picked.
```

After the paragraph "Owner-merge PRs are not in the queue and block nothing. …" comes a new paragraph:

```text
**Free slots.** A free team-lead slot goes first to a resume for a ready PR, an owner-merge PR's included
(*After ready, the loop, and failures* says which those are). Then to a team lead that isn't running and is
to be resumed: one that is gone, one that exited while it waited and whose reply is there, or one the PO
found exited at its start. Only then is a new issue picked.
```

The first tier points to the first bullet of *After ready, the loop, and failures* and doesn't list the
resumes again (§7, *No duplication*). That bullet already names the owner-merge PR the owner is about to
merge, which settles point 2.

*Picking and starting an issue* points to the paragraph. Its first sentence

```text
When fewer than 2 team leads run, the PO picks an open issue without `active`: all `v1` first, then `v2`,
then `v3`, the most important first within a label.
```

becomes

```text
When fewer than 2 team leads run and no resume waits for the slot (*Merging*, **Free slots**), the PO picks
an open issue without `active`: all `v1` first, then `v2`, then `v3`, the most important first within a
label.
```

A team lead that exited while it waits for a reply that isn't there yet doesn't wait for a slot, so the PO
may pick a new issue in the meantime, as today.

### 3. Only a session that is no longer running is resumed

In *After ready, the loop, and failures*, the paragraph that closes the first bullet ends

```text
Every resume in this section uses this resume
command, run in the team lead's issue worktree.
```

It becomes

```text
Every resume in this section uses this resume
command, run in the team lead's issue worktree, and only for a team lead `claude agents --json` no longer
shows: `--bg` with `--resume` starts a copy of a session that is still running.
```

### 4. The 2-loops check (point 4)

In the bullet "A team lead that is gone is resumed once; …", the second sentence

```text
One with nothing new in `claude logs <id>` for 2 loops is asked for its status, then escalated.
```

becomes

```text
A running team lead that isn't waiting for the PO's reply to one of its messages, with nothing new in
`claude logs <id>` for 2 loops, is asked for its status, then escalated.
```

A team lead that waits for a reply is neither asked nor escalated. One that exited while waiting isn't
running, so the line no longer reaches it; #89's bullet covers it.

### 5. A team lead that exited while the PO was down (point 5)

A new bullet at the end of *After ready, the loop, and failures*, after "If the PO session ends, team leads
keep running. …", which itself doesn't change:

```text
- A `hello` to a team lead that exited while the PO was down reaches nothing. At its start the PO gives the
  `hello` as the prompt of the resume command to each team lead in `.git/po-sessions.json` that
  `claude agents --json` doesn't show and whose issue worktree is still in place (the PO removes it when it
  stops a team lead), when a slot is free (*Merging*, **Free slots**); the team lead then re-sends its kept
  messages as above. The PO can't tell whether it exited while it waited or failed, so this is the one
  resume of a team lead that is gone. The exception is a team lead with an open `PO question` on its issue:
  the PO knows it waits for that reply, and the bullet on a waiting team lead that exited applies, with the
  `hello` ahead of the reply in the prompt.
```

The issue worktree is the test, not "the PR isn't ready": a team lead the PO resumed after ready (*After
ready*, first bullet) can exit too, and its worktree was re-created for that resume; the team lead of a
ready or merged PR that the PO stopped has none.

### 6. D48, in `docs/decisions.md`

Added at the end:

```markdown
### D48: The PO flow's open points: a moved head, free slots, and a team lead that exited
- **Date:** 2026-10-02 · **Status:** active
- **Decision:** A ready PR whose head moved without the PO asking for the push is escalated, not re-checked
  and merged. A free team-lead slot goes first to a resume for a ready PR (an owner-merge PR's included),
  then to a team lead that isn't running and is to be resumed, then to a new issue. The check on a team lead
  with nothing new for 2 loops skips one that waits for the PO's reply, and a team lead a new PO finds
  exited, its issue worktree still in place, is resumed with `hello`, as its one resume.
- **Why:** Each case had two instructions or none (#90, #97). These keep the owner in control of what
  nobody planned, put started work before new work, and need no new state.
- **Source:** [PO open points spec](superpowers/specs/2026-10-02-po-open-points-design.md), Decisions
```

## Execution shape

Docs only: no code and no tests change. One docs task, so `Model: opus` (D33).

| Task | Wave | Files | Guarded files |
|---|---|---|---|
| 1 | 1 | `docs/way-of-working.md`, `docs/decisions.md` | none |

It runs in the issue worktree; a wave of one task needs no task worktree.

Checks, on the task and on the branch: the gates (`CLAUDE.md` → *Commands*), and these searches:

```bash
git grep -n -e 'or the PR.s head is a different commit' -e 'One with nothing new' -e 'takes a free team-lead slot' -- docs/way-of-working.md
git grep -c -e 'Free slots' -- docs/way-of-working.md
git grep -c -e 'A moved head' -e 'or for a moved head' -e 'starts a copy' -e 'exited while the PO was down' -e 'that isn.t waiting for the PO.s reply' -- docs/way-of-working.md
git grep -n -e '^### D48' -- docs/decisions.md
git diff --name-only origin/main...HEAD
```

- The first gives no hit (the three old sentences are gone).
- The second prints `docs/way-of-working.md:3`: the paragraph and the two pointers to it.
- The third prints `docs/way-of-working.md:6`: **A moved head** on two lines (the paragraph and step 3's
  bullet), and the four other phrases once each. `or for a moved head`, `starts a copy` and the last two
  phrases each stay on one line.
- The fourth gives one hit.
- The last lists only `docs/way-of-working.md`, `docs/decisions.md` and this change's spec and plan.

`visible: no` (nothing changes in Home Assistant).

Another team lead is changing §1 step 6 of `way-of-working.md` (#101). The edits here are all in §8, so
merging `origin/main` in before `branch ready` should not conflict.

## Risks

- **The PO reads a push it asked for as an unasked one.** In one session the PO knows which resumes it
  started. A later session sees it by the team lead's issue worktree, which is in place only while such a
  resume is open (edit 1).
- **The PO goes down in the middle of step 6** of *From branch ready to PR ready*, after it stopped the team
  lead and before it removed the worktree. The worktree test then reads a stopped team lead as one that
  exited. Rare; the resumed team lead has nothing to do and says so, and the PO removes the worktree.
- **A PO restart uses up a team lead's one resume** although it only waited (point 5). The cost is an
  earlier escalation if that team lead fails later; the owner then decides. The exception for an open
  `PO question` covers the case the PO can see.
- **The one resume isn't recorded.** `.git/po-sessions.json` doesn't say that a team lead's one resume is
  used, so a later PO session can't know. That gap exists today; point 5 makes it matter more often. It is
  outside the five points and is named in the learnings step, for the PO to file as an issue.
- **A message that reached a PO that then went down unanswered is not re-sent** on `hello`; only failed
  sends are. Also outside the five points, and named in the learnings step.
- **A later `claude` version changes what `--bg --resume` does to a running session.** The doc states what
  `claude --help` says today; a PO that finds otherwise raises it as a learning (§1 step 8).
- **The owner changes a proposal in review.** Each point is one edit in *Design*, so one can change
  without the others; D48's text follows.
