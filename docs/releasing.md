# Releasing

## Versioning

This project uses [Semantic Versioning](https://semver.org/). Versions `0.0.x` and any version with a `-`
suffix (for example `1.0.0-beta.1`) are published as pre-releases.

## The bump PR

1. Set `version` in `custom_components/nortec_go/manifest.json` to the new version.
2. In `CHANGELOG.md`, move the relevant entries from `## [Unreleased]` under a new
   `## [X.Y.Z] - YYYY-MM-DD` section.
3. Open a pull request with these changes and merge it once the gates pass.

## Tagging (owner only)

```bash
git switch main
git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

## What `release.yml` checks

- The pushed tag equals `v` followed by the `version` in `manifest.json`. If it doesn't match, the
  release fails.
- The `CHANGELOG.md` has a `## [X.Y.Z]` section for that version, and it is not empty. If it's missing or
  empty, the release fails.
- If both checks pass, it runs `gh release create`, using that changelog section as the release notes, and
  marks the release as a pre-release when the version is `0.0.x` or has a `-` suffix.

## Bumping `pynortecgo`

`requirements` in `manifest.json` pins the `pynortecgo` client library to an exact version, for example
`pynortecgo==X.Y.Z`, and `pyproject.toml` pins the same version. A new client release gets its own pull
request that bumps both pins, updates the lock with `uv lock --upgrade-package pynortecgo` (which leaves the other
pins alone, apart from what the new version needs), runs the usual gates, and works through this checklist before merging:

- [ ] Read the new version's exception messages, including errors it wraps from lower layers, and confirm
  they hold no email, password, token, IDs or request bodies. The integration passes them into logs and
  `ConfigEntry*` errors (`CLAUDE.md`, hard rule 5).
- [ ] Look for new exception classes the charger, car, price, start and stop calls can raise, and give each
  the right handling. The charger read's catch-all only keeps an unknown error from crashing the read.
- [ ] Read the client's changelog for breaking changes to the models the entities use.

## Bumping Home Assistant

A `pytest-homeassistant-custom-component` bump pull request also raises `hacs.json`'s `homeassistant` key
to the Home Assistant version that dependency pins, and updates `requires-python` if that Home Assistant
version needs a newer Python. A `requires-python` change also updates `[tool.mypy] python_version` in
`pyproject.toml` and the `.devcontainer` image tag.
