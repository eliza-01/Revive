# core/engines/autofarm/service.py
from __future__ import annotations
from typing import Callable, Optional, Dict, Any
import threading, time

from core.engines.autofarm.runner import run_autofarm
from core.logging import console


class AutoFarmService:
    """
    Долгоживущий цикл фарма.

    ВАЖНО (новая модель):
    - Гейты: enabled, paused, alive.
      * paused=True → сервис простаивает (не запускаем и прерываем текущий прогон)
      * alive=False → прерываем текущий прогон
      * enabled=False → сервис в режиме ожидания
    - В auto-режиме запускаем ровно один прогон по событию `_kick` (из пайплайна),
      если к моменту выполнения не стоит пауза, включено и персонаж жив.
    """

    def __init__(
        self,
        server: Callable[[], str],
        controller: Any,
        get_window: Callable[[], Optional[Dict[str, Any]]],
        get_language: Callable[[], str],
        get_cfg: Callable[[], Dict[str, Any]],
        is_enabled: Callable[[], bool],
        is_alive: Callable[[], Optional[bool]] = lambda: True,
        is_paused: Callable[[], bool] = lambda: False,   # ← новое
        *,
        set_busy: Optional[Callable[[bool], None]] = None,
    ):
        self._server = server
        self._controller = controller
        self._get_window = get_window
        self._get_language = get_language
        self._get_cfg = get_cfg

        self._is_enabled = is_enabled
        self._is_alive = is_alive
        self._is_paused = is_paused

        self._set_busy = set_busy or (lambda _b: None)

        self._thr: Optional[threading.Thread] = None
        self._run = False
        self._cancel = False
        self._kick = threading.Event()   # триггер для auto
        self._poll = 1.0

    # ---------- API ----------
    def is_running(self) -> bool:
        return bool(self._run)

    def start(self, poll_interval: float = 0.5):
        if self._run:
            return
        self._run = True
        self._cancel = False
        self._poll = float(max(0.1, poll_interval))
        self._thr = threading.Thread(target=self._loop, args=(self._poll,), daemon=True)
        self._thr.start()

    def stop(self):
        self._run = False
        try:
            self._set_busy(False)
        except Exception:
            pass

    def cancel_cycle(self):
        """Прервать текущий прогон run_autofarm()."""
        self._cancel = True

    def run_once_now(self):
        # не запускаем прогон, если гейты закрыты
        if (not self._is_enabled()) or self._is_paused() or (self._is_alive() is False):
            return

        cfg = self._normalize_cfg(self._get_cfg() or {})
        mode = (cfg.get("mode") or "auto").lower()
        if mode == "auto":
            self._kick.set()
        else:
            self._run_once()

    # ---------- worker ----------
    def _loop(self, poll_interval: float):
        while self._run:
            # простаиваем при паузе/отключении/смерти
            if (not self._is_enabled()) or self._is_paused() or (self._is_alive() is False):
                time.sleep(self._poll)
                continue

            cfg = self._normalize_cfg(self._get_cfg() or {})
            mode = (cfg.get("mode") or "auto").lower()

            if mode == "manual":
                # manual крутится постоянно, но только когда нет паузы
                self._run_once()
                time.sleep(self._poll)
                continue

            fired = self._kick.wait(timeout=self._poll)
            if not fired:
                continue

            # перепроверка перед стартом
            if (not self._is_enabled()) or self._is_paused() or (self._is_alive() is False):
                # событие не сбрасываем — сохранится до снятия паузы
                continue

            self._kick.clear()
            self._run_once()

    def _run_once(self):
        self._cancel = False
        self._set_busy(True)
        try:
            cfg = self._normalize_cfg(self._get_cfg() or {})
            ok = run_autofarm(
                server=self._server(),
                controller=self._controller,
                get_window=self._get_window,
                get_language=self._get_language,
                cfg=cfg,
                should_abort=lambda: (
                        (not self._is_enabled())
                        or self._is_paused()
                        or (self._is_alive() is False)
                        or self._cancel
                ),
            )

            # единый вывод статуса
            try:
                if ok:
                    console.hud("succ", "Автофарм: цикл завершён")
                else:
                    console.hud("err", "Автофарм: цикл завершён (ошибка)")
                console.log(f"[autofarm] cycle finished → {bool(ok)}")
            except Exception:
                pass

        finally:
            self._set_busy(False)

    # ---------- utils ----------
    @staticmethod
    def _normalize_cfg(raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Принимает либо весь узел features.autofarm, либо только features.autofarm.config.
        Сначала берём config как базу, затем поверх непустые верхнеуровневые поля.
        """
        base = dict(raw.get("config") or {})
        top = {k: raw.get(k) for k in ("profession", "skills", "zone", "monsters", "mode") if k in raw}
        cfg = dict(base)
        for k, v in top.items():
            if v not in (None, "", [], {}):
                cfg[k] = v

        cfg.setdefault("mode", "auto")
        cfg.setdefault("profession", "")
        cfg.setdefault("skills", [])
        cfg.setdefault("zone", "")
        cfg.setdefault("monsters", [])

        # лёгкая нормализация
        try:
            skills = []
            for s in cfg.get("skills") or []:
                skills.append({
                    "key": str((s or {}).get("key", "1"))[:1] or "1",
                    "slug": (s or {}).get("slug", "") or "",
                    "cast_ms": max(0, int(float((s or {}).get("cast_ms", 0)))),
                })
            cfg["skills"] = skills
        except Exception:
            cfg["skills"] = []

        return cfg
