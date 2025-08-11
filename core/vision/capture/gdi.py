# core/vision/capture/gdi.py
def find_window(title: str):
    known = {"Lineage", "Lineage II", "L2MAD", "L2"}
    return 1 if title in known else 0

def get_window_info(hwnd, client: bool = True):
    if not hwnd:
        return {}
    return {"x": 100, "y": 100, "width": 1024, "height": 768}
