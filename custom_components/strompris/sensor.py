"""strompris sensors."""

from __future__ import annotations

from collections.abc import MutableMapping
from datetime import datetime, timedelta
import logging
from typing import Any, List, Optional

from strompris.common import getNorwayTime
from strompris.const import SOURCE_HVAKOSTERSTROMMEN
from strompris.schemas import *
from strompris.strompris import Strompris

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity import (
    DeviceInfo,
    EntityCategory,
    async_generate_entity_id,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get as async_get_entity_reg
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import Throttle, dt as dt_util

from custom_components.strompris.message_compose import ComposeMessage

from .const import DOMAIN, PRICE_ZONE, PRICE_ZONES

_LOGGER = logging.getLogger(__name__)

strompris: Strompris = None
zone_no: str = None

def getSone(selected_price_zone: str) -> int:
    return PRICE_ZONES.index(selected_price_zone) + 1


def uidPrisSone() -> str:
    return f"{DOMAIN.lower()}_pris_sone_{zone_no}"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Elvia Sensor."""
    entity_registry = async_get_entity_reg(hass)

    addable = []

    sone = hass.data[PRICE_ZONE]
    global zone_no
    zone_no = sone
    
    # Declaring global in order to make it re-usable
    global strompris
    strompris = Strompris(source=SOURCE_HVAKOSTERSTROMMEN, zone=getSone(sone))
    
    
    entities = [
        StromprisSensor(strompris),
        StromprisAlertSensor(strompris)
        ]
    async_add_entities(entities, True)    

class StromSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_extra_state_attributes = {}

    strompris: Strompris

    def __init__(self, strompris: Strompris) -> None:
        super().__init__()
        self.strompris = strompris
        self._last_updated = None
        


class StromprisSensor(StromSensor):
    """Representation of a generic Strompris Sensor."""

    _price_end: datetime | None = None

    def __init__(self, strompris: Strompris) -> None:
        super().__init__(strompris)
        self._attr_extra_state_attributes = {}
        self._last_updated = None
        self._attr_native_unit_of_measurement = "NOK/kWh"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_unique_id = uidPrisSone()
        self._attr_name = f"Electricity price - NO{strompris.priceSource._price_zone}"
        self._model = "Price Sensor"

    @property
    def icon(self) -> str:
        """Icon of the entity."""
        return "mdi:cash"

    async def async_update(self) -> None:
        today = await self.strompris.async_get_prices_for_today()
        if not today or len(today) == 0:
            _LOGGER.error(
                "Could not obtain electricity pricing for today. Setting sensor available state to False"
            )
            self._attr_available = False
            return

        current: Pris = await self.strompris.async_get_current_price()
        if not current:
            _LOGGER.error(
                "Could not obtain current electricity pricing. Setting sensor available state to False"
            )
            self._attr_available = False
            return
        self._attr_available = True
        self._attr_native_value = round(current.total, 3)
        self._last_updated = current.start

        self._attr_extra_state_attributes.update(
            await self.strompris.async_get_price_attrs()
        )

        if self._price_end is None:
            self._price_end = today[-1].start

        today_price_attrs = {
            "price_today": list(map(lambda value: round(value.total, 2), today)),
            "price_start": today[0].start.isoformat(),
            "price_end": self._price_end.isoformat(),
        }

        self._attr_extra_state_attributes.update(today_price_attrs)
        await self.async_fetch_prices_for_tomorrow_with_throttle()

    @Throttle(timedelta(minutes=5))
    async def async_fetch_prices_for_tomorrow_with_throttle(self) -> list[Pris]:
        tomorrow = await self.strompris.async_get_prices_for_tomorrow()
        if tomorrow is None or len(tomorrow) == 0:
            print("Fikk ingen priser for i morgen..")
            _LOGGER.info("Priser for i morgen er ikke tilgjengelig enda")
            price_attrs = {
                "price_tomorrow": [],
            }
            self._attr_extra_state_attributes.update(price_attrs)
            return []
        self._price_end = tomorrow[-1].start
        price_attrs = {
            "price_tomorrow": list(map(lambda value: round(value.total, 2), tomorrow)),
            "price_end": self._price_end.isoformat(),
        }
        self._attr_extra_state_attributes.update(price_attrs)
        return tomorrow


# class StromprisAverageToday(StromSensor):
#     """_summary_
#     """
#     
#     @property
#     def icon(self) -> str:
#         """Icon of the entity."""
#         return "mdi:cash"



class StromprisAlertSensor(StromSensor):
        
    TYPE_INCREASE = "INCREASE"
    TYPE_DECREASE = "DECREASE"
    
    _last_updated: Optional[datetime] = None
    
    def __init__(self, strompris: Strompris) -> None:
        super().__init__(strompris)
        self._attr_extra_state_attributes = {}
        self._last_updated = None
        self.__attr_friendly_name = "Electricity Price alert"
        self._attr_unique_id = f"{uidPrisSone()}_ALERT"
        self._attr_name = f"Electricity price - NO{strompris.priceSource._price_zone} ALERT"
        
    @property
    def icon(self) -> str:
        """Icon of the entity."""
        return "mdi:flash-alert"

    @Throttle(timedelta(minutes=5))
    async def async_update(self) -> None:
        """Update extreme price changes
        """
        
        if (self._last_updated != None and datetime.now() < (self._last_updated + timedelta(hours=1))):
            return
        
        tomorrow = await self.strompris.async_get_prices_for_tomorrow()
        if tomorrow is None or len(tomorrow) == 0:
            _LOGGER.warn("Electricity prices for tomorrow are not available yet")
            return
        
        grouped = self.strompris.get_price_level_grouped(self.strompris.get_prices_with_level(tomorrow))
                
        cm = ComposeMessage(grouped)
        messages = cm.compose()
         
        attr = {
            "friendly_name": "Electricity Price alert",
            "title": messages["title"],
            "message": messages["message"],
            "tts": messages["tts"]
        }
        self._attr_extra_state_attributes.update(attr)
        self._attr_available = True
        self._last_updated = datetime.now()
    
    