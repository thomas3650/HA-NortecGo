"""Constants for the Nortec Go integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "nortec_go"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_EXPIRES_AT: Final = "expires_at"

# Charger and car polling, by the charger's state (D22).
INTERVAL_UNPLUGGED: Final = timedelta(minutes=60)
INTERVAL_CONNECTED: Final = timedelta(minutes=15)
INTERVAL_CHARGING: Final = timedelta(minutes=5)

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
CHARGE_CONTROL_STORE_VERSION: Final = 1
CHARGE_CONTROL_STORE_KEY: Final = "nortec_go.{entry_id}.charge_control"
START_BLOCKED_ISSUE_ID: Final = "start_blocked_{entry_id}"
