"""strompris sensors."""

from __future__ import annotations

from collections.abc import MutableMapping
from datetime import datetime, timedelta
import logging
from typing import Any, List

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


def getSone(selected_price_zone: str) -> int:
    return PRICE_ZONES.index(selected_price_zone) + 1


def uidPrisSone(pris_sone: str) -> str:
    return f"{DOMAIN.lower()}_pris_sone_{pris_sone}"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Elvia Sensor."""
    entity_registry = async_get_entity_reg(hass)

    addable = []

    sone = hass.data[PRICE_ZONE]
    entities = [StromPrisSensor(pris_sone_nummer=getSone(sone), pris_sone=sone)]
    async_add_entities(entities, True)


""""
    for entity in entities:
        foundId = entity_registry.async_get_entity_id(
            "sensor", DOMAIN, entity.unique_id
        )
        if not foundId:
            addable.append(entity)
        else:
            print("Skipping", entity.unique_id)

    if len(addable) > 0:
        async_add_entities(addable, True)
"""


class StromSensor(SensorEntity):
    _pris_sone_nummer: int
    _pris_sone: str
    _attr_has_entity_name = True
    _attr_extra_state_attributes = {}

    strompris: Strompris

    def __init__(self, pris_sone_nummer: int, pris_sone: str) -> None:
        self._pris_sone_nummer = pris_sone_nummer
        self._pris_sone = pris_sone
        super().__init__()
        self.strompris = Strompris(
            source=SOURCE_HVAKOSTERSTROMMEN, zone=pris_sone_nummer
        )


class StromPrisSensor(StromSensor):
    """Representation of a generic Strompris Sensor."""

    _price_end: datetime | None = None

    def __init__(self, pris_sone_nummer: int, pris_sone: str) -> None:
        super().__init__(pris_sone_nummer, pris_sone)
        self._last_updated = None
        self._attr_native_unit_of_measurement = "NOK/kWh"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_unique_id = uidPrisSone(pris_sone=pris_sone)
        self._attr_name = f"Electricity price - {pris_sone}"
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

        current: Prising = await self.strompris.async_get_current_price()
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
    async def async_fetch_prices_for_tomorrow_with_throttle(self) -> list[Prising]:
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


"""
    async def settPrisingPaaSensor(self) -> None:
        data = await self.transformer_til_graf()
        statistics = []
        for pris in self._pris_i_dag:
            statistics.append(
                StatisticData(start=pris.start, state=pris.NOK_kwh, sum=pris.NOK_kwh)
            )

        statistic_id = f"sensor.{self._attr_unique_id}"  # f"{DOMAIN}:energy_{self._attr_unique_id}"

        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=f"{self._pris_sone} - Electricity price",
            source=DOMAIN,
            statistic_id=statistic_id,
            unit_of_measurement=self._attr_native_unit_of_measurement,
        )

        print(statistics)
        async_add_external_statistics(self.hass, metadata, statistics)
"""
