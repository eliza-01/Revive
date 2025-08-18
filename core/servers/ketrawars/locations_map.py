# core/servers/ketrawars/locations_map.py
def get_categories():
    return [
        {"id": "catacombs", "display_rus": "Катакомбы2", "display_eng": "Catacombs"},
        {"id": "necropolis", "display_rus": "Некрополь2", "display_eng": "Necropolis"},
    ]

def get_locations(category_id: str):
    if category_id == "catacombs":
        return [
            {"id": "dark_omen", "display_rus": "Тёмное предзнаменование2", "display_eng": "Dark Omen"},
            {"id": "apostate", "display_rus": "Отступник2", "display_eng": "Apostate"},
        ]
    if category_id == "necropolis":
        return [
            {"id": "martyrdom", "display_rus": "Мученичество2", "display_eng": "Martyrdom"},
            {"id": "sacrifice", "display_rus": "Жертвоприношение2", "display_eng": "Sacrifice"},
        ]
    return []
