# PR descriptions link the spec and plan at a commit — design

Date: 2026-10-02 · Branch: `docs/pr-links` · Issue: #101

## Goal

- **What:** `way-of-working.md` §1 step 6 says which form the links to the spec and plan take in a PR
  description: a link to the pushed commit that holds the file, by its full SHA. The PR template's comment
  points to that step.
- **Why:** step 6 asks for "links to the spec and plan" and names no form. Recent PRs link the files on the
  branch, and the repo deletes the branch at merge, so the links return 404 afterwards (#98's and #100's
  do). The owner reviews the spec and plan on the draft PR, so the link must work before the merge, and
  it must still work after the branch is gone.
- **Not in this work:**
  - the links in PRs that are already merged. This work's PR names them in its learnings step, as a
    question to the PO: whether they become a backlog issue (§6, *Backlog*);
  - a hook or check that enforces the form (a new rule, and an edit to `.pre-commit-config.yaml` or
    `.github/workflows/`);
  - `way-of-working.md` outside §1 step 6: step 10 and §8 already say that the PR description is updated,
    and don't change;
  - `CLAUDE.md`, `decisions.md`, `.claude/`, `scripts/` and `.github/workflows/`.
- **Done when:** §1 step 6 holds the two sentences in *Design*, the template's comment points to the step,
  the checks in *Execution shape* give the results named there, and the gates pass.

## Decisions

Proposed by the team lead and approved by the PO on 2026-10-02.

| Topic | Decision |
|---|---|
| Link form | `https://github.com/<owner>/<repo>/blob/<full sha>/<path>`, where the commit is the pushed one that holds the file's current text: for a new draft PR, the commit with the Ready spec and plan |
| Refresh | A commit link is not refreshed when the branch moves: it is a permalink and shows the file as it was at that commit. So step 6 also says to update the links when a later commit changes the spec or the plan. A link that isn't updated still works; it shows the older text |
| Full SHA | Not a short one: a short SHA resolves today, and can stop resolving when another object gets the same prefix |
| Where | Two sentences at the end of `docs/way-of-working.md` §1 step 6. `.github/pull_request_template.md`: its comment points to the step and states no form (§7, *No duplication*) |
| Decision log | No entry: this is a convention of form, as #89's and #99's additions to `way-of-working.md` were, and its reason sits in the sentence that lands. D16 (the draft PR) names no link form, so no decision changes |
| Enforcement | None. No listed check reads the links: `full-reviewer`'s branch review gets a commit range, not the PR description, and neither step 10 nor the PO's acceptance check (§8) names the links. The rule rests on whoever writes the description. Adding the links to one of those checks is outside this work's scope (§8, and `.claude/`) |
| This work's own PR | Uses the new form, as the first PR that does; the team lead checks it (*Execution shape*) |
| Title | `process: PR descriptions link the spec and plan at a commit (#101)` (the type #89's and #99's changes to `way-of-working.md` used; the branch name stays); non-releasing, so no `CHANGELOG.md` entry and no bump |

Forms that were rejected:

| Form | Why not |
|---|---|
| `blob/<branch>/<path>` | 404 once the merge deletes the branch |
| `blob/main/<path>` | The file is on `main` only after the merge, so the owner can't review the draft with it |
| A relative path (`docs/superpowers/…`) | Never resolves to the file in a PR description (*Facts used*) |
| `../blob/<ref>/<path>` | Only a shorter way to write one of the forms above, and it resolves differently on the PR's other tabs |
| A link into the PR's *Files changed* tab | Always current and survives the merge, but it shows a diff, not the rendered document, and its anchor is a hash of the path |

## Facts used

Checked on 2026-10-02 against the public repo, without a login except where a fact says otherwise. Each
check of a link looked at the final URL and the page title, not only at the status (see the last fact).

- The repo deletes the head branch when a PR is merged: the repo setting `delete_branch_on_merge` is on
  (read with `gh api`, so with a login), and `git ls-remote` shows `main` as the only branch.
- `blob/<branch>/<path>` for merged #98's spec, and for #100's: 404. #96 and #94 hold branch links too.
- `blob/main/<path>` for the same file: 200. It exists there only since the merge.
- `blob/<full sha>/<path>` at the head commit of #98, and at the head commit of the older #87: 200, with the
  file shown at that commit.
- `blob/<full sha>/<path>` at a commit that is not the head: 200, for #98's spec and its plan at that PR's
  spec-and-plan commit. That commit is on no branch: `main` holds the squash commit only.
- Why such a commit stays reachable: GitHub keeps the ref `refs/pull/<n>/head` after the merge
  (`git ls-remote` shows it for #87 and #98), and a branch here is never force-pushed
  (`way-of-working.md` §6), so every commit that was pushed to a PR's branch is in that ref's history.
- `blob/refs/pull/<n>/head/<path>` and `tree/refs/pull/<n>/head`: 404. So no link form both follows the
  branch and survives its deletion, and the choice is between a link that follows the branch and breaks,
  and one that is fixed and keeps working.
- A relative link in a PR description: GitHub keeps the `href` as written. The Markdown API, given the
  repo as context, renders `[x](docs/…)` with `href="docs/…"`, and the rendered description of #79 shows
  the same. The browser resolves it against the PR page, `/pull/<n>`, to `/pull/docs/…`, which isn't the
  file. #79, #31 and #25 hold such links.
- A short SHA resolves today, also one of 4 characters.
- Step 6 is the only place that says what a PR description links: no other doc, agent file or script
  names a link form. The template's comment says "Link the spec/plan in docs/superpowers/ for non-trivial
  work."
- No test reads the text of `way-of-working.md` or of the template.
- A trap when checking a link: `curl -L` reports 200 for a page that redirects to the login page. Check
  the page title or the final URL too.

## Design

Two edits.

**`docs/way-of-working.md` §1 step 6.** Two sentences go at the end of the step, after "The owner reviews
the spec and plan there.", which doesn't change, and neither does the rest of the step. The wording below
is the text to land; the plan fixes the line breaks, and keeps "full SHA" on one line, for the first
search in *Execution shape*.

```text
Each of the two links names the pushed commit that holds the file's current text, by its full SHA
(`https://github.com/<owner>/<repo>/blob/<full sha>/<path>`): a link to the branch breaks when the merge
deletes the branch. A commit link doesn't follow the branch, so when a later commit changes the spec or
the plan, update the links to that commit.
```

**`.github/pull_request_template.md`.** The comment under *What and why* becomes:

```text
<!-- One or two sentences. For non-trivial work, link the spec and plan (docs/way-of-working.md §1 step 6). -->
```

For the reader of this spec only, not text to land:

- "the pushed commit that holds the file's current text" is, for a new draft PR, the commit of step 6
  itself. The link works only once the commit is pushed, which step 6's order already gives: commit, push,
  open the PR.
- "update the links" names no role. Whoever changes the spec or the plan after the draft is opened (the
  controller, or a team lead in the PO flow) pushes the commit and edits the description. Step 10 and §8
  have the description updated before the PR is ready, which is a natural moment for it, but neither
  names the links, so nothing catches a missed update (*Risks*).
- Merging `origin/main` into the branch (§8, **Behind `main`**) changes neither file, so the links stay.

## Execution shape

Docs only: no code and no tests change. One docs task, so `Model: opus` (D33).

| Task | Wave | Files | Guarded files |
|---|---|---|---|
| 1 | 1 | `docs/way-of-working.md`, `.github/pull_request_template.md` | none |

It runs in the issue worktree, `<HA-NortecGo-wt>/pr-links`; a wave of one task needs no task worktree.

Checks, on the task and on the branch: the gates (`CLAUDE.md` → *Commands*), and three searches.

```bash
git grep -n -e 'full SHA' -- . ':!docs/superpowers'
```

It gives one hit, in `docs/way-of-working.md`, inside §1 step 6.

```bash
git grep -n -e 'step 6' -- .github
```

It gives one hit, in `.github/pull_request_template.md`.

```bash
git grep -n -e 'docs/superpowers/' -- .github/pull_request_template.md
```

It gives no hit: the old comment is replaced, not kept beside the new one. (Today it gives one.)

A check on this work's own PR, which the team lead runs, not the task: once after opening the draft PR,
and again before `branch ready`. The description's links to the spec and to the plan have the form in
*Decisions*, each names a pushed commit that holds that file's current text, each opens the file (the page
title names the file and the commit), and the description holds no `blob/docs/pr-links/` link.

`visible: no` (nothing changes in Home Assistant).

## Risks

- **The sentences are read as a new decision.** They set a convention of form, and no decision changes
  (*Decisions*, Decision log). If a review finds that the work needs a decision-log entry, or an edit to a
  hard rule, `.claude/`, `.pre-commit-config.yaml`, `.github/workflows/` or `scripts/`, the work stops and
  goes to the PO as `blocked`.
- **A link goes stale.** A commit link that isn't updated after a later change shows the older spec or
  plan. It still opens, and the PR's *Files changed* tab always shows the current text. The second
  sentence in step 6 asks for the update, and no check enforces it (*Decisions*, Enforcement).
- **GitHub stops keeping a merged PR's commits.** The links rely on `refs/pull/<n>/head` being kept. If
  that changes, the links of merged PRs break, as the branch links do today; the files themselves are on
  `main`.
