"""Plain data types for Auto Rota's decision core.

This module must not import Py4GWCoreLib: the decision core runs offline in
unit tests, outside the injected Guild Wars runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class CastKind(IntEnum):
    SPELL = 0
    CHANT = 1
    ATTACK = 2
    OTHER = 3


class InterruptReach(IntEnum):
    ANY_CAST = 0
    SPELL = 1
    SPELL_OR_CHANT = 2
    ATTACK = 3


@dataclass(frozen=True)
class EnemyCast:
    agent_id: int
    skill_id: int
    kind: CastKind
    is_resurrection: bool
    is_healing: bool
    is_elite: bool
    activation_ms: int
    remaining_ms: int


@dataclass(frozen=True)
class InterruptSlot:
    slot: int  # index in CombatClass.skills (priority order)
    bar_slot: int  # 1-based skillbar slot passed to SkillBar.UseSkill
    skill_id: int
    reach: InterruptReach


@dataclass(frozen=True)
class Decision:
    bar_slot: int
    skill_id: int
    target_id: int
    label: str
    enemy_skill_id: int = 0  # 0 = no enemy cast (rotation play)


@dataclass(frozen=True)
class BuildCandidate:
    primary_is_mesmer: bool
    is_fallback_candidate: bool  # e.g. the generic HeroAI build GetBestBuild returns when nothing matches
    overrides_skill_casting: bool  # e.g. farm builds with their own multi-cast ProcessSkillCasting
