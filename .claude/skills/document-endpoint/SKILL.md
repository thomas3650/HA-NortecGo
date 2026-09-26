---
name: document-endpoint
description: Use when adding or updating an endpoint in docs/api.md, or after a capture or probe reveals a new endpoint, parameter or response shape for the Nortec Go / Monta API, or when capturing charger and car state across a charge.
---

# Document an endpoint

`docs/api.md` describes the API. **`docs/api-standard.md` is the standard** — the template, the rules per
section, redaction and the checklist. This skill is the procedure; it never restates the standard's rules.

## Safety first

- GET only. Never call `POST /api/v1/charges`, `/charges/start` or anything that starts or stops a charge —
  it places a card hold. Ask the user first for anything that isn't a read. Logging in is the one allowed
  POST; it is rate-limited (429 after a few logins in minutes), so reuse the cached token.
- `docs/api.md` is committed: nothing real that the standard says to redact may land in it.

## Procedure

1. **Get real data** — never write a response from memory or from APK strings.
   - From a capture: `.venv-tools/bin/python tools/analyze_flows.py captures/nortec.flows --dump <path-substring>`
   - Charger and car state: `python3 tools/capture_states.py` (step 1a).
   - By probing: `TOK=$(.venv-tools/bin/python tools/analyze_flows.py captures/nortec.flows --token)` then
     `python3 tools/probe_api.py --token "$TOK" "<path?query>"`
     Without a capture, take the token `capture_states.py` cached: `TOK=$(cat local/.token)` (run
     `capture_states.py` once first; it logs in from `NORTEC_EMAIL` / `NORTEC_PASSWORD` in `.env`).
   - Test whether a parameter is required by calling without it.

   **1a. Capture state across a charge.** The charge itself is the user's action in the app (explicit OK,
   card hold); the tool only reads.
   - One snapshot per phase. Before probing, the tool asks the user what is actually happening — the
     phase, whether the cable is in the car, what they did in the app and how long ago, what the app's
     charger screen says, and whether the car says it is charging — and saves the answers as `observed`
     next to the responses. Claude can't answer the prompts interactively, so it passes the answers as
     flags (see `--help`):
     1. Take a quick read first (GET `charge_points/{id}` and `vehicles` with `probe_api.py` and the cached
        token).
     2. Show the user a table of **suggested answers** — phase, cable in the car, app action (+ minutes
        ago), what the app's charger screen says, car charging, note — each with what it is based on.
     3. Wait for the user to confirm or correct them; the user's answers are the ground truth. Never take a
        snapshot with unconfirmed answers.
     4. Run the tool with the confirmed answers as flags.

     During a charge, poll to catch short states:
     `python3 tools/capture_states.py charging --every 30 --count 20 <flags>` (the answers apply to the
     whole run; the minutes since the action count up by themselves).
   - Snapshots land in `local/state-captures/` with a generated `README.md` index (one row per snapshot:
     what the user observed next to what the charger, the latest charge and the car reported). It is
     gitignored and never committed — it holds personal data.
   - Read the index and the JSON, then fill *State across a charge* in `docs/api.md` with **values and field
     names only**, and update the entries whose shapes changed (steps 2–4).
2. **Redact** per `docs/api-standard.md` → *Redaction*.
3. **Write the entry** under the right topic H2 in `docs/api.md`, per `docs/api-standard.md` → *Template* and
   *Rules per section*.
4. **Update** the Endpoint index row and *Open questions* in `docs/api.md`.
5. **Client check** — if `pynortecgo` calls this endpoint, compare `src/pynortecgo/models.py` and the fixture in
   `tests/fixtures/` with the real shape. Don't change the client in a docs change; if they differ, note it in
   README → Client status.
6. **Verify** — work through `docs/api-standard.md` → *Checklist*; run `uv run python tools/check_api_md.py`
   (must pass) and `grep -nE "ory_st_[A-Za-z0-9]{8,}|@[a-z]+\.[a-z]{2,}" docs/api.md` (must print nothing).
7. **Commit on a branch** and open a PR — never commit to `main`.
