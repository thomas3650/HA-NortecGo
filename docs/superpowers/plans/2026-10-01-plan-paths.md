# Plans name a worktree by a placeholder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, the `Model:` tag, waves).

**Goal:** `docs/way-of-working.md` §1 step 5 says that a plan names a worktree by a placeholder or a relative path, never by a local absolute path (#99).

**Architecture:** one task adds one sentence at the end of §1 step 5 of one file. The spec fixes the wording; this plan fixes the line breaks too.

**Tech Stack:** Markdown only. No code and no tests change.

**Spec:** `docs/superpowers/specs/2026-10-01-plan-paths-design.md` (issue #99).

## Global Constraints

- **Nothing private (hard rule 3):** no IDs, tokens or emails, no real-instance data, and no local absolute
  path of a worktree: not in `docs/way-of-working.md`, not in the commit message, and not in the report's
  quoted commands where a placeholder does.
- **Docs principles (`way-of-working.md` §7):** each fact lives in one place. That the dispatches give the
  worktree's absolute path stays in *Parallel waves*; the new sentence points there.
- **The wording is fixed:** the text in Task 1's block lands exactly as written there, line breaks
  included. "local absolute path" stays on one line.
- **Only step 5's last line changes, and three lines are added after it.** Don't reword neighbouring text:
  the sentence on `text` blocks stays as it is, and so do *Parallel waves* and §8. Don't touch any other
  file: not `.claude/`, `scripts/`, `.pre-commit-config.yaml`, `.github/`, `CLAUDE.md`, `docs/decisions.md`,
  `docs/notes.md` or `CHANGELOG.md`.
- **Gates before the commit** (`CLAUDE.md` → Commands): `uv run pytest -q`, then `uv run ruff check && uv
  run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`.
  The coverage gate (`uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing
  --cov-fail-under=95`) too.
- **Every command runs in the issue worktree:** `cd <worktree> && …`, or `git -C <worktree> …`. The dispatch
  gives the worktree's absolute path. Edit files by absolute path under it.
- **Commit message:** write it with the Write tool to `/tmp/plan-paths-task-1-msg.txt` and commit with
  `git commit -F <file>`. No heredocs. End the message with the co-author trailer given in the dispatch. The
  title starts with `process:`.
- **Never push.** The team lead pushes.
- **PR:** title `process: plans name a worktree by a placeholder (#99)`. It doesn't release, so there is no
  `CHANGELOG.md` entry and no bump.

## Review Focus

Docs have no tests here, so each line names the check that pins it.

1. **The sentence rules out more than a local absolute path.** `way-of-working.md` writes a relative form
   itself (`../<repo>-wt/<topic>-task-<n>`, `../HA-NortecGo-wt/<topic>`), so the placeholders must read as
   examples ("say") and "or a relative path" must be there. Pinned by Task 1, Step 2's greps.
2. **The sentence is read against "by absolute path" in *Parallel waves* and §8.** It must name the dispatch
   as where the path is given, and link *Parallel waves*. Pinned by Task 1, Step 2's grep for the link, and
   by the task review against the spec's *Facts used*.
3. **The dispatch rule is written twice.** The sentence holds one clause and a link, not the rule that the
   dispatches give the worktree's absolute path. Pinned by Task 1, Step 2's `git diff --numstat` and by the
   task review.
4. **A wrap splits "local absolute path", and the spec's first search finds nothing.** Pinned by Task 1,
   Step 2's first search.
5. **This work breaks its own sentence:** a path under a home directory in the spec, the plan, the doc or
   the commit message. Pinned by Task 1, Step 2's last search, by the same search in *After the last task*,
   and by the check on the commit message in Task 1, Step 4.

## Waves

| Wave | Tasks | Notes |
|---|---|---|
| 1 | Task 1 (`docs/way-of-working.md`) | Alone, in the issue worktree `<HA-NortecGo-wt>/plan-paths`; no task worktree |

No task has guarded files.

---

### Task 1: `docs/way-of-working.md` §1 step 5

Model: opus (a docs task, D33)
Wave: 1

**Files:**
- Modify: `docs/way-of-working.md` (§1 step 5: its last line, and three new lines after it)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing another task uses.

- [ ] **Step 1: Add the sentence**

In `docs/way-of-working.md`, under `## 1. Flow for non-trivial changes`, step 5 (`5. **Plan:** …`) ends with
these two lines, right before `6. **Draft PR:**`:

```text
   methods (indented `def`s): a pre-commit hook reformats Python blocks in Markdown
   ([`ha-notes.md`](ha-notes.md#tooling)).
```

Change them to (the first line stays as it is; every line starts with three spaces):

```text
   methods (indented `def`s): a pre-commit hook reformats Python blocks in Markdown
   ([`ha-notes.md`](ha-notes.md#tooling)). A plan is a public file, so it names a worktree by a placeholder
   (`<worktree>`, or `<HA-NortecGo-wt>/<topic>`, say) or a relative path, never by a local absolute path,
   which can hold the local user name (hard rule 3); the dispatch gives the path
   ([Parallel waves](#parallel-waves)).
```

`6. **Draft PR:**` follows directly, with no blank line, as before.

- [ ] **Step 2: Check the edit**

Run each command in the issue worktree.

```bash
git grep -n -e 'local absolute path' -- . ':!docs/superpowers'
```

Expected: one hit, in `docs/way-of-working.md`, on a line between `5. **Plan:**` and `6. **Draft PR:**`
(before the edit: no hit).

```bash
grep -cF 'A plan is a public file, so it names a worktree by a placeholder' docs/way-of-working.md
grep -cF '(`<worktree>`, or `<HA-NortecGo-wt>/<topic>`, say) or a relative path, never by a local absolute path,' docs/way-of-working.md
grep -cF 'which can hold the local user name (hard rule 3); the dispatch gives the path' docs/way-of-working.md
```

Expected: `1` from each of the three (before the edit: `0` from each).

```bash
grep -A1 -F 'the dispatch gives the path' docs/way-of-working.md
```

Expected: two lines; the second is `   ([Parallel waves](#parallel-waves)).` and nothing else.

```bash
grep -cF 'fragment that isn'"'"'t a whole statement (parametrize rows, say) goes in a `text` block, and so do class' docs/way-of-working.md
```

Expected: `1` (the sentence on `text` blocks is as it was).

```bash
git diff --numstat
```

Expected: `4	1	docs/way-of-working.md`, and no other file.

```bash
git diff | grep '^-[^-]'
```

Expected: one removed line, `-   ([`ha-notes.md`](ha-notes.md#tooling)).`

```bash
git diff -U0 -- docs/way-of-working.md | grep '^+[^+]' | awk 'length > 111'
```

Expected: no output: no added line is wider than 110 characters (111 with the leading `+`). The 110 is this
task's own limit, the width the neighbouring prose keeps; no doc sets it. This is a guard: it also prints
nothing before the edit.

```bash
git grep -nE '/(Users|home)/' -- . ':!.devcontainer'
```

Expected: no output, before and after the edit.

- [ ] **Step 3: Run the gates**

```bash
uv run pytest -q
uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95
uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows
```

Expected: all pass, as on the branch before the task (no code changed).

- [ ] **Step 4: Commit**

Write this to `/tmp/plan-paths-task-1-msg.txt` with the Write tool, with the co-author trailer from the
dispatch as its last line:

```text
process: plans name a worktree by a placeholder (#99)

way-of-working §1 step 5: a plan is a public file, so it names a
worktree by a placeholder or a relative path, never by a local
absolute path (hard rule 3). The dispatch gives the path.
```

Check the message before the commit:

```bash
grep -cE '/(Users|home)/' /tmp/plan-paths-task-1-msg.txt
```

Expected: `0`.

Then:

```bash
git add docs/way-of-working.md
git commit -F /tmp/plan-paths-task-1-msg.txt
```

Expected: the hooks pass and one commit is added. Don't push.

---

## After the last task

The team lead runs, on the branch:

- the gates (`CLAUDE.md` → Commands);
- the spec's first search, `git grep -n -e 'local absolute path' -- . ':!docs/superpowers'`: one hit, in
  `docs/way-of-working.md`, inside §1 step 5;
- the spec's second search, `git grep -nE '/(Users|home)/' -- . ':!.devcontainer'`: no hit;
- the same pattern over the branch's commit messages, `git log origin/main..HEAD --format=%B | grep -cE
  '/(Users|home)/'`: `0`.

Then learnings (§1 step 8) and the branch review (§1 step 9). The PR description holds no local absolute
path either: `gh pr view --json body --jq .body | grep -cE '/(Users|home)/'` gives `0`. `visible: no`.
