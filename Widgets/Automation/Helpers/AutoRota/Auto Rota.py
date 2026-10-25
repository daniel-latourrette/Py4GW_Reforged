"""Auto Rota: a key toggles an automatic Mesmer play loop on and off (interrupts first)."""

from __future__ import annotations

import ctypes
import time
import traceback
from collections import deque
from collections.abc import Generator
from typing import Any
from typing import Optional

import PyImGui
import PySystem

from Py4GWCoreLib import Player
from Py4GWCoreLib import Routines
from Py4GWCoreLib import Timer
from Py4GWCoreLib.enums_src.IO_enums import Key
from Py4GWCoreLib.HeroAI.cache_data import CacheData
from Py4GWCoreLib.py4gwcorelib_src.Console import Console
from Py4GWCoreLib.py4gwcorelib_src.Console import ConsoleLog
from Py4GWCoreLib.py4gwcorelib_src.Settings import Settings
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.build_mode import BuildMode
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.build_mode import BuildPassOutcome
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.build_mode import SuggestedBuild
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.game_adapter import REASON_BUSY
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.game_adapter import STOP_REASONS
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.game_adapter import GameAdapter
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import build_paused_by_guard
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import guard_reason
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import guarded_skill_ids
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import history_text
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import warning_text
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.key_edge import KeyEdge
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.key_edge import next_auto_state
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import ActiveHex
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import Decision
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import BUILD_MODE_MAX_TIER

MODULE_NAME = "Auto Rota"
MODULE_ICON = "Assets/Textures/Module_Icons/Combat.png"

_SETTINGS_SECTION = "AutoRota"
_SETTINGS_HOTKEY = "hotkey"
_SETTINGS_BUFF_HOTKEY = "buff_hotkey"
_SETTINGS_HEX_GUARD = "hex_guard"
_PREVIEW_INTERVAL_MS = 100
_HISTORY_SIZE = 5
_HEARTBEAT_MAX_S = 0.5
_LOAD_TIMEOUT_S = 10.0
_LOGGED_ERRORS_MAX = 64
_WARNING_COLOR = (1.0, 0.35, 0.35, 1.0)
_ON_COLOR = (0.35, 1.0, 0.45, 1.0)
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
_key_loaded = False
_key_index = 0
_key_edge = KeyEdge()
_buff_key_index = 2
_buff_key_edge = KeyEdge()
_ignored_text = ""
_auto_on = False
_buffs_on = False  # always starts off: buffs are an explicit opt-in per session
_guard_on = True  # loaded from the settings together with the keys; on by default
_guard_hexes: tuple[ActiveHex, ...] = ()
_guard_ids: frozenset[int] = frozenset()
_guard_error = False
_load_job: Optional[Generator[Any, Any, Any]] = None
_load_name = ""
_load_started_s = 0.0
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


def _load_key_index(setting: str, default: Key) -> int:
    saved = _settings.get_str(_SETTINGS_SECTION, setting, default.name)
    for index, (_, key) in enumerate(_KEY_CHOICES):
        if key.name == saved:
            return index
    return next(index for index, (_, key) in enumerate(_KEY_CHOICES) if key is default)


def _is_key_down(vk_code: int) -> bool:
    # Read the key straight from Windows: HOTKEY_MANAGER feeds Win32 VK codes to PyImGui.is_key_pressed,
    # which takes ImGuiKey codes since the ImGui migration, so it never fires for keys like F1.
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)


def _ignore_press(reason: str) -> None:
    global _ignored_text
    _ignored_text = f"{time.strftime('%H:%M:%S')}  {reason}"


def _set_auto(on: bool, reason: str = "") -> None:
    global _auto_on
    if on == _auto_on:
        return
    _auto_on = on
    if on:
        _push_history("Auto Rota LIGADA")
        return
    _build_mode.cancel()
    _push_history(f"Auto Rota DESLIGADA ({reason})" if reason else "Auto Rota DESLIGADA")


def _stop_reason() -> Optional[str]:
    """A blocker that must switch the toggle off (death, outpost, HeroAI combat), else None."""
    reason = _adapter.blocker()
    return reason if reason in STOP_REASONS else None


def _update_guard() -> None:
    """Read the punishing hexes on the player once per frame and derive the skills the guard blocks."""
    global _guard_hexes, _guard_ids, _guard_error
    previous = {active.skill_id for active in _guard_hexes}
    if not _guard_on:
        _guard_hexes, _guard_ids, _guard_error = (), frozenset(), False
        return
    try:
        hexes = _adapter.punishing_hexes_on_player()
        guarded = guarded_skill_ids(_adapter.bar_skills(), hexes) if hexes else frozenset[int]()
    except Exception as exc:
        # Fail open: an unreadable effects list must not freeze the loop; the window says so.
        _guard_hexes, _guard_ids, _guard_error = (), frozenset(), True
        _log_error_once("hex guard", exc)
        return
    _guard_hexes, _guard_ids, _guard_error = hexes, guarded, False
    if _auto_on:
        current = {active.skill_id for active in hexes}
        for skill_id in sorted(current - previous):
            _push_history(history_text(skill_id, started=True))
        for skill_id in sorted(previous - current):
            _push_history(history_text(skill_id, started=False))


def _press_allowed() -> bool:
    if not PySystem.window.is_window_active():
        _ignore_press("Guild Wars sem foco")
        return False
    if Player.IsTyping() or PyImGui.get_io().want_text_input:
        _ignore_press("a escrever (chat ou campo de texto)")
        return False
    return True


def _on_buff_toggle_press() -> None:
    global _buffs_on
    if not _press_allowed():
        return
    _buffs_on = not _buffs_on
    _push_history("Buffs LIGADOS" if _buffs_on else "Buffs DESLIGADOS")


def _on_toggle_press() -> None:
    if not _press_allowed():
        return
    stop_reason = _stop_reason()
    turning_on = not _auto_on
    if turning_on and stop_reason is not None:
        _push_history(f"recusado: {stop_reason}")
    _set_auto(next_auto_state(_auto_on, True, stop_reason is not None), stop_reason or "")


def _play_once() -> None:
    """One play while the toggle is on; silent when busy or when there is nothing to do."""
    if _build_mode.busy or _adapter.blocker() is not None:
        return
    # A build pass cannot skip single skills: while the guard blocks one of the build's skills, play the
    # generic rotation (all interrupt tiers, then HeroAI) over the skills the guard still allows.
    if _build_mode.build_name is None or build_paused_by_guard(_guard_ids, _build_mode.blocked_skill_ids()):
        decision = _adapter.next_decision(allow_buffs=_buffs_on, blocked_skill_ids=_guard_ids)
        if decision is not None:
            _adapter.execute(decision)
            _push_history(_adapter.describe(decision))
        return
    interrupt = _adapter.interrupt_decision(BUILD_MODE_MAX_TIER, blocked_skill_ids=_guard_ids)
    if interrupt is not None:
        _adapter.execute(interrupt)
        _push_history(_adapter.describe(interrupt))
        return
    _build_mode.request_pass()  # main() drives the pass over the next frames


def _finish_build_pass(outcome: BuildPassOutcome) -> None:
    # A pass can fail after it already queued a skill: record that cast (and start the debounce) first.
    if outcome.cast is not None:
        skill_id, target_id = outcome.cast
        _adapter.note_external_cast()
        label = f"Build: {_build_mode.build_name or '?'}"
        cast = Decision(bar_slot=0, skill_id=skill_id, target_id=target_id, label=label)
        _push_history(_adapter.describe(cast, no_target_text="(sem alvo)"))
    if outcome.error is not None:
        # A build that fails once will usually fail every frame: switch off instead of flooding.
        _set_auto(False, f"erro na build: {outcome.error}")
        ConsoleLog(MODULE_NAME, f"build pass: {outcome.error}", Console.MessageType.Error)
        return
    if outcome.cast is not None or not _auto_on or _adapter.blocker() is not None:
        return
    blocked = set(_build_mode.blocked_skill_ids()) | _guard_ids
    decision = _adapter.rotation_after_build(sorted(blocked), allow_buffs=_buffs_on)
    if decision is not None:
        _adapter.execute(decision)
        _push_history(_adapter.describe(decision))


def _copy_template(build: SuggestedBuild) -> None:
    PyImGui.set_clipboard_text(build.template_code)
    _push_history(f"Template copiado: {build.name}")


def _request_load(build: SuggestedBuild) -> None:
    global _load_job, _load_name, _load_started_s
    if _load_job is not None:
        _push_history("recusado: ja esta a carregar uma build")
        return
    if not Routines.Checks.Map.IsOutpost():
        _push_history("recusado: carregar so em outpost")
        return
    _load_job = Routines.Yield.Skills.LoadSkillbar(build.template_code, log=False)
    _load_name = build.name
    _load_started_s = time.monotonic()
    _push_history(f"A carregar build: {build.name}")


def _cancel_load() -> None:
    global _load_job
    if _load_job is None:
        return
    _load_job.close()
    _load_job = None
    _push_history(f"carregamento cancelado: {_load_name}")


def _advance_load() -> None:
    """Drive a template load one step per frame (the loader waits between steps)."""
    global _load_job
    if _load_job is None:
        return
    try:
        next(_load_job)
    except StopIteration:
        _load_job = None
        _push_history(f"Build carregada: {_load_name}")
        return
    except Exception as exc:
        _load_job = None
        _push_history(f"erro ao carregar: {exc}")
        _log_error_once("load build", exc)
        return
    if time.monotonic() - _load_started_s > _LOAD_TIMEOUT_S:
        _load_job.close()
        _load_job = None
        _push_history(f"carregamento expirou: {_load_name}")


def _draw_suggested_builds() -> None:
    if not PyImGui.collapsing_header("Builds sugeridas"):
        return
    try:
        suggestions = _build_mode.suggested_builds()
    except Exception as exc:
        PyImGui.text("Erro ao listar as builds (ver consola)")
        _log_error_once("suggested builds", exc)
        return
    if not suggestions:
        PyImGui.text("Nenhuma build disponivel")
        return
    for index, build in enumerate(suggestions):
        if PyImGui.small_button(f"Copiar##auto_rota_copy_{index}"):
            _copy_template(build)
        PyImGui.same_line(0.0, -1.0)
        if PyImGui.small_button(f"Carregar##auto_rota_load_{index}"):
            _request_load(build)
        PyImGui.same_line(0.0, -1.0)
        PyImGui.text(build.name)
    PyImGui.text_disabled("Carregar: so em outpost; substitui a barra atual (skills e atributos).")


def _update_preview() -> None:
    global _preview_text, _heroai_conflict
    _heroai_conflict = _adapter.heroai_conflict()
    reason = _adapter.blocker()
    if reason is not None and reason != REASON_BUSY:
        _preview_text = f"em pausa ({reason})"
        return
    build_ids = _build_mode.blocked_skill_ids()
    build_paused = _build_mode.build_name is not None and build_paused_by_guard(_guard_ids, build_ids)
    if _build_mode.build_name is None or build_paused:
        decision = _adapter.next_decision(preview=True, allow_buffs=_buffs_on, blocked_skill_ids=_guard_ids)
        text = _adapter.describe(decision) if decision is not None else "nada a fazer"
        _preview_text = f"build em pausa ({guard_reason(_guard_hexes)}): {text}" if build_paused else text
        return
    interrupt = _adapter.interrupt_decision(BUILD_MODE_MAX_TIER, blocked_skill_ids=_guard_ids)
    _preview_text = _adapter.describe(interrupt) if interrupt is not None else "jogada da build (decidida ao jogar)"


def _draw_window() -> None:
    global _key_index, _key_edge, _buff_key_index, _buff_key_edge, _guard_on
    opened = PyImGui.begin(MODULE_NAME, int(PyImGui.WindowFlags.AlwaysAutoResize))
    try:
        if opened:
            key_label = _KEY_CHOICES[_key_index][0]
            if _auto_on:
                PyImGui.text_colored(f"LIGADA  ({key_label} para desligar)", _ON_COLOR)
            else:
                PyImGui.text(f"DESLIGADA  ({key_label} para ligar)")
            buff_label = _KEY_CHOICES[_buff_key_index][0]
            if _buffs_on:
                PyImGui.text_colored(f"Buffs: LIGADOS  ({buff_label})", _ON_COLOR)
            else:
                PyImGui.text(f"Buffs: DESLIGADOS  ({buff_label})")
            if _guard_error:
                PyImGui.text_colored("Guarda: erro a ler efeitos (ver consola)", _WARNING_COLOR)
            for active in _guard_hexes:
                PyImGui.text_colored(warning_text(active), _WARNING_COLOR)
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
                _key_edge = KeyEdge()
            new_buff_index = PyImGui.combo("Tecla buffs", _buff_key_index, labels)
            if new_buff_index != _buff_key_index:
                _buff_key_index = new_buff_index
                _settings.set_str(_SETTINGS_SECTION, _SETTINGS_BUFF_HOTKEY, _KEY_CHOICES[new_buff_index][1].name)
                _buff_key_edge = KeyEdge()
            if _buff_key_index == _key_index:
                PyImGui.text_colored("As duas teclas sao iguais: a tecla dos buffs e ignorada", _WARNING_COLOR)
            new_guard_on = PyImGui.checkbox("Guarda de hexes", _guard_on)
            if new_guard_on != _guard_on:
                _guard_on = new_guard_on
                _settings.set_bool(_SETTINGS_SECTION, _SETTINGS_HEX_GUARD, new_guard_on)
                _push_history("Guarda de hexes LIGADA" if new_guard_on else "Guarda de hexes DESLIGADA")
            if _ignored_text:
                PyImGui.text(f"Ultimo toque ignorado: {_ignored_text}")
            PyImGui.separator()
            PyImGui.text("Historico:")
            for line in _history:
                PyImGui.text(line)
            PyImGui.separator()
            _draw_suggested_builds()
    finally:
        PyImGui.end()


def tooltip() -> None:
    PyImGui.begin_tooltip()
    PyImGui.text("Auto Rota")
    PyImGui.separator()
    PyImGui.text("A tecla liga e desliga. Ligada, joga sozinha:")
    PyImGui.bullet_text("1. Interrupt por prioridade em qualquer inimigo")
    PyImGui.bullet_text("   (com build detetada: so ressurreicao, cura e elite)")
    PyImGui.bullet_text("2. Senao, a jogada da build de Mesmer detetada, se houver")
    PyImGui.bullet_text("3. Senao, a proxima skill da rotacao do HeroAI")
    PyImGui.text("Ataque e hexes vao para o alvo que selecionares (ao alcance); sem alvo, nao ataca.")
    PyImGui.text("Excecao: com build detetada, a jogada da build escolhe o proprio alvo.")
    PyImGui.text("Desliga ao morrer, mudar de mapa ou ligar o combate do HeroAI.")
    PyImGui.text("A tecla dos buffs liga/desliga o uso de buffs (Mantras, Channeling, Ether Signet...).")
    PyImGui.text("Guarda de hexes: pausa as skills que um hex em ti castiga (ex.: Backfire -> spells).")
    PyImGui.end_tooltip()


def on_disable() -> None:
    global _auto_on
    _auto_on = False
    _build_mode.cancel()


def main() -> None:
    global _key_index, _buff_key_index, _key_loaded, _main_tick_s, _preview_text, _guard_on
    try:
        if not Routines.Checks.Map.MapValid():
            _set_auto(False, "mudanca de mapa")
            _build_mode.cancel()
            _cancel_load()
            return
        _cached_data.Update()
        if not (Routines.Checks.Map.IsMapReady() and Routines.Checks.Party.IsPartyLoaded()):
            _set_auto(False, "mudanca de mapa")
            _build_mode.cancel()
            _cancel_load()
            return
        if time.monotonic() - _main_tick_s > _HEARTBEAT_MAX_S:
            _set_auto(False, "widget em pausa")
            _build_mode.cancel()  # main() was not ticking (pause, load, stall): never resume an old pass
        _main_tick_s = time.monotonic()
        if not _key_loaded:
            _key_index = _load_key_index(_SETTINGS_HOTKEY, Key.VK_OEM_3)
            _buff_key_index = _load_key_index(_SETTINGS_BUFF_HOTKEY, Key.VK_F2)
            _guard_on = _settings.get_bool(_SETTINGS_SECTION, _SETTINGS_HEX_GUARD, True)
            _key_loaded = True
        try:
            _build_mode.refresh()
        except Exception as exc:
            _log_error_once("build", exc)
        try:
            _update_guard()  # before the play and the preview, so a fresh hex is seen on the frame it lands
        except Exception as exc:
            _log_error_once("hex guard", exc)
        if _key_edge.update(_is_key_down(_KEY_CHOICES[_key_index][1].value)):
            try:
                _on_toggle_press()
            except Exception as exc:
                _push_history(f"erro: {exc}")
                _log_error("key press", exc)
        buff_key_down = _buff_key_index != _key_index and _is_key_down(_KEY_CHOICES[_buff_key_index][1].value)
        if _buff_key_edge.update(buff_key_down):
            try:
                _on_buff_toggle_press()
            except Exception as exc:
                _push_history(f"erro: {exc}")
                _log_error("buff key press", exc)
        if _auto_on:
            stop_reason = _stop_reason()
            if stop_reason is not None:
                _set_auto(False, stop_reason)
            else:
                try:
                    _play_once()
                except Exception as exc:
                    _set_auto(False, f"erro: {exc}")
                    _log_error_once("auto play", exc)
        outcome = _build_mode.advance()
        if outcome is not None:
            try:
                _finish_build_pass(outcome)
            except Exception as exc:
                _set_auto(False, f"erro: {exc}")
                _log_error_once("build pass", exc)
        _advance_load()
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
