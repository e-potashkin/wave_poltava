"""Constants for the Wave Poltava integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "wave_poltava"
NAME: Final = "Wave Poltava"
VERSION: Final = "1.0.12"
LOGGER_NAME: Final = f"custom_components.{DOMAIN}"

PLATFORMS: Final = ["sensor", "binary_sensor"]

# The channel this integration reads. The preview page is public and needs no
# account, so the integration owns the fetch as well as the parsing.
FEED_URL: Final = "https://telegram.me/s/monitoringplt"
FEED_NAME: Final = "Monitoring Poltavshchina text"
SCAN_INTERVAL_SECONDS: Final = 30
HTTP_TIMEOUT_SECONDS: Final = 20

# The silence after the last message that ends a wave. It is NOT the length of
# a wave: every message moves the deadline.
CONF_RELEASE_MINUTES: Final = "release_after_minutes"
DEFAULT_RELEASE_MINUTES: Final = 30
MIN_RELEASE_MINUTES: Final = 5
MAX_RELEASE_MINUTES: Final = 240

# The districts that count as "ours" for the red row and the reason rows.
# Keys from markers.AREAS.
LOCAL_AREAS: Final = ("poltava_city", "poltava_raion", "poltava_rural")

# States of the wave sensors.
STATE_ACTIVE: Final = "active"
STATE_IDLE: Final = "idle"
# What a reason row says when there is nothing to say. The card hides it.
STATE_QUIET: Final = "—"

# Entity names. They are explicit so the derived entity ids stay the same as
# the ones the dashboard and the automations already read.
ENTITY_WAVE_NAME: Final = "Air wave"
ENTITY_LOCAL_NAME: Final = "Air wave local"
ENTITY_STARTED_NAME: Final = "Air wave started"
ENTITY_ENDED_NAME: Final = "Air wave ended"
ENTITY_DURATION_NAME: Final = "Air wave duration"
ENTITY_LABEL_NAME: Final = "Air wave label"
ENTITY_ALERT_NAME: Final = "Air threat local alert"

# One reason row per kind of danger, so the card can colour a message by the
# weapon the channel named. The tuple holds the classifier's type names that
# light that row. `cruise` speaks for cruise missiles and for a generic missile
# warning, because the channel does not always separate them.
ENTITY_LABEL_TYPES: Final = (
    ("drone", "Air wave label drone", ("drone",)),
    ("cruise", "Air wave label cruise", ("cruise", "rocket")),
    ("ballistic", "Air wave label ballistic", ("ballistic",)),
    ("gab", "Air wave label gab", ("gab",)),
)

# The card and the two small frontend helpers it needs are shipped inside the
# integration, so a HACS install carries them.
CARD_STATIC_PATH: Final = "/wave_poltava_static"
CARD_FILES: Final = (
    "i18n-card.js",
    "i18n-chrome.js",
    "wave-divider-card.js",
)

# The wave record is written to .storage so a restart does not lose it.
STORAGE_VERSION: Final = 1
