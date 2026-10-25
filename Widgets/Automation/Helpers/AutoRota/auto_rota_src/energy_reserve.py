"""Interrupt energy reserve: how much energy the rotation must leave for an interrupt, and which skills that stops.

This module must not import Py4GWCoreLib: it runs offline in unit tests.
Spec: docs/superpowers/specs/2026-10-25-auto-rota-energy-reserve-design.md.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ReserveMode(Enum):
    CHEAPEST = "cheapest"  # the value is what auto_rota.ini stores
    FIXED = "fixed"
    OFF = "off"


MODE_CHOICES: tuple[ReserveMode, ...] = (ReserveMode.CHEAPEST, ReserveMode.FIXED, ReserveMode.OFF)
MODE_LABELS: dict[ReserveMode, str] = {
    ReserveMode.CHEAPEST: "Interrupt mais barato",
    ReserveMode.FIXED: "Fixa",
    ReserveMode.OFF: "Desligada",
}
RESERVE_FIXED_DEFAULT = 10
RESERVE_FIXED_MAX = 25

# HeroAI tags these Offensive although they give energy back (Drain Enchantment, Energy Drain, Energy Tap,
# Waste Not, Want Not; ids checked in Py4GWCoreLib/skill_descriptions.json): blocking them would cut the way out.
ENERGY_GAIN_SKILL_IDS: frozenset[int] = frozenset({68, 79, 80, 1995})
# Ether Lord: "You lose all Energy", so a cost-based check would let it empty the reserve.
DRAINS_ALL_ENERGY_SKILL_IDS: frozenset[int] = frozenset({41})

CANNOT_INTERRUPT_TEXT = "sem energia para interromper"


@dataclass(frozen=True)
class InterruptCost:
    skill_id: int
    cost: float  # effective energy cost (effects and Expertise included)
    ready: bool  # off recharge, with enough adrenaline


@dataclass(frozen=True)
class EnergyStatus:
    current: Optional[float]  # None: the energy could not be read
    maximum: float
    mode: ReserveMode
    reserve: float
    reserve_skill_id: int  # the interrupt that sets the reserve in CHEAPEST mode (0: none)
    cannot_interrupt: bool  # a ready interrupt exists and none of the ready ones is affordable


def mode_from_setting(text: str) -> ReserveMode:
    for mode in ReserveMode:
        if mode.value == text:
            return mode
    return ReserveMode.CHEAPEST


def cheapest_interrupt(costs: Sequence[InterruptCost]) -> Optional[InterruptCost]:
    """Cheapest interrupt on the bar, ready or recharging; a tie keeps the first (CombatClass priority order)."""
    best: Optional[InterruptCost] = None
    for item in costs:
        if best is None or item.cost < best.cost:
            best = item
    return best


def effective_reserve(mode: ReserveMode, fixed: int, costs: Sequence[InterruptCost], maximum: float) -> float:
    """The energy the rotation must leave, capped at half the maximum (0 when the maximum is unknown)."""
    if mode is ReserveMode.OFF or maximum <= 0:
        return 0.0
    if mode is ReserveMode.FIXED:
        raw = float(fixed)
    else:
        cheapest = cheapest_interrupt(costs)
        raw = cheapest.cost if cheapest is not None else 0.0
    return min(max(0.0, raw), maximum / 2.0)


def breaks_reserve(
    current: float, cost: float, reserve: float, maximum: float, skill_id: int, energy_buff: bool
) -> bool:
    """Would casting this rotation skill leave less than the reserve? The spec's rules, in order."""
    if reserve <= 0:
        return False
    if skill_id in DRAINS_ALL_ENERGY_SKILL_IDS:
        return True
    if cost <= 0 or energy_buff or skill_id in ENERGY_GAIN_SKILL_IDS:
        return False
    if current >= maximum:
        return False  # a full bar never blocks, so a skill costing more than maximum - reserve is never stuck
    return current - cost < reserve


def cannot_interrupt(current: Optional[float], costs: Sequence[InterruptCost]) -> bool:
    """A ready interrupt exists and the energy pays for none of the ready ones."""
    ready_costs = [item.cost for item in costs if item.ready]
    return current is not None and bool(ready_costs) and all(current < cost for cost in ready_costs)


def make_energy_status(
    current: Optional[float], maximum: float, mode: ReserveMode, fixed: int, costs: Sequence[InterruptCost]
) -> EnergyStatus:
    cheapest = cheapest_interrupt(costs) if mode is ReserveMode.CHEAPEST else None
    return EnergyStatus(
        current=current,
        maximum=maximum,
        mode=mode,
        reserve=effective_reserve(mode, fixed, costs, maximum),
        reserve_skill_id=cheapest.skill_id if cheapest is not None else 0,
        cannot_interrupt=cannot_interrupt(current, costs),
    )


def energy_line(status: EnergyStatus, reserve_skill_name: str) -> str:
    if status.current is None:
        return "Energia: ?"
    head = f"Energia: {math.floor(status.current)}/{math.floor(status.maximum)}"
    if status.mode is ReserveMode.OFF:
        return f"{head} - reserva desligada"
    reserve = math.ceil(status.reserve)
    if status.mode is ReserveMode.FIXED:
        return f"{head} - reserva {reserve} (fixa)"
    return f"{head} - reserva {reserve} ({reserve_skill_name or 'sem interrupts'})"


def reserve_pause_text(skill_name: str) -> str:
    return f"rotacao em pausa: reserva para interrupt ({skill_name})"


def reserve_skipped_suffix(skill_name: str) -> str:
    return f" (reserva: saltou {skill_name})"
