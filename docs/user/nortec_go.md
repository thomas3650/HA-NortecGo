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

- A charger on a Nortec Go account.
- The car linked to that account.

## Unsupported devices

An account with more than one charger. With more than one car, the integration works without car entities.

## Prerequisites

You need a Nortec Go account with exactly one charger. A car is optional: without one there is no car
device. A car added later appears after you reload the integration.

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

Home Assistant stores your email, the session that the sign-in returns and a device ID, never the password.
It renews the session by itself. The integration is named after your charger, or *Nortec Go* if the charger
has no name.

## Configuration options

The integration has no options to change after setup.

## Supported functionality

The integration adds two devices: the charger, and the car when the account has one.

### Charger

| Entity | Type | Description |
|---|---|---|
| Current price | Sensor | The spot price for the current 15 minutes, per kWh, incl. VAT. Its `prices_today` and `prices_tomorrow` attributes are in the format EV Smart Charging reads |
| Cable connected | Binary sensor | On when a cable is connected to the charger |
| Charging | Binary sensor | On while the car draws power |
| Charge | Switch | Starts and stops a charge. On while a charge is starting, charging or paused, and right after a start until the charger shows it |
| Charge status | Sensor | Start blocked, Starting, Charging, Paused, Stopping, Waiting for replug, Unplugged or Idle |

### Car

| Entity | Type | Description |
|---|---|---|
| Battery | Sensor | The car's state of charge, in % |
| Charge limit | Sensor | The charge limit set in the car, in % |
| Last seen | Sensor (diagnostic) | When the car last reported its data |
| Plugged in | Binary sensor | On when the car reports that it's plugged in, at any charger |
| Connected to charger | Binary sensor | On when the charger's cable is connected and the car reports it's plugged in |

Values the car doesn't report show as unknown. Until the car has been read once, the car device is called
*Car* and its entities are unavailable. If that happens when the integration is first added, the car's entity IDs start
with `car_` (for example `sensor.car_battery`) and keep that name after the car's own name arrives; rename
them in the entity settings if you like.

## Use cases

### Smart charging with EV Smart Charging

[EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging) plans charging in the cheapest
hours. Set it up with these entities:

| EV Smart Charging setting | Entity |
|---|---|
| Electricity price entity | Current price |
| EV SOC entity | Battery |
| EV target SOC entity | Charge limit |
| EV connected entity | Connected to charger |
| Charger control entity | Charge |
| Charging state entity | Charging (or leave it empty) |

*Connected to charger* is on only when your own car is at your charger. A guest car plugged into the
charger leaves it off, so EV Smart Charging leaves the charger alone and the guest charges normally.

Use *Charging* as the charging state entity, not the *Charge* switch: *Charge* stays on while the charge is
paused and right after a start, so EV Smart Charging's retry wouldn't fire when it should. Keep *Continuous
charging preferred* on: after a stop the charger needs the cable unplugged and replugged before it can
start again, so planning one continuous session suits it best.

## Starting a charge

Turning on *Charge* starts a charge; turning it off stops one. Each start can place a card hold on your
payment method, so a start is never retried.

If a start may have left a card hold without a charge starting, further starts are blocked until you unplug
the cable, Home Assistant sees a charge start (for example one started in the Nortec Go app), or you
confirm in the repair issue that Home Assistant creates. Find it under **Settings** > **System** >
**Repairs**. *Charge status* shows *Start blocked* while this applies.

Starts are also blocked, to be safe, if Home Assistant can't read its saved start guard. This clears the
same way.

After you turn *Charge* on, it shows on for up to 10 minutes while Home Assistant waits to see the charge
start. If no charge is seen by then, starts are blocked. After a stop, the charger needs the cable unplugged
and replugged before the next start.

## Actions, conditions and triggers

Not available yet.

## Automation examples

### Read the charger when you get home

The charger is read once an hour while no cable is connected. To see a plugged-in car sooner, read it
when you arrive:

```yaml
automation:
  - alias: "Read the Nortec Go charger when I get home"
    triggers:
      - trigger: zone
        entity_id: person.me
        zone: zone.home
        event: enter
    actions:
      - delay: "00:05:00"
      - action: homeassistant.update_entity
        target:
          entity_id: binary_sensor.garage_charger_cable_connected
```

Replace `person.me` and the entity ID with your own.

## Data updates

The integration reads the charger and the car:

- every 60 minutes while no cable is connected,
- every 15 minutes while a cable is connected,
- every 5 minutes while a charge is starting, running or stopping,
- every 5 minutes while a start is pending.

It reads the price forecast when it starts and at 00:05, 05:05, 10:05, 15:05 and 20:05. The current price
moves to the next 15 minutes by itself, without a read.

To read the charger and the car now, call the `homeassistant.update_entity` action on any Nortec Go entity
(see *Automation examples*). It doesn't read the prices.

## Known limitations

- One charger per account. An account with no charger or with more than one can't be added.
- Unofficial: the integration uses the same private API as the app, which can change without notice.
- The price is the spot price including VAT, without fees or grid tariff, so it isn't what you pay in
  total.
- The price is assumed to be in the currency set in Home Assistant. This has been checked only for DKK.
- Tomorrow's prices are a forecast until the day-ahead prices come out, around 13:00; the 15:05 read
  replaces them.
- Car data can be hours old (see *Last seen*), so *Connected to charger* can turn on late.
- Days and the price times follow Home Assistant's time zone.
- A car removed from the account, with its entities, disappears after you reload the integration.
- An unplug and replug between two reads (up to 15 minutes apart while a cable is connected) can't be seen;
  use the repair issue to allow starts again in that case.
- A hold that led to no charge is expected to expire by itself within about 7 days and can't be cancelled
  from Home Assistant.
- After a stop, the charger needs the cable unplugged and replugged before the next start, so an EV Smart
  Charging plan with more than one session needs a replug between them too.
- EV Smart Charging logs the integration's start errors as its own failed action.
- No live power reading.

## Troubleshooting

### Asked to sign in again

When the stored session is rejected, Home Assistant shows a **Reauthentication required** notice for Nortec
Go. Select it and enter your password. You sign in to the same account; signing in to an account with
another charger is refused.

### "The set charger was not found"

The charger you added is no longer on your Nortec Go account. Remove the integration and add it again.

### "Too many sign-in attempts"

The Nortec Go service limits sign-ins. Wait a while before you try again.

### "Starts are blocked"

See *Starting a charge*.

## Removing the integration

1. Go to **Settings** > **Devices & services** and select **Nortec Go**.
2. Open the menu (⋮) and select **Delete**.
3. To remove the files as well, remove **Nortec Go** in HACS and restart Home Assistant.
