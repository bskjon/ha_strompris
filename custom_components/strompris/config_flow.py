"""Config flow for strompris integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_registry import async_get as async_get_entity_reg

from .const import DOMAIN, PRICE_ZONE, PRICE_ZONES

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(PRICE_ZONE, default=False): vol.In(PRICE_ZONES),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    valgt_pris_sone = data[PRICE_ZONE]
    entity_registry = async_get_entity_reg(hass)

    if not entity_registry.async_get_entity_id("sensor", DOMAIN, valgt_pris_sone):

        # Return info that you want to store in the config entry.
        return {
            "title": f"Strømpris for {data[PRICE_ZONE]}",
            PRICE_ZONE: data[PRICE_ZONE],
        }
    else:
        raise AlreadyConfigured(f"{valgt_pris_sone} is already configured..")


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for strompris."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        current = self._async_current_ids(include_ignore=True)
        user_input["ids"] = current

        errors = {}
        info = None
        try:
            info = await validate_input(self.hass, user_input)
        except AlreadyConfigured:
            errors["base"] = "already_configured"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"

        if errors or not info:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        self._async_abort_entries_match(match_dict=user_input)
        return self.async_create_entry(title=info["title"], data=user_input)


class AlreadyConfigured(HomeAssistantError):
    """Error to indicate entity already present."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
