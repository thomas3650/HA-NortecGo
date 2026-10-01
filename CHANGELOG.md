# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.4.0] - 2026-10-01

### Added

- *Total energy*: the energy the charger has delivered since the sensor was added, kept across restarts. It
  starts at 0 with this update. Use it as the charger's individual device in the Energy dashboard, instead
  of *Energy this charge*.

## [0.3.0] - 2026-10-01

### Changed

- If the car can't be read when the integration starts, the start is tried again until the service answers,
  instead of adding a car device that may not exist. All entities are unavailable until then.
- A car that goes from the account while Home Assistant runs makes its entities unavailable and raises a
  repair notice that offers to remove the car device. Before, the entities kept showing the last data.

### Fixed

- An account without a car no longer keeps an unavailable *Car* device after a failed first car read.
- After a change of car, the car device no longer keeps the old car's brand and model.
- A stop asked for before a restart is no longer lost when the car read is rejected at the start.

## [0.2.0] - 2026-10-01

### Added

- *Cost this charge*: what the open charge costs so far.
- *Last charge cost*: the billed total of the most recent completed charge. Its long-term statistics add
  up what the charges completed from then on cost.

### Changed

- `pynortecgo` 0.7.0. Each charger read makes one more request.
- A start refused because the charger reports an unknown state says so, instead of showing a general
  failure.

## [0.1.2] - 2026-10-01

### Fixed

- The *Refresh* button shows an error when its charger read or its price read fails, instead of succeeding
  silently. A `button.press` step in a script or an automation fails then too.

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
