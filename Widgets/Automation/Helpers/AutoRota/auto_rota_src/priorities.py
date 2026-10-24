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

LONG_CAST_MS = 2000

# In build mode the Auto Rota only interrupts casts up to this tier; lower tiers are left to the
# build's own (damage-optimised) interrupt logic.
BUILD_MODE_MAX_TIER = Tier.ELITE

# Member names of Py4GWCoreLib.enums_src.GameData_enums.Attribute. Kept as
# strings so this module stays importable outside the game runtime.
HEALING_ATTRIBUTE_NAMES: tuple[str, ...] = ("HealingPrayers", "ProtectionPrayers", "RestorationMagic")
