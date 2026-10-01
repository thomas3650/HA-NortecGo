## What and why

<!-- One or two sentences. Link the spec/plan in docs/superpowers/ for non-trivial work. -->

Closes #

## Checklist

- [ ] Gates pass (`CLAUDE.md` → *Commands*: the tests, the coverage gate and the lint line)
- [ ] Title type per `docs/releasing.md` (user-visible → `feat`, `fix` or `perf`, with a `CHANGELOG.md` entry)
- [ ] Releasing title → the bump step run last (`docs/releasing.md`)
- [ ] `custom_components/nortec_go/quality_scale.yaml` updated (rules completed or changed)
- [ ] `docs/user/nortec_go.md` updated (user-visible changes)
- [ ] No private data: IDs, tokens, emails, captures, raw API details, links into the private repo
- [ ] `pytest-homeassistant-custom-component` bump → `hacs.json` `homeassistant` minimum raised
- [ ] `pynortecgo` bump → the checklist in `docs/releasing.md` → *Bumping `pynortecgo`* done
- [ ] Lasting decision → `docs/decisions.md` entry
- [ ] `full-reviewer` run on the branch (non-trivial changes)
