"""The binary sensor the notifications and the pop-up header read."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .const import DOMAIN, ENTITY_ALERT_NAME
from .coordinator import WavePoltavaCoordinator
from .entity import WaveEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Add the alert binary sensor."""
    coordinator: WavePoltavaCoordinator = hass.data[DOMAIN][
        entry.entry_id
    ]
    async_add_entities([AirThreatAlert(coordinator)])


class AirThreatAlert(WaveEntity, BinarySensorEntity):
    """On while one of our districts is under alert.

    It replaces the template sensor that read the old wave, and it keeps the
    same entity id because two automations trigger on its transitions.
    """

    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_icon = "mdi:shield-alert"

    def __init__(self, coordinator: WavePoltavaCoordinator) -> None:
        """Initialize the alert sensor."""
        super().__init__(coordinator, "alert")
        self._attr_name = ENTITY_ALERT_NAME

    @property
    def is_on(self) -> bool:
        """Return True while our area is under alert."""
        return self.coordinator.local_active()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the wave detail and the local clocks."""
        attrs = self._common()
        attrs["local_started_at"] = (
            self.coordinator.local_started_at.isoformat()
            if self.coordinator.local_started_at is not None
            else None
        )
        attrs["local_last_at"] = (
            self.coordinator.local_last_at.isoformat()
            if self.coordinator.local_last_at is not None
            else None
        )
        return attrs
