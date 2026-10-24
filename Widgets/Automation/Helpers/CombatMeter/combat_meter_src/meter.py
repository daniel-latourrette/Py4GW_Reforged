"""Pure Combat Meter core: event classification, health amounts, fights and per-row totals.

This module must not import Py4GWCoreLib: it runs offline in unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

# Mirrors PyAgentEvents.PyEventType (stubs/PyAgentEvents.pyi); kept as plain ints so this module stays pure.
DAMAGE = 30
CRITICAL = 31
ARMOR_IGNORING = 32  # sign not verified in-game; heals are filtered by the receiver (an ally), not here
HEALING = 33

FIGHT_GAP_MS = 8000


class Channel(Enum):
    DAMAGE = "damage"
    HEALING = "healing"


def classify_event(event_type: int, fraction: float) -> Optional[tuple[Channel, float]]:
    """Map a raw agent event to (channel, health fraction), or None if it is not counted."""
    if fraction == 0.0:
        return None
    if event_type in (DAMAGE, CRITICAL, ARMOR_IGNORING):
        return (Channel.DAMAGE, abs(fraction))
    if event_type == HEALING:
        return (Channel.HEALING, abs(fraction))
    return None


def health_amount(fraction: float, known_max_hp: int, level: int) -> tuple[float, bool]:
    """Turn a fraction of the target's max health into points; (amount, estimated).

    Enemy max health is not sent by the game, so it is estimated with the rule most creatures follow:
    80 + 20 * level.
    """
    if known_max_hp > 0:
        return (fraction * known_max_hp, False)
    return (fraction * (80 + 20 * max(level, 0)), True)


@dataclass(frozen=True)
class RowSummary:
    name: str
    total: float
    per_second: float
    share: float  # fraction of the channel total, 0..1
    estimated: bool


@dataclass
class _Row:
    total: float = 0.0
    estimated: bool = False


class _Tally:
    def __init__(self) -> None:
        self.rows: dict[Channel, dict[str, _Row]] = {Channel.DAMAGE: {}, Channel.HEALING: {}}

    def add(self, channel: Channel, name: str, amount: float, estimated: bool) -> None:
        row = self.rows[channel].setdefault(name, _Row())
        row.total += amount
        row.estimated = row.estimated or estimated

    def summary(self, channel: Channel, seconds: float) -> list[RowSummary]:
        rows = self.rows[channel]
        grand_total = sum(row.total for row in rows.values())
        summaries = [
            RowSummary(
                name=name,
                total=row.total,
                per_second=row.total / seconds,
                share=row.total / grand_total if grand_total > 0 else 0.0,
                estimated=row.estimated,
            )
            for name, row in rows.items()
        ]
        return sorted(summaries, key=lambda summary: summary.total, reverse=True)


def _fight_seconds(first_ms: int, last_ms: int) -> float:
    return max(1.0, (last_ms - first_ms) / 1000.0)


class CombatMeter:
    """Current fight (restarts after `fight_gap_ms` without events) and the running total."""

    def __init__(self, fight_gap_ms: int = FIGHT_GAP_MS) -> None:
        self._fight_gap_ms = fight_gap_ms
        self.reset()

    def reset(self) -> None:
        self._current = _Tally()
        self._total = _Tally()
        self._fight_first_ms: Optional[int] = None
        self._fight_last_ms: Optional[int] = None
        self._closed_fights_s = 0.0

    def record(self, channel: Channel, name: str, amount: float, estimated: bool, timestamp_ms: int) -> None:
        if self._fight_last_ms is not None and timestamp_ms - self._fight_last_ms > self._fight_gap_ms:
            assert self._fight_first_ms is not None
            self._closed_fights_s += _fight_seconds(self._fight_first_ms, self._fight_last_ms)
            self._current = _Tally()
            self._fight_first_ms = None
        if self._fight_first_ms is None or timestamp_ms < self._fight_first_ms:
            self._fight_first_ms = timestamp_ms
        self._fight_last_ms = max(timestamp_ms, self._fight_last_ms or timestamp_ms)
        self._current.add(channel, name, amount, estimated)
        self._total.add(channel, name, amount, estimated)

    def fight_seconds(self) -> float:
        if self._fight_first_ms is None or self._fight_last_ms is None:
            return 0.0
        return _fight_seconds(self._fight_first_ms, self._fight_last_ms)

    def total_seconds(self) -> float:
        return self._closed_fights_s + self.fight_seconds()

    def summary(self, channel: Channel, current_fight: bool) -> list[RowSummary]:
        if current_fight:
            return self._current.summary(channel, max(1.0, self.fight_seconds()))
        return self._total.summary(channel, max(1.0, self.total_seconds()))
