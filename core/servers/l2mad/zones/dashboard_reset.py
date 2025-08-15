from typing import Dict, Tuple, Union, List

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {
    "dashboard_body": {"fullscreen": True},
}

TEMPLATES: Dict[str, List[str]] = {
    "dashboard_init": ["dashboard", "dashboard_init.png"],
}
