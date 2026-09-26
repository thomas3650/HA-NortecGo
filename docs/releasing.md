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

The tag version must match the `version` in `manifest.json` exactly, including the leading `v`.

## What `release.yml` checks

- The pushed tag equals `v` followed by the `version` in `manifest.json`. If it doesn't match, the
  release fails.
- The `CHANGELOG.md` has a `## [X.Y.Z]` section for that version, and it is not empty. If it's missing or
  empty, the release fails.
- If both checks pass, it runs `gh release create`, using that changelog section as the release notes, and
  marks the release as a pre-release when the version is `0.0.x` or has a `-` suffix.

## Bumping `pynortecgo`

Once the integration depends on the `pynortecgo` client library, `requirements` in `manifest.json` pins it
to an exact version, for example `pynortecgo==X.Y.Z`. A new client release gets its own pull request that
bumps this pin and runs the usual gates before merging.

## Bumping Home Assistant

A `pytest-homeassistant-custom-component` bump pull request also raises `hacs.json`'s `homeassistant` key
to the Home Assistant version that dependency pins, and updates `requires-python` if that Home Assistant
version needs a newer Python.
