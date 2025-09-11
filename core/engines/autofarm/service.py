# core/engines/autofarm/service.py
from __future__ import annotations
from typing import Callable, Optional, Dict, Any
import threading, time

from core.engines.autofarm.runner import run_autofarm

class AutoFarmService:
    """
    Долгоживущий цикл фарма.
    API: start(), stop(), is_running(), cancel_cycle(), run_once_now()
    """

    def __init__(
        self,
        server: Callable[[], str],
        controller: Any,
        get_window: Callable[[], Optional[Dict[str, Any]]],
        get_language: Callable[[], str],
        get_cfg: Callable[[], Dict[str, Any]],        # features.autofarm или features.autofarm.config
        is_enabled: Callable[[], bool],               # features.autofarm.enabled
        is_alive: Callable[[], bool] = lambda: True,  # player.alive
        on_status: Optional[Callable[[str, Optional[bool]], None]] = None,
    ):
        self._server = server
        self._controller = controller
        self._get_window = get_window
        self._get_language = get_language
        self._get_cfg = get_cfg
        self._is_enabled = is_enabled
        self._is_alive = is_alive
        self._on_status = on_status or (lambda *_: None)

        self._thr: Optional[threading.Thread] = None
        self._run = False
        self._cancel = False
        self._kick = threading.Event()   # ← триггер для auto-режима
        self._poll = 1.0
        self._last_sig = None          # отпечаток конфигурации для режима manual

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
        """Прервать текущий заход run_autofarm."""
        self._cancel = True

    def run_once_now(self):
        """В auto: просто даём пинок сервису; в manual: запускаем цикл немедленно."""
        if not self._is_enabled() or not self._is_alive():
            return
        cfg = self._normalize_cfg(self._get_cfg() or {})
        mode = (cfg.get("mode") or "auto").lower()
        if mode == "auto":
            self._kick.set()        # ← сервис сам выполнит ОДИН цикл
        else:
            self._run_once()        # ← manual: запускаем сразу

    def _loop(self, poll_interval: float):
        while self._run:
            if not self._is_enabled() or not self._is_alive():
                time.sleep(self._poll); continue

            cfg  = self._normalize_cfg(self._get_cfg() or {})
            mode = (cfg.get("mode") or "auto").lower()

            if mode == "manual":
                # крутится постоянно, пока включён
                self._run_once()
                time.sleep(self._poll)
                continue

            # mode == "auto": ждём явного пинка от пайплайна
            fired = self._kick.wait(timeout=self._poll)
            if not fired:
                continue
            self._kick.clear()
            if self._is_enabled() and self._is_alive():
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
            # стопаем цикл немедленно, если сервис выключен, игрок мёртв или пришёл cancel
            should_abort=lambda: (not self._is_enabled()) or (not self._is_alive()) or self._cancel,
        )
        self._on_status("Автофарм цикл завершён", ok)

    def _cfg_signature(self, cfg: Dict[str, Any]) -> tuple:
        try:
            mode = (cfg.get("mode") or "auto")
            zone = (cfg.get("zone") or "")
            skills = tuple(
                (str((s or {}).get("key", "1"))[:1],
                 (s or {}).get("slug", "") or "",
                 int(float((s or {}).get("cast_ms", 0))))
                for s in (cfg.get("skills") or [])
            )
            monsters = tuple(sorted(cfg.get("monsters") or []))
            return (mode, zone, skills, monsters)
        except Exception:
            return ("auto", "", (), ())

    def _wait_until_changed_or_disabled(self, baseline_sig: tuple):
        # ждём, пока настройки/режим изменятся ИЛИ сервис выключат/умрёт игрок
        while self._run and self._is_enabled() and self._is_alive():
            try:
                cur = self._normalize_cfg(self._get_cfg() or {})
                if self._cfg_signature(cur) != baseline_sig:
                    break
            except Exception:
                pass
            time.sleep(self._poll)

    @staticmethod
    def _normalize_cfg(raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Принимает либо весь узел features.autofarm, либо только features.autofarm.config.
        Сначала берём config как базу, потом ПЕРЕЗАТИРАЕМ непустыми верхнеуровневыми полями.
        """
        base = dict(raw.get("config") or {})
        top = {k: raw.get(k) for k in ("profession", "skills", "zone", "monsters", "mode") if k in raw}

        cfg = dict(base)
        for k, v in top.items():
            if v not in (None, "", [], {}):
                cfg[k] = v

        # дефолты
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
                    "cast_ms": max(0, int(float((s or {}).get("cast_ms", 0))))
                })
            cfg["skills"] = skills
        except Exception:
            cfg["skills"] = []

        return cfg
