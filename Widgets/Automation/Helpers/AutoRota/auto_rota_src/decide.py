"""Pure decision core for Auto Rota.

This module must not import Py4GWCoreLib: it runs offline in unit tests.
"""

from __future__ import annotations

from typing import Callable
from typing import Optional
from typing import Sequence

from .model import BuildCandidate
from .model import CastKind
from .model import CastRow
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


def _first_slot(cast: EnemyCast, slots: Sequence[InterruptSlot], feasible: FeasibilityCheck) -> Optional[InterruptSlot]:
    """First slot, in the given (CombatClass priority) order, that can hit the cast and lands in time."""
    for slot in slots:
        if can_hit(slot.reach, cast.kind) and feasible(slot, cast):
            return slot
    return None


def _interrupt_decision(cast: EnemyCast, slot: InterruptSlot, tier: Tier) -> Decision:
    return Decision(
        bar_slot=slot.bar_slot,
        skill_id=slot.skill_id,
        target_id=cast.agent_id,
        label=f"Interrupt: {TIER_LABELS[tier]}",
        enemy_skill_id=cast.skill_id,
    )


def choose_interrupt(
    casts: Sequence[EnemyCast],
    slots: Sequence[InterruptSlot],
    feasible: FeasibilityCheck,
    max_tier: Tier = Tier.OTHER,
) -> Optional[Decision]:
    """Pick the best (interrupt, cast) pair.

    Casts are tried by lowest tier, then earliest finish (input order breaks exact ties). Casts whose
    tier is above `max_tier` are ignored. For each cast, slots are tried in the given order
    (CombatClass priority order); `feasible` is only called for slots whose reach can hit the cast.
    """
    for cast in sorted(casts, key=_cast_key):
        tier = classify(cast)
        if tier > max_tier:
            break  # casts are sorted by tier, so every remaining cast is above the limit too
        slot = _first_slot(cast, slots, feasible)
        if slot is not None:
            return _interrupt_decision(cast, slot, tier)
    return None


def cast_rows(casts: Sequence[EnemyCast], slots: Sequence[InterruptSlot], feasible: FeasibilityCheck) -> list[CastRow]:
    """Every cast in choose_interrupt's order, each with its first feasible slot (eager: the cast watch lists all)."""
    return [
        CastRow(cast=cast, tier=classify(cast), slot=_first_slot(cast, slots, feasible))
        for cast in sorted(casts, key=_cast_key)
    ]


def interrupt_from_rows(rows: Sequence[CastRow], max_tier: Tier = Tier.OTHER) -> Optional[Decision]:
    """The decision choose_interrupt makes, read from cast_rows output (same order, same slot rule)."""
    for row in rows:
        if row.tier > max_tier:
            break
        if row.slot is not None:
            return _interrupt_decision(row.cast, row.slot, row.tier)
    return None


def is_eligible_build(candidate: BuildCandidate) -> bool:
    """A build can drive one key press only if it is a regular Mesmer combat build."""
    return (
        candidate.primary_is_mesmer and not candidate.is_fallback_candidate and not candidate.overrides_skill_casting
    )
