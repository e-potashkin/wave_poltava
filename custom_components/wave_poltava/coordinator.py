"""The one object that owns the feed, the wave and the local row.

    Telegram preview        this coordinator             entities
    -----------------       -------------------          --------------------
    one page every 30 s --> classify() per new post -->  wave, local, labels
                            tracker.note_message()       alert, feed
                            Store (survives restart)

The coordinator does three jobs and they are deliberately in one place:

1. It fetches the channel's preview page itself. No `rest` sensor, no `scrape`
   sensor and no parser integration is needed.
2. It classifies every new post with the channel's own markers (start,
   continuation, wind-down, reversal, end, noise).
3. It keeps the wave and the clocks that decide whether Poltava is red, and
   writes both to `.storage` so a restart does not lose them.

A post is processed once. The preview page holds the last twenty-odd posts, so
the newest post id is stored and only a greater id is new.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_RELEASE_MINUTES,
    ENTITY_LABEL_TYPES,
    DEFAULT_RELEASE_MINUTES,
    DOMAIN,
    FEED_URL,
    HTTP_TIMEOUT_SECONDS,
    LOCAL_AREAS,
    MAX_RELEASE_MINUTES,
    MIN_RELEASE_MINUTES,
    SCAN_INTERVAL_SECONDS,
    STATE_QUIET,
    STORAGE_VERSION,
)
from .feed import Post, async_fetch
from .markers import AREAS, END, NOISE, UNKNOWN, classify, clean_text
from .tracker import WaveSnapshot, WaveTracker

_LOGGER = logging.getLogger(__name__)

AREA_NAMES = {key: name for key, name, _pattern in AREAS}


def _stamp(value: datetime | None) -> str | None:
    """Return a readable local timestamp, without the timezone suffix."""
    if value is None:
        return None
    return dt_util.as_local(value).strftime("%Y-%m-%d %H:%M:%S")


def _moment(value: Any) -> datetime | None:
    """Read a saved timestamp and shrug at anything else."""
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt_util.UTC)
    return dt_util.as_utc(moment)


class WavePoltavaCoordinator:
    """Fetch the channel, keep the wave, and push the entities."""

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        """Initialize the coordinator from the config entry."""
        self.hass = hass
        self.entry = entry
        try:
            configured = int(
                entry.options.get(
                    CONF_RELEASE_MINUTES, DEFAULT_RELEASE_MINUTES
                )
            )
        except (TypeError, ValueError):
            configured = DEFAULT_RELEASE_MINUTES
        self.release_after = max(
            MIN_RELEASE_MINUTES, min(MAX_RELEASE_MINUTES, configured)
        )
        self.tracker = WaveTracker(release_after_minutes=self.release_after)
        self.snapshot: WaveSnapshot | None = None

        # The districts that count as ours for the red row and the reason rows.
        self.local_areas = set(LOCAL_AREAS)
        self.local_message: str | None = None
        self.local_type: str | None = None
        self.local_last_at: datetime | None = None
        self.local_cleared_at: datetime | None = None
        # When the CURRENT alert of our area began. It is not the wave start:
        # one wave can hold an all-clear and a second alert.
        self.local_started_at: datetime | None = None

        # The feed.
        self.last_post_id: int | None = None
        self.last_message: str | None = None
        self.last_post_at: datetime | None = None
        self.last_fetch_ok: bool | None = None
        self.last_error: str | None = None
        self._logged_error: str | None = None

        # The wave identity, readable by a person.
        self.wave_id: str | None = None
        self.restored = False
        self.restored_from: str | None = None

        self._listeners: list[Any] = []
        self._unsub: Any = None
        self._lock = asyncio.Lock()
        self._published: str | None = None
        self._saved: str | None = None
        self._store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

    # -- lifecycle -------------------------------------------------------

    async def async_setup(self) -> None:
        """Restore the record, fetch once, and start the 30 second beat."""
        saved = await self._store.async_load()
        if isinstance(saved, dict):
            self._restore(saved)
        await self._async_refresh()
        self._unsub = async_track_time_interval(
            self.hass,
            self._handle_tick,
            timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )

    @callback
    def async_stop(self) -> None:
        """Stop the beat."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_tick(self, _now: datetime) -> None:
        """Fetch and refresh on the beat."""
        self.hass.async_create_task(self._async_refresh())

    @callback
    def add_listener(self, target: Any) -> Any:
        """Register an entity for updates. Return the remove callback."""
        self._listeners.append(target)

        @callback
        def _remove() -> None:
            if target in self._listeners:
                self._listeners.remove(target)

        return _remove

    # -- state -----------------------------------------------------------

    @property
    def active(self) -> bool:
        """Return True while the wave runs."""
        return self.snapshot.active if self.snapshot is not None else False

    def local_active(self, now: datetime | None = None) -> bool:
        """True while one of our districts has a live alert.

        The wave's own district set is not the test: the channel names a
        district once and often never clears it, so that set only grows. The
        test is the last message about our area and the silence after it.
        """
        if not self.local_areas or not self.tracker.wave.started:
            return False
        if self.local_last_at is None:
            return False
        if (
            self.local_cleared_at is not None
            and self.local_cleared_at >= self.local_last_at
        ):
            return False
        when = now or dt_util.utcnow()
        return when - self.local_last_at <= timedelta(
            minutes=self.release_after
        )

    def duration_minutes(self) -> float | None:
        """Return the running or finished wave length in minutes."""
        return self.tracker.duration_minutes(dt_util.utcnow())

    def local_label(self) -> str:
        """The reason row for every kind that has no row of its own."""
        return self.local_label_for(None)

    def local_label_for(self, type_key: str | None) -> str:
        """The reason row of one kind, or of the kinds without a row."""
        typed = {
            kind for _key, _name, kinds in ENTITY_LABEL_TYPES for kind in kinds
        }
        if type_key is None:
            if self.local_type in typed:
                return STATE_QUIET
        else:
            row = next(
                (
                    kinds
                    for key, _name, kinds in ENTITY_LABEL_TYPES
                    if key == type_key
                ),
                (),
            )
            if self.local_type not in row:
                return STATE_QUIET
        if not self.local_active():
            return STATE_QUIET
        return self.local_message or STATE_QUIET

    # -- feed ------------------------------------------------------------

    async def _async_refresh(self) -> None:
        """Fetch the page, process new posts, close an expired wave."""
        async with self._lock:
            now = dt_util.utcnow()
            try:
                posts = await async_fetch(
                    async_get_clientsession(self.hass),
                    FEED_URL,
                    HTTP_TIMEOUT_SECONDS,
                )
            except Exception as exc:  # noqa: BLE001
                self.last_fetch_ok = False
                self.last_error = f"{type(exc).__name__}: {exc}"
                if self.last_error != self._logged_error:
                    self._logged_error = self.last_error
                    _LOGGER.warning(
                        "the channel preview could not be read: %s",
                        self.last_error,
                    )
            else:
                self.last_fetch_ok = True
                self.last_error = None
                self._logged_error = None
                self._process(posts, now)

            self.snapshot = self.tracker.refresh(
                now, dt_util.as_local(now).date()
            )
            await self._publish()

    def _process(self, posts: list[Post], now: datetime) -> None:
        """Take the posts this integration has not seen yet."""
        if not posts:
            return
        if self.last_post_id is None:
            # First start: adopt the page. A post older than the release delay
            # must not open a wave at boot, so only the recent tail is replayed.
            # It gives a fresh install the alert that is running now.
            newest = posts[-1]
            self.last_post_id = newest.post_id
            self.last_message = newest.text
            self.last_post_at = newest.at
            cutoff = now - timedelta(minutes=self.release_after)
            recent = [
                post for post in posts if post.at is not None and post.at >= cutoff
            ]
            for post in recent:
                self._handle_post(post)
            _LOGGER.info(
                "feed adopted at post %s, replayed %d recent post(s)",
                self.last_post_id,
                len(recent),
            )
            return
        new = [post for post in posts if post.post_id > self.last_post_id]
        for post in new:
            self._handle_post(post)
        if new:
            self.last_post_id = new[-1].post_id
            _LOGGER.info(
                "read %d new post(s), newest %s",
                len(new),
                self.last_post_id,
            )

    def _handle_post(self, post: Post) -> None:
        """Classify one post and move the wave and the local row."""
        self.last_message = post.text
        self.last_post_at = post.at
        marker = classify(post.text)
        if marker.kind == NOISE:
            return

        when = post.at or dt_util.utcnow()

        if self.local_areas.intersection(marker.areas):
            if marker.kind == END:
                # The channel says our area is clear. That is the end of it,
                # and no silence test is needed.
                self.local_cleared_at = when
            else:
                # The start moves only when the row was idle before this
                # message: a second report inside one alert must not restart
                # the caption. The test runs before the clocks move.
                if not self.local_active(when):
                    self.local_started_at = when
                self.local_message = clean_text(post.text)
                self.local_type = marker.type
                self.local_last_at = when

        started = self.tracker.note_message(
            when,
            message=post.text,
            area=", ".join(marker.area_names) or None,
            danger=marker.type if marker.type != UNKNOWN else None,
            source=FEED_URL,
            event_type=marker.type,
            kind=marker.kind,
            areas=marker.areas,
        )
        if started:
            self.wave_id = when.strftime("%Y%m%dT%H%M%SZ")
            _LOGGER.info(
                "a wave started: %s %s",
                marker.kind,
                ",".join(marker.area_names) or "no area named",
            )

    # -- persistence -----------------------------------------------------

    def _restore(self, saved: dict[str, Any]) -> None:
        """Adopt the saved wave and the local clocks."""
        now = dt_util.utcnow()
        self.last_post_id = saved.get("last_post_id")
        self.last_message = saved.get("last_message")
        self.last_post_at = _moment(saved.get("last_post_at"))
        self.wave_id = saved.get("wave_id")
        self.tracker.waves_today = int(saved.get("waves_today") or 0)
        self.tracker.messages_today = int(saved.get("messages_today") or 0)
        wave = saved.get("wave")
        if isinstance(wave, dict) and self.tracker.restore(
            {"wave": wave, "uses_markers": True}, now
        ):
            self.restored = True
            self.restored_from = dt_util.as_local(now).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            _LOGGER.info(
                "wave restored: started %s, messages %s",
                wave.get("started_at"),
                wave.get("message_count"),
            )

        # Keep the counters of the same day. A refresh would zero them when
        # `day_key` is empty, which is how a restart in the middle of an alert
        # made waves_today read 0 while the wave was open.
        today = dt_util.as_local(now).date()
        started = self.tracker.wave.started_at
        if started is not None and dt_util.as_local(started).date() == today:
            self.tracker.day_key = today
            self.tracker.waves_today = max(self.tracker.waves_today, 1)
            self.tracker.messages_today = max(
                self.tracker.messages_today, self.tracker.wave.message_count
            )
        elif saved.get("day") == today.isoformat():
            self.tracker.day_key = today

        local = saved.get("local")
        if isinstance(local, dict):
            self.local_last_at = _moment(local.get("last_at"))
            self.local_cleared_at = _moment(local.get("cleared_at"))
            self.local_started_at = _moment(local.get("started_at"))
            self.local_message = local.get("message") or None
            self.local_type = local.get("kind") or None
        if self.local_started_at is None and self.local_last_at is not None:
            self.local_started_at = self.local_last_at
        self.snapshot = self.tracker.refresh(
            now, dt_util.as_local(now).date()
        )

    def _save_data(self) -> dict[str, Any]:
        """Return everything a restart must keep."""
        return {
            "last_post_id": self.last_post_id,
            "last_message": self.last_message,
            "last_post_at": (
                self.last_post_at.isoformat() if self.last_post_at else None
            ),
            "wave_id": self.wave_id,
            "wave": self.tracker.wave.as_dict(),
            "waves_today": self.tracker.waves_today,
            "messages_today": self.tracker.messages_today,
            "day": (
                self.tracker.day_key.isoformat()
                if self.tracker.day_key is not None
                else None
            ),
            "local": {
                "last_at": (
                    self.local_last_at.isoformat()
                    if self.local_last_at
                    else None
                ),
                "cleared_at": (
                    self.local_cleared_at.isoformat()
                    if self.local_cleared_at
                    else None
                ),
                "started_at": (
                    self.local_started_at.isoformat()
                    if self.local_started_at
                    else None
                ),
                "message": self.local_message,
                "kind": self.local_type,
            },
        }

    async def _publish(self) -> None:
        """Tell the entities, and save only when the record moved."""
        signature = self._signature()
        if signature != self._published:
            self._published = signature
            for target in list(self._listeners):
                target()

        # The duration moves on every beat, and saving it would write the
        # storage file every 30 seconds. The record below holds only what a
        # restart must keep.
        save_signature = self._save_signature()
        if save_signature == self._saved:
            return
        self._saved = save_signature
        try:
            await self._store.async_save(self._save_data())
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("the wave record could not be saved: %s", exc)

    def _save_signature(self) -> str:
        """The part of the state that must survive a restart."""
        return repr(
            (
                self.last_post_id,
                self.last_message,
                self.wave_id,
                self.tracker.waves_today,
                self.tracker.messages_today,
                self.local_last_at,
                self.local_cleared_at,
                self.local_started_at,
                self.local_message,
                self.local_type,
                tuple(self.tracker.wave.as_dict().items()),
            )
        )

    def _signature(self) -> str:
        """Everything the entities show, as one string."""
        snapshot = self.snapshot
        wave = self.tracker.wave
        return repr(
            (
                snapshot.active if snapshot else None,
                snapshot.reason if snapshot else None,
                self.release_after,
                self.tracker.waves_today,
                self.tracker.messages_today,
                self.wave_id,
                self.restored,
                self.last_post_id,
                self.last_fetch_ok,
                self.last_error,
                self.last_message,
                self.local_active(),
                self.local_last_at,
                self.local_cleared_at,
                self.local_started_at,
                self.local_message,
                self.local_type,
                round(self.duration_minutes() or 0, 1),
                tuple(wave.as_dict().items()),
                tuple(
                    self.local_label_for(key)
                    for key, _name, _kinds in ENTITY_LABEL_TYPES
                ),
            )
        )

    # -- attributes shared by the entities -------------------------------

    def area_name(self, key: str) -> str:
        """Return the display name of a district key."""
        return AREA_NAMES.get(key, key)

    def common_attributes(self) -> dict[str, Any]:
        """Return the attributes every wave entity carries."""
        snapshot = self.snapshot
        wave = self.tracker.wave
        attrs: dict[str, Any] = {
            "wave": wave.as_dict(),
            "wave_id": self.wave_id,
            "restored_after_restart": self.restored,
            "restored_from": self.restored_from,
            "started_at": _stamp(wave.started_at),
            "last_message_at": _stamp(wave.last_message_at),
            "ended_at": _stamp(wave.ended_at),
            "duration_minutes": self.duration_minutes(),
            "message_count": wave.message_count,
            "last_message": wave.last_message,
            "last_area": wave.last_area,
            "last_danger": wave.last_danger,
            "last_source": wave.last_source,
            "areas": [self.area_name(key) for key in wave.areas],
            "cleared": [self.area_name(key) for key in wave.cleared],
            "last_kind": wave.last_kind,
            "last_event_type": wave.last_event_type,
            "release_after_minutes": self.release_after,
            "waves_today": self.tracker.waves_today,
            "messages_today": self.tracker.messages_today,
            "day": (
                self.tracker.day_key.isoformat()
                if self.tracker.day_key is not None
                else None
            ),
            "feed_ok": self.last_fetch_ok,
        }
        if snapshot is not None:
            attrs["reason"] = snapshot.reason
        return attrs
