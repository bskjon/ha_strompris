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

from .const import DOMAIN, PRICE_ZONE, PRICE_ZONES

_LOGGER = logging.getLogger(__name__)

strompris: Strompris = None

def getSone(selected_price_zone: str) -> int:
    return PRICE_ZONES.index(selected_price_zone) + 1


def uidPrisSone(pris_sone: str) -> str:
    return f"{DOMAIN.lower()}_pris_sone_no{pris_sone}"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Elvia Sensor."""
    entity_registry = async_get_entity_reg(hass)

    addable = []

    sone = hass.data[PRICE_ZONE]
    
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
        self._last_updated = None
        self._attr_native_unit_of_measurement = "NOK/kWh"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_unique_id = uidPrisSone(pris_sone=strompris.priceSource._price_zone)
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
            await self.strompris.async_get_current_price_attrs()
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
    
    def __init__(self, strompris: Strompris) -> None:
        super().__init__(strompris)
        self.__attr_friendly_name = "Electricity Price alert"
        self._attr_unique_id = f"{uidPrisSone(pris_sone=strompris.priceSource._price_zone)}_ALERT"
        self._attr_name = f"Electricity price - NO{strompris.priceSource._price_zone} ALERT"
        
    @property
    def icon(self) -> str:
        """Icon of the entity."""
        return "mdi:flash-alert"

    @Throttle(timedelta(minutes=15))
    async def async_update(self) -> None:
        """Update extreme price changes
        """
        tomorrow = await self.strompris.async_get_prices_for_tomorrow()
        if tomorrow is None or len(tomorrow) == 0:
            return
        floor = await self.strompris.async_get_extreme_price_reductions(tomorrow)
        roof = await self.strompris.async_get_extreme_price_increases(tomorrow)
        
        floors = self.__group(floor)
        roofs = self.__group(roof)
        
        msgAttr = self.__compose_message(floors=floors, roofs=roofs)        
        attr = {
            "friendly_name": "Electricity Price alert",
            "message": msgAttr["message"],
            "tts": msgAttr["tts"]
        }
        self._attr_extra_state_attributes.update(attr)
    
    def __group(self, prices: List[Pris]) -> List[List[Pris]]:
        grouped: List[List[Pris]] = []
        
        group: List[Pris] = []
        for price in prices:
            prev = group[-1]
            if (prev is None):
                group.append(prev)
            else:
                if (prev.slutt == price.start):
                    group.append(price)
                else:
                    if (len(group) > 0):
                        grouped.append(group)
                    group = []
        return grouped
        
    def __compose_message(self, floors: List[List[Pris]], roofs: List[List[Pris]]) -> dict[str, str]:
        #groups: List[PriceDef] = []       
        messages: List[str] = []
        tts: List[str] = []
        if (len(floors) > 0 and len(roofs) > 0):
            messages.append("Strømprisen for i morgen vil variere kraftig.")
            tts.append("Strømprisen for i morgen vil variere kraftig.")
        elif (len(floors) > 0 and len(roofs) == 0):
            messages.append("Strømprisen for i morgen vil falle en del.")
            tts.append("Strømprisen for i morgen vil falle en del.")
        elif (len(floors) == 0 and len(roofs) > 0):
            messages.append("Strømprisen for i morgen vil stige en del.")
            tts.append("Strømprisen for i morgen vil stige en del.")
        
        floor: Optional[List[Pris]] = None
        if (len(floors) > 0):
            floor = next(filter(lambda inner: inner != None and min(inner, key=lambda p: p.kwh) , floors))
        roof: Optional[List[Pris]] = None
        if (len(roofs) > 0):
            roof = next(filter(lambda inner: inner != None and max(inner, key=lambda p: p.kwh) , roofs))
        
        if (floor != None and roof != None):
            if (floor[-1].start < roof[-1].start):
                # Start med floor
                messages.append(self.__compose_message_price_change(floor, self.TYPE_DECREASE, False))
                tts.append(self.__compose_message_price_change(floor, self.TYPE_DECREASE, True))
            else:
                messages.append(self.__compose_message_price_change(roof, self.TYPE_INCREASE, False))
                tts.append(self.__compose_message_price_change(roof, self.TYPE_INCREASE, True))
        elif (floor != None):
            messages.append(self.__compose_message_price_change(floor, self.TYPE_DECREASE, False))
            tts.append(self.__compose_message_price_change(floor, self.TYPE_DECREASE, True))
        elif (roof != None):
            messages.append(self.__compose_message_price_change(roof, self.TYPE_INCREASE, False))
            tts.append(self.__compose_message_price_change(roof, self.TYPE_INCREASE, True))
            
        # Join arrays and assign to attr
        message_str = ' '.join(messages)
        tts_str = ' '.join(tts)
        return {
            "message": message_str,
            "tts": tts_str
        }
            
    
    def __ore_or_nok(self, pris: float, tts: bool = False) -> str:
        if (pris < 1.0):
            return "Øre"
        else:
            if (tts == False):
                return "Kroner"
            else:
                return "Kr"
        
    def __compose_message_price_change(self, prices: List[Pris], type: TYPE_INCREASE | TYPE_DECREASE, tts: bool = False):
        start = prices[0]
        
        time = "Kl"
        if (tts):
            time = "Klokken"
        
        current_direction: str
        end_direction: str
        if (type == self.TYPE_DECREASE):
            current_direction = "falle"
            end_direction = "øker"
        else:
            current_direction = "øke"
            end_direction = "faller"
        
        if (len(Pris) == 1):
            return f"Fra {time} {start.start.hour} til {time} {start.slutt.hour} vil prisen {current_direction} til {start.total} {self.__ore_or_nok(start.total, tts)}, før den {end_direction} igjen."
        else:
            slutt = prices[-1]
            return f"I perioden Kl {start.start.hour} til Kl {slutt.slutt.hour} vil prisen falle til {start.total} {self.__ore_or_nok(start.total, tts)}, for deretter å ende på {slutt.total} {self.__ore_or_nok(slutt.total, tts)} før den øker igjen."
                    
        