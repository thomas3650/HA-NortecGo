# Plans name a worktree by a placeholder — design

Date: 2026-10-01 · Branch: `docs/plan-paths` · Issue: #99

## Goal

- **What:** `way-of-working.md` §1 step 5 says that a plan names a worktree by a placeholder or a relative
  path, never by a local absolute path.
- **Why:** a plan is a committed file in a public repo, and a path under a home directory holds the local
  user name (hard rule 3: nothing private). Earlier plans already avoid such paths, but nothing says so:
  §1 *Parallel waves* only says that the dispatches give the worktree's absolute path. The plan for #89 held
  such a path until its review, and was fixed before its commit (#99).
- **Not in this work:**
  - a hook or check that enforces it (a new rule, and an edit to `.pre-commit-config.yaml`);
  - specs and other docs, by choice: the sentence's reason holds for them too, but the issue scopes plans,
    the one kind of file written to be run from a worktree, and the second search in *Execution shape*
    covers the whole repo;
  - `CLAUDE.md`: hard rule 3 is applied, not edited;
  - `decisions.md`, `.claude/`, `scripts/`, `.devcontainer/` and `.github/`;
  - the text of *Parallel waves* and §8 on what the dispatches and commands use.
- **Done when:** §1 step 5 ends with the sentence in *Design*, the two searches in *Execution shape* give
  the results named there, and the gates pass.

## Decisions

Proposed by the team lead and approved by the PO (issue #99, 2026-10-01).

| Topic | Decision |
|---|---|
| Where | Only `docs/way-of-working.md` §1 step 5, one sentence added at its end |
| What is ruled out | Only a local absolute path. The placeholders in the sentence (`<worktree>`, `<HA-NortecGo-wt>/<topic>`) are examples, and a relative path (`../HA-NortecGo-wt/<topic>`, as `way-of-working.md` itself writes) stays fine |
| The dispatch side | One clause and a link: the sentence says the dispatch gives the path and points to *Parallel waves*, which holds the rule that the dispatches give the worktree's absolute path (§7, *No duplication*) |
| Decision log | No entry: the sentence writes down what plans already do and applies hard rule 3. No lasting decision is made |
| Enforcement | None beyond the reviews: `full-reviewer` reads the plan against `way-of-working.md` |
| Title | `process: plans name a worktree by a placeholder (#99)` (the type #89's change to `way-of-working.md` used; the branch name stays); non-releasing, so no `CHANGELOG.md` entry and no bump |

Facts used:

- No plan in `docs/superpowers/plans/` names a worktree by a local absolute path. Plans write `<worktree>`,
  `<HA-NortecGo-wt>/<topic>` or `<HA-NortecGo-wt>/<topic>-task-<n>`
  (`git grep -n -e '<worktree>' -e '<HA-NortecGo-wt>' -- docs/superpowers/plans`), and one plan also writes
  the relative form (`git grep -n -e '\.\./HA-NortecGo-wt' -- docs/superpowers/plans`).
- `way-of-working.md` writes the relative form itself: `../<repo>-wt/<topic>-task-<n>` in *Parallel waves*
  and `../HA-NortecGo-wt/<topic>` in §8. So the sentence must not rule it out.
- No tracked file holds a path under a home directory. The second search in *Execution shape* leaves out
  `.devcontainer/`, whose one absolute path is the generic path inside the container image: not a plan, and
  not private.
- Not every local absolute path holds a user name (plans use `/tmp/…` for commit-message files), so the
  sentence says "can hold", and it is about worktrees only.
- Hard rule 3 names no paths. It applies because a path under a home directory holds the user name of the
  machine it was written on, and the rule's subject is "nothing private in this public repo".
- *Parallel waves* has "(For a team lead in the PO flow: `<HA-NortecGo-wt>/<topic>-task-<n>`, by absolute
  path; §8.)" and §8 has "by absolute path" for the same worktrees. Both are about the command the team lead
  runs, not about what a plan's text holds, so the new sentence doesn't contradict them: the plan holds the
  placeholder, and the command and the dispatch hold the path.
- No test reads the text of `way-of-working.md`.

## Design

One edit in `way-of-working.md` §1 step 5. The sentence goes at the end of the step, after the sentence on
`text` blocks, which itself doesn't change. The wording below is the text to land; the plan fixes the line
breaks, and keeps "local absolute path" on one line, for the first search in *Execution shape*.

```text
A plan is a public file, so it names a worktree by a placeholder (`<worktree>`, or
`<HA-NortecGo-wt>/<topic>`, say) or a relative path, never by a local absolute path, which can hold the
local user name (hard rule 3); the dispatch gives the path ([Parallel waves](#parallel-waves)).
```

For the reader of this spec only, not text to land: `<worktree>` is the form a dispatch fills in. `<HA-NortecGo-wt>/<topic>` is a team lead's issue worktree in
the PO flow, which it knows from its start prompt; it passes the path on in its dispatches.

## Execution shape

Docs only: no code and no tests change. One docs task, so `Model: opus` (D33).

| Task | Wave | Files | Guarded files |
|---|---|---|---|
| 1 | 1 | `docs/way-of-working.md` | none |

It runs in the issue worktree, `<HA-NortecGo-wt>/plan-paths`; a wave of one task needs no task worktree.

Checks, on the task and on the branch: the gates (`CLAUDE.md` → *Commands*), and two searches.

```bash
git grep -n -e 'local absolute path' -- . ':!docs/superpowers'
```

It gives one hit, in `docs/way-of-working.md`, inside §1 step 5.

```bash
git grep -nE '/(Users|home)/' -- . ':!.devcontainer'
```

It gives no hit: this work's own spec and plan follow the sentence too.

`visible: no` (nothing changes in Home Assistant).

## Risks

- **The sentence is read as a new rule.** It is hard rule 3 applied to one kind of file, and it describes
  what every earlier plan does (*Facts used*). If a review finds that it needs a decision-log entry or an
  edit to a hard rule, the work stops and goes to the PO as `blocked`.
- **The sentence is read against "by absolute path" in *Parallel waves* and §8.** Those are about commands
  and dispatches; the sentence names the dispatch as where the path is given, and points to *Parallel
  waves*.
