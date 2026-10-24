"""Auto Rota: one key press, one best play (Mesmer-focused interrupts first)."""

from __future__ import annotations

import time
import traceback
from collections import deque

import PyImGui

from Py4GWCoreLib import Player
from Py4GWCoreLib import Routines
from Py4GWCoreLib import Timer
from Py4GWCoreLib.enums_src.IO_enums import Key
from Py4GWCoreLib.HeroAI.cache_data import CacheData
from Py4GWCoreLib.HotkeyManager import HOTKEY_MANAGER
from Py4GWCoreLib.py4gwcorelib_src.Console import Console
from Py4GWCoreLib.py4gwcorelib_src.Console import ConsoleLog
from Py4GWCoreLib.py4gwcorelib_src.Settings import Settings
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.build_mode import BuildMode
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.build_mode import BuildPassOutcome
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.game_adapter import REASON_BUSY
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.game_adapter import GameAdapter
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import Decision
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import BUILD_MODE_MAX_TIER

MODULE_NAME = "Auto Rota"
MODULE_ICON = "Assets/Textures/Module_Icons/Combat.png"

_HOTKEY_ID = "auto_rota.play"
_SETTINGS_SECTION = "AutoRota"
_SETTINGS_HOTKEY = "hotkey"
_PREVIEW_INTERVAL_MS = 100
_HISTORY_SIZE = 5
_HEARTBEAT_MAX_S = 0.5
_LOGGED_ERRORS_MAX = 64
_WARNING_COLOR = (1.0, 0.35, 0.35, 1.0)
_KEY_CHOICES: list[tuple[str, Key]] = [
    ("` (acento grave)", Key.VK_OEM_3),
    ("F1", Key.VK_F1),
    ("F2", Key.VK_F2),
    ("F3", Key.VK_F3),
    ("F4", Key.VK_F4),
    ("F5", Key.VK_F5),
]

_cached_data = CacheData()
_adapter = GameAdapter(_cached_data)
_build_mode = BuildMode()
_settings = Settings("Widgets/Config/auto_rota.ini", "global")
_preview_timer = Timer()
_preview_timer.Start()
_preview_text = "-"
_heroai_conflict = False
_history: deque[str] = deque(maxlen=_HISTORY_SIZE)
_hotkey_registered = False
_key_index = 0
_main_tick_s = 0.0
_logged_errors: set[str] = set()


def _log_error(stage: str, exc: Exception) -> None:
    ConsoleLog(MODULE_NAME, f"{stage}: {exc}\n{traceback.format_exc()}", Console.MessageType.Error)


def _log_error_once(stage: str, exc: Exception) -> None:
    key = f"{stage}:{exc}"
    if key in _logged_errors:
        return
    if len(_logged_errors) >= _LOGGED_ERRORS_MAX:
        _logged_errors.clear()
    _logged_errors.add(key)
    _log_error(stage, exc)


def _push_history(text: str) -> None:
    _history.appendleft(f"{time.strftime('%H:%M:%S')}  {text}")


def _load_key_index() -> int:
    saved = _settings.get_str(_SETTINGS_SECTION, _SETTINGS_HOTKEY, Key.VK_OEM_3.name)
    for index, (_, key) in enumerate(_KEY_CHOICES):
        if key.name == saved:
            return index
    return 0


def _on_hotkey() -> None:
    try:
        if not PyImGui.is_key_pressed(_KEY_CHOICES[_key_index][1].value, False):
            return  # ignore auto-repeat while the key is held
        if time.monotonic() - _main_tick_s > _HEARTBEAT_MAX_S:
            return  # widget paused, loading, or main() not running
        if Player.IsTyping() or PyImGui.get_io().want_text_input:
            return
        if _build_mode.busy:
            _push_history(f"recusado: {REASON_BUSY}")
            return
        reason = _adapter.blocker()
        if reason is not None:
            _push_history(f"recusado: {reason}")
            return
        if _build_mode.build_name is None:
            decision = _adapter.next_decision()
            if decision is None:
                _push_history("nada a fazer")
                return
            _adapter.execute(decision)
            _push_history(_adapter.describe(decision))
            return
        interrupt = _adapter.interrupt_decision(BUILD_MODE_MAX_TIER)
        if interrupt is not None:
            _adapter.execute(interrupt)
            _push_history(_adapter.describe(interrupt))
            return
        _build_mode.request_pass()  # the widget's main() drives the pass over the next frames
    except Exception as exc:
        _push_history(f"erro: {exc}")
        _log_error("hotkey", exc)


def _finish_build_pass(outcome: BuildPassOutcome) -> None:
    if outcome.error is not None:
        _push_history(f"erro: {outcome.error}")
        ConsoleLog(MODULE_NAME, f"build pass: {outcome.error}", Console.MessageType.Error)
        return
    if outcome.cast is not None:
        skill_id, target_id = outcome.cast
        _adapter.note_external_cast()
        label = f"Build: {_build_mode.build_name or '?'}"
        cast = Decision(bar_slot=0, skill_id=skill_id, target_id=target_id, label=label)
        _push_history(_adapter.describe(cast, no_target_text="(sem alvo)"))
        return
    decision = _adapter.rotation_after_build(_build_mode.blocked_skill_ids())
    if decision is None:
        _push_history("nada a fazer")
        return
    _adapter.execute(decision)
    _push_history(_adapter.describe(decision))


def _register_hotkey() -> None:
    global _hotkey_registered
    # Re-registering the same identifier replaces the previous key binding.
    HOTKEY_MANAGER.register_hotkey(_KEY_CHOICES[_key_index][1], _HOTKEY_ID, _on_hotkey, name="Auto Rota: jogada")
    _hotkey_registered = True


def _update_preview() -> None:
    global _preview_text, _heroai_conflict
    _heroai_conflict = _adapter.heroai_conflict()
    reason = _adapter.blocker()
    if reason is not None and reason != REASON_BUSY:
        _preview_text = f"em pausa ({reason})"
        return
    if _build_mode.build_name is None:
        decision = _adapter.next_decision(preview=True)
        _preview_text = _adapter.describe(decision) if decision is not None else "nada a fazer"
        return
    interrupt = _adapter.interrupt_decision(BUILD_MODE_MAX_TIER)
    _preview_text = (
        _adapter.describe(interrupt) if interrupt is not None else "jogada da build (decidida ao carregar)"
    )


def _draw_window() -> None:
    global _key_index
    opened = PyImGui.begin(MODULE_NAME, int(PyImGui.WindowFlags.AlwaysAutoResize))
    try:
        if opened:
            if _heroai_conflict:
                PyImGui.text_colored("HeroAI com combate ligado: Auto Rota em pausa", _WARNING_COLOR)
            build_name = _build_mode.build_name
            PyImGui.text(f"Build: {build_name}" if build_name else "Build: nenhuma (rotacao generica)")
            PyImGui.text(f"Proxima jogada: {_preview_text}")
            PyImGui.separator()
            labels = [label for label, _ in _KEY_CHOICES]
            new_index = PyImGui.combo("Tecla", _key_index, labels)
            if new_index != _key_index:
                _key_index = new_index
                _settings.set_str(_SETTINGS_SECTION, _SETTINGS_HOTKEY, _KEY_CHOICES[new_index][1].name)
                _register_hotkey()
            PyImGui.separator()
            PyImGui.text("Historico:")
            for line in _history:
                PyImGui.text(line)
    finally:
        PyImGui.end()


def tooltip() -> None:
    PyImGui.begin_tooltip()
    PyImGui.text("Auto Rota")
    PyImGui.separator()
    PyImGui.text("Cada toque na tecla faz uma jogada:")
    PyImGui.bullet_text("1. Interrupt por prioridade (ressurreicao, cura, elite, cast longo)")
    PyImGui.bullet_text("2. Senao, a jogada da build de Mesmer detetada, se houver")
    PyImGui.bullet_text("3. Senao, a proxima skill da rotacao do HeroAI")
    PyImGui.text("Nao funciona com o combate do HeroAI ligado.")
    PyImGui.end_tooltip()


def on_disable() -> None:
    global _hotkey_registered
    HOTKEY_MANAGER.unregister_hotkey(_HOTKEY_ID)
    _hotkey_registered = False


def main() -> None:
    global _key_index, _main_tick_s, _preview_text
    try:
        if not Routines.Checks.Map.MapValid():
            return
        _cached_data.Update()
        if not (Routines.Checks.Map.IsMapReady() and Routines.Checks.Party.IsPartyLoaded()):
            return
        _main_tick_s = time.monotonic()
        if not _hotkey_registered:
            _key_index = _load_key_index()
            _register_hotkey()
        try:
            _build_mode.refresh()
        except Exception as exc:
            _log_error_once("build", exc)
        outcome = _build_mode.advance()
        if outcome is not None:
            _finish_build_pass(outcome)
        if _preview_timer.HasElapsed(_PREVIEW_INTERVAL_MS):
            _preview_timer.Reset()
            try:
                _update_preview()
            except Exception as exc:
                _preview_text = "erro (ver consola)"
                _log_error_once("preview", exc)
        _draw_window()
    except Exception as exc:
        _log_error_once("main", exc)


if __name__ == "__main__":
    main()
