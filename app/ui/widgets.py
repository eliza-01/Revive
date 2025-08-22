# app/ui/widgets.py
import tkinter as tk
import tkinter.ttk as ttk


class Collapsible(tk.Frame):
    def __init__(self, parent, title: str, opened: bool = True):
        super().__init__(parent)
        self._open = tk.BooleanVar(value=opened)
        self._btn = ttk.Button(self, text=("▼ " + title if opened else "► " + title), command=self._toggle)
        self._btn.pack(fill="x", pady=(6, 2))
        self._body = tk.Frame(self)
        if opened:
            self._body.pack(fill="x")

    def _toggle(self):
        if self._open.get():
            self._open.set(False)
            self._btn.config(text="► " + self._btn.cget("text")[2:])
            self._body.forget()
        else:
            self._open.set(True)
            self._btn.config(text="▼ " + self._btn.cget("text")[2:])
            self._body.pack(fill="x")

    def body(self) -> tk.Frame:
        return self._body


class VScrollFrame(tk.Frame):
    """
    Вертикально прокручиваемый контейнер. Внутреннюю область берите как .interior
    """
    def __init__(self, parent):
        super().__init__(parent)
        self._canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self._vsb = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vsb.set)

        self._vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self.interior = tk.Frame(self._canvas)
        self._win_id = self._canvas.create_window((0, 0), window=self.interior, anchor="nw")

        def _on_interior_configure(_evt=None):
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
            try:
                self._canvas.itemconfigure(self._win_id, width=self._canvas.winfo_width())
            except Exception:
                pass

        def _on_canvas_configure(evt):
            try:
                self._canvas.itemconfigure(self._win_id, width=evt.width)
            except Exception:
                pass

        self.interior.bind("<Configure>", _on_interior_configure)
        self._canvas.bind("<Configure>", _on_canvas_configure)

        # колёсико
        def _on_mousewheel(event):
            delta = 0
            if hasattr(event, "delta") and event.delta:
                delta = int(-event.delta / 120)
            elif getattr(event, "num", None) == 4:
                delta = -1
            elif getattr(event, "num", None) == 5:
                delta = 1
            if delta:
                self._canvas.yview_scroll(delta, "units")

        self._canvas.bind_all("<MouseWheel>", _on_mousewheel)  # Windows/macOS
        self._canvas.bind_all("<Button-4>", _on_mousewheel)    # X11
        self._canvas.bind_all("<Button-5>", _on_mousewheel)
