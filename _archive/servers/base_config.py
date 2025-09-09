# _archive/servers/base_config.py
import importlib

def load_feature_config(server: str, feature: str):
    """
    feature: 'respawn' | 'buffer' | 'tp'
    returns dict: {"ZONES":..., "TEMPLATES":..., "SEQUENCE":...} or empty
    """
    module_name = f"core.servers.{server}.zones.{feature}"
    try:
        mod = importlib.import_module(module_name)
        return {
            "ZONES": getattr(mod, "ZONES"),
            "TEMPLATES": getattr(mod, "TEMPLATES"),
            "SEQUENCE": getattr(mod, "SEQUENCE"),
        }
    except Exception as e:
        print(f"[config] missing {module_name}: {e}")
        return {"ZONES": {}, "TEMPLATES": {}, "SEQUENCE": []}
