"""Constants for the Nortec Go integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "nortec_go"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_EXPIRES_AT: Final = "expires_at"

# Charger polling, by the charge status (D29): 30 s while a charge starts or stops.
INTERVAL_CHANGING: Final = timedelta(seconds=30)
INTERVAL_CHARGING: Final = timedelta(minutes=5)
INTERVAL_IDLE: Final = timedelta(minutes=60)
# The charger's own starting or stopping state keeps the 30 s reads only while the last good
# read is younger than this, so an outage doesn't read every 30 s (D31).
FAST_READ_MAX_AGE: Final = timedelta(minutes=2)
# A read also reads the car when its last try is at least this old; the margin keeps an
# early 5-minute read from skipping it (D29).
CAR_READ_MIN_AGE: Final = INTERVAL_CHARGING - INTERVAL_CHANGING

# Price reads (local time) and the quarter-hour tick that moves the current slot.
PRICE_READ_HOURS: Final = (0, 5, 10, 15, 20)
PRICE_READ_MINUTE: Final = 5
# A failed setup or scheduled price read is read once more after this (D37).
PRICE_RETRY_DELAY: Final = timedelta(minutes=15)
TICK_MINUTES: Final = (0, 15, 30, 45)
SLOT_LENGTH: Final = timedelta(minutes=15)

# EV Smart Charging's lists are padded to a full day (D23).
PAST_SLOT_PRICE: Final = 0.0
MISSING_SLOT_PRICE: Final = 10.0

PRICE_STORE_VERSION: Final = 2
PRICE_STORE_KEY: Final = "nortec_go.{entry_id}.prices"

# The Total energy ledger (D47).
ENERGY_STORE_VERSION: Final = 1
ENERGY_STORE_KEY: Final = "nortec_go.{entry_id}.energy"

# The charge switch's start guard (D26).
START_CONFIRM_TIMEOUT: Final = timedelta(minutes=10)
# How long the switch shows off after a stop while the charger still reports the charge (D29).
STOP_CONFIRM_TIMEOUT: Final = timedelta(minutes=2)
# At a restart a pending start waits at least this long, so the setup's charger read and car read (D44)
# decide first (D31). If the two take longer, the deadline ends it and forgets a stop asked for (#85).
START_LOAD_GRACE: Final = timedelta(minutes=2)
CHARGE_CONTROL_STORE_VERSION: Final = 1
CHARGE_CONTROL_STORE_KEY: Final = "nortec_go.{entry_id}.charge_control"
START_BLOCKED_ISSUE_ID: Final = "start_blocked_{entry_id}"
# The repair issue for a car that went from the account while running (D44).
CAR_GONE_ISSUE_ID: Final = "car_gone_{entry_id}"
