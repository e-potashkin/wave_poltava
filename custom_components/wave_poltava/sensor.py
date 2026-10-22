"""The sensors that carry the wave, the local row and the reason rows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime

from .const import (
    DOMAIN,
    ENTITY_DURATION_NAME,
    ENTITY_ENDED_NAME,
    ENTITY_LABEL_NAME,
    ENTITY_LABEL_TYPES,
    ENTITY_LOCAL_NAME,
    ENTITY_STARTED_NAME,
    ENTITY_WAVE_NAME,
    FEED_NAME,
    STATE_ACTIVE,
    STATE_IDLE,
)
from .coordinator import WavePoltavaCoordinator
from .entity import WaveEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Add the sensors."""
    coordinator: WavePoltavaCoordinator = hass.data[DOMAIN][
        entry.entry_id
    ]
    entities: list[SensorEntity] = [
        WaveSensor(coordinator),
        WaveLocalSensor(coordinator),
        WaveStartedSensor(coordinator),
        WaveEndedSensor(coordinator),
        WaveDurationSensor(coordinator),
        WaveLabelSensor(coordinator),
    ]
    entities.extend(
        WaveLabelTypeSensor(coordinator, key, name, kinds)
        for key, name, kinds in ENTITY_LABEL_TYPES
    )
    entities.append(FeedSensor(coordinator))
    async_add_entities(entities)


class WaveSensorBase(WaveEntity, SensorEntity):
    """A sensor that reads the coordinator."""


class WaveSensor(WaveSensorBase):
    """The wave itself: active or idle."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [STATE_ACTIVE, STATE_IDLE]
    _attr_icon = "mdi:waves"

    def __init__(self, coordinator: WavePoltavaCoordinator) -> None:
        """Initialize the wave sensor."""
        super().__init__(coordinator, "wave")
        self._attr_name = ENTITY_WAVE_NAME

    @property
    def native_value(self) -> str:
        """Return active while the wave runs, idle otherwise."""
        return STATE_ACTIVE if self.coordinator.active else STATE_IDLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the wave detail."""
        return self._common()


class WaveLocalSensor(WaveSensorBase):
    """active while one of our districts is under alert."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [STATE_ACTIVE, STATE_IDLE]
    _attr_icon = "mdi:shield-alert"

    def __init__(self, coordinator: WavePoltavaCoordinator) -> None:
        """Initialize the local row."""
        super().__init__(coordinator, "local")
        self._attr_name = ENTITY_LOCAL_NAME

    @property
    def native_value(self) -> str:
        """Return active while our area is under alert."""
        return (
            STATE_ACTIVE if self.coordinator.local_active() else STATE_IDLE
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the wave detail and the clocks behind the local state."""
        attrs = self._common()
        attrs["local_areas"] = sorted(self.coordinator.local_areas)
        attrs["local_last_at"] = (
            self.coordinator.local_last_at.isoformat()
            if self.coordinator.local_last_at is not None
            else None
        )
        attrs["local_cleared_at"] = (
            self.coordinator.local_cleared_at.isoformat()
            if self.coordinator.local_cleared_at is not None
            else None
        )
        # The start of the alert that is running now, not the start of the
        # wave: one wave can hold an all-clear and a second alert.
        attrs["local_started_at"] = (
            self.coordinator.local_started_at.isoformat()
            if self.coordinator.local_started_at is not None
            else None
        )
        return attrs


class WaveStartedSensor(WaveSensorBase):
    """When the current or last wave started."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-start"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: WavePoltavaCoordinator) -> None:
        """Initialize the started sensor."""
        super().__init__(coordinator, "started")
        self._attr_name = ENTITY_STARTED_NAME

    @property
    def native_value(self) -> datetime | None:
        """Return the start time."""
        return self.coordinator.tracker.wave.started_at

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the common attributes."""
        return self._common()


class WaveEndedSensor(WaveSensorBase):
    """When the current or last wave ended."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-end"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: WavePoltavaCoordinator) -> None:
        """Initialize the ended sensor."""
        super().__init__(coordinator, "ended")
        self._attr_name = ENTITY_ENDED_NAME

    @property
    def native_value(self) -> datetime | None:
        """Return the end time, or None while the wave runs."""
        return self.coordinator.tracker.wave.ended_at

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the common attributes."""
        return self._common()


class WaveDurationSensor(WaveSensorBase):
    """How long the current or last wave lasted."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-outline"
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: WavePoltavaCoordinator) -> None:
        """Initialize the duration sensor."""
        super().__init__(coordinator, "duration")
        self._attr_name = ENTITY_DURATION_NAME

    @property
    def native_value(self) -> float | None:
        """Return the length in minutes."""
        return self.coordinator.duration_minutes()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the common attributes."""
        return self._common()


class WaveLabelSensor(WaveSensorBase):
    """The reason row: the channel's own words about our area."""

    _attr_icon = "mdi:message-alert-outline"

    def __init__(self, coordinator: WavePoltavaCoordinator) -> None:
        """Initialize the generic reason row."""
        super().__init__(coordinator, "label")
        self._attr_name = ENTITY_LABEL_NAME

    @property
    def native_value(self) -> str:
        """Return the message, or the sentinel the card hides."""
        return self.coordinator.local_label()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the common attributes."""
        return self._common()


class WaveLabelTypeSensor(WaveSensorBase):
    """The reason row of one kind of danger."""

    _attr_icon = "mdi:eye"

    def __init__(
        self,
        coordinator: WavePoltavaCoordinator,
        key: str,
        name: str,
        kinds: tuple[str, ...],
    ) -> None:
        """Initialize one typed reason row."""
        super().__init__(coordinator, f"label_{key}")
        self._attr_name = name
        self._type_key = key
        self._kinds = kinds

    @property
    def native_value(self) -> str:
        """Return the message when the last local message was this kind."""
        return self.coordinator.local_label_for(self._type_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the common attributes."""
        return self._common()


class FeedSensor(WaveSensorBase):
    """The raw text of the newest post, for diagnostics and notifications.

    The all-clear automation quotes this sensor, so it keeps the id the old
    rest sensor had: `sensor.monitoring_poltavshchina_text`.
    """

    _attr_icon = "mdi:bullhorn-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: WavePoltavaCoordinator) -> None:
        """Initialize the feed sensor."""
        super().__init__(coordinator, "feed")
        self._attr_name = FEED_NAME

    @property
    def native_value(self) -> str | None:
        """Return the newest post text."""
        return self.coordinator.last_message or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return where the post came from and whether the feed works."""
        return {
            "post_id": self.coordinator.last_post_id,
            "post_at": (
                self.coordinator.last_post_at.isoformat()
                if self.coordinator.last_post_at
                else None
            ),
            "feed_ok": self.coordinator.last_fetch_ok,
            "feed_error": self.coordinator.last_error,
            "source": "https://telegram.me/s/monitoringplt",
        }

