# core/engines/autofarm/service.py
from __future__ import annotations
from typing import Callable, Optional, Dict, Any
import threading, time

from core.engines.autofarm.runner import run_autofarm


class AutoFarmService:
    """
    Долгоживущий цикл фарма.

    ВАЖНО:
    - Останавливаемся не из-за vitals==None, а из-за потери фокуса.
      Факторов три: enabled, focus, alive.
      * focus=False → пауза цикла (не запускаем и прерываем текущий прогон)
      * alive=False → тоже прерываем текущий прогон (чтобы «мертвые» не фармили)
      * enabled=False → сервис в режиме ожидания
    - В auto-режиме запускаем РОВНО один прогон по событию `_kick` (из пайплайна),
      если к моменту выполнения есть фокус и включено.
    """

    def __init__(
        self,
        server: Callable[[], str],
        controller: Any,
        get_window: Callable[[], Optional[Dict[str, Any]]],
        get_language: Callable[[], str],
        get_cfg: Callable[[], Dict[str, Any]],      # features.autofarm (или .config)
        is_enabled: Callable[[], bool],
        is_alive: Callable[[], bool] = lambda: True,
        has_focus: Callable[[], bool] = lambda: True,
        on_status: Optional[Callable[[str, Optional[bool]], None]] = None,
    ):
        self._server = server
        self._controller = controller
        self._get_window = get_window
        self._get_language = get_language
        self._get_cfg = get_cfg

        self._is_enabled = is_enabled
        self._is_alive = is_alive
        self._has_focus = has_focus

        self._on_status = on_status or (lambda *_: None)

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

    def cancel_cycle(self):
        """Прервать текущий прогон run_autofarm()."""
        self._cancel = True

    def run_once_now(self):
        """
        В auto: ставим триггер на ОДИН прогон;
        в manual: запускаем сразу, если есть фокус.
        """
        if (not self._is_enabled()) or (not self._has_focus()) or (not self._is_alive()):
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
            # Паузим сервис, если отключен/нет фокуса/мертвы
            if (not self._is_enabled()) or (not self._has_focus()) or (not self._is_alive()):
                time.sleep(self._poll)
                continue

            cfg = self._normalize_cfg(self._get_cfg() or {})
            mode = (cfg.get("mode") or "auto").lower()

            if mode == "manual":
                # manual крутится постоянно, но только при фокусе
                self._run_once()
                time.sleep(self._poll)
                continue

            # auto: ждём явного «пинка» из пайплайна
            fired = self._kick.wait(timeout=self._poll)
            if not fired:
                continue
            # на момент старта прогона перепроверим гейты
            if (not self._is_enabled()) or (not self._has_focus()) or (not self._is_alive()):
                # не сбрасываем событие — пусть сохранится до возврата фокуса
                continue

            self._kick.clear()
            self._run_once()

    def _run_once(self):
        self._cancel = False
        cfg = self._normalize_cfg(self._get_cfg() or {})
        ok = run_autofarm(
            server=self._server(),
            controller=self._controller,
            get_window=self._get_window,
            get_language=self._get_language,
            on_status=self._on_status,
            cfg=cfg,
            should_abort=lambda: (
                (not self._is_enabled())
                or (not self._has_focus())
                or (not self._is_alive())
                or self._cancel
            ),
        )
        self._on_status("Автофарм цикл завершён", bool(ok))

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
