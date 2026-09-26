# Notes

Small learned facts that fit no other doc, newest last. When a topic passes about three entries, propose
moving it to its own doc.

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

`.claude/settings.json` denies `git push` commands that name `main`. The rule matches the whole Bash command
text, so a push chained with anything that mentions `main` later (`gh pr create --base main`,
`git fetch origin main:main`) is refused too. Run `git push` as its own command.

## 2026-09-26: Home Assistant and HACS facts

- Setting up a config entry always imports the integration's `config_flow` platform, even with
  `"config_flow": false`. An integration with no config flow yet uses `async_setup` with
  `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)` instead of an empty entry.
- `pytest-homeassistant-custom-component` ships its own `custom_components` package. HA only finds ours if a
  test imports `custom_components.nortec_go` first.
- hassfest requires the `manifest.json` keys in the order `domain`, `name`, then alphabetical.
- HACS's `license` check reads the license GitHub detects on the default branch, so `LICENSE` must be on
  `main` before a PR's `hacs` check can pass.
- HACS's `brands` check accepts a local `custom_components/<domain>/brand/icon.png` (HA 2026.3 and later).
