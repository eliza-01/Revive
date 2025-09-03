# tools/dump_target_zone.py
from pathlib import Path
import os, sys
import cv2

# --- make 'core' importable ---
ROOT = Path(__file__).resolve().parents[1]  # C:\Projects\Revive
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.vision.win32.gdi_backend import ensure_dpi_awareness, find_window, get_client_rect
from core.vision.capture.window_bgr_capture import capture_window_region_bgr

def target_zone_ltrb(win):
    w, h = int(win["width"]), int(win["height"])
    zw, zh = 400, 100
    l = max(0, (w - zw) // 2)
    t = max(0, 1)
    return (l, t, l + zw, t + zh)

def main():
    ensure_dpi_awareness()
    hwnd = find_window("Lineage")
    if not hwnd:
        print("[×] Окно не найдено (ищется по 'Lineage')."); sys.exit(1)
    ax, ay, ww, wh = get_client_rect(hwnd)
    win = {"x": ax, "y": ay, "width": ww, "height": wh}

    l, t, r, b = target_zone_ltrb(win)
    img = capture_window_region_bgr(win, (l, t, r, b))
    if img is None or img.size == 0:
        print("[×] Не удалось захватить зону."); sys.exit(2)

    out = ROOT / "target_zone.png"
    cv2.imwrite(str(out), img)
    print(f"[✓] Сохранено: {out}")
    try: os.startfile(out)
    except Exception: pass

if __name__ == "__main__":
    main()
