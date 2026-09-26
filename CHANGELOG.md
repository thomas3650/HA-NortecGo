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

## [0.0.1] - 2026-09-26

### Added

- Initial project skeleton; not usable yet.
