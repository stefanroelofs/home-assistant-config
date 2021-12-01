import logging

from decimal import Decimal

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
    PERCENTAGE,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_SIGNAL_STRENGTH,
)
from homeassistant.core import HomeAssistant

from .const import DOMAIN, Device
from. const import get_child_value
from .entity import EufySecurityEntity
from .coordinator import EufySecurityDataUpdateCoordinator

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_devices):
    coordinator: EufySecurityDataUpdateCoordinator = hass.data[DOMAIN]

    INSTRUMENTS = [
        ("battery", "Battery", "state.battery", PERCENTAGE, None, DEVICE_CLASS_BATTERY),
        ("wifiRSSI", "Wifi RSSI", "state.wifiRSSI", None, None, DEVICE_CLASS_SIGNAL_STRENGTH),
        ("detected_person_name", "Detected Person Name", "state.personName", None, None, None),
    ]

    CAMERA_INSTRUMENTS = [
        ("stream_source_type", "Streaming Source Type", "stream_source_type", None, None, None),
        ("stream_source_address", "Streaming Source Address", "stream_source_address", None, None, None),
        ("codec", "Codec", "codec", None, None, None),
    ]

    entities = []
    for device in coordinator.devices.values():
        instruments = INSTRUMENTS
        _LOGGER.debug(f"{DOMAIN} {device.name} - {device.serial_number} - {device.is_camera()}")
        if device.is_camera() == True:
            instruments = instruments + CAMERA_INSTRUMENTS
        for id, description, key, unit, icon, device_class in instruments:
            if not get_child_value(device.__dict__, key) is None:
                entities.append(EufySecuritySensor(coordinator, config_entry, device, id, description, key, unit, icon, device_class))

    async_add_devices(entities, True)


class EufySecuritySensor(EufySecurityEntity):
    def __init__(self, coordinator: EufySecurityDataUpdateCoordinator, config_entry: ConfigEntry, device: Device, id: str, description: str, key: str, unit: str, icon: str, device_class: str):
        super().__init__(coordinator, config_entry, device)
        self._id = id
        self.description = description
        self.key = key
        self.unit = unit
        self._icon = icon
        self._device_class = device_class

    @property
    def state(self):
        return get_child_value(self.device.__dict__, self.key)

    @property
    def unit_of_measurement(self):
        return self.unit

    @property
    def icon(self):
        return self._icon

    @property
    def device_class(self):
        return self._device_class

    @property
    def name(self):
        return f"{self.device.name} {self.description}"

    @property
    def id(self):
        return f"{DOMAIN}_{self.device.serial_number}_{self._id}_sensor"

    @property
    def unique_id(self):
        return self.id