"""Punishing-hex guard: which of the player's own skills a hex on the player punishes.

This module must not import Py4GWCoreLib: it runs offline in unit tests. Hexes are keyed by skill id
(checked against Py4GWCoreLib/skill_descriptions.json), not by name: Skill.GetID(name) is native and the
repo spells some names two ways. Spec: docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

from .model import ActionKind
from .model import ActiveHex
from .model import BarSkill

_SPELLS: frozenset[ActionKind] = frozenset({ActionKind.SPELL})
_ATTACKS: frozenset[ActionKind] = frozenset({ActionKind.ATTACK})
_ANY_SKILL: frozenset[ActionKind] = frozenset(ActionKind)
_ATTACKS_AND_SPELLS: frozenset[ActionKind] = frozenset({ActionKind.ATTACK, ActionKind.SPELL})
_SHOUTS_AND_CHANTS: frozenset[ActionKind] = frozenset({ActionKind.SHOUT_OR_CHANT})

_PAUSED_TEXT: dict[frozenset[ActionKind], str] = {
    _SPELLS: "spells",
    _ATTACKS: "ataques",
    _ANY_SKILL: "todas as skills",
    _ATTACKS_AND_SPELLS: "ataques e spells",
    _SHOUTS_AND_CHANTS: "shouts e chants",
}

# A remaining time above the effect's own duration plus this slack is not trusted (e.g. an unsigned value
# that wrapped at expiry): the hex still blocks, the window just shows "?".
_TIME_SLACK_MS = 1000


@dataclass(frozen=True)
class PunishingHex:
    name: str
    punishes: frozenset[ActionKind]


# Never add Wastrel's Worry (50) or Wastrel's Demise (1335): using a skill ENDS them, so pausing makes them
# hit harder. The repeated names are the separate "(PvP)" skill ids, which follow the same rule.
PUNISHING_HEXES: dict[int, PunishingHex] = {
    # Spells. Guilt and Mistrust only punish spells on foes, Shame and Mark of Subversion only spells on
    # allies, but HeroAI's target data cannot tell them apart (unknown skills default to Enemy), so these
    # pause every spell, for at most 6 s.
    28: PunishingHex("Backfire", _SPELLS),
    128: PunishingHex("Soul Leech", _SPELLS),
    804: PunishingHex("Arcane Languor", _SPELLS),
    979: PunishingHex("Mistrust", _SPELLS),
    3191: PunishingHex("Mistrust", _SPELLS),
    46: PunishingHex("Guilt", _SPELLS),
    51: PunishingHex("Shame", _SPELLS),
    127: PunishingHex("Mark of Subversion", _SPELLS),
    # Attacks
    26: PunishingHex("Empathy", _ATTACKS),
    3151: PunishingHex("Empathy", _ATTACKS),
    123: PunishingHex("Insidious Parasite", _ATTACKS),
    66: PunishingHex("Spirit Shackles", _ATTACKS),
    43: PunishingHex("Clumsiness", _ATTACKS),
    47: PunishingHex("Ineptitude", _ATTACKS),
    2056: PunishingHex("Wandering Eye", _ATTACKS),
    3195: PunishingHex("Wandering Eye", _ATTACKS),
    227: PunishingHex("Glimmering Mark", _ATTACKS),
    # Any skill
    121: PunishingHex("Spiteful Spirit", _ANY_SKILL),
    878: PunishingHex("Visions of Regret", _ANY_SKILL),
    3234: PunishingHex("Visions of Regret", _ANY_SKILL),
    30: PunishingHex("Diversion", _ANY_SKILL),
    52: PunishingHex("Panic", _ANY_SKILL),
    # Attacks and spells
    1066: PunishingHex("Spoil Victor", _ATTACKS_AND_SPELLS),
    3233: PunishingHex("Spoil Victor", _ATTACKS_AND_SPELLS),
    # Shouts and chants
    1998: PunishingHex("Cacophony", _SHOUTS_AND_CHANTS),
}


def _plausible_ms(remaining_ms: int, duration_s: float) -> Optional[int]:
    if remaining_ms <= 0 or remaining_ms > duration_s * 1000.0 + _TIME_SLACK_MS:
        return None
    return remaining_ms


def _longer(candidate: Optional[int], current: Optional[int]) -> bool:
    if candidate is None:
        return False
    return current is None or candidate > current


def active_punishing_hexes(effects: Iterable[tuple[int, int, float]]) -> tuple[ActiveHex, ...]:
    """Punishing hexes among (skill_id, remaining_ms, duration_s) effects, one per id.

    Duplicates keep the longest known time. A hex counts while its effect exists, whatever its time.
    """
    best: dict[int, Optional[int]] = {}
    for skill_id, remaining_ms, duration_s in effects:
        if skill_id not in PUNISHING_HEXES:
            continue
        remaining = _plausible_ms(remaining_ms, duration_s)
        if skill_id not in best or _longer(remaining, best[skill_id]):
            best[skill_id] = remaining
    return tuple(ActiveHex(skill_id=skill_id, remaining_ms=remaining) for skill_id, remaining in best.items())


def guarded_skill_ids(bar: Sequence[BarSkill], hexes: Sequence[ActiveHex]) -> frozenset[int]:
    """Ids of the bar skills that an active punishing hex would punish (empty slots never count)."""
    punished: set[ActionKind] = set()
    for active in hexes:
        entry = PUNISHING_HEXES.get(active.skill_id)
        if entry is not None:
            punished |= entry.punishes
    return frozenset(skill.skill_id for skill in bar if skill.skill_id != 0 and skill.kind in punished)


def build_paused_by_guard(guarded: frozenset[int], build_skill_ids: Iterable[int]) -> bool:
    """A build pass cannot skip single skills: the whole build waits while the guard blocks one of them."""
    return not guarded.isdisjoint(build_skill_ids)


def warning_text(active: ActiveHex) -> str:
    entry = PUNISHING_HEXES[active.skill_id]
    seconds = "?" if active.remaining_ms is None else str(math.ceil(active.remaining_ms / 1000))
    return f"{entry.name} em ti: {_PAUSED_TEXT[entry.punishes]} em pausa ({seconds} s)"


def history_text(skill_id: int, started: bool) -> str:
    entry = PUNISHING_HEXES[skill_id]
    if started:
        return f"Guarda: {entry.name} - {_PAUSED_TEXT[entry.punishes]} em pausa"
    return f"Guarda: {entry.name} acabou"


def guard_reason(hexes: Sequence[ActiveHex]) -> str:
    """Names of the active punishing hexes, for the preview's "build em pausa (...)"."""
    return ", ".join(PUNISHING_HEXES[active.skill_id].name for active in hexes)
