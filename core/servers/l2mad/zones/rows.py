from typing import Dict, Tuple, Union, List

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {
    "fullscreen": {"fullscreen": True},
    "center_block": {"centered": True, "width": 600, "height": 400},
    # добавляй зоны миникарты, компаса и т.п.
}

TEMPLATES: Dict[str, List[str]] = {

    # клади реальные PNG в templates/ со своей структурой

    # Interface
    "autofarm": ["interface", "autofarm.png"],

    #Varka_1
    "Varka_1_capt1": ["rows", "Goddard", "VarkaSilenosStronghold", "Varka_1", "1.png"],
    "Varka_1_capt2": ["rows", "Goddard", "VarkaSilenosStronghold", "Varka_1", "2.png"],
    "Varka_1_capt3": ["rows", "Goddard", "VarkaSilenosStronghold", "Varka_1", "3.png"],

    #Primeval_1
    "Primeval_1_capt1": ["rows", "Rune", "PrimevalIsle", "Primeval_1", "1.png"],
    "Primeval_1_capt2": [1"rows", "Rune", "PrimevalIsle", "Primeval_1", "2.png"],
    "Primeval_1_capt3": ["rows", "Rune", "PrimevalIsle", "Primeval_1", "3.png"],
}
