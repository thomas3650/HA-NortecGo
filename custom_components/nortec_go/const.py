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
TICK_MINUTES: Final = (0, 15, 30, 45)
SLOT_LENGTH: Final = timedelta(minutes=15)

# EV Smart Charging's lists are padded to a full day (D23).
PAST_SLOT_PRICE: Final = 0.0
MISSING_SLOT_PRICE: Final = 10.0

PRICE_STORE_VERSION: Final = 1
PRICE_STORE_KEY: Final = "nortec_go.{entry_id}.prices"

# The charge switch's start guard (D26).
START_CONFIRM_TIMEOUT: Final = timedelta(minutes=10)
# How long the switch shows off after a stop while the charger still reports the charge (D29).
STOP_CONFIRM_TIMEOUT: Final = timedelta(minutes=2)
# At a restart a pending start waits at least this long, so the setup's first read decides first (D31).
START_LOAD_GRACE: Final = timedelta(minutes=2)
CHARGE_CONTROL_STORE_VERSION: Final = 1
CHARGE_CONTROL_STORE_KEY: Final = "nortec_go.{entry_id}.charge_control"
START_BLOCKED_ISSUE_ID: Final = "start_blocked_{entry_id}"
