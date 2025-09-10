# app/api/image_access.py

from pathlib import Path
import base64
import mimetypes

class ImageAccess:
    def get_image_uri(self, path: str) -> dict:
        """
        Принимает относительный или абсолютный путь (можно с префиксом file://),
        возвращает {"ok": True, "uri": "data:<mime>;base64,<...>"} или {"ok": False, "error": "..."}.
        """
        try:
            if not path:
                return {"ok": False, "error": "empty_path"}

            # Убираем префикс file:// если есть
            if path.startswith("file://"):
                path = path[7:]

            p = Path(path)
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()

            if not p.exists():
                return {"ok": False, "error": "not_found"}

            data = base64.b64encode(p.read_bytes()).decode("ascii")
            mime, _ = mimetypes.guess_type(str(p))
            if not mime:
                # По умолчанию
                mime = "image/png"

            return {"ok": True, "uri": f"data:{mime};base64,{data}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
