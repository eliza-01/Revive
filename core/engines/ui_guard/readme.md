Жизненный цикл одного прогона (run_once())

Старт

Ставит features.ui_guard.busy = True, report = "empty", очищает свой pause_reason.

Если нет фокуса или нет окна → сразу busy=False, report="empty" и выход. Ничего никому не паузит.

pages_blocker

Если detect_pages_blocker() → это главный триггер массовой паузы:

Ставит паузу всем фичам и сервисам, кроме ui_guard:
paused=True, pause_reason="pages_blocker".

Себе: features.ui_guard.paused=True, pause_reason="pages_blocker".

Многократно жмёт кресты (close_all_pages_crosses).

Если страницы не исчезли → завершает прогон с report="pages_blocker", busy=False (все остальные остаются на паузе).

Если исчезли — идёт дальше (пауза пока остаётся, но reason может обновиться на следующем шаге).

dashboard_blocker

Если обнаружен → обновляет паузы у всех на pause_reason="dashboard_blocker"
(те же paused=True, просто меняется причина).

Пытается закрыть кнопкой (close_dashboard_blocker).

Если не снялся → выход с report="dashboard_blocker", busy=False.

language_blocker

Аналогично: ставит/обновляет паузы на pause_reason="language_blocker", делает Alt+Shift, жмёт кнопку.

Не снялся → выход с report="language_blocker", busy=False.

disconnect_blocker

Только уведомляет. Массовых пауз не раздаёт.

Выход с report="disconnect_blocker", busy=False.

Экран чист

Если что-то закрыли на шагах 2–4, показывает HUD «screen clear».

Снимает паузы у всех фич/сервисов, только если их pause_reason ∈ {pages_blocker,dashboard_blocker,language_blocker}:

пишет paused=False, pause_reason="" для совпавших.

Себе: features.ui_guard.busy=False, paused=False, pause_reason="", report="empty".

Важные детали поведения

Массовая пауза раздаётся только при реальном блокере: pages/dashboard/language.
Для disconnect — нет; для «нет фокуса» — ui_guard сам никого не трогает (но координатор может поставить пайплайн на паузу своим правилом unfocused).

run_once() — один прогон. Он не висит в фоне; кто-то должен его вызывать (координатор/правило).

ui_guard сам ставит busy=True на время работы. Если координатор подключён с правилом UiGuardReason, он может параллельно поставить pipeline.paused с причиной ui_guard на время прогона — это нормально.

Разпаузивание целевое: снимает только те паузы, у кого причина из тройки _REASONS = ("pages_blocker","dashboard_blocker","language_blocker"). Любые другие pause_reason он не трогает.

Если нужно, могу вкрутить вариант, где глобальные паузы раздаёт только координатор (по features.ui_guard.busy), а ui_guard пишет состояния только в свой узел — скажи, сделаю патч.