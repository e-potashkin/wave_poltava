#!/usr/bin/env python3
"""Glue test: one post in, the local row and the wave out.

This imports the real coordinator, with small stand-ins for the three Home
Assistant helpers it calls. It adds no test framework: `make test` runs it.

    python3 tests/test_coordinator.py
"""

import asyncio
import sys
import types
from datetime import datetime, timedelta, timezone

# -- stand-ins for Home Assistant -------------------------------------------

ha = types.ModuleType("homeassistant")
ha.__path__ = []
sys.modules["homeassistant"] = ha

core = types.ModuleType("homeassistant.core")
core.HomeAssistant = object
core.callback = lambda func: func
sys.modules["homeassistant.core"] = core

helpers = types.ModuleType("homeassistant.helpers")
helpers.__path__ = []
sys.modules["homeassistant.helpers"] = helpers

event = types.ModuleType("homeassistant.helpers.event")
event.async_track_time_interval = lambda *args, **kwargs: (lambda: None)
sys.modules["homeassistant.helpers.event"] = event

storage = types.ModuleType("homeassistant.helpers.storage")


class Store:
    def __init__(self, *args, **kwargs):
        self.data = None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data


storage.Store = Store
sys.modules["homeassistant.helpers.storage"] = storage

components = types.ModuleType("homeassistant.components")
components.__path__ = []
sys.modules["homeassistant.components"] = components
frontend = types.ModuleType("homeassistant.components.frontend")
frontend.add_extra_js_url = lambda *args, **kwargs: None
sys.modules["homeassistant.components.frontend"] = frontend
http = types.ModuleType("homeassistant.components.http")
http.StaticPathConfig = object
sys.modules["homeassistant.components.http"] = http
config_entries = types.ModuleType("homeassistant.config_entries")
config_entries.ConfigEntry = object
sys.modules["homeassistant.config_entries"] = config_entries
config_validation = types.ModuleType("homeassistant.helpers.config_validation")
config_validation.config_entry_only_config_schema = lambda domain: {}
sys.modules["homeassistant.helpers.config_validation"] = config_validation
entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
entity_registry.async_get = lambda hass: None
sys.modules["homeassistant.helpers.entity_registry"] = entity_registry

aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")
aiohttp_client.async_get_clientsession = lambda hass: None
sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

util = types.ModuleType("homeassistant.util")
util.__path__ = []
sys.modules["homeassistant.util"] = util
dt_util = types.ModuleType("homeassistant.util.dt")
dt_util.UTC = timezone.utc
dt_util.utcnow = lambda: datetime.now(timezone.utc)
dt_util.as_local = lambda value: value.astimezone()
dt_util.as_utc = lambda value: value.astimezone(timezone.utc)
sys.modules["homeassistant.util.dt"] = dt_util

sys.path.insert(0, ".")

from custom_components.wave_poltava.coordinator import (  # noqa: E402
    WavePoltavaCoordinator,
)
from custom_components.wave_poltava.const import STATE_QUIET  # noqa: E402
from custom_components.wave_poltava.feed import Post  # noqa: E402

T0 = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=25)
FAILS = []


class Entry:
    entry_id = "test"
    options = {}


class Hass:
    data = {}

    def async_create_task(self, coro):
        return asyncio.ensure_future(coro)


def check(name, got, want):
    ok = got == want
    print("%-4s %-52s %s" % ("ok" if ok else "FAIL", name, got))
    if not ok:
        FAILS.append("%s: got %r, want %r" % (name, got, want))


def main():
    coordinator = WavePoltavaCoordinator(Hass(), Entry())
    coordinator._process([Post(100, "old post", T0)], T0)
    check("the first page is adopted", coordinator.last_post_id, 100)
    check("nothing is replayed", coordinator.active, False)
    # The coordinator refreshes before the first post in real life; this sets
    # the day, so the wave counters are not zeroed by the first check.
    coordinator.snapshot = coordinator.tracker.refresh(T0, T0.date())

    start = "🟡м. Полтава та околиці — тривога по БпЛА"
    coordinator._handle_post(Post(101, start, T0 + timedelta(minutes=1)))
    coordinator.snapshot = coordinator.tracker.refresh(
        T0 + timedelta(minutes=1), T0.date()
    )
    check("a local start opens the wave", coordinator.active, True)
    check("the local row is red", coordinator.local_active(T0 + timedelta(minutes=1)), True)
    check("the typed row carries it, without emoji", coordinator.local_label_for("drone"), "м. Полтава та околиці — тривога по БпЛА")
    check("the generic row hides it", coordinator.local_label(), STATE_QUIET)
    check("the start clock is set", coordinator.local_started_at, T0 + timedelta(minutes=1))

    end = "м. Полтава та околиці Відбій уваги по БпЛА"
    coordinator._handle_post(Post(102, end, T0 + timedelta(minutes=11)))
    coordinator.snapshot = coordinator.tracker.refresh(
        T0 + timedelta(minutes=11), T0.date()
    )
    check("the all-clear clears the row", coordinator.local_active(T0 + timedelta(minutes=11)), False)
    check("the wave keeps its start", coordinator.tracker.wave.started_at, T0 + timedelta(minutes=1))
    check("the wave ends", coordinator.active, False)
    check("the row is quiet again", coordinator.local_label_for("drone"), STATE_QUIET)

    second = "м. Полтава Київський район ❗️Реактивний БпЛА у вашому напрямку"
    coordinator._handle_post(Post(103, second, T0 + timedelta(minutes=20)))
    coordinator.snapshot = coordinator.tracker.refresh(
        T0 + timedelta(minutes=20), T0.date()
    )
    check("a second alert reopens", coordinator.local_active(T0 + timedelta(minutes=20)), True)
    check("its own start clock", coordinator.local_started_at, T0 + timedelta(minutes=20))
    check("two waves today", coordinator.tracker.waves_today, 2)

    attrs = coordinator.common_attributes()
    check("areas are readable names", attrs["areas"], ["м. Полтава"])
    check("the event type is kept", attrs["last_event_type"], "drone")
    check("the wave record is kept", attrs["wave"]["started_at"], (T0 + timedelta(minutes=20)).isoformat())

    print()
    if FAILS:
        print("FAILED:", len(FAILS))
        for fail in FAILS:
            print(" -", fail)
        return 1
    print("all coordinator checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
