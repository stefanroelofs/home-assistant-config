from datetime import timedelta
import logging

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Config
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .const import CONF_PORT, CONF_HOST, DOMAIN, PLATFORMS, DEFAULT_SYNC_INTERVAL, CONF_USE_RTSP_SERVER_ADDON, DEFAULT_USE_RTSP_SERVER_ADDON, CONF_SYNC_INTERVAL, DEFAULT_SYNC_INTERVAL
from .coordinator import EufySecurityDataUpdateCoordinator

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup(hass: HomeAssistant, config: Config):
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    async def async_handle_send_message(call):
        coordinator: EufySecurityDataUpdateCoordinator = hass.data[DOMAIN]
        _LOGGER.debug(f"{DOMAIN} - send_message - call.data: {call.data}")
        message = call.data.get("message")
        _LOGGER.debug(f"{DOMAIN} - end_message - message: {message}")
        await coordinator.async_send_message(message)

    async def async_force_sync(call):
        coordinator: EufySecurityDataUpdateCoordinator = hass.data[DOMAIN]
        await coordinator.async_refresh()

    hass.services.async_register(DOMAIN, "force_sync", async_force_sync)
    hass.services.async_register(DOMAIN, "send_message", async_handle_send_message)
    return True

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})

    coordinator: EufySecurityDataUpdateCoordinator = EufySecurityDataUpdateCoordinator(hass, config_entry)

    await coordinator.initialize_ws()
    await coordinator.async_refresh()

    _LOGGER.debug(f"{DOMAIN} - coordinator initialized - {coordinator.data}")

    hass.data[DOMAIN] = coordinator
    for platform in PLATFORMS:
        coordinator.platforms.append(platform)
        hass.async_add_job(hass.config_entries.async_forward_entry_setup(config_entry, platform))

    async def update(event_time_utc):
        coordinator.async_set_updated_data(coordinator.data)

    coordinator.update_listener = async_track_time_interval(hass, update, timedelta(seconds=1))
    config_entry.add_update_listener(async_reload_entry)
    return True

async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    coordinator = hass.data[DOMAIN]
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(config_entry, platform)
                for platform in PLATFORMS
                if platform in coordinator.platforms
            ]
        )
    )
    coordinator.update_listener()
    if unloaded:
        hass.data[DOMAIN] = []

    return unloaded

async def async_reload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    await async_unload_entry(hass, config_entry)
    await async_setup_entry(hass, config_entry)
