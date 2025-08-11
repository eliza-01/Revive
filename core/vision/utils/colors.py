# core/vision/utils/colors.py
import numpy as np
import cv2

def mask_for_colors_bgr(img_bgr, colors_rgb, tol=2):
    # img_bgr: HxWx3 (BGR), цвета заданы в RGB → переворачиваем
    masks = []
    for r, g, b in colors_rgb:
        lower = np.array([b - tol, g - tol, r - tol], dtype=np.int16)
        upper = np.array([b + tol, g + tol, r + tol], dtype=np.int16)
        lower = np.clip(lower, 0, 255).astype(np.uint8)
        upper = np.clip(upper, 0, 255).astype(np.uint8)
        mask = cv2.inRange(img_bgr, lower, upper)
        masks.append(mask)
    if not masks:
        return np.zeros(img_bgr.shape[:2], dtype=np.uint8)
    m = masks[0]
    for extra in masks[1:]:
        m = cv2.bitwise_or(m, extra)
    return m

def biggest_horizontal_band(mask):
    # Морфология и поиск самого широкого контура — прикидываем прямоугольник HP-полосы
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3))
    merged = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    # Выбираем по максимальной ширине
    rects = [cv2.boundingRect(c) for c in contours]
    rects.sort(key=lambda r: (r[2], -r[3]), reverse=True)  # ширина, потом «приплюснутость»
    return rects[0]  # (x, y, w, h)
