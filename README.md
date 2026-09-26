# Nortec Go for Home Assistant

An unofficial Home Assistant integration for Nortec Go EV chargers (a white-label Monta app).

> **Unofficial.** Not affiliated with, endorsed by or supported by Nortec or Monta. It uses the same private
> API as the app (through the `pynortecgo` library), which can change without notice.

## Status

Sign-in only; no entities yet. Follow the [changelog](CHANGELOG.md).

## Installation

Install via HACS as a custom repository:

1. In HACS, open the menu (⋮) and choose **Custom repositories**.
2. Add `https://github.com/thomas3650/HA-NortecGo` with type **Integration**.
3. Search for **Nortec Go** in HACS, open it and select **Download**.
4. Restart Home Assistant.

## Documentation

See [`docs/user/nortec_go.md`](docs/user/nortec_go.md).

## License

Apache-2.0, see [`LICENSE`](LICENSE).
