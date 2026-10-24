"""Pure decision core for Auto Rota.

This module must not import Py4GWCoreLib: it runs offline in unit tests.
"""

from __future__ import annotations

from typing import Callable
from typing import Optional
from typing import Sequence

from .model import CastKind
from .model import Decision
from .model import EnemyCast
from .model import InterruptReach
from .model import InterruptSlot
from .priorities import LONG_CAST_MS
from .priorities import TIER_LABELS
from .priorities import Tier


def classify(cast: EnemyCast) -> Tier:
    """Return the first matching tier, checked from highest to lowest priority."""
    if cast.is_resurrection:
        return Tier.RESURRECTION
    if cast.is_healing:
        return Tier.HEALING
    if cast.is_elite:
        return Tier.ELITE
    if cast.activation_ms >= LONG_CAST_MS:
        return Tier.LONG_CAST
    return Tier.OTHER


def can_hit(reach: InterruptReach, kind: CastKind) -> bool:
    """Return whether an interrupt with this reach can stop a cast of this kind.

    ANY_CAST hits every kind, including OTHER (signets, shouts); the others only hit their named kinds.
    """
    if reach == InterruptReach.ANY_CAST:
        return True
    if reach == InterruptReach.SPELL:
        return kind == CastKind.SPELL
    if reach == InterruptReach.SPELL_OR_CHANT:
        return kind in (CastKind.SPELL, CastKind.CHANT)
    if reach == InterruptReach.ATTACK:
        return kind == CastKind.ATTACK
    raise ValueError(f"Unhandled InterruptReach: {reach!r}")


FeasibilityCheck = Callable[[InterruptSlot, EnemyCast], bool]


def _cast_key(cast: EnemyCast) -> tuple[int, int]:
    return (int(classify(cast)), cast.remaining_ms)


def choose_interrupt(
    casts: Sequence[EnemyCast],
    slots: Sequence[InterruptSlot],
    feasible: FeasibilityCheck,
) -> Optional[Decision]:
    """Pick the best (interrupt, cast) pair.

    Casts are tried by lowest tier, then earliest finish (input order breaks exact ties). For each
    cast, slots are tried in the given order (CombatClass priority order); `feasible` is only called
    for slots whose reach can hit the cast.
    """
    for cast in sorted(casts, key=_cast_key):
        tier = classify(cast)
        for slot in slots:
            if can_hit(slot.reach, cast.kind) and feasible(slot, cast):
                return Decision(
                    bar_slot=slot.bar_slot,
                    skill_id=slot.skill_id,
                    target_id=cast.agent_id,
                    label=f"Interrupt: {TIER_LABELS[tier]}",
                    enemy_skill_id=cast.skill_id,
                )
    return None
