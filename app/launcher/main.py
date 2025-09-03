# app/launcher/main.py
# минимум обязанностей: создать окно, собрать секции, экспортировать их методы.
from __future__ import annotations
import os, json, webview
from .wiring import build_container

def launch_gui(local_version: str):
    index = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "webui", "index.html"))
    if not os.path.exists(index):
        raise RuntimeError(f"UI not found: {index}")

    window = webview.create_window("Revive Launcher", url=index, width=820, height=900, resizable=False)
    c = build_container(window, local_version)            # все зависимости/сервисы/секции
    api_methods = {}
    for sec in c["sections"]:
        api_methods.update(sec.expose())                  # собрать публичные API

    # единоразовая регистрация
    window.expose(*api_methods.values())

    # опционально: on_close → c["shutdown"]()
    def _on_closing():
        try: c["shutdown"]()
        finally: os._exit(0)
    window.events.closing += _on_closing

    webview.start(debug=False, gui="edgechromium", http_server=True)
