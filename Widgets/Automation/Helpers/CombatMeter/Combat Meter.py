"""Combat Meter: party damage and healing per member (current fight and combat-zone total)."""

from __future__ import annotations

import traceback

import PyImGui

from Py4GWCoreLib import Map
from Py4GWCoreLib import Routines
from Py4GWCoreLib.py4gwcorelib_src.Console import Console
from Py4GWCoreLib.py4gwcorelib_src.Console import ConsoleLog
from Widgets.Automation.Helpers.CombatMeter.combat_meter_src.game_source import GameSource
from Widgets.Automation.Helpers.CombatMeter.combat_meter_src.meter import Channel
from Widgets.Automation.Helpers.CombatMeter.combat_meter_src.meter import CombatMeter
from Widgets.Automation.Helpers.CombatMeter.combat_meter_src.meter import RowSummary

MODULE_NAME = "Combat Meter"
MODULE_ICON = "Assets/Textures/Module_Icons/Combat.png"

_LOGGED_ERRORS_MAX = 64
_WARNING_COLOR = (1.0, 0.35, 0.35, 1.0)
_VIEW_CURRENT = 0
_VIEW_TOTAL = 1

_meter = CombatMeter()
_source = GameSource(_meter)
_view = _VIEW_CURRENT
_map_id = 0
_logged_errors: set[str] = set()


def _log_error_once(stage: str, exc: Exception) -> None:
    key = f"{stage}:{exc}"
    if key in _logged_errors:
        return
    if len(_logged_errors) >= _LOGGED_ERRORS_MAX:
        _logged_errors.clear()
    _logged_errors.add(key)
    ConsoleLog(MODULE_NAME, f"{stage}: {exc}\n{traceback.format_exc()}", Console.MessageType.Error)


def _format_amount(value: float, estimated: bool) -> str:
    return f"~{round(value)}" if estimated else f"{round(value)}"


def _draw_table(table_id: str, rows: list[RowSummary], per_second_label: str) -> None:
    if not rows:
        PyImGui.text("Sem dados ainda.")
        return
    if not PyImGui.begin_table(table_id, 4, 0):
        return
    try:
        PyImGui.table_setup_column("Nome")
        PyImGui.table_setup_column("Total")
        PyImGui.table_setup_column(per_second_label)
        PyImGui.table_setup_column("%")
        PyImGui.table_headers_row()
        for row in rows:
            PyImGui.table_next_row()
            PyImGui.table_next_column()
            PyImGui.text(_source.display_name(row.name))
            PyImGui.table_next_column()
            PyImGui.text(_format_amount(row.total, row.estimated))
            PyImGui.table_next_column()
            PyImGui.text(_format_amount(row.per_second, row.estimated))
            PyImGui.table_next_column()
            PyImGui.progress_bar(row.share, 120.0, 0.0, f"{round(row.share * 100)}%")
    finally:
        PyImGui.end_table()


def _reset_all() -> None:
    _meter.reset()
    _source.clear_rows()


def _draw_window() -> None:
    global _view
    opened = PyImGui.begin(MODULE_NAME, int(PyImGui.WindowFlags.AlwaysAutoResize))
    try:
        if not opened:
            return
        if not _source.capture_enabled():
            PyImGui.text_colored("A captura de eventos do Py4GW esta desligada.", _WARNING_COLOR)
        _view = PyImGui.radio_button("Combate atual", _view, _VIEW_CURRENT)
        PyImGui.same_line(0.0, -1.0)
        _view = PyImGui.radio_button("Total da zona", _view, _VIEW_TOTAL)
        PyImGui.same_line(0.0, -1.0)
        if PyImGui.small_button("Reiniciar"):
            _reset_all()
        current = _view == _VIEW_CURRENT
        seconds = _meter.fight_seconds() if current else _meter.total_seconds()
        PyImGui.text(f"Tempo de combate: {int(seconds) // 60}:{int(seconds) % 60:02d}   (~ = valor estimado)")
        if PyImGui.begin_tab_bar("combat_meter_tabs"):
            if PyImGui.begin_tab_item("Dano"):
                _draw_table("combat_meter_damage", _meter.summary(Channel.DAMAGE, current), "DPS")
                PyImGui.end_tab_item()
            if PyImGui.begin_tab_item("Cura"):
                _draw_table("combat_meter_healing", _meter.summary(Channel.HEALING, current), "HPS")
                PyImGui.end_tab_item()
            PyImGui.end_tab_bar()
    finally:
        PyImGui.end()


def tooltip() -> None:
    PyImGui.begin_tooltip()
    PyImGui.text("Combat Meter")
    PyImGui.separator()
    PyImGui.text("Dano e cura por membro da party, no combate atual e no total da zona de combate.")
    PyImGui.text("Invocacoes (minions, espiritos, pets) contam para o dono quando o jogo o indica;")
    PyImGui.text("senao aparecem na linha Invocacoes.")
    PyImGui.text("Dano a inimigos e estimado (~): o jogo nao envia a vida maxima deles.")
    PyImGui.end_tooltip()


def on_enable() -> None:
    # Events buffered while the widget was off may belong to another map instance: never count them.
    _source.discard_pending()
    _source.reset_instance()
    _reset_all()


def main() -> None:
    global _map_id
    try:
        if not (Routines.Checks.Map.MapValid() and Routines.Checks.Map.IsMapReady()):
            _source.discard_pending()  # loading screens: drop events instead of letting the buffer fill
            return
        map_id = int(Map.GetMapID())
        if map_id != _map_id:
            _map_id = map_id
            _source.reset_instance()
            if Map.IsExplorable():
                _reset_all()  # a new combat area starts a new total; outposts keep the last one readable
        try:
            _source.pump()
        except Exception as exc:
            _log_error_once("pump", exc)
        _draw_window()
    except Exception as exc:
        _log_error_once("main", exc)


if __name__ == "__main__":
    main()
