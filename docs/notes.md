# Notes

Small learned facts that fit no other doc, newest last. When a topic passes about three entries, propose
moving it to its own doc. Home Assistant and HACS facts live in [`ha-notes.md`](ha-notes.md).

## 2026-09-26: Interaction limit

Issues and PRs from non-collaborators are blocked by a GitHub interaction limit (collaborators only), which
expires after six months. Renew it with:

`gh api -X PUT repos/thomas3650/HA-NortecGo/interaction-limits -f limit=collaborators_only -f expiry=six_months`

Check the current limit and its expiry with `gh api repos/thomas3650/HA-NortecGo/interaction-limits`.

Set on 2026-09-26; expires 2027-03-26.

## 2026-09-26: CI images aren't pinned

The workflow actions are pinned to commit SHAs, but `hacs/action` runs the Docker image
`ghcr.io/hacs/action:main` and the hassfest action runs `ghcr.io/home-assistant/hassfest` unpinned, so their
checks can change without a change here. That's why both also run weekly. The hassfest action itself is
pinned to a `master` commit SHA, which Dependabot can't bump; refresh it by hand if the weekly run breaks.

## 2026-09-26: The push-to-`main` deny rule matches too much

`.claude/settings.json` denies `git push` commands that name `main`. In practice it also refuses a push
chained with anything that mentions `main` later (`gh pr create --base main`, `git fetch origin main:main`).
Run `git push` as its own command.

## 2026-09-26: ruff-format reformats Markdown code blocks

The ruff-format pre-commit hook also formats Python code blocks inside `.md` files, such as specs and plans.
A commit of a plan can fail once with "files were modified by this hook"; re-stage and commit again.

## 2026-09-28: EV Smart Charging doesn't re-send *off*

EV Smart Charging compares its schedule with its own remembered state (`auto_charging_state`), not with the
charger switch's state. If the switch goes back on after an *off*, it doesn't send *off* again until its
schedule changes, so a turn-off that fails silently isn't retried. Found while looking at #32.
