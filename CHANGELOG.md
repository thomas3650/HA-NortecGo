# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-09-29

### Fixed

- The release tooling's bump step reports a missing file as an error; no change to the integration.

## [0.1.0] - 2026-09-29

### Added

- Add the integration from the UI with your Nortec Go email and password. Your email and the session are
  stored, never the password.
- Reauthentication: when the session is rejected, Home Assistant asks for the password again.
- If the charger is removed from your Nortec Go account, setup stops with the error "The charger is no
  longer on the Nortec Go account".
- Sensors and binary sensors for [EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging):
  the current total price (spot, fees and grid tariff) in the price data's currency, with today's and
  tomorrow's prices, the car's battery and charge limit, and whether your own car is connected to the
  charger.
- A *Charge* switch that starts and stops charging, guarded against repeated starts that could place extra
  card holds, and shown off right after a stop until the charger follows; a *Charge status* sensor; and a
  repair issue to allow starts again after a failed start.
- A *Refresh* button that reads the charger, the car and the prices right away.
- A failed price read at start-up or at a read time is tried once more 15 minutes later, and an outage logs
  one warning instead of one per read.
- A *Last read* sensor that shows when the charger was last read.
- The charger is read every 30 seconds while a charge is starting or stopping, for about 2 minutes (10 after
  a start) while it can't be read, and right away after turning *Charge* on or off.
- The charger's device name follows a rename in the Nortec Go app.
- Debug logging turned on from the integration's page also covers the `pynortecgo` client, and the docs
  explain debug logging and what to leave out of a bug report.
- *Energy this charge* (kWh) and *Charging power* (kW) sensors for the open charge.
- Setup and read errors show the integration's own texts, not the client library's.
- A diagnostics download for the integration, with your email, the session tokens and the device ID left
  out.

## [0.0.1] - 2026-09-26

### Added

- Initial project skeleton; not usable yet.
