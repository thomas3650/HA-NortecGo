## What and why

<!-- One or two sentences: what this changes and why. -->

Closes #

## Checklist

- [ ] Gates pass: `pytest`, the 95% coverage gate, `ruff check`, `ruff format --check`, `mypy`, `actionlint` and `zizmor`
- [ ] Title type fits the change (user-visible → `feat`, `fix` or `perf`, with a `CHANGELOG.md` entry)
- [ ] Releasing title → the bump step run last (`uv run python scripts/release_check.py release-pr --title='<PR title>'`), then `chore: release X.Y.Z` committed
- [ ] `custom_components/nortec_go/quality_scale.yaml` updated (rules completed or changed)
- [ ] `README.md` updated (user-visible changes)
- [ ] No private data: IDs, tokens, emails, captures, raw API details, links into the private repo
- [ ] `pytest-homeassistant-custom-component` bump → `hacs.json` `homeassistant` minimum raised
- [ ] `pynortecgo` bump → its exception messages hold no secrets; new client model fields reviewed for redaction in diagnostics; new exception classes handled; the client's changelog read for breaking changes
