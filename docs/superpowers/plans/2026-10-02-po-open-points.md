# The PO flow's open points: a moved head, free slots, and a team lead that exited — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, the `Model:` tag, waves).

**Goal:** `docs/way-of-working.md` §8 gives the PO one instruction for a ready PR whose head moved, for what takes a free team-lead slot, for the 2-loops check on a waiting team lead, and for a team lead that exited while the PO was down; `docs/decisions.md` records it as D48 (#90, #97).

**Architecture:** one task makes eight edits in three subsections of `docs/way-of-working.md` §8 (*Picking and starting an issue*, *Merging*, *After ready, the loop, and failures*) and adds one entry at the end of `docs/decisions.md`. The spec fixes the wording; this plan fixes the line breaks too.

**Tech Stack:** Markdown only. No code and no tests change.

**Spec:** `docs/superpowers/specs/2026-10-02-po-open-points-design.md` (issues #90 and #97). The decisions in it are proposals for the owner's review; the PR is the owner's to merge.

## Global Constraints

- **Nothing private (hard rule 3):** no IDs, tokens or emails, no real-instance data, and no local absolute path.
- **Docs principles (`way-of-working.md` §7):** each fact lives in one place. The slot order is written once, in **Free slots**; *Picking and starting an issue* and the new last bullet point to it. The moved-head rule is written once, in **A moved head**; step 3 of the merge points to it. The resume command is not repeated.
- **The wording is fixed:** the text in Task 1's blocks lands exactly as written there, line breaks included.
- **Only the listed passages change.** Don't reword neighbouring text. Don't touch any other file: not `CLAUDE.md`, `.claude/`, `scripts/`, `.pre-commit-config.yaml`, `.github/`, `docs/notes.md` or `CHANGELOG.md`. In `docs/decisions.md`, no existing entry changes: D35 and D45 keep their status.
- **Gates before the commit** (`CLAUDE.md` → Commands): `uv run pytest -q`, then `uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`. The coverage gate (`uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`) too.
- **Every command runs in the issue worktree:** `cd <worktree> && …`, or `git -C <worktree> …`. The dispatch gives the worktree's absolute path. Edit files by absolute path under it.
- **Commit message:** write it with the Write tool to `/tmp/po-open-points-task-1-msg.txt` and commit with `git commit -F <file>`. No heredocs. End the message with the co-author trailer given in the dispatch. The title starts with `process:`.
- **Never push.** The team lead pushes.
- **PR:** title `process: settle the PO flow's open points (#90, #97)`. It doesn't release, so there is no `CHANGELOG.md` entry and no bump.

## Review Focus

Docs have no tests here, so each line names the check that pins it.

1. **A moved head keeps two instructions.** The old "or the PR's head is a different commit" clause must be
   gone, and step 3 must point to **A moved head**, not carry a second rule. Pinned by Task 1, Step 10's
   first and third searches, and by the task review against the spec's *Design* §1.
2. **The slot order is written twice, or a resume is left out of it.** The old sentence in **The queue**
   must be gone, and **Free slots** must be the one paragraph, with two pointers to it. Pinned by Step 10's
   first and second searches.
3. **The new last bullet resumes a team lead the PO stopped,** or one that is still running. It must test
   both `claude agents --json` and the issue worktree. Pinned by Step 10's `grep -cF` checks.
4. **The 2-loops line still reaches a waiting team lead,** or the "gone … resumed once" sentence changed.
   Pinned by Step 10's third search and its check on the "gone" sentence.
5. **A rule beyond the spec slips in, or a neighbouring passage is reworded.** Pinned by Step 10's
   `git diff --numstat` and removed-lines checks, and by the task review.

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (`docs/way-of-working.md`, `docs/decisions.md`) | Alone, in the issue worktree `<HA-NortecGo-wt>/po-open-points`; no task worktree |

No task has guarded files.

---

### Task 1: `docs/way-of-working.md` §8 and D48

Model: opus (a docs task, D33)
Wave: 1

**Files:**
- Modify: `docs/way-of-working.md` (§8: *Picking and starting an issue*, *Merging*, *After ready, the loop,
  and failures*)
- Modify: `docs/decisions.md` (one new entry at the end)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing another task uses.

Steps 1 to 8 are in `docs/way-of-working.md`, in the order the passages appear in the file. In every step
the first block is the text as it is today and the second is the text to land.

- [ ] **Step 1: *Picking and starting an issue* points to Free slots**

Under `### Picking and starting an issue`, the first paragraph reads:

```text
When fewer than 2 team leads run, the PO picks an open issue without `active`: all `v1` first, then `v2`,
then `v3`, the most important first within a label. It skips issues without an urgency label, issues in the
same area as one in progress, and issues that depend on an unfinished one. Then it:
```

Change it to:

```text
When fewer than 2 team leads run and no resume waits for the slot (*Merging*, **Free slots**), the PO picks
an open issue without `active`: all `v1` first, then `v2`, then `v3`, the most important first within a
label. It skips issues without an urgency label, issues in the same area as one in progress, and issues that
depend on an unfinished one. Then it:
```

- [ ] **Step 2: What the PO records, and the new paragraph A moved head**

Under `### Merging`, the paragraph **What the PO records** ends with these lines:

```text
go-ahead, or a team lead's fix and for which comment or check). A later session reads it there. If the entry
or the checked head is missing, or the PR's head is a different commit, the PR goes through *From branch
ready to PR ready* again before any merge.
```

Change them to this, which also adds a new paragraph after it (one blank line between the two, and one
blank line before "The merge, after a `git fetch`:", as there is today):

```text
go-ahead, or a team lead's fix and for which comment or check). A later session reads it there. If the entry
or the checked head is missing, the PR goes through *From branch ready to PR ready* again before any merge.

**A moved head.** The PO compares a ready PR's head with its checked head before it does anything else with
the PR: before step 1 of the merge, before it resumes a team lead for it, and for an owner-merge PR before
it brings it up to date. A head moves with a push the PO asked for, in a resume it started
(**Behind `main`**, a failed required check, a requested change); that push follows the resume's rule, which
ends with a new checked head. A later session sees that such a resume is open by the team lead's issue
worktree, which is in place only then. Any other moved head is escalated at once, on an owner-merge PR too,
and until the owner answers the PO runs no check on the PR and resumes no team lead for it. After the
owner's go-ahead the PR goes through *From branch ready to PR ready* again on the new head (without
`gh pr ready`), and the PO records the new checked head.
```

- [ ] **Step 3: Step 3 of the merge points to A moved head**

In the numbered list "The merge, after a `git fetch`:", step 3's first bullet reads:

```text
   - the head is still the checked head, and no review has the state `CHANGES_REQUESTED`
     (`gh pr view <n> --json headRefOid,reviews,comments`);
```

Change it to (the indent stays: three spaces before the `-`, five before the second line):

```text
   - the head is still the checked head (if not: **A moved head**), and no review has the state
     `CHANGES_REQUESTED` (`gh pr view <n> --json headRefOid,reviews,comments`);
```

- [ ] **Step 4: The cleared time**

The paragraph **The cleared time** holds these lines (its first line, which ends "marked the PR", doesn't
change):

```text
ready. When the owner gives a go-ahead in step 3 of the merge, the PO sets it to the time of that answer, so
the comments the owner has dealt with no longer stop the merge. Nothing else moves it: not a new checked
head, and not a team lead's fix alone.
```

Change them to:

```text
ready. When the owner gives a go-ahead in step 3 of the merge, or for a moved head, the PO sets it to the
time of that answer, so the comments the owner has dealt with no longer stop the merge. Nothing else moves
it: not a new checked head, and not a team lead's fix alone.
```

- [ ] **Step 5: The queue loses its slot sentence, and the new paragraph Free slots**

The paragraph **The queue** ends with its rule for rejoining the queue and a sentence on the free slot, and
the paragraph on owner-merge PRs follows it:

```text
at the front: after the owner's go-ahead (step 3 of the merge, or a refusal in its step 4), or once the fix
for a failed required check (step 2 of the merge) has been through *From branch ready to PR ready* again. A
resume for a PR that is first in the queue, or has stepped out of it, takes a free team-lead slot before a
new issue is picked.

Owner-merge PRs are not in the queue and block nothing. One that falls behind `main` stays as it is until
the owner says they are about to merge it; the PO then brings it up to date (**Behind `main`**, without the
merge) and tells the owner.
```

Change them to this: the rejoin rule names a moved head, the slot sentence is gone, the owner-merge
paragraph is as it was, and a new paragraph follows it (one blank line before `### After a merge`, as there is today):

```text
at the front: after the owner's go-ahead (step 3 of the merge, or a refusal in its step 4; for a moved head,
once the PR has then been through *From branch ready to PR ready* again), or once the fix for a failed
required check (step 2 of the merge) has been through *From branch ready to PR ready* again.

Owner-merge PRs are not in the queue and block nothing. One that falls behind `main` stays as it is until
the owner says they are about to merge it; the PO then brings it up to date (**Behind `main`**, without the
merge) and tells the owner.

**Free slots.** A free team-lead slot goes first to a resume for a ready PR, an owner-merge PR's included
(*After ready, the loop, and failures* says which those are). Then to a team lead that isn't running and is
to be resumed: one that is gone, one that exited while it waited and whose reply is there, or one the PO
found exited at its start. Only then is a new issue picked.
```

- [ ] **Step 6: Only a session that is no longer running is resumed**

Under `### After ready, the loop, and failures`, the paragraph that closes the first bullet ends:

```text
  name, and messages to `tl-<topic>` no longer reach it. Every resume in this section uses this resume
  command, run in the team lead's issue worktree.
```

Change it to:

```text
  name, and messages to `tl-<topic>` no longer reach it. Every resume in this section uses this resume
  command, run in the team lead's issue worktree, and only for a team lead `claude agents --json` no longer
  shows: `--bg` with `--resume` starts a copy of a session that is still running.
```

- [ ] **Step 7: The 2-loops check**

In the same subsection, this bullet:

```text
- A team lead that is gone is resumed once; if that fails, the PO escalates and leaves the issue `active`.
  One with nothing new in `claude logs <id>` for 2 loops is asked for its status, then escalated.
```

becomes (its first line doesn't change):

```text
- A team lead that is gone is resumed once; if that fails, the PO escalates and leaves the issue `active`.
  A running team lead that isn't waiting for the PO's reply to one of its messages, with nothing new in
  `claude logs <id>` for 2 loops, is asked for its status, then escalated.
```

- [ ] **Step 8: A team lead that exited while the PO was down**

The subsection's last bullet ends with these two lines, which are also the last lines of the file:

```text
  in `.git/po-sessions.json`, and carries on; on that `hello`, each team lead re-sends the messages that
  failed, in order.
```

Add a new bullet after them, so that the file ends:

```text
  in `.git/po-sessions.json`, and carries on; on that `hello`, each team lead re-sends the messages that
  failed, in order.
- A `hello` to a team lead that exited while the PO was down reaches nothing. At its start the PO gives the
  `hello` as the prompt of the resume command to each team lead in `.git/po-sessions.json` that
  `claude agents --json` doesn't show and whose issue worktree is still in place (the PO removes it when it
  stops a team lead), when a slot is free (*Merging*, **Free slots**); the team lead then re-sends its kept
  messages as above. The PO can't tell whether it exited while it waited or failed, so this is the one
  resume of a team lead that is gone. The exception is a team lead with an open `PO question` on its issue:
  the PO knows it waits for that reply, and the bullet on a waiting team lead that exited applies, with the
  `hello` ahead of the reply in the prompt.
```

- [ ] **Step 9: D48 in `docs/decisions.md`**

The file ends with the entry `### D47: Total energy is summed in the integration`. Add one blank line after
its last line, and then this entry, as the new end of the file (one newline after its last line):

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

- [ ] **Step 10: Check the edits**

Run each command in the issue worktree.

```bash
git grep -n -e 'or the PR.s head is a different commit' -e 'One with nothing new' -e 'takes a free team-lead slot' -- docs/way-of-working.md
```

Expected: no output (before the edits: three hits). The three old sentences are gone.

```bash
git grep -c -e 'Free slots' -- docs/way-of-working.md
```

Expected: `docs/way-of-working.md:3` (before the edits: no output). The paragraph and the two pointers to it.

```bash
git grep -c -e 'A moved head' -e 'or for a moved head' -e 'starts a copy' -e 'exited while the PO was down' -e 'that isn.t waiting for the PO.s reply' -- docs/way-of-working.md
```

Expected: `docs/way-of-working.md:6` (before the edits: no output). **A moved head** is on two lines (the
paragraph and step 3's bullet); the four other phrases are on one line each.

```bash
grep -cF "doesn't show and whose issue worktree is still in place" docs/way-of-working.md
grep -cF 'so this is the one' docs/way-of-working.md
grep -cF "an owner-merge PR's included" docs/way-of-working.md
grep -cF 'one that is gone, one that exited while it waited and whose reply is there' docs/way-of-working.md
grep -cF 'on an owner-merge PR too' docs/way-of-working.md
grep -cF 'A team lead that is gone is resumed once; if that fails, the PO escalates and leaves the issue `active`.' docs/way-of-working.md
```

Expected: `1` from each of the six. The last one shows the "gone" sentence is as it was (it gives `1` before
the edits too; the other five give `0`).

```bash
git grep -n -e '^### D48' -e '^### D47' -- docs/decisions.md
tail -n 1 docs/decisions.md
```

Expected: two hits, D47 before D48, and the last line of the file is D48's `- **Source:**` line.

```bash
git diff --numstat
```

Expected: `11	0	docs/decisions.md` and `40	16	docs/way-of-working.md`, and no other file.

```bash
git diff -- docs/way-of-working.md | grep -c '^-[^-]'
git diff -- docs/decisions.md | grep -c '^-[^-]'
```

Expected: `16` and `0`. Every removed line is from a "today" block of Steps 1 to 8; nothing is removed from
`docs/decisions.md`.

```bash
git diff -U0 | grep '^+[^+]' | awk 'length > 111'
```

Expected: no output: no added line is wider than 110 characters (111 with the leading `+`). The 110 is this
task's own limit, the width the neighbouring prose keeps; no doc sets it. This is a guard: it also prints
nothing before the edits.

- [ ] **Step 11: Run the gates**

```bash
uv run pytest -q
uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95
uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows
```

Expected: all pass, as on the branch before the task (no code changed).

- [ ] **Step 12: Commit**

Write this to `/tmp/po-open-points-task-1-msg.txt` with the Write tool, with the co-author trailer from the
dispatch as its last line:

```text
process: settle the PO flow's open points (#90, #97)

way-of-working §8: a ready PR whose head moved without the PO asking
is escalated; a free slot goes to a resume for a ready PR, then to a
team lead that is to be resumed, then to a new issue; the 2-loops
check skips a team lead that waits for the PO's reply; a team lead
found exited at the PO's start is resumed with hello. D48 records it.
```

Then:

```bash
git add docs/way-of-working.md docs/decisions.md
git commit -F /tmp/po-open-points-task-1-msg.txt
```

Expected: the hooks pass and one commit is added. Don't push.

---

## After the last task

The team lead runs, on the branch:

- the gates (`CLAUDE.md` → Commands);
- the spec's searches (*Execution shape*): no hit for the three old sentences, `docs/way-of-working.md:3`
  for `Free slots`, `docs/way-of-working.md:6` for the positive search, one hit for `^### D48`, and
  `git diff --name-only origin/main...HEAD` lists only `docs/way-of-working.md`, `docs/decisions.md` and
  this change's spec and plan.

Then learnings (§1 step 8): the two gaps the spec's *Risks* names go to the PO to file as issues. Then the
team lead merges `origin/main` in (another change edits §1 step 6 of the same file), and the branch review
(§1 step 9) follows. The PR description gets the section *Proposed decisions, for the owner's review* and
says the PR is the owner's to merge. `visible: no`.
