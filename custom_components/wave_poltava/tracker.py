"""Wave tracking logic for the Wave Layer integration.

This module holds no Home Assistant imports, so it can be tested offline.
A "wave" is one episode of aerial danger: it starts with the first matching
message, it grows with every further message, and it ends when no message has
arrived for the release delay.

    message 1        message 2            release delay after message 2
       |                |                              |
       v                v                              v
   ----+----------------+------------------------------+------> time
       |<----------------- wave active --------------->|
       |                                                |
    started_at                                     ended_at
    duration_minutes = ended_at - started_at
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

# An OPEN wave with no message for longer than this is stale, not resumed.
# A wave that had already ended is display-only and has no such limit: a
# restart must not erase the start, end, length and message of the last wave.
MAX_RESTORE_HOURS = 24


@dataclass
class Wave:
    """One episode of aerial danger."""

    started_at: datetime | None = None
    last_message_at: datetime | None = None
    ended_at: datetime | None = None
    message_count: int = 0
    last_message: str | None = None
    last_area: str | None = None
    last_danger: str | None = None
    last_source: str | None = None
    last_event_type: str | None = None
    # The districts still under alert, in the order the channel named them. A
    # wave ends when this is empty, which is what makes a partial all-clear
    # behave: the channel clears one district while another is still red.
    areas: list[str] = field(default_factory=list)
    # The districts already cleared inside this wave. Kept so an all-clear that
    # arrives twice, or for a district that never declared, changes nothing.
    cleared: list[str] = field(default_factory=list)
    # What the channel said last, for the entity attributes and for the log.
    last_kind: str | None = None

    @property
    def started(self) -> bool:
        """Return True while a wave is running.

        A wave that has ended keeps its record, so `started_at` alone is not the
        test: an all-clear with no open wave used to set `started_at` and leave
        `ended_at` empty, and the tracker then believed a wave was running.
        """
        return self.started_at is not None and self.ended_at is None

    def as_dict(self) -> dict:
        """Return the wave as plain data, for the entity state and for storage."""
        return {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_message_at": (
                self.last_message_at.isoformat() if self.last_message_at else None
            ),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "message_count": self.message_count,
            "last_message": self.last_message,
            "last_area": self.last_area,
            "last_danger": self.last_danger,
            "last_source": self.last_source,
            "last_event_type": self.last_event_type,
            "areas": list(self.areas),
            "cleared": list(self.cleared),
            "last_kind": self.last_kind,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Wave:
        """Build a wave from stored data."""

        def when(key: str) -> datetime | None:
            value = data.get(key)
            if not isinstance(value, str):
                return None
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None

        return cls(
            started_at=when("started_at"),
            last_message_at=when("last_message_at"),
            ended_at=when("ended_at"),
            message_count=int(data.get("message_count") or 0),
            last_message=data.get("last_message"),
            last_area=data.get("last_area"),
            last_danger=data.get("last_danger"),
            last_source=data.get("last_source"),
            last_event_type=data.get("last_event_type"),
            areas=list(data.get("areas") or []),
            cleared=list(data.get("cleared") or []),
            last_kind=data.get("last_kind"),
        )


@dataclass
class WaveDay:
    """Counters for one local day."""

    day: object = None
    waves_started: int = 0
    messages: int = 0


@dataclass
class WaveSnapshot:
    """What the sensor should show right now."""

    active: bool
    wave: Wave
    release_after_minutes: int
    waves_today: int
    messages_today: int
    restored: bool = False
    reason: str = ""


@dataclass
class WaveTracker:
    """Track the wave from three borrowed signals.

    danger_on   the parser's raw flag, true while a message still matches
    hold_on     the 30 minute hold sensor, the same clock the notifications use
    event_fired one event per matching message, which is the message counter

    A wave ends when the hold is off AND the release delay has passed since the last
    message. The second test is a fallback, because the hold sensor is a
    template sensor and does not survive a restart.

    A hold that is already off does not extend the wave. Measured 2026-10-14: the
    parser cleared its danger flag at 12:46, the hold expired at 12:47, and the
    wave stayed red until 13:10 because the deadline was `last message + 30
    minutes`. It now ends with the hold.
    """

    release_after_minutes: int = 30
    wave: Wave = field(default_factory=Wave)
    danger_on: bool = False
    hold_on: bool = False
    last_event_at: datetime | None = None
    # The moment the hold went from on to off. Ends a wave that would otherwise
    # wait out a full release delay after every danger report is already off.
    hold_released_at: datetime | None = None
    # True once a message carried a marker. From then on the markers decide when
    # a wave ends, and the hold is only a fallback for a silent channel.
    uses_markers: bool = False
    # True after a restore, until a publish has shown it once.
    restored: bool = False
    day_key: object = None
    waves_today: int = 0
    messages_today: int = 0

    # -- inputs ----------------------------------------------------------

    def set_release_after(self, minutes: object) -> None:
        """Set the release delay, from input_number.air_threat_release_after.

        The number is the silence that ends a wave, not its length: the
        deadline is `last message + N` and it moves with every message.
        """
        try:
            value = int(minutes)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        if 1 <= value <= 1440:
            self.release_after_minutes = value

    def set_flag(self, name: str, value: bool, when: datetime | None = None) -> bool:
        """Set the danger or the hold flag. Return True when it changed.

        `when` is the moment of the change. The caller supplies it, because
        this module does not depend on Home Assistant.
        """
        if name not in ("danger_on", "hold_on"):
            raise ValueError(name)
        changed = getattr(self, name) != value
        setattr(self, name, value)
        if name == "hold_on" and not value and changed and when is not None:
            # The hold released. Remember when: the wave may not outlive it by a
            # full release delay. The parser clears its danger flag as soon as
            # the channel reports an all-clear, and the hold follows at its own
            # deadline, so a wave that waited for `last message + delay` stayed
            # red for up to thirty minutes after every report was off.
            self.hold_released_at = when
        return changed

    def note_message(
        self,
        when: datetime,
        message: str | None = None,
        area: str | None = None,
        danger: str | None = None,
        source: str | None = None,
        event_type: str | None = None,
        kind: str | None = None,
        areas: list[str] | None = None,
    ) -> bool:
        """Record one message from the channel. Return True when a wave started.

        `kind` and `areas` come from the marker classifier, which reads the
        channel's own words. When they are absent the behaviour is the old one:
        the parser's flag and the hold decide.

            start         add the districts, open a wave if none is open
            continuation  refresh the deadline, open a wave if none is open
            end           remove the districts, close the wave when none is left
            wind_down     refresh the deadline; it is not an end
            reversal      refresh the deadline; it cancels a wind-down
            noise         ignored
        """
        if kind == "noise":
            return False
        if kind is not None:
            self.uses_markers = True

        # A message after a silence longer than the release delay belongs to a
        # new episode. This test runs first, because every later branch clears
        # `ended_at`, and a wave closed here would otherwise be reopened by the
        # message that follows it.
        if (
            self.wave.started
            and self.wave.ended_at is None
            and self.wave.areas
            and self.wave.last_message_at is not None
            and self.uses_markers
            and when - self.wave.last_message_at
            > timedelta(minutes=self.release_after_minutes)
        ):
            self.wave.ended_at = self.wave.last_message_at + timedelta(
                minutes=self.release_after_minutes
            )
            self.wave.cleared.extend(
                name for name in self.wave.areas if name not in self.wave.cleared
            )
            self.wave.areas = []

        started = False

        # The district set, before anything else: it decides whether this message
        # opens, continues or closes the wave.
        if kind == "end":
            if not self.wave.started:
                # Nothing is running, so there is nothing to clear. Recording it
                # left `ended_at` set on a wave that never ran, and the next
                # wind-down then opened a wave from it.
                return False
            for name in areas or []:
                if name in self.wave.areas:
                    self.wave.areas.remove(name)
                if name not in self.wave.cleared:
                    self.wave.cleared.append(name)
            if self.wave.ended_at is None and not self.wave.areas:
                # The last district is clear, so the wave is over. The moment is
                # this message, not a later timeout: the channel said so.
                self.wave.ended_at = when
            # The all-clear belongs to the wave it closes. Without this return
            # the code below saw a finished wave and opened a new one from the
            # all-clear: `started_at` became the all-clear time, the length
            # became zero and `waves_today` grew by one for every all-clear.
            self.wave.last_message_at = when
            self.wave.message_count += 1
            self.wave.last_message = message or self.wave.last_message
            self.wave.last_area = area or self.wave.last_area
            self.wave.last_danger = danger or self.wave.last_danger
            self.wave.last_source = source or self.wave.last_source
            self.wave.last_event_type = event_type or self.wave.last_event_type
            self.wave.last_kind = "end"
            self.messages_today += 1
            self.last_event_at = when
            return started

        # A wave opens on a start, and also on a continuation when the channel
        # began mid-sentence: that happens after a restart.
        if kind in ("start", "continuation") and self.wave.areas == [] and (
            not self.wave.started or self.wave.ended_at is not None
        ):
            self.wave = Wave(started_at=when)
            self.hold_released_at = None
            self.waves_today += 1
            started = True
            if kind == "start":
                for name in areas or []:
                    if name not in self.wave.areas:
                        self.wave.areas.append(name)
        elif kind == "start":
            # Only a declaration puts a district under alert. The channel names
            # districts for other reasons too: "В сторону Чутівського району."
            # is a route, and "Пройшли … Глобинський район" is a description of
            # where drones went. Adding those put 17 districts on one wave and no
            # all-clear ever emptied the set.
            for name in areas or []:
                if name not in self.wave.areas and name not in self.wave.cleared:
                    self.wave.areas.append(name)
        # A message after a longer silence than the release delay belongs to a new
        # wave. The old wave is closed at its real deadline, so the length of
        # the finished wave does not grow because the next one arrived late.
        if (
            self.wave.started
            and self.wave.ended_at is None
            and self.wave.areas
            and self.uses_markers
        ):
            # The channel named the districts and has not cleared them all, so
            # the wave is open whatever the silence. A channel that goes quiet
            # mid-raid is normal at night.
            self.wave.last_message_at = when
            self.wave.message_count += 1
            self.wave.last_message = message or self.wave.last_message
            self.wave.last_area = area or self.wave.last_area
            self.wave.last_danger = danger or self.wave.last_danger
            self.wave.last_source = source or self.wave.last_source
            self.wave.last_event_type = event_type or self.wave.last_event_type
            self.wave.last_kind = kind
            self.messages_today += 1
            self.last_event_at = when
            return started

        if (
            self.wave.started
            and self.wave.ended_at is None
            and self.wave.last_message_at is not None
            and when - self.wave.last_message_at > timedelta(minutes=self.release_after_minutes)
        ):
            self.wave.ended_at = self.wave.last_message_at + timedelta(
                minutes=self.release_after_minutes
            )
        if not self.wave.started or self.wave.ended_at is not None:
            self.wave = Wave(started_at=when)
            self.hold_released_at = None
            self.waves_today += 1
            started = True
        self.wave.last_message_at = when
        self.wave.ended_at = None
        self.wave.message_count += 1
        self.wave.last_message = message
        self.wave.last_area = area
        self.wave.last_danger = danger
        self.wave.last_source = source
        self.wave.last_event_type = event_type
        self.messages_today += 1
        self.last_event_at = when
        self.wave.last_kind = kind
        return started

    @property
    def areas(self) -> list[str]:
        """The districts still under alert."""
        return self.wave.areas

    @property
    def cleared(self) -> list[str]:
        """The districts cleared inside the current wave."""
        return self.wave.cleared

    # -- state -----------------------------------------------------------

    @property
    def deadline(self) -> datetime | None:
        """Return the moment the wave ends, or None when no wave is open."""
        if not self.wave.started or self.wave.last_message_at is None:
            return None
        return self.wave.last_message_at + timedelta(minutes=self.release_after_minutes)

    def save(self) -> dict:
        """Return everything that must survive a restart."""
        return {
            "wave": self.wave.as_dict(),
            "uses_markers": self.uses_markers,
            "waves_today": self.waves_today,
            "messages_today": self.messages_today,
        }

    def refresh(self, now: datetime, day_key: object) -> WaveSnapshot:
        """Close an expired wave and return what the sensor shows now.

        One-shot markers are cleared here, so they appear in exactly one
        published state. A refresh that nobody reads must not eat them, and
        that is why a caller cannot consume them by looking.
        """
        if day_key != self.day_key:
            self.day_key = day_key
            self.waves_today = 0
            self.messages_today = 0

        wave = self.wave
        active = False
        reason = "no wave yet"

        if wave.started and wave.ended_at is None:
            deadline = self.deadline
            # A wave that no declaration opened has no districts and no markers
            # behind it: a wind-down or a reversal arrived with nothing running.
            if self.uses_markers and wave.last_kind in ("wind_down", "reversal") and not wave.areas:
                wave.ended_at = self.last_event_at or now
                reason = "no alert was open when this message arrived"
            elif self.uses_markers and wave.last_kind in (
                "start",
                "continuation",
                "wind_down",
                "reversal",
                "end",
            ):
                # The channel's own markers decide. A wave is red while a district
                # it named is still under alert, and green when the last one is
                # cleared. The hold and the release delay are not consulted: they
                # are the fallback for a channel that carries no markers.
                if wave.areas and deadline is not None and now >= deadline:
                    # The channel named these districts and then went quiet for
                    # longer than the release delay. A channel that is reporting a
                    # live raid posts every few minutes, so silence this long ends
                    # the wave.
                    #
                    # The districts are dropped as well. Without this the set only
                    # grows: a 24-hour replay of the real channel produced ONE wave
                    # that named 17 districts and never closed, because several
                    # districts never get an explicit all-clear.
                    wave.ended_at = self.last_event_at or now
                    wave.cleared.extend(
                        name for name in wave.areas if name not in wave.cleared
                    )
                    wave.areas = []
                    reason = "the channel went quiet for %d minutes with %d district(s) named" % (
                        self.release_after_minutes,
                        len(wave.cleared),
                    )
                elif wave.areas:
                    active = True
                    reason = "the wave is active: %d district(s) under alert" % len(wave.areas)
                elif wave.last_kind == "end" or not self.hold_on:
                    wave.ended_at = wave.ended_at or (self.last_event_at or now)
                    reason = "every district is clear"
                else:
                    active = True
                    reason = "the districts are clear, the hold is still on"
            elif (
                self.hold_released_at is not None
                and self.hold_released_at <= now
                and (deadline is None or self.hold_released_at < deadline)
            ):
                # A hold that is already off cannot extend the wave, so this test
                # comes before the release delay. This is the normal shape of an
                # all-clear: the parser reports no danger, the hold expires, and
                # the wave ends with it instead of waiting out a fresh delay.
                wave.ended_at = self.hold_released_at
                reason = "the hold released, so the wave ended with it"
            elif deadline is not None and now < deadline:
                active = True
                reason = "inside the release delay after the last message"
            elif deadline is not None:
                wave.ended_at = deadline
                reason = "release delay passed after the last message"
            else:
                reason = "no message recorded"

        if (
            reason == "no wave yet"
            and wave.started_at is not None
            and wave.ended_at is not None
        ):
            # The wave was closed by an all-clear before this refresh. Say so,
            # instead of calling a finished wave "no wave yet".
            reason = (
                "every district is clear"
                if wave.last_kind == "end"
                else "the wave has ended"
            )

        restored = self.restored
        self.restored = False

        return WaveSnapshot(
            active=active,
            wave=wave,
            release_after_minutes=self.release_after_minutes,
            waves_today=self.waves_today,
            messages_today=self.messages_today,
            restored=restored,
            reason=reason,
        )

    def duration_minutes(self, now: datetime) -> float | None:
        """Return the wave length in minutes: closed or running."""
        wave = self.wave
        # A closed wave still has a length: this reports both running and ended.
        if wave.started_at is None:
            return None
        end = wave.ended_at or now
        return round((end - wave.started_at).total_seconds() / 60, 1)

    # -- persistence -----------------------------------------------------

    def restore(self, saved: dict | None, now: datetime) -> bool:
        """Restore a saved wave. Return True when it is resumed or shown.

        An OPEN wave with no message for longer than the release delay is
        already over. It is closed at its real deadline and kept for display,
        so a restart never resurrects an old alert. An open wave older than
        MAX_RESTORE_HOURS is dropped.

        A wave that had ALREADY ended before the restart is restored exactly as
        it was written. It is display-only (`Wave.started` is False), so it
        cannot resurrect an alert. It has no age limit for that reason: the
        dashboard and the timestamp sensors show the last wave, and a restart
        must not erase its start, end, length and messages. Without this, the
        next save wrote an empty record over the stored wave (Eugene,
        2026-10-24).
        """
        if not saved:
            return False
        # `save()` returns the whole state; the coordinator keeps only the wave.
        # Both shapes are accepted, so a saved file from either one still loads.
        if "wave" in saved and isinstance(saved.get("wave"), dict):
            if saved.get("uses_markers"):
                self.uses_markers = True
            saved = saved["wave"]
        wave = Wave.from_dict(saved)
        # A record with no start is an empty or broken save, not a wave.
        if wave.started_at is None:
            return False
        if wave.ended_at is not None:
            # A finished wave is shown, never resumed. Its fields are the last
            # thing a person read, so keep them all.
            self.wave = wave
            self.restored = True
            return True
        if wave.last_message_at is None:
            return False
        if now - wave.last_message_at > timedelta(hours=MAX_RESTORE_HOURS):
            return False
        deadline = wave.last_message_at + timedelta(minutes=self.release_after_minutes)
        if now >= deadline:
            wave.ended_at = deadline
        self.wave = wave
        self.restored = True
        return True


