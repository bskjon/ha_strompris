from typing import Any, List, Optional
from strompris.const import SOURCE_HVAKOSTERSTROMMEN
from strompris.schemas import *
from strompris.strompris import Strompris


class ComposeMessage():
    """Compose Electricity price message
    """
    TYPE_INCREASE: int = 0
    TYPE_DECREASE: int = -1
    
    floors: List[Pris] = []
    roofs: List[Pris] = []
    def __init__(self, floors: List[Pris], roofs: List[Pris]) -> None:
        self.floors = floors
        self.roofs = roofs
    
    
    def get_floor(self) -> Optional[List[Pris]]:
        prices = self.__group(self.floors)
        floor = next(filter(lambda inner: inner != None and min(inner, key=lambda p: p.kwh) , prices), None)
        if (len(prices) > 0):
            assert floor != None
        return floor
    
    def get_roof(self) -> Optional[List[Pris]]:
        prices = self.__group(self.roofs)
        roof = next(filter(lambda inner: inner != None and max(inner, key=lambda p: p.kwh) , prices), None)
        if (len(prices) > 0):
            assert roof != None
        return roof
        
    
    
    def compose(self, floor: List[Pris], roof: List[Pris]) -> dict[str, str]:
        #groups: List[PriceDef] = []       
        messages: List[str] = []
        tts: List[str] = []
        if (floor != None and roof != None):
            msg = "Strømprisen vil variere kraftig i morgen."
            messages.append(msg)
            tts.append(msg)
        elif (floor != None and roof == None):
            msg = "Strømprisen vil falle en del i morgen."
            messages.append(msg)
            tts.append(msg)
        elif (floor == None and roof != None):
            msg = "I morgen vil strømprisen stige en del."
            messages.append(msg)
            tts.append(msg)
        
        
        if (floor != None and roof != None):
            if (floor[-1].start < roof[-1].start):
                # Start med floor
                messages.append(self.__compose_message_price_change(floor, self.TYPE_DECREASE, False))
                tts.append(self.__compose_message_price_change(floor, self.TYPE_DECREASE, True))
                
                messages.append(self.__compose_message_price_change(roof, self.TYPE_INCREASE, False))
                tts.append(self.__compose_message_price_change(roof, self.TYPE_INCREASE, True))
            else:
                messages.append(self.__compose_message_price_change(roof, self.TYPE_INCREASE, False))
                tts.append(self.__compose_message_price_change(roof, self.TYPE_INCREASE, True))
                
                messages.append(self.__compose_message_price_change(floor, self.TYPE_DECREASE, False))
                tts.append(self.__compose_message_price_change(floor, self.TYPE_DECREASE, True))
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
    
    def __group(self, prices: List[Pris]) -> List[List[Pris]]:
        grouped: List[List[Pris]] = []
        if len(prices) == 0:
            return grouped
        group: List[Pris] = []
        for price in prices:
            prev = group[-1] if len(group) > 0 else None
            if (prev is None):
                group.append(price)
            else:
                if (prev.slutt == price.start):
                    group.append(price)
                else:
                    if (len(group) > 0):
                        grouped.append(group)
                    group = []
        if (len(group) > 0):
            grouped.append(group)
        return grouped
    
    def __ore_or_nok(self, pris: float, tts: bool = False) -> str:
        if (pris > 1.0):
            return "Øre"
        else:
            if (tts == True):
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
        
        if (len(prices) == 1):
            return f"Fra {time} {start.start.hour} til {time} {start.slutt.hour} vil prisen {current_direction} til {start.total} {self.__ore_or_nok(start.total, tts)}, før den {end_direction} igjen."
        else:
            slutt = prices[-1]
            return f"I perioden {time} {start.start.hour} til {time} {slutt.slutt.hour} vil prisen {current_direction} til {start.total} {self.__ore_or_nok(start.total, tts)}, for deretter å ende på {slutt.total} {self.__ore_or_nok(slutt.total, tts)} før den {end_direction} igjen."
                    
        