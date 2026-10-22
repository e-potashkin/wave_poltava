"""Wave Poltava: own air-raid monitor for Poltava, card included."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    CARD_FILES,
    CARD_STATIC_PATH,
    DOMAIN,
    ENTITY_LABEL_TYPES,
    PLATFORMS,
    VERSION,
)
from .coordinator import WavePoltavaCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the bundled frontend modules."""
    www = Path(__file__).parent / "www"
    if not www.exists():
        _LOGGER.warning("the bundled card folder is missing: %s", www)
        return True

    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_STATIC_PATH, str(www), False)]
    )
    for name in CARD_FILES:
        add_extra_js_url(hass, f"{CARD_STATIC_PATH}/{name}?v={VERSION}")
    _LOGGER.debug("frontend modules registered under %s", CARD_STATIC_PATH)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the feed, the wave and the entities."""
    await _async_cleanup(hass, entry)

    coordinator = WavePoltavaCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(coordinator.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info(
        "wave %s is listening: release_after=%d min, feed=%s",
        VERSION,
        coordinator.release_after,
        coordinator.last_post_id,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the platforms and drop the coordinator."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unloaded:
        coordinator = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if coordinator is not None:
            coordinator.async_stop()
    return unloaded


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_cleanup(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove entities this version no longer creates."""
    expected = {
        f"{DOMAIN}_{entry.entry_id}_{key}"
        for key in (
            "wave",
            "local",
            "started",
            "ended",
            "duration",
            "label",
            "feed",
            "alert",
        )
    }
    expected.update(
        f"{DOMAIN}_{entry.entry_id}_label_{key}"
        for key, _name, _kinds in ENTITY_LABEL_TYPES
    )
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(
        registry, entry.entry_id
    ):
        if entity.unique_id not in expected:
            registry.async_remove(entity.entity_id)
