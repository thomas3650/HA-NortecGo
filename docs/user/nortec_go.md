---
title: Nortec Go
description: Instructions on how to integrate a Nortec Go EV charger into Home Assistant.
ha_iot_class: Cloud Polling
ha_domain: nortec_go
ha_integration_type: hub
ha_codeowners:
  - '@thomas3650'
---

The **Nortec Go** integration connects Home Assistant to an EV charger managed through the Nortec Go app,
a white-label version of the [Monta](https://monta.com) app.

**Unofficial.** Not affiliated with, endorsed by or supported by Nortec or Monta. It uses the same private
API as the app (through the `pynortecgo` library), which can change without notice.

## Supported devices

Not available yet.

## Unsupported devices

Not available yet.

## Prerequisites

You need a Nortec Go account with exactly one charger and one car registered, since that is what the
client library currently supports.

## Installation

This section isn't part of core's integration docs template; it is kept here because this integration is
installed through HACS rather than bundled with Home Assistant.

Install via HACS as a custom repository:

1. In HACS, open the menu (⋮) and choose **Custom repositories**.
2. Add `https://github.com/thomas3650/HA-NortecGo` with type **Integration**.
3. Restart Home Assistant.

## Configuration options

Not available yet.

## Supported functionality

Not available yet.

## Actions, conditions and triggers

Not available yet.

## Automation examples

Not available yet.

## Data updates

Not available yet.

## Known limitations

Not available yet.

## Troubleshooting

Not available yet.

## Removing the integration

Once this integration has a config flow, remove it from **Settings** > **Devices & services** first.
Then remove it in HACS and restart Home Assistant.
