# core/vision/matching.py
from typing import Tuple, Optional

def find_in_zone(window: dict, zone: Tuple[int, int, int, int], template_id: str, threshold: float = 0.85) -> Optional[Tuple[int, int]]:
    return None

def click_center(controller, point: Tuple[int, int]):
    controller.send(f"click:{point[0]},{point[1]}")

def find_dynamic_in_zone(window: dict, zone, category_id: str, location_id: str, kind: str) -> Optional[Tuple[int, int]]:
    """
    kind: 'teleport_category' | 'teleport_location' | 'gk_category' | 'gk_location' | 'buffer_icon' ...
    Верни центр подходящего элемента.
    """
    return None
