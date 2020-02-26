"""
Sensor component to monitor waste collection by ACV.
Original Author:  Floris Kruisselbrink <floris+homeassistant@vloris.nl>
Modification by: Cadster <cadsters@hotmail.com>

This repo works in Ede, Renkum, Renswoude, Veenendaal and Wageningen
"""

import logging
from datetime import date, datetime, timedelta
from typing import NamedTuple

import homeassistant.helpers.config_validation as cv
import requests
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_DATE, CONF_RESOURCES
from homeassistant.helpers.entity import Entity

__version__ = '1.0.0'

_LOGGER = logging.getLogger(__name__)

ATTR_TRASHTYPE = 'trash_type'

CONF_POSTCODE = 'postcode'
CONF_HOUSENUMBER = 'housenumber'

SENSOR_TYPES = {
    'today': ['Vandaag', 'mdi:recycle'],
    'tomorrow': ['Morgen', 'mdi:recycle'],
    'grey': ['Rest', 'mdi:recycle'],
    'paper': ['Papier', 'mdi:recycle'],
    'green': ['GFT', 'mdi:recycle'],
    'packages': ['PMD', 'mdi:recycle'],
    'textile': ['Textiel', 'mdi:recycle']
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_RESOURCES, default=[]):
        vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
    vol.Required(CONF_POSTCODE, default='1111AA'): cv.string,
    vol.Required(CONF_HOUSENUMBER, '1'): cv.string,
})


def setup_platform(hass, config, add_entities, discovery_info=None):
    _LOGGER.debug("Setting up ACV API Reader...")

    postcode = config.get(CONF_POSTCODE)
    housenumber = config.get(CONF_HOUSENUMBER)
    reader = WasteApiReader(postcode, housenumber)

    entities = []

    for resource in config.get(CONF_RESOURCES):
        if resource == 'today':
            entities.append(TodayWasteSensor(reader))
        elif resource == 'tomorrow':
            entities.append(TomorrowWasteSensor(reader))
        else:
            entities.append(WasteTypeSensor(reader, resource))

    add_entities(entities)


##########################################
# WasteApiReader
##########################################


# Settings for ACV:
DEFAULT_BASEURL = 'https://wasteapi.ximmio.com/api/{}'
DEFAULT_COMPANYCODE = 'f8e2844a-095e-48f9-9f98-71fceb51d2c3'
DEFAULT_HEADERS = {
    'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36",
    'Referer': 'https://acv-afvalkalender.nl/'
}


class WasteApiException(Exception):
    pass


#class WasteSchedule(NamedTuple):
#    trash_type: str
#    pickup_date: date
#
#    def __repr__(self):
#        return "WasteSchedule({}: {})".format(self.pickup_date, self.trash_type)
WasteSchedule = NamedTuple('WasteSchedule', [('trash_type', str), ('pickup_date', date)])


class WasteApiReader:

    def __init__(self, postcode, housenumber):
        self.postcode = postcode
        self.housenumber = housenumber
        self._request_headers = DEFAULT_HEADERS
        self._companycode = DEFAULT_COMPANYCODE
        self._baseurl = DEFAULT_BASEURL

        self._schedules = []
        self._lastupdated = None

    def next_collection(self):
        return self._schedules[0] if self._schedules else None

    def next_collection_of(self, type):
        return next((s for s in self._schedules if s.trash_type == type), None)

    def collection_on(self, date):
        return next((s for s in self._schedules if s.pickup_date == date), None)

    def collection_today(self):
        today = datetime.now().date()
        return self.collection_on(today)

    def collection_tomorrow(self):
        tomorrow = datetime.now().date() + timedelta(days=1)
        return self.collection_on(tomorrow)

    def update(self):
        if self._lastupdated == datetime.now().date():
            return

        self._lastupdated = datetime.now().date()
        _LOGGER.debug("Updating waste collection dates using Rest API")

        try:
            address_id = self._find_unique_address_id()
            pickup_calendar = self._get_pickup_calendar(address_id)
            self._parse_calendar(pickup_calendar)
        except requests.exceptions.RequestException as x:
            self._schedules = []
            raise WasteApiException(
                "Error occurred while fetching data: %r", x)

    def _do_post_request(self, action, post_data):
        url = self._baseurl.format(action)
        data = {
            'companyCode': self._companycode
        }
        data.update(post_data)

        response = requests.post(
            url, headers=self._request_headers, data=data).json()
        # TODO: error checking, raise WasteApiException('blabla')
        return response

    def _find_unique_address_id(self):
        data = {
            'postCode': self.postcode,
            'houseNumber': self.housenumber
        }
        response = self._do_post_request('FetchAdress', data)
        return response['dataList'][0]['UniqueId']

    def _get_pickup_calendar(self, unique_address_id):
        start_date = datetime.now()
        end_date = start_date + timedelta(days=99)
        data = {
            'uniqueAddressId': unique_address_id,
            'startDate': start_date.strftime('%Y-%m-%d'),
            'endDate': end_date.strftime('%Y-%m-%d')
        }
        response = self._do_post_request('GetCalendar', data)
        return response

    def _parse_calendar(self, waste_calendar):
        schedules = []

        for pickup_type in waste_calendar['dataList']:
            for pickup_date in pickup_type['pickupDates']:
                trash_type = pickup_type['_pickupTypeText']
                trash_date = datetime.strptime(
                    pickup_date[0:10], '%Y-%m-%d').date()

                schedules.append(WasteSchedule(trash_type, trash_date))

        self._schedules = sorted(schedules, key=lambda s: s.pickup_date)
        _LOGGER.debug("Schedules found: %r", self._schedules)


##########################################
# WasteSensors
##########################################


class AbstractWasteSensor(Entity):

    def __init__(self, reader, sensor_type):
        self._reader = reader
        self._schedule = None
        self._name = "afval {}".format(SENSOR_TYPES[sensor_type][0])
        self._icon = SENSOR_TYPES[sensor_type][1]

    @property
    def name(self):
        return self._name

    @property
    def icon(self):
        return self._icon

    @property
    def state(self):
        if not self._schedule:
            return None

        return self._schedule.pickup_date.strftime('%Y-%m-%d')

    @property
    def device_state_attributes(self):
        if not self._schedule:
            return None

        return {
            ATTR_DATE: self._schedule.pickup_date.strftime('%Y-%m-%d'),
            ATTR_TRASHTYPE: self._schedule.trash_type
        }


class WasteTypeSensor(AbstractWasteSensor):

    def __init__(self, reader, trash_type):
        super().__init__(reader, trash_type)
        self._trash_type = trash_type.upper()

    def update(self):
        self._reader.update()
        self._schedule = self._reader.next_collection_of(self._trash_type)


class TodayWasteSensor(AbstractWasteSensor):

    def __init__(self, reader):
        super().__init__(reader, 'today')

    def update(self):
        self._reader.update()
        self._schedule = self._reader.collection_today()

    @property
    def state(self):
        if self._schedule is None:
            return 'Geen'

        return SENSOR_TYPES[self._schedule.trash_type.lower()][0]


class TomorrowWasteSensor(AbstractWasteSensor):

    def __init__(self, reader):
        super().__init__(reader, 'tomorrow')

    def update(self):
        self._reader.update()
        self._schedule = self._reader.collection_tomorrow()

    @property
    def state(self):
        if self._schedule is None:
            return 'Geen'

        return SENSOR_TYPES[self._schedule.trash_type.lower()][0]
