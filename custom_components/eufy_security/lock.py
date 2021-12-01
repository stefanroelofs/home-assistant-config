import logging
from homeassistant.components.lock import LockEntity

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, Device
from .entity import EufySecurityEntity
from .coordinator import EufySecurityDataUpdateCoordinator


_LOGGER: logging.Logger = logging.getLogger(__package__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_devices):
    coordinator: EufySecurityDataUpdateCoordinator = hass.data[DOMAIN]
    for device in coordinator.devices.values():
        if device.is_lock() == True:
            async_add_devices([Lock(coordinator, config_entry, device)], True)

class Lock(EufySecurityEntity, LockEntity):
    def __init__(self, coordinator: EufySecurityDataUpdateCoordinator, config_entry: ConfigEntry, device: Device):
        EufySecurityEntity.__init__(self, coordinator, config_entry, device)
        LockEntity.__init__(self)

    @property
    def name(self):
        return f"{self.device.name}"

    @property
    def id(self):
        return f"{DOMAIN}_{self.device.serial_number}_lock"

    @property
    def unique_id(self):
        return self.id

    @property
    def is_locked(self):
        return self.device.state.get("lockStatus")

    async def async_lock(self):
        await self.coordinator.async_set_lock(self.device.serial_number, True)

    async def async_unlock(self):
        await self.coordinator.async_set_lock(self.device.serial_number, False)