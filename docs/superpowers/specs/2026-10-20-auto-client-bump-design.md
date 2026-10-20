# Bump pynortecgo automatically with Renovate — design

Date: 2026-10-20 · Branch: `feat/auto-client-bump` · Issue: #49

## Goal

- **What:** when a new `pynortecgo` release is on PyPI, a PR opens that bumps the client in all three
  places it is pinned: `requirements` in `manifest.json`, the dev pin in `pyproject.toml`, and `uv.lock`.
  - The owner chose option A on #49: Renovate's hosted GitHub App does it.
  - A `renovate.json` limits Renovate to `pynortecgo`.
  - Dependabot stops bumping `pynortecgo`.
- **Why:** `pynortecgo` releases on every `feat`/`fix`/`perf` merge, and today the manifest bump is done by
  hand, so client fixes wait until someone remembers. Dependabot can't do it, because it doesn't read
  `manifest.json`. Its monthly `uv` group can bump the `pyproject.toml` pin alone, and that PR then fails
  `test_pynortecgo_pins_match`.
- **Not in this work:**
  - merging, auto-merge, or any release from the Renovate PR. A person finishes it, as with Dependabot's;
  - Renovate for any other dependency. Dependabot keeps everything else;
  - a CI check that validates `renovate.json`, which would edit `.github/workflows/`;
  - installing the app. Only the owner can do that, since it changes the repo's settings, and does it
    after this PR merges (*Installing the app*).
- **Done when:**
  - `renovate.json` is on `main`, and the Renovate config validator accepts it as a repo config;
  - `.github/dependabot.yml` ignores `pynortecgo` in its `uv` entry;
  - the docs below say how to install the app, how to finish a Renovate PR, and who merges it;
  - D51 is in `decisions.md`;
  - the gates pass.

## How it works

- **The managers:** only two are enabled.
  - `homeassistant-manifest` reads `requirements` in `manifest.json`.
  - `pep621` reads `pyproject.toml` (the `dependency-groups` dev group) and updates `uv.lock` with the `uv`
    CLI.
- **Only `pynortecgo`:** a first package rule disables every package, and a second turns `pynortecgo` back
  on, with `groupName: "pynortecgo"`. The group puts both managers' updates for one version in one branch,
  `renovate/pynortecgo`, and so in one PR. A local Renovate dry run showed one `renovate/pynortecgo` branch holding both updates.
- **The PR title:** semantic commits, type `chore` and scope `deps`, give
  `chore(deps): update dependency pynortecgo to vX.Y.Z`. That title doesn't release, and `version-check`
  passes it as it passes Dependabot's, because the PR changes neither `version` nor `CHANGELOG.md`.
- **No dashboard:** `dependencyDashboard: false`. Otherwise Renovate opens a standing issue, and the
  backlog is the issues (D19).
- **No changelog fetching:** `fetchChangeLogs: "off"`. PyPI lists no source URL for `pynortecgo` today. If
  the client ever adds one that points at its private repo, no text or link from there reaches a public PR
  body (hard rule 3).
- **When:** the hosted app runs each repo every few hours, and a PyPI release triggers no run. So the PR
  opens within a few hours of a release.

### The config

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "enabledManagers": ["homeassistant-manifest", "pep621"],
  "dependencyDashboard": false,
  "fetchChangeLogs": "off",
  "semanticCommits": "enabled",
  "semanticCommitType": "chore",
  "semanticCommitScope": "deps",
  "packageRules": [
    {
      "description": "Renovate bumps only pynortecgo; Dependabot keeps the rest (D51).",
      "matchPackageNames": ["*"],
      "enabled": false
    },
    {
      "description": "One PR for manifest.json, pyproject.toml and uv.lock.",
      "matchPackageNames": ["pynortecgo"],
      "enabled": true,
      "groupName": "pynortecgo"
    }
  ]
}
```

### Dependabot

In `.github/dependabot.yml`, the `uv` entry gains:

```yaml
    ignore:
      - dependency-name: pynortecgo  # Renovate bumps it, with manifest.json (D51)
```

## Installing the app

After this PR merges, the owner installs the Renovate GitHub App (Mend) with *Only select repositories*,
choosing this repo alone.
- An install for *All repositories* puts the app in silent mode: no PRs and no issues, with no error.
- It would also give the app the private `NortecGo` repo.

With `renovate.json` already on `main`, the app counts the repo as onboarded and opens no onboarding PR.
If the app goes in after #112 merges, the pin is already the newest version, and the first Renovate PR comes
with the next client release. If it goes in before, Renovate opens a 0.10.0 PR next to #112, and closes it
itself once #112 merges.

## Finishing a Renovate PR

It is a client bump like any other (*Bumping `pynortecgo`* in `releasing.md`). The owner finishes it, or a
controller session the owner starts for it. The PO flow doesn't pick it up, because it has no issue. On its
branch:
1. Work through the checklist, and fix what the new version breaks.
2. Push the first commit of our own (the fix, or the changelog entry) **before** retitling. Renovate puts
   its own title back until the branch holds a commit that isn't Renovate's.
3. If users see a difference, retitle it `fix` or `feat`, then run the bump step.
4. Once the branch holds our commits, don't tick Renovate's rebase or retry box: that drops them.

It is the owner's to merge, as Dependabot's PRs are (§8 *Merging*). If a feature PR bumps the client by hand
first, Renovate closes its own PR once the version is on `main`. If we had pushed to that PR, Renovate marks
it "abandoned" instead, and we close it.

## Docs

| File | Change |
|---|---|
| `docs/releasing.md`, *PR titles* | The Dependabot bullet also covers Renovate's `chore(deps): update dependency pynortecgo …` PRs, with step 2 above: our commit before the retitle |
| `docs/releasing.md`, *Bumping `pynortecgo`* | Renovate opens the bump PR, with all three pins, within hours of a release. It is finished as *Finishing a Renovate PR* says (steps 1 to 4, who finishes it, a hand bump first). How the app is installed (*Installing the app*) |
| `docs/way-of-working.md` §8 *Merging* | "also Dependabot's" becomes "also Dependabot's and Renovate's" |
| `docs/decisions.md` | D51, below |
| `docs/README.md`, *Useful links* → *Tools and CI* | Renovate's `homeassistant-manifest` and `pep621` manager pages (`https://docs.renovatebot.com/modules/manager/homeassistant-manifest/`, `https://docs.renovatebot.com/modules/manager/pep621/`) and the hosted app's config page (`https://docs.renovatebot.com/mend-hosted/hosted-apps-config/`). Check each for HTTP 200, and add "(added 2026-10-20)" after each new link, since the section's header dates its checks to 2026-09-26 |

D51:

```markdown
### D51: Renovate bumps pynortecgo
- **Date:** 2026-10-20 · **Status:** active
- **Decision:** Renovate's GitHub App, installed for this repo only, opens the PR for a new `pynortecgo`
  release, with `manifest.json`, `pyproject.toml` and `uv.lock` in one PR. Dependabot ignores `pynortecgo`
  and keeps every other dependency. A person finishes the PR as a client bump (`releasing.md`), and the
  owner merges it.
- **Why:** Dependabot doesn't read `manifest.json`, and a workflow of our own would need a token secret
  for its PR to run the required checks. Renovate's app needs neither, and has a manager for HA manifests.
- **Source:** [spec](superpowers/specs/2026-10-20-auto-client-bump-design.md)
```

## Decisions

Approved by the controller on 2026-10-20, under the owner's delegation. Option A is the owner's choice.

| Topic | Decision |
|---|---|
| Title | `chore: bump pynortecgo automatically with Renovate (#49)`. It isn't user-visible, so it has no changelog entry and no bump |
| `CHANGELOG.md`, `quality_scale.yaml`, `docs/user/nortec_go.md` | Unchanged: users see nothing |
| Guarded files | None: no `.claude/` or `.pre-commit-config.yaml` path, and no `.github/workflows/` change |
| Merge | The owner's: this isn't the PO flow, and the owner installs the app after the merge |
| Merge order with #112 | #112 also edits `releasing.md` *Bumping `pynortecgo`*. Whichever merges second takes in `origin/main` first |
| Merge-confidence badges | Left as the hosted app's default: harmless |

## Testing

- `npx --yes --package renovate -- renovate-config-validator --strict --no-global renovate.json` validates
  the file as a repo config, and passes.
- The `check json` and `check yaml` pre-commit hooks pass on the two files.
- The gates pass. No Python code changes.
- After the merge and the install, the first check is live: the next `pynortecgo` release opens one PR
  that holds all three pins. The owner watches for it. If `uv.lock` is missing from it, that becomes an
  issue.

## Execution shape

One task, `Model: opus` (a docs task, D33, with the config next to it). It covers `renovate.json`,
`.github/dependabot.yml`, the docs table and D51.
