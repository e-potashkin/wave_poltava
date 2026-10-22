"""Config and options flow for Wave Poltava."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_RELEASE_MINUTES,
    DEFAULT_RELEASE_MINUTES,
    DOMAIN,
    MAX_RELEASE_MINUTES,
    MIN_RELEASE_MINUTES,
    NAME,
)


class WavePoltavaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add the single Wave Poltava entry."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Confirm the single entry."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Return the options flow."""
        return WavePoltavaOptionsFlow()


class WavePoltavaOptionsFlow(OptionsFlow):
    """Change the silence that ends a wave."""

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Show and save the release delay."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = int(
            self.config_entry.options.get(
                CONF_RELEASE_MINUTES, DEFAULT_RELEASE_MINUTES
            )
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_RELEASE_MINUTES, default=current
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_RELEASE_MINUTES,
                            max=MAX_RELEASE_MINUTES,
                        ),
                    )
                }
            ),
        )
