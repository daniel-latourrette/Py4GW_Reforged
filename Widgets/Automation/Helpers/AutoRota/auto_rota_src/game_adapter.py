"""Runtime bridge between Auto Rota's pure decision core and the live game.

This is the only Auto Rota module that touches Py4GWCoreLib/HeroAI. It owns a
private CombatClass: CacheData is a process-wide singleton shared with HeroAI,
so it is only read (account options, and inside CombatClass.Update), and the
skill and targeting toggles forced in _sync_combat() live only on the private
instance, never on the CombatClass that HeroAI itself drives.
"""

from __future__ import annotations

import time
from typing import Optional
from typing import Sequence

from Py4GWCoreLib import GLOBAL_CACHE
from Py4GWCoreLib import ActionQueueManager
from Py4GWCoreLib import Agent
from Py4GWCoreLib import AgentArray
from Py4GWCoreLib import Player
from Py4GWCoreLib import Range
from Py4GWCoreLib import Routines
from Py4GWCoreLib import Utils
from Py4GWCoreLib.enums_src.GameData_enums import Attribute
from Py4GWCoreLib.enums_src.GameData_enums import SkillType
from Py4GWCoreLib.GlobalCache.HexRemovalPriority import get_hexed_ally_for_removal
from Py4GWCoreLib.HeroAI.cache_data import CacheData
from Py4GWCoreLib.HeroAI.combat import MAX_SKILLS
from Py4GWCoreLib.HeroAI.combat import CombatClass
from Py4GWCoreLib.HeroAI.combat import custom_skill_data_handler
from Py4GWCoreLib.HeroAI.interrupt import cast_observer
from Py4GWCoreLib.HeroAI.interrupt import is_interrupt_feasible
from Py4GWCoreLib.HeroAI.types import SkillNature
from Py4GWCoreLib.HeroAI.types import Skilltarget
from Py4GWCoreLib.py4gwcorelib_src.Console import Console
from Py4GWCoreLib.py4gwcorelib_src.Console import ConsoleLog
from Py4GWCoreLib.py4gwcorelib_src.WidgetManager import get_widget_handler

from .decide import choose_interrupt
from .model import CastKind
from .model import Decision
from .model import EnemyCast
from .model import InterruptReach
from .model import InterruptSlot
from .priorities import HEALING_ATTRIBUTE_NAMES
from .priorities import Tier

LOG_SENDER = "Auto Rota"

REASON_HEROAI = "HeroAI com combate ligado"
REASON_NOT_EXPLORABLE = "fora de combate (outpost)"
REASON_DEAD = "personagem morto"
REASON_BUSY = "ocupado"

# Blockers that switch the Auto Rota toggle off (as opposed to "busy", which only delays the next play).
STOP_REASONS: frozenset[str] = frozenset({REASON_HEROAI, REASON_NOT_EXPLORABLE, REASON_DEAD})

_ENEMY_ALLEGIANCE = 3  # Py4GWCoreLib Allegiance.Enemy

_DEBOUNCE_MS = 250
_AFTERCAST_MS = 250

_REACH_BY_ALLEGIANCE: dict[int, InterruptReach] = {
    Skilltarget.EnemyCasting.value: InterruptReach.ANY_CAST,
    Skilltarget.EnemyCastingSpell.value: InterruptReach.SPELL,
    Skilltarget.EnemyCastingSpellOrChant.value: InterruptReach.SPELL_OR_CHANT,
    Skilltarget.EnemyAttacking.value: InterruptReach.ATTACK,
}

# GetAppropiateTarget resolves these allegiances with reserve=True, which posts a
# cross-account whiteboard lock (resurrection / hex-removal / minion-corpse). That is right for
# a real cast but wrong for the 10 Hz preview, which would leave phantom locks blocking the
# other multibox accounts. Verified in Py4GWCoreLib/HeroAI/combat.py (the only reserve=True calls).
_RESERVING_ALLEGIANCES: frozenset[int] = frozenset(
    {
        Skilltarget.ResurrectionAlly.value,
        Skilltarget.HexedAlly.value,
        Skilltarget.ExploitableCorpse.value,
    }
)

# Attack skills (enemy-targeted, not interrupts) go to the target the player selected. With
# is_targeting_enabled False, CombatClass.GetAppropiateTarget returns Player.GetTargetID(), so the
# skill's cast conditions are checked against that target (e.g. a hex is not re-applied).
_PLAYER_TARGETED_ALLEGIANCES: frozenset[int] = frozenset(
    {
        Skilltarget.Enemy.value,
        Skilltarget.EnemyCaster.value,
        Skilltarget.EnemyMartial.value,
        Skilltarget.EnemyMartialMelee.value,
        Skilltarget.EnemyMartialRanged.value,
        Skilltarget.EnemyClustered.value,
        Skilltarget.EnemyAttacking.value,
        Skilltarget.EnemyCasting.value,
        Skilltarget.EnemyCastingSpell.value,
        Skilltarget.EnemyCastingSpellOrChant.value,
        Skilltarget.EnemyInjured.value,
        Skilltarget.EnemyConditioned.value,
        Skilltarget.EnemyHexed.value,
        Skilltarget.EnemyDegenHexed.value,
        Skilltarget.EnemyEnchanted.value,
        Skilltarget.EnemyMoving.value,
        Skilltarget.EnemyKnockedDown.value,
        Skilltarget.EnemyBleeding.value,
        Skilltarget.EnemyPoisoned.value,
        Skilltarget.EnemyCrippled.value,
        Skilltarget.EnemyHealthy.value,
        Skilltarget.EnemyNotNearby.value,
    }
)

_MARTIAL_ALLEGIANCES: frozenset[int] = frozenset(
    {
        Skilltarget.EnemyMartial.value,
        Skilltarget.EnemyMartialMelee.value,
        Skilltarget.EnemyMartialRanged.value,
    }
)

# Flags.IsSpell only matches the plain "Spell" type; hexes, enchantments,
# wells, wards and weapon/item spells are spells for interrupt purposes too.
_SPELL_TYPES: frozenset[int] = frozenset(
    {
        SkillType.Spell.value,
        SkillType.Hex.value,
        SkillType.Enchantment.value,
        SkillType.Well.value,
        SkillType.Ward.value,
        SkillType.WeaponSpell.value,
        SkillType.ItemSpell.value,
    }
)

_HEALING_ATTRIBUTE_IDS: frozenset[int] = frozenset(Attribute[name].value for name in HEALING_ATTRIBUTE_NAMES)


def _cast_kind(skill_id: int) -> CastKind:
    skill_type, _ = GLOBAL_CACHE.Skill.GetType(skill_id)
    if skill_type == SkillType.Attack.value:
        return CastKind.ATTACK
    if skill_type == SkillType.Chant.value:
        return CastKind.CHANT
    if skill_type in _SPELL_TYPES:
        return CastKind.SPELL
    return CastKind.OTHER


def _skill_name(skill_id: int) -> str:
    name = GLOBAL_CACHE.Skill.GetName(skill_id)
    return name.replace("_", " ") if name else f"skill {skill_id}"


class GameAdapter:
    def __init__(self, cached_data: CacheData) -> None:
        self._cached_data = cached_data
        self._combat = CombatClass()
        self._last_execute_s: float = 0.0
        self._logged_failures: set[tuple[int, int]] = set()

    def _sync_combat(self, blocked_skill_ids: Sequence[int] = ()) -> CombatClass:
        """Rebuild the private CombatClass from the live skillbar right before a decision."""
        combat = self._combat
        combat.Update(self._cached_data)
        combat.PrioritizeSkills()
        combat.ApplyBlockedSkillIDs(list(blocked_skill_ids))
        combat.is_skill_enabled = [True] * MAX_SKILLS
        combat.is_targeting_enabled = True
        return combat

    def heroai_conflict(self) -> bool:
        if not get_widget_handler().is_widget_enabled("HeroAI"):
            return False
        options = self._cached_data.account_options
        return bool(options is not None and options.Combat)

    def blocker(self) -> Optional[str]:
        """Return why no play may be made right now, or None."""
        if self.heroai_conflict():
            return REASON_HEROAI
        if not Routines.Checks.Map.IsExplorable():
            return REASON_NOT_EXPLORABLE
        player_id = Player.GetAgentID()
        if not Agent.IsAlive(player_id):
            return REASON_DEAD
        is_casting = Agent.IsCasting(player_id) or (GLOBAL_CACHE.SkillBar.GetCasting() or 0) != 0
        if Agent.IsKnockedDown(player_id) or is_casting:
            return REASON_BUSY
        if (time.monotonic() - self._last_execute_s) * 1000.0 < _DEBOUNCE_MS:
            return REASON_BUSY
        if not ActionQueueManager().IsEmpty("ACTION"):
            return REASON_BUSY  # a queued cast has not run yet: never stack another behind it
        return None

    def _enemy_casts(self) -> list[EnemyCast]:
        player_xy = Player.GetXY()
        casts: list[EnemyCast] = []
        for agent_id in AgentArray.GetEnemyArray():
            skill_id = 0
            try:
                if not Agent.IsAlive(agent_id) or not Agent.IsCasting(agent_id):
                    continue
                if Utils.Distance(player_xy, Agent.GetXY(agent_id)) > Range.Longbow.value:
                    continue
                skill_id = Agent.GetCastingSkillID(agent_id)
                if skill_id == 0:
                    continue
                casts.append(self._describe_cast(agent_id, skill_id))
            except Exception as exc:
                key = (agent_id, skill_id)
                if key not in self._logged_failures:
                    if len(self._logged_failures) > 256:
                        self._logged_failures.clear()
                    self._logged_failures.add(key)
                    ConsoleLog(
                        LOG_SENDER, f"enemy_casts: ignoring agent {agent_id}: {exc}", Console.MessageType.Warning
                    )
        return casts

    def _describe_cast(self, agent_id: int, skill_id: int) -> EnemyCast:
        activation_ms = int((GLOBAL_CACHE.Skill.Data.GetActivation(skill_id) or 0.0) * 1000)
        elapsed_ms = cast_observer.elapsed_ms(agent_id, skill_id) or 0
        nature = custom_skill_data_handler.get_skill(skill_id).Nature
        attribute_id = int(GLOBAL_CACHE.Skill.Attribute.GetAttribute(skill_id))
        return EnemyCast(
            agent_id=agent_id,
            skill_id=skill_id,
            kind=_cast_kind(skill_id),
            is_resurrection=nature == SkillNature.Resurrection.value,
            is_healing=nature == SkillNature.Healing.value or attribute_id in _HEALING_ATTRIBUTE_IDS,
            is_elite=bool(GLOBAL_CACHE.Skill.Flags.IsElite(skill_id)),
            activation_ms=activation_ms,
            remaining_ms=max(0, activation_ms - elapsed_ms),
        )

    def _interrupt_slots(self) -> list[InterruptSlot]:
        combat = self._combat
        slots: list[InterruptSlot] = []
        for index, skill in enumerate(combat.GetSkills()):
            data = skill.custom_skill_data
            if data.Nature != SkillNature.Interrupt.value:
                continue
            reach = _REACH_BY_ALLEGIANCE.get(int(data.TargetAllegiance))
            if reach is None:
                continue
            if not combat.IsSkillReady(index):
                continue
            if not self._has_resources(skill.skill_id, int(skill.skillbar_data.adrenaline_a)):
                continue
            slots.append(
                InterruptSlot(slot=index, bar_slot=combat.skill_order[index] + 1, skill_id=skill.skill_id, reach=reach)
            )
        return slots

    def _has_resources(self, skill_id: int, adrenaline_a: int) -> bool:
        # Mirrors the adrenaline/energy gates of CombatClass.IsReadyToCast,
        # which cannot be reused here because it also picks its own target.
        combat = self._combat
        player_id = Player.GetAgentID()
        adrenaline_required = GLOBAL_CACHE.Skill.Data.GetAdrenaline(skill_id)
        if adrenaline_required > 0 and adrenaline_a < adrenaline_required:
            return False
        energy_fraction = combat.GetEnergyValues(player_id)
        if energy_fraction < 0.0:
            return False
        current_energy = energy_fraction * Agent.GetMaxEnergy(player_id)
        energy_cost = Routines.Checks.Skills.GetEnergyCostWithEffects(skill_id, player_id)
        if combat.expertise_exists:
            energy_cost = Routines.Checks.Skills.apply_expertise_reduction(
                energy_cost, combat.expertise_level, skill_id
            )
        return current_energy >= energy_cost

    def _is_feasible(self, slot: InterruptSlot, cast: EnemyCast) -> bool:
        combat = self._combat
        return is_interrupt_feasible(
            target_agent_id=cast.agent_id,
            our_skill_id=slot.skill_id,
            fast_casting_level=combat.fast_casting_level,
            ping_ms=int(combat.ping_handler.GetCurrentPing()),
        )

    @staticmethod
    def _selected_enemy() -> int:
        """The player's selected target if it is a living enemy within cast range, else 0.

        Out-of-range targets count as "no target": UseSkill would make the character walk there,
        overriding the player's own movement.
        """
        target_id = int(Player.GetTargetID() or 0)
        if target_id == 0 or not Agent.IsValid(target_id) or not Agent.IsLiving(target_id):
            return 0
        if Agent.IsDead(target_id):
            return 0
        allegiance, _ = Agent.GetAllegiance(target_id)
        if int(allegiance) != _ENEMY_ALLEGIANCE:
            return 0
        if Utils.Distance(Player.GetXY(), Agent.GetXY(target_id)) > Range.Spellcast.value:
            return 0
        return target_id

    @staticmethod
    def _matches_target_kind(allegiance: int, target_id: int) -> bool:
        # These filters only live in HeroAI's target resolver, which is bypassed for the selected target.
        if allegiance == Skilltarget.EnemyCaster.value:
            return Agent.IsCaster(target_id)
        if allegiance in _MARTIAL_ALLEGIANCES:
            return Agent.IsMartial(target_id)
        if allegiance == Skilltarget.EnemyKnockedDown.value:
            return Agent.IsKnockedDown(target_id)
        return True

    def _rotation_decision(self, preview: bool = False) -> Optional[Decision]:
        combat = self._combat
        selected_enemy = self._selected_enemy()
        for index, skill in enumerate(combat.GetSkills()):
            data = skill.custom_skill_data
            allegiance = int(data.TargetAllegiance)
            if data.Nature == SkillNature.Interrupt.value and allegiance in _REACH_BY_ALLEGIANCE:
                continue  # handled by the interrupt layer; other interrupt skills rotate normally
            if not combat.IsSkillReady(index):
                continue
            attacks_selected_target = allegiance in _PLAYER_TARGETED_ALLEGIANCES
            if attacks_selected_target:
                if selected_enemy == 0:
                    continue  # no enemy selected in range: never pick a fight on our own
                # Like HeroAI, only strict skills insist on the target kind: Agent.IsCaster/IsMartial go by weapon
                # type, which many monsters lack, so a non-strict Backfire must still go on such a target.
                strict = bool(data.Conditions.TargetingStrict)
                if strict and not self._matches_target_kind(allegiance, selected_enemy):
                    continue
            elif not combat.in_aggro and not combat.IsOOCSkill(index):
                continue  # out of combat only out-of-combat skills, like HeroAI (no buff spam while walking)
            combat.is_targeting_enabled = not attacks_selected_target
            if preview and allegiance in _RESERVING_ALLEGIANCES:
                # IsReadyToCast would reserve a cross-account lock: only check readiness and look the
                # target up without reserving; the real (reserving) lookup happens on an actual play.
                if not self._has_resources(skill.skill_id, int(skill.skillbar_data.adrenaline_a)):
                    continue
                # ExploitableCorpse keeps target_id 0 ("alvo ao carregar"): GetNearestExploitableCorpse logs a
                # CorpseDebug line on every call, which would spam at 10 Hz.
                preview_target = 0
                if allegiance == Skilltarget.ResurrectionAlly.value:
                    preview_target = int(Routines.Agents.GetResurrectionTarget(Range.Spellcast.value) or 0)
                elif allegiance == Skilltarget.HexedAlly.value:
                    preview_target = int(get_hexed_ally_for_removal(Range.Spellcast.value) or 0)
                if preview_target == 0 and allegiance != Skilltarget.ExploitableCorpse.value:
                    continue
                return Decision(
                    bar_slot=combat.skill_order[index] + 1,
                    skill_id=skill.skill_id,
                    target_id=preview_target,
                    label="Rotacao",
                )
            ready, target_id = combat.IsReadyToCast(index)
            if not ready or target_id == 0 or not Agent.IsLiving(target_id):
                continue
            return Decision(
                bar_slot=combat.skill_order[index] + 1, skill_id=skill.skill_id, target_id=target_id, label="Rotacao"
            )
        return None

    def next_decision(self, preview: bool = False) -> Optional[Decision]:
        self._sync_combat()
        interrupt = choose_interrupt(self._enemy_casts(), self._interrupt_slots(), self._is_feasible)
        if interrupt is not None:
            return interrupt
        return self._rotation_decision(preview)

    def interrupt_decision(self, max_tier: Tier) -> Optional[Decision]:
        """Interrupt layer only (build mode): no rotation fallback, never reserves targets."""
        self._sync_combat()
        return choose_interrupt(self._enemy_casts(), self._interrupt_slots(), self._is_feasible, max_tier=max_tier)

    def rotation_after_build(self, blocked_skill_ids: Sequence[int]) -> Optional[Decision]:
        """Rotation over the skills the build does not own (actual plays only, never the preview)."""
        self._sync_combat(blocked_skill_ids)
        return self._rotation_decision(preview=False)

    def note_external_cast(self) -> None:
        """Start the debounce after a cast queued outside execute() (e.g. by a build pass)."""
        self._last_execute_s = time.monotonic()

    def execute(self, decision: Decision) -> None:
        GLOBAL_CACHE.SkillBar.UseSkill(decision.bar_slot, decision.target_id, aftercast_delay=_AFTERCAST_MS)
        self._last_execute_s = time.monotonic()

    def describe(self, decision: Decision, no_target_text: str = "(alvo ao carregar)") -> str:
        if decision.target_id == 0:
            target_name = no_target_text
        else:
            target_name = Agent.GetNameByID(decision.target_id) or f"agente {decision.target_id}"
        text = f"{_skill_name(decision.skill_id)} -> {target_name}"
        if decision.enemy_skill_id:
            text += f" ({_skill_name(decision.enemy_skill_id)})"
        return f"{text} [{decision.label}]"
