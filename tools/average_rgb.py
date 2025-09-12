# extract_neutral_rgb.py
# -*- coding: utf-8 -*-
"""
Извлекает пул из 6 RGB-цветов из изображения
core/engines/autofarm/server/boh/templates/common/interface/target_gray_dot.png
и печатает их в формате Python-литерала для вставки в код:

NEUTRAL_RGB = [(r,g,b), ...]

Требования:
- cv2 (OpenCV) и numpy
- Цвета в результате НЕ должны быть слишком близки друг к другу.

Запуск:
    python extract_neutral_rgb.py
    # или с аргументами:
    python extract_neutral_rgb.py <path_to_png> <min_dist> <kmeans_k> <sample_n>

Где:
- path_to_png  — путь к PNG (по умолчанию указан внутри скрипта)
- min_dist     — минимальная евклидова дистанция между центрами (по умолчанию 14)
- kmeans_k     — число кластеров для k-means (по умолчанию 12)
- sample_n     — сколько пикселей семплировать максимум (по умолчанию 50000)
"""
import sys
import os
from typing import List, Tuple
import numpy as np
import cv2

DEFAULT_PATH = os.path.join(
    "core", "engines", "autofarm", "server", "boh",
    "templates", "common", "interface", "target_gray_dot.png"
)

def _euclid(a: np.ndarray, b: np.ndarray) -> float:
    # a,b — np.array shape (3,) в RGB
    return float(np.linalg.norm(a.astype(np.float32) - b.astype(np.float32)))

def _greedy_distinct(colors: np.ndarray, weights: np.ndarray, want: int, min_dist: float) -> List[Tuple[int,int,int]]:
    """
    colors: (K,3) RGB float/ints
    weights: (K,) — сколько пикселей в каждом кластере
    Жадно набираем центры, гарантируя расстояние >= min_dist.
    Если отобрали меньше, чем нужно — дозаполняем наибольшими по "удалённости к ближайшему выбранному".
    """
    # Отсортируем по убыванию веса (самые значимые — первыми)
    order = np.argsort(-weights)
    centers = colors[order].astype(np.float32)
    ws = weights[order].astype(np.int64)

    selected: List[np.ndarray] = []
    for c in centers:
        if len(selected) == 0:
            selected.append(c)
            if len(selected) >= want:
                break
            continue
        if all(_euclid(c, s) >= min_dist for s in selected):
            selected.append(c)
            if len(selected) >= want:
                break

    if len(selected) >= want:
        pass
    else:
        # Дозаполнение: берём точки, у которых расстояние до ближайшей выбранной максимально велико
        remaining = [c for c in centers if not any(np.allclose(c, s) for s in selected)]
        while len(selected) < want and remaining:
            # расстояние до ближайшего выбранного центра
            dists = []
            for c in remaining:
                if selected:
                    dmin = min(_euclid(c, s) for s in selected)
                else:
                    dmin = float("inf")
                dists.append(dmin)
            # выбираем с максимальным dmin
            idx = int(np.argmax(dists))
            best = remaining.pop(idx)
            # Если всё равно слишком близко — увеличим порог только для дозаполнения?
            # Нет: добавляем как есть, чтобы получить 6 штук при бедной палитре.
            selected.append(best)

    # Преобразуем в int RGB и вернём
    out = [(int(round(c[0])), int(round(c[1])), int(round(c[2]))) for c in selected[:want]]
    return out

def extract_palette(
    path: str = DEFAULT_PATH,
    want: int = 6,
    min_dist: float = 14.0,
    kmeans_k: int = 12,
    sample_n: int = 50_000,
) -> List[Tuple[int,int,int]]:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"PNG not found: {path}")

    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)  # BGR[A]
    if img is None or img.size == 0:
        raise RuntimeError("Failed to load image or image is empty")

    # Отделим альфу (если есть) и возьмём только непрозрачные пиксели
    if img.shape[2] == 4:
        bgr = img[:, :, :3]
        alpha = img[:, :, 3]
        mask = alpha >= 16   # считаем заметным при альфе >= 16
        if not np.any(mask):
            raise RuntimeError("No visible pixels (alpha mask empty)")
        bgr = bgr[mask]
    else:
        bgr = img.reshape(-1, 3)

    # Переведём в RGB
    rgb = bgr[:, ::-1].astype(np.float32)

    # Выкинуть явные дубликаты и семплировать
    if rgb.shape[0] > sample_n:
        # случайный семпл чтобы упростить k-means
        idx = np.random.choice(rgb.shape[0], size=sample_n, replace=False)
        data = rgb[idx]
    else:
        data = rgb

    # Если очень мало уникальных цветов — вернём их как есть
    uniq = np.unique(data.astype(np.uint8), axis=0)
    if uniq.shape[0] <= want:
        # Убедимся, что они не слишком близки — иначе «раздуем» по одному пикселю
        uniq_list = uniq.astype(int).tolist()
        # Дополнение копиями (нежелательно, но предотвращает пустой результат)
        while len(uniq_list) < want:
            uniq_list.append(tuple(uniq_list[-1]))
        return [tuple(map(int, c)) for c in uniq_list[:want]]

    # K-means: K берем чуть больше want, чтобы потом отфильтровать близкие центры
    K = max(want + 4, int(kmeans_k))
    Z = data.reshape((-1, 3)).astype(np.float32)
    # критерий: до 20 итераций или eps
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    # запуск kmeans (1 попытка, можно повысить attempts при желании)
    compactness, labels, centers = cv2.kmeans(
        Z, K, None, criteria, attempts=3, flags=cv2.KMEANS_PP_CENTERS
    )
    centers = centers.astype(np.float32)  # RGB
    # посчитаем веса кластеров
    hist = np.bincount(labels.flatten(), minlength=K).astype(np.int64)

    # Жадно выберем 6 центров с ограничением на минимальную дистанцию
    picked = _greedy_distinct(centers, hist, want=want, min_dist=min_dist)

    return picked

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    try:
        min_dist = float(sys.argv[2]) if len(sys.argv) > 2 else 14.0
    except Exception:
        min_dist = 14.0
    try:
        kmeans_k = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    except Exception:
        kmeans_k = 12
    try:
        sample_n = int(sys.argv[4]) if len(sys.argv) > 4 else 50_000
    except Exception:
        sample_n = 50_000

    colors = extract_palette(
        path=path, want=6, min_dist=min_dist, kmeans_k=kmeans_k, sample_n=sample_n
    )

    # Выводим как Python-литерал для вставки:
    # (ВАЖНО: это RGB-значения — совместимы с mask_for_colors_bgr(colors_rgb=...))
    print("NEUTRAL_RGB = [")
    for (r, g, b) in colors:
        print(f"    ({r},{g},{b}),")
    print("]")

    # Также короткая строка в одну линию:
    flat = ", ".join(f"({r},{g},{b})" for (r,g,b) in colors)
    print("\n# one-liner:")
    print(f"NEUTRAL_RGB = [{flat}]")

if __name__ == "__main__":
    main()
