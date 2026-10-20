# Bump pynortecgo automatically with Renovate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this repo the flow in `docs/way-of-working.md` §1–2 applies (implementer and task-reviewer agents, waves, worktrees).

**Goal:** Renovate's app opens one PR for each new `pynortecgo` release, holding `manifest.json`,
`pyproject.toml` and `uv.lock`, and Dependabot leaves `pynortecgo` alone (#49).

**Architecture:** one task and one commit, made of config plus docs:
- `renovate.json` at the repo root, as the spec gives it;
- an `ignore` in Dependabot's `uv` entry;
- `docs/releasing.md`: how to finish and install;
- `docs/way-of-working.md` §8: who merges;
- `docs/decisions.md`: D51;
- `docs/README.md`: links.

No Python changes.

**Tech Stack:** Renovate (Mend-hosted GitHub App) with its `homeassistant-manifest` and `pep621` managers,
Dependabot, Markdown.

**Spec:** `docs/superpowers/specs/2026-10-20-auto-client-bump-design.md` (issue #49). Read it with the task:
this plan argues from it.

## Global Constraints

- **`renovate.json` is the spec's *The config* block, byte for byte**, followed by a final newline.
- **Only these files change:**
  - `renovate.json` (new);
  - `.github/dependabot.yml`;
  - `docs/releasing.md`;
  - `docs/way-of-working.md`;
  - `docs/decisions.md`;
  - `docs/README.md`.

  No `CHANGELOG.md`, no `version`, no `.github/workflows/`, `.claude/` or `.pre-commit-config.yaml`.
- **Nothing private (hard rule 3):** no IDs, endpoints, or links into the private client repo. The private
  repo may be named as "the private client repo", but never linked.
- **One fact in one place (`way-of-working.md` §7):** how to finish a Renovate PR lives in `releasing.md`
  *Bumping `pynortecgo`*. Other places point to it.
- **Gates before the commit** (`CLAUDE.md` → Commands): `uv run pytest -q`, then
  `uv run ruff check && uv run ruff format --check && uv run mypy && uv run actionlint && uv run zizmor --offline .github/workflows`,
  then the coverage gate, `uv run pytest --cov=custom_components.nortec_go --cov-report=term-missing --cov-fail-under=95`.
- **Where it runs:** in the worktree `<HA-NortecGo-wt>/auto-client-bump`, on branch `feat/auto-client-bump`.
  The dispatch gives the absolute path. Run every command with `cd <worktree> && …`, and edit files by
  absolute path under it. Don't run `pre-commit install` there.
- **Commit message:** write it with the Write tool to `/tmp/auto-client-bump-task-1-msg.txt`, and commit with
  `git commit -F <file>`. No heredocs. End it with the co-author trailer from the dispatch.
- **PR:** titled `chore: bump pynortecgo automatically with Renovate (#49)`. It doesn't release.

## Review Focus

1. **A Renovate config that validates only as a global config.** Expected: it passes as a repo config.
   Pinned by Task 1, Step 2 (`--no-global`).
2. **Renovate touching other dependencies.** Expected: only `pynortecgo`. Pinned by the config's two package
   rules, copied verbatim (Step 1). `task-reviewer` compares them with the spec.
3. **Dependabot still bumping `pynortecgo`.** Expected: its `uv` entry ignores it. Pinned by Step 3 and by
   the `check yaml` hook.
4. **The finish steps in the wrong order.** The commit must come before the retitle, and the bump step
   after. Expected: `releasing.md`'s steps keep the spec's order. `task-reviewer` checks them against the
   spec's *Finishing a Renovate PR*.
5. **#112's text disturbed.** Expected: the new text goes right after the checklist, and #112's *To compare
   two client versions* paragraph and the notes.md paragraph are unchanged. Pinned by Step 4's anchor and
   `task-reviewer`'s diff check.

---

### Task 1: Renovate config, Dependabot ignore, docs and D51

**Model:** opus. It's a docs task (D33), with the config next to it.
**Wave:** 1

**Files:**
- Create: `renovate.json`
- Modify: `.github/dependabot.yml` (the `uv` entry)
- Modify: `docs/releasing.md` (*PR titles*, and *Bumping `pynortecgo`*)
- Modify: `docs/way-of-working.md` (§8 *Merging*, first paragraph)
- Modify: `docs/decisions.md` (append D51)
- Modify: `docs/README.md` (*Useful links* → *Tools and CI*)

**Interfaces:**
- Consumes: nothing.
- Produces: D51, which the docs cite.

- [ ] **Step 1: Write `renovate.json`**

Copy the JSON block under *The config* in the spec into `<worktree>/renovate.json`, unchanged, with a final
newline.

- [ ] **Step 2: Validate it as a repo config**

Run: `cd <worktree> && npx --yes --package renovate -- renovate-config-validator --strict --no-global renovate.json`
Expected: `Validating renovate.json as repo config`, then `Config validated successfully`. It may print npm
deprecation warnings. If it prints `as global config`, stop and report it.

- [ ] **Step 3: Ignore `pynortecgo` in Dependabot**

In `.github/dependabot.yml`, the `uv` entry gets an `ignore` key after its `groups` block, indented like
`groups:`:

```text
    groups:
      uv:
        patterns: ["*"]
    ignore:
      - dependency-name: pynortecgo  # Renovate bumps it, with manifest.json (D51)
```

- [ ] **Step 4: `docs/releasing.md`**

In *PR titles*, put these lines right after the Dependabot bullet, which ends "which is fine for a PR about
to merge.":

```text
- Renovate's `pynortecgo` PRs are titled `chore(deps): update dependency pynortecgo to vX.Y.Z`. Before
  you retitle one, see *Bumping `pynortecgo`*.
```

In *Bumping `pynortecgo`*, put this text right after the checklist's last item ("- [ ] Read the client's
changelog for breaking changes to the models the entities use."), with a blank line on each side. It goes
before the paragraph "Title such a PR by what it changes for users".

```markdown
Renovate opens a new release's own pull request (D51). Within a few hours of a new release on PyPI, its `renovate/pynortecgo`
branch bumps both pins and the lock. The owner finishes it, or a controller session the owner starts for it.
The PO flow doesn't pick it up, because it has no issue. On its branch:

1. Work through the checklist above, and fix what the new version breaks.
2. Push the first commit of our own (the fix, or the changelog entry) before you retitle it. Until the
   branch holds a commit that isn't Renovate's, Renovate puts its own title back.
3. Title it by what it changes for users (*Title such a PR…*, below), then run the bump step.
4. Once the branch holds our commits, don't tick Renovate's rebase or retry box: that drops them.

The owner merges it ([`way-of-working.md`](way-of-working.md) §8 *Merging*). If a feature's pull request
bumps the client first, Renovate closes its own once the version is on `main`. If we had pushed to it,
Renovate marks it abandoned, and we close it.

The app is installed with *Only select repositories*, for this repo alone. An install for *All repositories*
runs it in silent mode, with no PRs and no error, and would give it the private client repo too.
`renovate.json` limits it to `pynortecgo`, and Dependabot ignores `pynortecgo` (`.github/dependabot.yml`).
```

Wrap the paragraph lines at about 110 characters, as the rest of the file does.

- [ ] **Step 5: `docs/way-of-working.md` §8 *Merging***

In the first paragraph of *Merging*, change `also\nDependabot's, the owner's own and trivial ones (§4).` so
that it reads "also Dependabot's and Renovate's, the owner's own and trivial ones (§4)." Re-wrap only those
two lines.

- [ ] **Step 6: `docs/decisions.md`**

Append the spec's D51 block, unchanged, after D50, with one blank line before it. The file ends with a
single newline.

- [ ] **Step 7: `docs/README.md`**

At the end of the *Tools and CI* list (after the Keep a Changelog line), add:

```markdown
- Renovate `homeassistant-manifest` manager: https://docs.renovatebot.com/modules/manager/homeassistant-manifest/ (added 2026-10-20)
- Renovate `pep621` manager: https://docs.renovatebot.com/modules/manager/pep621/ (added 2026-10-20)
- Renovate hosted app config: https://docs.renovatebot.com/mend-hosted/hosted-apps-config/ (added 2026-10-20)
```

Run: `for u in https://docs.renovatebot.com/modules/manager/homeassistant-manifest/ https://docs.renovatebot.com/modules/manager/pep621/ https://docs.renovatebot.com/mend-hosted/hosted-apps-config/; do curl -s -o /dev/null -w '%{http_code} %{url}\n' "$u"; done`
Expected: `200` for each.

- [ ] **Step 8: Gates and scope**

Run the gate commands from *Global Constraints*, then `cd <worktree> && uv run pre-commit run --files renovate.json .github/dependabot.yml docs/releasing.md docs/way-of-working.md docs/decisions.md docs/README.md`.
Expected: all pass.

Run: `cd <worktree> && git status --short`
Expected: exactly the six files in *Files*.

- [ ] **Step 9: Commit**

Write `/tmp/auto-client-bump-task-1-msg.txt`:

```text
chore: bump pynortecgo automatically with Renovate (#49)

renovate.json limits Renovate to pynortecgo, in manifest.json,
pyproject.toml and uv.lock in one PR; Dependabot ignores it. The docs
say how the app is installed and how its PR is finished (D51).

<co-author trailer from the dispatch>
```

Run: `cd <worktree> && git add renovate.json .github/dependabot.yml docs/releasing.md docs/way-of-working.md docs/decisions.md docs/README.md && git commit -F /tmp/auto-client-bump-task-1-msg.txt`
Expected: the hooks pass and the commit is made on `feat/auto-client-bump`.
