"""Constants for the Nortec Go integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "nortec_go"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_EXPIRES_AT: Final = "expires_at"

# Charger polling, by the charge status: 30 s while a charge starts or stops.
INTERVAL_CHANGING: Final = timedelta(seconds=30)
INTERVAL_CHARGING: Final = timedelta(minutes=5)
INTERVAL_IDLE: Final = timedelta(minutes=60)
# The charger's own starting or stopping state keeps the 30 s reads only while the last good
# read is younger than this, so an outage doesn't read every 30 s.
FAST_READ_MAX_AGE: Final = timedelta(minutes=2)
# A read also reads the car when its last try is at least this old; the margin keeps an
# early 5-minute read from skipping it.
CAR_READ_MIN_AGE: Final = INTERVAL_CHARGING - INTERVAL_CHANGING

# Price reads (local time) and the quarter-hour tick that moves the current slot.
PRICE_READ_HOURS: Final = (0, 5, 10, 15, 20)
PRICE_READ_MINUTE: Final = 5
# A failed setup or scheduled price read is read once more after this, once only,
# so the load on the rate-limited API at most doubles.
PRICE_RETRY_DELAY: Final = timedelta(minutes=15)
TICK_MINUTES: Final = (0, 15, 30, 45)
SLOT_LENGTH: Final = timedelta(minutes=15)

# EV Smart Charging's lists are padded to a full day: it rejects a short one.
PAST_SLOT_PRICE: Final = 0.0
MISSING_SLOT_PRICE: Final = 10.0

PRICE_STORE_VERSION: Final = 2
PRICE_STORE_KEY: Final = "nortec_go.{entry_id}.prices"

# The Total energy ledger.
ENERGY_STORE_VERSION: Final = 1
ENERGY_STORE_KEY: Final = "nortec_go.{entry_id}.energy"

# The client's grid tariff, kept as it hands it over.
GRID_TARIFF_STORE_VERSION: Final = 1
GRID_TARIFF_STORE_KEY: Final = "nortec_go.{entry_id}.grid_tariff"

# The charge switch's start guard: a start whose charge isn't seen in this time blocks further
# starts, as it may have left a card hold.
START_CONFIRM_TIMEOUT: Final = timedelta(minutes=10)
# How long the switch shows off after an accepted stop while the charger still reports the charge
# (it reports the old state for about 25 s). Also the least time between two stop calls.
STOP_CONFIRM_TIMEOUT: Final = timedelta(minutes=2)
# A stop asked for is tried at most this many times, and for at most this long from the ask:
# the stop isn't tied to one charge, so its age bounds the chance of stopping a later one.
STOP_MAX_TRIES: Final = 10
STOP_ASKED_MAX_AGE: Final = timedelta(minutes=30)
# At a restart a pending start waits at least this long, so the setup's charger read and car read
# decide first.
START_LOAD_GRACE: Final = timedelta(minutes=2)
CHARGE_CONTROL_STORE_VERSION: Final = 1
CHARGE_CONTROL_STORE_MINOR_VERSION: Final = 2
CHARGE_CONTROL_STORE_KEY: Final = "nortec_go.{entry_id}.charge_control"
START_BLOCKED_ISSUE_ID: Final = "start_blocked_{entry_id}"
# The repair issue for a stop the control gave up on.
STOP_FAILED_ISSUE_ID: Final = "stop_failed_{entry_id}"
# The repair issue for a car that went from the account while running.
CAR_GONE_ISSUE_ID: Final = "car_gone_{entry_id}"
