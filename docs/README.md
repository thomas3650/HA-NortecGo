# Documentation map

The root [`README.md`](../README.md) is the public intro; everything else lives here.

| Doc | Contents | Read it when |
|---|---|---|
| [`../README.md`](../README.md) | What the integration is, install via HACS, status | First look at the repo |
| [`../CLAUDE.md`](../CLAUDE.md) | What this repo is, layout, commands, hard rules | Starting any work here |
| [`way-of-working.md`](way-of-working.md) | Flow, agents, model policy, conventions, the PO flow | Doing non-trivial work |
| [`decisions.md`](decisions.md) | Lasting decisions, newest last | Why something is the way it is |
| [`releasing.md`](releasing.md) | PR titles, the bump step, the automatic release, when a release fails, what `release.yml` checks | Cutting a release |
| [`notes.md`](notes.md) | Small learned facts that fit no other doc | Looking for a fact that isn't elsewhere |
| [`ha-notes.md`](ha-notes.md) | Learned Home Assistant and HACS facts: loading, config flows, tooling, testing, coordinators and actions, devices and entities, diagnostics | Building or testing the integration |
| [`manual-testing.md`](manual-testing.md) | Testing by hand against the owner's real account: running it, where real data lives, who may do what, checklists per feature | Testing the integration live |
| [`user/nortec_go.md`](user/nortec_go.md) | The user-facing integration docs | Setting up or using the integration |
| [`superpowers/specs/`](superpowers/specs/) | Design specs, one per change | Why a change is shaped this way |
| [`superpowers/plans/`](superpowers/plans/) | Implementation plans, one per change | How a change was done |

## Useful links

Collected while writing the ground-structure spec, all returning HTTP 200 on 2026-09-26.

**Building an integration (HA developer docs)**
- Creating your first integration: https://developers.home-assistant.io/docs/creating_component_index/
- File structure: https://developers.home-assistant.io/docs/creating_integration_file_structure/
- Tests file structure: https://developers.home-assistant.io/docs/creating_integration_tests_file_structure/
- Manifest: https://developers.home-assistant.io/docs/creating_integration_manifest/
- Config flow: https://developers.home-assistant.io/docs/core/integration/config_flow/
- Options flow: https://developers.home-assistant.io/docs/core/integration/options_flow/
- Config entries: https://developers.home-assistant.io/docs/config_entries_index/
- Fetching data (`DataUpdateCoordinator`): https://developers.home-assistant.io/docs/integration_fetching_data/
- Setup failures: https://developers.home-assistant.io/docs/integration_setup_failures/
- Entities: https://developers.home-assistant.io/docs/core/entity/
- Diagnostics: https://developers.home-assistant.io/docs/core/integration/diagnostics/
- System health: https://developers.home-assistant.io/docs/core/integration/system_health/
- Brand images (local `brand/` from 2026.3): https://developers.home-assistant.io/docs/core/integration/brand_images/
- Example custom integrations: https://github.com/home-assistant/example-custom-config/tree/master/custom_components

**Code standards and checklists**
- Development checklist: https://developers.home-assistant.io/docs/development_checklist/
- Component checklist: https://developers.home-assistant.io/docs/creating_component_code_review/
- Platform checklist: https://developers.home-assistant.io/docs/creating_platform_code_review/
- Style guidelines: https://developers.home-assistant.io/docs/development_guidelines/
- Testing (incl. snapshot tests): https://developers.home-assistant.io/docs/development_testing/
- Typing: https://developers.home-assistant.io/docs/development_typing/
- Building a Python library for an API: https://developers.home-assistant.io/docs/api_lib_index/
- HA core `pyproject.toml` (ruff and mypy settings): https://github.com/home-assistant/core/blob/dev/pyproject.toml

**Integration Quality Scale**
- Overview and tiers: https://developers.home-assistant.io/docs/core/integration-quality-scale/
- Checklist: https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/
- Rules: https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/
- `dependency-transparency`: https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/dependency-transparency/

**User documentation (home-assistant.io)**
- Integration docs template: https://github.com/home-assistant/home-assistant.io/blob/current/source/_integrations/_integration_docs_template.markdown
- Creating a docs page: https://developers.home-assistant.io/docs/documenting/create-page/
- Documentation standards: https://developers.home-assistant.io/docs/documenting/standards/

**HACS**
- Publishing, getting started: https://hacs.xyz/docs/publish/start/
- Publishing an integration: https://hacs.xyz/docs/publish/integration/
- What HACS checks: https://hacs.xyz/docs/publish/include/
- The HACS action: https://hacs.xyz/docs/publish/action/ and https://github.com/hacs/action

**Tools and CI**
- `pytest-homeassistant-custom-component`: https://github.com/MatthewFlamm/pytest-homeassistant-custom-component
- hassfest action: https://github.com/home-assistant/actions
- Brands repo: https://github.com/home-assistant/brands
- Material Design Icons `ev-station`: https://pictogrammers.com/library/mdi/icon/ev-station/
- gitleaks action: https://github.com/gitleaks/gitleaks-action
- uv: https://docs.astral.sh/uv/
- Keep a Changelog: https://keepachangelog.com/en/1.1.0/

**GitHub**
- Dependabot options: https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference
- Branch protection REST API: https://docs.github.com/en/rest/branches/branch-protection
- Interaction limits REST API: https://docs.github.com/en/rest/interactions/repos
- CodeQL default setup: https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configure-code-scanning
