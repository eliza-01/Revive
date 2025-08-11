# core/vision/matching/__init__.py
# Совместимый слой для старых импортов.
# Временно даёт заглушки find_in_zone/click_center, чтобы проект стартовал.
# Позже переведём вызовы на template_matcher.match_in_zone с server/lang.

from typing import Tuple, Optional

def find_in_zone(window: dict, zone, template_id, threshold: float = 0.87) -> Optional[Tuple[int, int]]:
    """
    Заглушка: верни None. Сигнатура сохранена для совместимости.
    TODO: заменить на вызов template_matcher.match_in_zone с server/lang и template_parts.
    """
    return None

def click_center(controller, point: Tuple[int, int]):
    """Клик по экранной точке через контроллер."""
    controller.send(f"click:{int(point[0])},{int(point[1])}")
