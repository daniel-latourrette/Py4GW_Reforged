"""Interrupt priority tiers for Auto Rota. Edit this file to tune priorities."""

from __future__ import annotations

from enum import IntEnum


class Tier(IntEnum):
    # Lower value means higher priority.
    RESURRECTION = 1
    HEALING = 2
    ELITE = 3
    LONG_CAST = 4
    OTHER = 5


TIER_LABELS: dict[Tier, str] = {
    Tier.RESURRECTION: "Ressurreicao",
    Tier.HEALING: "Cura",
    Tier.ELITE: "Elite",
    Tier.LONG_CAST: "Cast longo",
    Tier.OTHER: "Outro",
}

# RGBA for the cast watch window (warm = must stop, grey = least important).
TIER_COLORS: dict[Tier, tuple[float, float, float, float]] = {
    Tier.RESURRECTION: (0.95, 0.40, 0.40, 1.0),
    Tier.HEALING: (1.00, 0.65, 0.25, 1.0),
    Tier.ELITE: (1.00, 0.84, 0.30, 1.0),
    Tier.LONG_CAST: (0.55, 0.75, 1.00, 1.0),
    Tier.OTHER: (0.55, 0.55, 0.55, 1.0),
}

LONG_CAST_MS = 2000

# In build mode the Auto Rota only interrupts casts up to this tier; lower tiers are left to the
# build's own (damage-optimised) interrupt logic.
BUILD_MODE_MAX_TIER = Tier.ELITE

# Member names of Py4GWCoreLib.enums_src.GameData_enums.Attribute. Kept as
# strings so this module stays importable outside the game runtime.
HEALING_ATTRIBUTE_NAMES: tuple[str, ...] = ("HealingPrayers", "ProtectionPrayers", "RestorationMagic")
