# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Add the integration from the UI with your Nortec Go email and password. Your email and the session are
  stored, never the password.
- Reauthentication: when the session is rejected, Home Assistant asks for the password again.
- If the charger is removed from your Nortec Go account, setup stops with a "charger not found" error.
- Sensors and binary sensors for [EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging):
  the current price with today's and tomorrow's prices, the car's battery and charge limit, and whether
  your own car is connected to the charger.
- A *Charge* switch that starts and stops charging, guarded against repeated starts that could place extra
  card holds, and shown off right after a stop until the charger follows; a *Charge status* sensor; and a
  repair issue to allow starts again after a failed start.
- A *Refresh* button that reads the charger, the car and the prices right away.
- A *Last read* sensor that shows when the charger was last read.
- The charger is read every 30 seconds while a charge is starting or stopping, for about 2 minutes (10 after
  a start) while it can't be read, and right away after turning *Charge* on or off.
- The charger's device name follows a rename in the Nortec Go app.
- Debug logging turned on from the integration's page also covers the `pynortecgo` client, and the docs
  explain debug logging and what to leave out of a bug report.

## [0.0.1] - 2026-09-26

### Added

- Initial project skeleton; not usable yet.
