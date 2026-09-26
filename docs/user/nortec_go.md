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
client library currently supports. The car isn't checked when you add the integration, but later features
need it.

## Installation

This section isn't part of core's integration docs template. It is kept here because this integration is
installed through HACS rather than bundled with Home Assistant.

Install via HACS as a custom repository:

1. In HACS, open the menu (⋮) and choose **Custom repositories**.
2. Add `https://github.com/thomas3650/HA-NortecGo` with type **Integration**.
3. Search for **Nortec Go** in HACS, open it and select **Download**.
4. Restart Home Assistant.

## Configuration

1. Go to **Settings** > **Devices & services** and select **Add integration**.
2. Search for **Nortec Go** and select it.
3. Enter the email and password you use in the Nortec Go app.

Email
: The email address of your Nortec Go account.

Password
: Your Nortec Go password. It is used once to sign in and is not stored.

Home Assistant stores only the session that the sign-in returns, and renews it by itself. The integration
is named after your charger.

## Configuration options

The integration has no options to change after setup.

## Supported functionality

Not available yet.

## Actions, conditions and triggers

Not available yet.

## Automation examples

Not available yet.

## Data updates

Not available yet.

## Known limitations

- One charger per account. An account with no charger or with more than one can't be added.
- Unofficial: the integration uses the same private API as the app, which can change without notice.
- No entities yet. The integration only signs in and checks the charger; sensors and charge control come
  in later releases.

## Troubleshooting

### Asked to sign in again

When the stored session is rejected, Home Assistant shows a **Reauthentication required** notice for Nortec
Go. Select it and enter your password. You sign in to the same account; signing in to an account with
another charger is refused.

### "Too many sign-in attempts"

The Nortec Go service limits sign-ins. Wait a while before you try again.

## Removing the integration

1. Go to **Settings** > **Devices & services** and select **Nortec Go**.
2. Open the menu (⋮) and select **Delete**.
3. To remove the files as well, remove **Nortec Go** in HACS and restart Home Assistant.
