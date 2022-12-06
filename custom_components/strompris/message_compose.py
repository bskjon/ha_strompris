from typing import Any, List, Optional
from strompris.const import SOURCE_HVAKOSTERSTROMMEN
from strompris.schemas import *
from strompris.strompris import Strompris

class ComposeMessage():
    """Compose Electricity price message
    """
    TYPE_INCREASE: int = 0
    TYPE_DECREASE: int = -1
    
    groups: List[PriceGroups] = []
    
    def __init__(self, groups: List[PriceGroups]) -> None:
        self.groups = groups
    
    def __flatten(self) -> List[PriceLevel]:
        return [item for items in self.groups for item in items.prices]
        
    def __has_Expensive(self) -> bool:
        return any(g.group == LEVEL__EXPENSIVE for g in self.groups)
    
    def __has_Cheap(self) -> bool:
        return any(g.group == LEVEL__CHEAP for g in self.groups)
    
    
    def get_peak(self) -> PriceLevel:
        return max(self.__flatten(), key=lambda p: p.total)
    
    def get_bottom(self) -> PriceLevel:
        return min(self.__flatten(), key=lambda p: p.total)
        
    
    def compose(self) -> dict[str, str]:
        #groups: List[PriceDef] = []   
        title: str = None    
        messages: List[str] = []
        tts: List[str] = []
        if (self.__has_Cheap() and self.__has_Expensive()):
            title = "Varierende strømpris i morgen"
            tts.append(f"{title}.")
        elif (self.__has_Cheap() and self.__has_Expensive() == False):
            title = "Fallende strømpris i morgen"
            tts.append(f"{title}.")
        elif (self.__has_Cheap() == False and self.__has_Expensive()):
            title = "Økende strømpris i morgen"
            tts.append(f"{title}.")
        
        for group in self.groups:
            prices = group.prices
            if (group.group == LEVEL__CHEAP):
                messages.append(self.__compose_message_price_change(prices, self.TYPE_DECREASE, False))
                tts.append(self.__compose_message_price_change(prices, self.TYPE_DECREASE, True))
            elif (group.group == LEVEL__EXPENSIVE):
                messages.append(self.__compose_message_price_change(prices, self.TYPE_INCREASE, False))
                tts.append(self.__compose_message_price_change(prices, self.TYPE_INCREASE, True))
                    
        messages.append(self.__compose_message_max_price(False))
        tts.append(self.__compose_message_max_price(True))
        # Join arrays and assign to attr
        message_str = ' '.join(messages)
        tts_str = ' '.join(tts)
        return {
            "title": title,
            "message": message_str,
            "tts": tts_str
        }
    
    def __prisTekst(self, pris: float, tts: bool = False) -> str:
        if (pris < 1.0):
            return f"{pris*100} Øre"
        else:
            pris = round(pris, 3)
            if (tts == True):
                return f"{pris} Kroner"
            else:
                return f"{pris} Kr"
    
    
            
    def __compose_message_price_change(self, prices: List[Pris], type: TYPE_INCREASE | TYPE_DECREASE, tts: bool = False):
        start = prices[0]
        
        time = "Kl."
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
            return f"Fra {time} {start.start.hour} til {time} {start.slutt.hour} vil prisen {current_direction} til {self.__prisTekst(start.total, tts)}, før den {end_direction} igjen."
        else:
            slutt = prices[-1]
            return f"I perioden {start.start.hour} til {slutt.slutt.hour} vil prisen {current_direction} til {self.__prisTekst(start.total, tts)}, for deretter å ende på {self.__prisTekst(slutt.total, tts)} før den {end_direction} igjen."
                    
    def __compose_message_max_price(self, tts: bool = False):
        time = "Kl"
        if (tts):
            time = "Klokken"
        maxPrice = self.get_peak()
        
        return f"Dyreste time er {time} {maxPrice.start.hour} på {self.__prisTekst(maxPrice.total, tts)}."