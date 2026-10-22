"""Shared base for the Wave Poltava entities."""

from __future__ import annotations

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, FEED_URL, VERSION


class WaveEntity(Entity):
    """An entity that reads the coordinator and follows its pushes."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, coordinator: Any, key: str) -> None:
        """Initialize the entity."""
        self.coordinator = coordinator
        self._attr_unique_id = (
            f"{DOMAIN}_{coordinator.entry.entry_id}_{key}"
        )

    @property
    def device_info(self) -> dict[str, Any]:
        """Group every entity under one device."""
        return {
            "identifiers": {(DOMAIN, "wave_poltava")},
            "name": "Wave Poltava",
            "manufacturer": "e-potashkin",
            "model": "Poltava air-raid monitor",
            "sw_version": VERSION,
            "configuration_url": FEED_URL,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to the coordinator."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.add_listener(self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        """Write the new state."""
        self.async_write_ha_state()

    def _common(self) -> dict[str, Any]:
        """Return the attributes every wave entity carries."""
        return self.coordinator.common_attributes()
