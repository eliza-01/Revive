# core/vision/colors.py
# Заглушечные утилиты работы с цветом в зоне.
# В реальном проекте сюда подключишь захват кадра окна и подсчёт доли пикселей заданного цвета.
from typing import Tuple, List, Dict, Optional

RGB = Tuple[int, int, int]
Zone = Tuple[int, int, int, int]  # left, top, right, bottom (client coords)

def sample_ratio_in_zone(window: Dict, zone: Zone, color_ranges: List[Tuple[RGB, RGB]]) -> float:
    """
    Возвращает оценку доли пикселей, попадающих в один из color_ranges.
    0.0..1.0. Сейчас — заглушка: 1.0 (как будто HP полная).
    window: {"x","y","width","height"}
    zone: относительная зона в координатах client-области.
    color_ranges: список диапазонов цветов [(low_rgb, high_rgb), ...]
    """
    # TODO: заменить на реальную выборку пикселей из client-области окна
    return 1.0

def in_range(c: RGB, low: RGB, high: RGB) -> bool:
    return all(low[i] <= c[i] <= high[i] for i in range(3))
