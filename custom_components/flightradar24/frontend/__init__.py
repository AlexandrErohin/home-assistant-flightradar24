"""JavaScript module registration for Lovelace cards."""

from __future__ import annotations

from logging import getLogger
from pathlib import Path
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

from ..const import JSMODULES, URL_BASE

_LOGGER = getLogger(__name__)


class JSModuleRegistration:
    """Registers JavaScript modules in Home Assistant."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.lovelace = self.hass.data.get("lovelace")

    async def async_register(self) -> None:
        """Register frontend resources."""
        await self._async_register_path()
        mode = getattr(self.lovelace, "mode", None) or getattr(
            self.lovelace, "resource_mode", "yaml"
        )
        if mode == "storage":
            await self._async_wait_for_lovelace_resources()

    async def _async_register_path(self) -> None:
        """Register the static HTTP path."""
        try:
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(URL_BASE, Path(__file__).parent, False)]
            )
            _LOGGER.debug("Path registered: %s -> %s", URL_BASE, Path(__file__).parent)
        except RuntimeError:
            _LOGGER.debug("Path already registered: %s", URL_BASE)

    async def _async_wait_for_lovelace_resources(self) -> None:
        """Wait for Lovelace resources to load."""

        async def _check_loaded(_now: Any) -> None:
            if self.lovelace is None:
                self.lovelace = self.hass.data.get("lovelace")
            if self.lovelace and getattr(self.lovelace.resources, "loaded", False):
                await self._async_register_modules()
            else:
                _LOGGER.debug("Lovelace resources not loaded, retrying in 5s")
                async_call_later(self.hass, 5, _check_loaded)

        await _check_loaded(0)

    async def _async_register_modules(self) -> None:
        """Register or update JavaScript modules."""
        existing_resources = [
            resource
            for resource in self.lovelace.resources.async_items()
            if resource["url"].startswith(URL_BASE)
        ]

        for module in JSMODULES:
            url = f"{URL_BASE}/{module['filename']}"
            registered = False

            for resource in existing_resources:
                if self._get_path(resource["url"]) == url:
                    registered = True
                    if self._get_version(resource["url"]) != module["version"]:
                        _LOGGER.info(
                            "Updating %s to version %s",
                            module["name"],
                            module["version"],
                        )
                        await self.lovelace.resources.async_update_item(
                            resource["id"],
                            {
                                "res_type": "module",
                                "url": f"{url}?v={module['version']}",
                            },
                        )
                    break

            if not registered:
                _LOGGER.info(
                    "Registering %s version %s",
                    module["name"],
                    module["version"],
                )
                await self.lovelace.resources.async_create_item(
                    {
                        "res_type": "module",
                        "url": f"{url}?v={module['version']}",
                    }
                )

    @staticmethod
    def _get_path(url: str) -> str:
        return url.split("?")[0]

    @staticmethod
    def _get_version(url: str) -> str:
        parts = url.split("?")
        if len(parts) > 1 and parts[1].startswith("v="):
            return parts[1].replace("v=", "", 1)
        return "0"
