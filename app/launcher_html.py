#app/launcher_html.py
from __future__ import annotations
import os
import webview
from core.connection import ReviveController

class Bridge:
    def __init__(self, version: str):
        self.version = version
        self.controller = ReviveController()

    def app_version(self):
        return {"version": self.version}

    def ping_arduino(self):
        try:
            self.controller.send("ping")
            r = self.controller.read()
            return {"ok": r == "pong", "resp": r}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def quit(self):
        try:
            self.controller.close()
        except Exception:
            pass
        os._exit(0)

def launch_gui_html(local_version: str):
    base = os.path.join(os.path.dirname(__file__), "webui")
    html_path = os.path.join(base, "index.html")
    if not os.path.isfile(html_path):
        raise FileNotFoundError(f"UI not found: {html_path}")

    api = Bridge(local_version)
    window = webview.create_window(
        title=f"Revive · {local_version}",
        url=f"file://{html_path}",
        width=620, height=700, resizable=False
    )
    webview.start(gui="edgechromium", debug=False, js_api=api)
