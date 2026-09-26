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
checks can change without a change here. That's why both also run weekly.
