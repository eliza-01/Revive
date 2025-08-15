from typing import List, Dict, Tuple

# Сопоставление локации списку путей
# Ключ: (village_id, location_id)
ROWS_MAP: Dict[Tuple[str, str], List[Dict]] = {
    ("Goddard", "VarkaSilenosStronghold"): [
        {"id": "Varka1", "title_rus": "Безопасный маршрут 1", "title_eng": "Varka1"},
        # {"id": "fast_route", "title_rus": "Быстрый маршрут", "title_eng": "Fast route"},
    ],
}

def list_rows(village_id: str, location_id: str) -> List[Dict]:
    return ROWS_MAP.get((village_id, location_id), [])
