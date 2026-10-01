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

An account with more than one charger. With no car or more than one when the integration starts, there are
no car entities, and starting a charge needs exactly one car and one saved card (see *Prerequisites*).

## Prerequisites

You need a Nortec Go account with exactly one charger. To start charges from Home Assistant, the account
also needs exactly one car and exactly one saved card; without them everything else works (the sensors, the
prices and *Refresh*), and a start is refused with the reason. A car added later to an account without one
appears after you reload the integration (see *Known limitations*).

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

The integration adds two devices: the charger, and the car if the account has exactly one when the
integration starts (see *Known limitations*).

### Charger

| Entity | Type | Description |
|---|---|---|
| Current price | Sensor | The total price (spot, fees and grid tariff) for the current 15 minutes, per kWh, incl. VAT, in the currency of the price data (Home Assistant's currency until price data has named one). Its `prices_today` and `prices_tomorrow` attributes are in the format EV Smart Charging reads |
| Cable connected | Binary sensor | On when a cable is connected to the charger |
| Charging | Binary sensor | On while the car draws power |
| Charge | Switch | Starts and stops a charge. On while a charge is starting, charging or paused, and right after a start until the charger shows it; off right after a stop until the charger shows it |
| Charge status | Sensor | Start blocked, Starting, Charging, Paused, Stopping, Waiting for replug, Unplugged or Idle |
| Energy this charge | Sensor | The energy the open charge has delivered so far, in kWh. Unknown when no charge is open. For the Energy dashboard, use *Total energy* |
| Total energy | Sensor | The energy the charger has delivered since the sensor was added, in kWh, kept across restarts. Use it for the Energy dashboard (see *Use cases*) |
| Charging power | Sensor | The charge's latest measured power, in kW. 0 when no charge is open, and unknown if the power couldn't be read |
| Cost this charge | Sensor | What the open charge costs so far, incl. VAT, fees and the grid tariff, in the charger's currency. Unknown when no charge is open. It can lag *Energy this charge* by a reading, and its last value can be below the billed total; while a charge is stopping it can already show the billed total |
| Last charge cost | Sensor | The billed total of the most recent completed charge on the charger. Its long-term statistics add up the charges completed after the sensor's first value. Unknown if the charge isn't among the charger's newest, or if it couldn't be read |
| Refresh | Button | Reads the charger, the car and the prices now |
| Last read | Sensor (diagnostic) | When the charger was last read. Shows how old the other values are, also after a failed read |

### Car

| Entity | Type | Description |
|---|---|---|
| Battery | Sensor | The car's state of charge, in % |
| Charge limit | Sensor | The charge limit set in the car, in % |
| Last seen | Sensor (diagnostic) | When the car last reported its data |
| Plugged in | Binary sensor | On when the car reports that it's plugged in, at any charger |
| Connected to charger | Binary sensor | On when the charger's cable is connected and the car reports it's plugged in |

Values the car doesn't report show as unknown.

If the car goes from the account, or a second car is added, the car's entities become unavailable and a
repair notice offers to remove the car device (see *Troubleshooting*). If you replace the car with another
one, the same device takes the new car's name, brand and model (it is called *Car* if the car has no name,
and a name you gave the device in Home Assistant stays). The entity IDs keep the old car's name; rename
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

### The charger in the Energy dashboard

In **Settings** > **Dashboards** > **Energy**, add an individual device with *Total energy* as its energy
sensor and, if you like, *Charging power* as its power sensor.

Don't add *Energy this charge* as well: the charger would be counted twice. If you added it before *Total
energy* existed, replace it.

## Starting a charge

Turning on *Charge* starts a charge; turning it off stops one. Each start can place a card hold on your
payment method, so a start is never retried.

A start is refused, with no card hold, without exactly one car and one saved card (see *Prerequisites*).

If a start may have left a card hold without a charge starting, further starts are blocked until you unplug
the cable, Home Assistant sees a charge start (for example one started in the Nortec Go app), or you
confirm in the repair issue that Home Assistant creates. Find it under **Settings** > **System** >
**Repairs**. *Charge status* shows *Start blocked* while this applies.

Starts are also blocked, to be safe, if Home Assistant can't read its saved start guard. This clears the
same way.

After you turn *Charge* on, it shows on for up to 10 minutes while Home Assistant waits to see the charge
start. If no charge is seen by then, starts are blocked. After a stop, the charger needs the cable unplugged
and replugged before the next start.

The 10-minute limit also applies while the charger can't be read; the block clears the same way.

After you turn *Charge* off, it shows off for up to 2 minutes, even while the charger can't be read, and
*Charge status* shows *Stopping* while Home Assistant waits for the charger to show the stop. Turning
*Charge* on in that time is refused.

## Actions, conditions and triggers

Not available yet.

## Automation examples

### Read the charger when you get home

The charger is read once an hour while no charge is running. To see a plugged-in car sooner, read it
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

The integration reads the charger:

- every 30 seconds while a charge is starting or stopping, including right after you turn *Charge* on or
  off,
- every 5 minutes while a charge is running,
- every 60 minutes otherwise.

While the charger can't be read, the 30-second reads stop after about 2 minutes, or about 10 minutes after
you turn *Charge* on.

It reads the car with the charger, but at most about every 5 minutes, and on every *Refresh*. It reads the
price forecast when it starts and at 00:05, 05:05, 10:05, 15:05 and 20:05. If a price read at start-up or at
one of these times fails, the integration tries once more 15 minutes later (or later, if the Nortec Go
service asks it to wait), unless the next read time comes first. The current price moves to the next 15
minutes by itself, without a read.

*Energy this charge*, *Charging power* and *Cost this charge* come from the last charger read, so while
charging they can be up to 5 minutes old. *Last charge cost* follows at the first read after a charge ends,
or the one after it (up to 60 minutes later); press *Refresh* to read it sooner. *Total energy* follows the
same reads. While a charge runs it grows with *Energy this charge*. When the charge ends, it moves up to
the charge's final energy at the read that first lists the charge as completed (see *Known limitations* for
when that doesn't happen).

Turning *Charge* on or off reads the charger right away. To read the charger, the car and the prices now,
press the *Refresh* button. From an automation, the `homeassistant.update_entity` action on any Nortec Go
entity reads the charger, and the car if it wasn't read in the last few minutes, but not the prices (see
*Automation examples*).

If the charger read or the price read of a *Refresh* press fails, the press shows an error. The other read
still runs; when both fail, the error is the charger read's. In a script or an automation, a `button.press`
step on *Refresh* fails then too.

## Known limitations

- One charger per account. An account with no charger or with more than one can't be added.
- Starting a charge needs exactly one car and one saved card (see *Prerequisites*).
- Unofficial: the integration uses the same private API as the app, which can change without notice.
- The grid tariff is estimated for the hours beyond those the charger prices itself. The estimates improve
  as the integration keeps running, and start over after a Home Assistant restart or a reload of the
  integration.
- The prices have been checked only for the DK2 price area (DKK).
- Tomorrow's prices are a forecast until the day-ahead prices come out, around 13:00; the 15:05 read
  replaces them (or its retry about 15 minutes later, if it fails).
- Car data can be hours old (see *Last seen*), so *Connected to charger* can turn on late.
- Days and the price times follow Home Assistant's time zone.
- The car device is added and removed only when the integration starts (a reload, or a restart of Home
  Assistant), never while it runs. A car added to an account without one appears after a reload. One
  removed makes its entities unavailable until then.
- An unplug and replug between two reads (up to 60 minutes apart while no charge is running) can't be seen;
  use the repair issue to allow starts again in that case.
- A charge started or resumed outside Home Assistant, for example in the Nortec Go app, can take up to 60
  minutes to show. Press *Refresh* to see it sooner.
- *Total energy* misses the end of a charge when a newer charge has completed before the charger was read
  again (two charges end between two reads, or a newer charge ends while Home Assistant is off). The older
  charge then keeps its highest reading, and the energy delivered after that reading isn't counted.
- A charge that the integration never read while it was open (it started and ended between two reads, which
  are up to 60 minutes apart, or while Home Assistant was off) is counted only if it is still the charger's
  most recent completed charge at the next read.
- *Total energy* starts at 0 when the sensor is added: with the update that brings it, or when you add the
  integration. It starts at 0 again if you remove the integration and add it back, or if its stored data
  can't be read. The Energy dashboard keeps its history.
- *Total energy* never goes down. In the rare case that a charge's final energy is below a reading taken
  while it ran, the reading counts.
- *Energy this charge* restarts with every charge, so it isn't meant for the Energy dashboard: a charge that
  follows a very short one, or that is first read late, can be missed there.
- A hold that led to no charge is expected to expire by itself within about 7 days and can't be cancelled
  from Home Assistant.
- After a stop, the charger needs the cable unplugged and replugged before the next start, so an EV Smart
  Charging plan with more than one session needs a replug between them too.
- EV Smart Charging logs the integration's start errors as its own failed action.
- *Charging power* has read 0 kW for about the first 30 seconds after a start, for up to about 2 minutes
  after a resume, and while stopping.
- *Last charge cost* misses a charge when two charges end between two reads, or when a charge that ended
  while Home Assistant was off is no longer the most recent one. Its statistics then lack that charge.
  They also lack the charge the sensor first showed: usually one from before you added the sensor, but
  the first one after it if the sensor was unknown until then.

## Troubleshooting

### Asked to sign in again

When the stored session is rejected, Home Assistant shows a **Reauthentication required** notice for Nortec
Go. Select it and enter your password. You sign in to the same account; signing in to an account with
another charger is refused.

### "The charger is no longer on the Nortec Go account"

The charger you added is no longer on your Nortec Go account. Remove the integration and add it again.

### "Too many sign-in attempts"

The Nortec Go service limits sign-ins. Wait a while before you try again.

### "Starts are blocked"

See *Starting a charge*.

### "The Nortec Go account … no longer has exactly one car"

The account had one car when the integration started, and now has none or more than one, so the car's
entities are unavailable. If the car comes back on the account, they work again by themselves and the
notice goes away. To remove the car device and its entities, select **Submit** in the notice: the
integration reloads. Reloading the integration yourself, or restarting Home Assistant, does the same.

### "Reading the car failed"

When the integration starts, it reads the charger and then the car. If the car can't be read then (the
service can't be reached, limits requests, returns an error or sends an answer the integration doesn't
understand), Home Assistant tries the start again by itself: first after a few seconds (or, while Home
Assistant itself is starting, when it has started), then at longer gaps of up to 10 minutes. Until a try
works, all the integration's entities are unavailable, *Charge* included. The integration's entry shows the
reason, which can also be one of the texts for a service that can't be reached, limits requests, returns an
error or sends an answer the integration doesn't understand.

### Debug logging

To see what the integration does, turn on debug logging from its page in Home Assistant, as described in
[Enabling debug logging](https://www.home-assistant.io/docs/configuration/troubleshooting/#enabling-debug-logging).
For Nortec Go this also covers `pynortecgo`, the library it uses to talk to the service.

Or add this to `configuration.yaml` (or merge it into your `logger:` block if you have one) and restart
Home Assistant:

```yaml
logger:
  default: warning
  logs:
    custom_components.nortec_go: debug
    pynortecgo: debug
```

Remove it again when you're done: debug logging writes a lot.

The logs hold no passwords or session tokens, but check them before you share them (see *Reporting a
problem*).

### Diagnostics

The diagnostics file shows what the integration last read from the charger and the car, and how its reads
are going. To download it, go to **Settings** > **Devices & services** > **Nortec Go**, open the entry's
menu (⋮) and select **Download diagnostics**.

The file leaves out your email, the session tokens and the device ID the integration signs in with; your
password is never stored. It keeps your charger's and car's names and IDs, the last charge's ID, cost,
energy and time, and the IDs, energy and times behind *Total energy*. Home Assistant adds its own
information, such as its version, your installed custom integrations and your time zone. Check the file
before you share it, and remove what you don't want public.

### Reporting a problem

Open an issue with the bug report template. Include your Home Assistant and integration versions and the
lines of the debug log around the problem, not the whole log. You can also attach the diagnostics file (see
*Diagnostics*). Before you post log lines, remove your email address, your charger's and car's names, and
anything else that identifies you or where you live.

## Removing the integration

1. Go to **Settings** > **Devices & services** and select **Nortec Go**.
2. Open the menu (⋮) and select **Delete**.
3. To remove the files as well, remove **Nortec Go** in HACS and restart Home Assistant.
