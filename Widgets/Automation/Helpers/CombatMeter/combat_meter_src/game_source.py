"""Runtime bridge for the Combat Meter: drains PyAgentEvents and feeds the pure meter.

This is the only Combat Meter module that touches the game. It is the single consumer of the native
agent-event buffer: PyAgentEvents.get_and_clear_events() empties it, and the CombatEvents facade that
used to read it is disabled (and calls the legacy PyCombatEvents module). If another widget starts
draining the buffer, both would see only part of the events.
"""

from __future__ import annotations

import time
from typing import Optional

import PyAgentEvents

from Py4GWCoreLib import GLOBAL_CACHE
from Py4GWCoreLib import Agent

from .meter import Channel
from .meter import CombatMeter
from .meter import classify_event
from .meter import health_amount

SUMMONS_ROW = "Invocacoes"

_ALLY = 1  # Py4GWCoreLib Allegiance values
_ENEMY = 3
_SPIRIT_PET = 4
_MINION = 5
_FRIENDLY = frozenset({_ALLY, _SPIRIT_PET, _MINION})
_SUMMON = frozenset({_SPIRIT_PET, _MINION})

_PARTY_REFRESH_S = 1.0


def _party_agent_ids() -> set[int]:
    party = GLOBAL_CACHE.Party
    ids = [int(party.Players.GetAgentIDByLoginNumber(player.login_number) or 0) for player in party.GetPlayers()]
    ids += [int(hero.agent_id) for hero in party.GetHeroes()]
    ids += [int(henchman.agent_id) for henchman in party.GetHenchmen()]
    ids += [int(other) for other in party.GetOthers()]
    return {agent_id for agent_id in ids if agent_id}


def _allegiance(agent_id: int) -> int:
    allegiance, _ = Agent.GetAllegiance(agent_id)
    return int(allegiance)


class GameSource:
    def __init__(self, meter: CombatMeter) -> None:
        self._meter = meter
        self._party: set[int] = set()
        self._party_refreshed_s = 0.0
        # Row key -> display name, captured while the agent id still belongs to that member: agent ids are
        # reused across map instances, so a name must never be looked up again after a map change.
        self._row_names: dict[str, str] = {}

    def reset_instance(self) -> None:
        """Map changed: party agent ids are no longer valid (row names are kept with their rows)."""
        self._party = set()
        self._party_refreshed_s = 0.0

    def clear_rows(self) -> None:
        """The meter was reset: forget the names of rows that no longer exist."""
        self._row_names = {}

    @staticmethod
    def capture_enabled() -> bool:
        return bool(PyAgentEvents.is_enabled())

    @staticmethod
    def discard_pending() -> None:
        """Drop buffered events (map loading, widget not ready) so they never land in a later fight."""
        PyAgentEvents.get_and_clear_events()

    def pump(self) -> None:
        """Drain the event buffer and record party damage/healing. Call once per frame."""
        events = PyAgentEvents.get_and_clear_events()
        if not events:
            return
        self._refresh_party()
        for event in events:
            classified = classify_event(int(event.event_type), float(event.float_value))
            if classified is None:
                continue
            channel, fraction = classified
            # Health events: agent_id is who RECEIVES, target_id is who DEALS.
            receiver, dealer = int(event.agent_id), int(event.target_id)
            row = self._row_key_for(dealer)
            if row is None or not self._valid_receiver(channel, receiver):
                continue
            self._remember_name(row)
            amount, estimated = health_amount(
                fraction, int(Agent.GetMaxHealth(receiver)), int(Agent.GetLevel(receiver))
            )
            self._meter.record(channel, row, amount, estimated, int(event.timestamp))

    def _refresh_party(self) -> None:
        now = time.monotonic()
        if now - self._party_refreshed_s < _PARTY_REFRESH_S:
            return
        self._party_refreshed_s = now
        self._party = _party_agent_ids()

    def _row_key_for(self, dealer: int) -> Optional[str]:
        """Row key of the party member credited for an event, the summons row, or None for other sources.

        Rows are keyed by agent id (not by name): names decode asynchronously, and keying by name would
        split one member into an "agente N" row and a named row.
        """
        if dealer in self._party:
            return str(dealer)
        if dealer == 0 or _allegiance(dealer) not in _SUMMON:
            return None
        owner = int(Agent.GetOwnerID(dealer) or 0)
        if owner in self._party:
            return str(owner)
        return SUMMONS_ROW

    def _valid_receiver(self, channel: Channel, receiver: int) -> bool:
        if receiver == 0:
            return False
        if channel is Channel.DAMAGE:
            return _allegiance(receiver) == _ENEMY  # also filters armor-ignoring heals, whatever their sign
        return receiver in self._party or _allegiance(receiver) in _FRIENDLY

    def _remember_name(self, row_key: str) -> None:
        if row_key == SUMMONS_ROW or row_key in self._row_names:
            return
        name = Agent.GetNameByID(int(row_key)) or ""
        if name:  # names decode asynchronously: retry on the next event until a real one arrives
            self._row_names[row_key] = name

    def display_name(self, row_key: str) -> str:
        if row_key == SUMMONS_ROW:
            return SUMMONS_ROW
        return self._row_names.get(row_key, f"agente {row_key}")
