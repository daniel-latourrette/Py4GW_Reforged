"""Runtime bridge between Auto Rota's pure decision core and the live game.

This is the only Auto Rota module that touches Py4GWCoreLib/HeroAI. It owns a
private CombatClass: CacheData is a process-wide singleton shared with HeroAI,
so it is only read (account options, and inside CombatClass.Update), and the
skill and targeting toggles forced in _sync_combat() live only on the private
instance, never on the CombatClass that HeroAI itself drives.
"""

from __future__ import annotations

import time
from typing import Iterable
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
from Py4GWCoreLib.Effect import Effects
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

from .decide import cast_rows
from .decide import choose_interrupt
from .decide import interrupt_from_rows
from .energy_reserve import EnergyStatus
from .energy_reserve import InterruptCost
from .energy_reserve import ReserveMode
from .energy_reserve import breaks_reserve
from .energy_reserve import effective_reserve
from .energy_reserve import make_energy_status
from .hex_guard import active_punishing_hexes
from .model import ActionKind
from .model import ActiveHex
from .model import BarSkill
from .model import CastKind
from .model import CastRow
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

# Skills the player's buff toggle controls (e.g. Mantras, Channeling, Ether Signet, Arcane Echo).
_BUFF_NATURES: frozenset[int] = frozenset(
    {
        SkillNature.Buff.value,
        SkillNature.EnergyBuff.value,
        SkillNature.SelfTargeted.value,
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


def _action_kind(skill_id: int) -> ActionKind:
    """Kind of a skill on the player's own bar, for the punishing-hex guard (signets are OTHER, not spells)."""
    skill_type, _ = GLOBAL_CACHE.Skill.GetType(skill_id)
    if skill_type in _SPELL_TYPES:
        return ActionKind.SPELL
    if skill_type == SkillType.Attack.value:
        return ActionKind.ATTACK
    if skill_type in (SkillType.Shout.value, SkillType.Chant.value):
        return ActionKind.SHOUT_OR_CHANT
    return ActionKind.OTHER


def _skill_name(skill_id: int) -> str:
    name = GLOBAL_CACHE.Skill.GetName(skill_id)
    return name.replace("_", " ") if name else f"skill {skill_id}"


class GameAdapter:
    def __init__(self, cached_data: CacheData) -> None:
        self._cached_data = cached_data
        self._combat = CombatClass()
        self._last_execute_s: float = 0.0
        self._logged_failures: set[tuple[int, int]] = set()
        # First rotation skill the energy reserve skipped in the last decision (0: none), for the preview line.
        self.reserve_skip_skill_id: int = 0

    def _sync_combat(self, blocked_skill_ids: Iterable[int] = ()) -> CombatClass:
        """Rebuild the private CombatClass from the live skillbar right before a decision."""
        combat = self._combat
        combat.Update(self._cached_data)
        combat.PrioritizeSkills()
        combat.ApplyBlockedSkillIDs(list(blocked_skill_ids))
        combat.is_skill_enabled = [True] * MAX_SKILLS
        combat.is_targeting_enabled = True
        self.reserve_skip_skill_id = 0
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
                # Spellcast is the widest reach of any interrupt: is_interrupt_feasible's range gate truncates the
                # distance to int and rejects anything farther. Mirror it exactly, so farther casts (never chosen)
                # are skipped and the cast watch lists exactly the casts the loop considers.
                if int(Utils.Distance(player_xy, Agent.GetXY(agent_id))) > Range.Spellcast.value:
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
        observed_ms = cast_observer.elapsed_ms(agent_id, skill_id)  # None until the observer has seen the cast
        elapsed_ms = observed_ms or 0
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
            elapsed_ms=observed_ms,
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

    def _current_energy(self) -> Optional[float]:
        """Current energy in points, read like IsReadyToCast (HeroAI mirror); None when it cannot be read."""
        player_id = Player.GetAgentID()
        energy_fraction = self._combat.GetEnergyValues(player_id)
        if energy_fraction < 0.0:
            return None
        return energy_fraction * Agent.GetMaxEnergy(player_id)

    def _energy_cost(self, skill_id: int) -> float:
        """Effective energy cost (effects such as Primal Echoes, then Expertise), as IsReadyToCast computes it."""
        combat = self._combat
        energy_cost = Routines.Checks.Skills.GetEnergyCostWithEffects(skill_id, Player.GetAgentID())
        if combat.expertise_exists:
            energy_cost = Routines.Checks.Skills.apply_expertise_reduction(
                energy_cost, combat.expertise_level, skill_id
            )
        return float(energy_cost)

    def _has_resources(self, skill_id: int, adrenaline_a: int) -> bool:
        # Mirrors the adrenaline/energy gates of CombatClass.IsReadyToCast,
        # which cannot be reused here because it also picks its own target.
        adrenaline_required = GLOBAL_CACHE.Skill.Data.GetAdrenaline(skill_id)
        if adrenaline_required > 0 and adrenaline_a < adrenaline_required:
            return False
        current_energy = self._current_energy()
        return current_energy is not None and current_energy >= self._energy_cost(skill_id)

    def _interrupt_costs(self) -> list[InterruptCost]:
        """Every interrupt-layer skill on the bar, ready or recharging, with its effective cost.

        No energy filter (it would drop the reserve to 0 exactly when energy is low) and no blocked-id filter:
        build-owned interrupts and the ones the hex guard pauses still need energy when they come back.
        """
        costs: list[InterruptCost] = []
        for skill in self._combat.GetSkills():
            data = skill.custom_skill_data
            if skill.skill_id == 0 or data.Nature != SkillNature.Interrupt.value:
                continue
            if int(data.TargetAllegiance) not in _REACH_BY_ALLEGIANCE:
                continue
            adrenaline_required = GLOBAL_CACHE.Skill.Data.GetAdrenaline(skill.skill_id)
            recharged = skill.skillbar_data.recharge == 0
            ready = recharged and int(skill.skillbar_data.adrenaline_a) >= adrenaline_required
            costs.append(InterruptCost(skill_id=skill.skill_id, cost=self._energy_cost(skill.skill_id), ready=ready))
        return costs

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

    def _rotation_decision(
        self,
        preview: bool = False,
        allow_buffs: bool = True,
        reserve_mode: ReserveMode = ReserveMode.OFF,
        reserve_fixed: int = 0,
    ) -> Optional[Decision]:
        combat = self._combat
        selected_enemy = self._selected_enemy()
        maximum_energy = float(Agent.GetMaxEnergy(Player.GetAgentID()))
        current_energy = self._current_energy()
        reserve = 0.0
        if reserve_mode is not ReserveMode.OFF and current_energy is not None:
            reserve = effective_reserve(reserve_mode, reserve_fixed, self._interrupt_costs(), maximum_energy)
        for index, skill in enumerate(combat.GetSkills()):
            data = skill.custom_skill_data
            allegiance = int(data.TargetAllegiance)
            if data.Nature == SkillNature.Interrupt.value and allegiance in _REACH_BY_ALLEGIANCE:
                continue  # handled by the interrupt layer; other interrupt skills rotate normally
            if not allow_buffs and data.Nature in _BUFF_NATURES:
                continue  # the player's buff toggle is off
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
            if reserve > 0 and current_energy is not None:
                energy_buff = data.Nature == SkillNature.EnergyBuff.value
                skill_cost = self._energy_cost(skill.skill_id)
                if breaks_reserve(current_energy, skill_cost, reserve, maximum_energy, skill.skill_id, energy_buff):
                    # Only an affordable skill is credited to the reserve: an unaffordable one would be refused
                    # anyway, so the preview must not blame the reserve for it.
                    if self.reserve_skip_skill_id == 0 and current_energy >= skill_cost:
                        self.reserve_skip_skill_id = skill.skill_id
                    # After the pure filters and before IsReadyToCast and the preview's target lookups,
                    # so a skipped skill never reserves a target lock.
                    continue
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

    def next_decision(
        self,
        preview: bool = False,
        allow_buffs: bool = True,
        blocked_skill_ids: Iterable[int] = (),
        rows: Optional[Sequence[CastRow]] = None,
        reserve_mode: ReserveMode = ReserveMode.OFF,
        reserve_fixed: int = 0,
    ) -> Optional[Decision]:
        # Blocked ids (the hex guard) must be passed on every call, the preview included:
        # ApplyBlockedSkillIDs replaces the set, so an omitted argument unblocks everything.
        self._sync_combat(blocked_skill_ids)
        if rows is None:
            interrupt = choose_interrupt(self._enemy_casts(), self._interrupt_slots(), self._is_feasible)
        else:
            interrupt = interrupt_from_rows(rows)  # rows from cast_watch() with the same blocked ids: no rescan
        if interrupt is not None:
            return interrupt
        return self._rotation_decision(
            preview=preview, allow_buffs=allow_buffs, reserve_mode=reserve_mode, reserve_fixed=reserve_fixed
        )

    def interrupt_decision(self, max_tier: Tier, blocked_skill_ids: Iterable[int] = ()) -> Optional[Decision]:
        """Interrupt layer only (build mode): no rotation fallback, never reserves targets."""
        self._sync_combat(blocked_skill_ids)
        return choose_interrupt(self._enemy_casts(), self._interrupt_slots(), self._is_feasible, max_tier=max_tier)

    def rotation_after_build(
        self,
        blocked_skill_ids: Sequence[int],
        allow_buffs: bool = True,
        reserve_mode: ReserveMode = ReserveMode.OFF,
        reserve_fixed: int = 0,
    ) -> Optional[Decision]:
        """Rotation over the skills the build does not own (actual plays only, never the preview)."""
        self._sync_combat(blocked_skill_ids)
        return self._rotation_decision(
            preview=False, allow_buffs=allow_buffs, reserve_mode=reserve_mode, reserve_fixed=reserve_fixed
        )

    @staticmethod
    def punishing_hexes_on_player() -> tuple[ActiveHex, ...]:
        """Punishing hexes on the local player, from the native effects list (not the multibox buff mirror)."""
        effects = Effects.GetEffects(Player.GetAgentID())
        return active_punishing_hexes(
            (int(effect.skill_id), int(effect.time_remaining), float(effect.duration)) for effect in effects
        )

    @staticmethod
    def bar_skills() -> list[BarSkill]:
        """The player's bar with each skill's kind, for the punishing-hex guard (empty slots skipped)."""
        skills: list[BarSkill] = []
        for slot in range(1, MAX_SKILLS + 1):
            skill_id = int(GLOBAL_CACHE.SkillBar.GetSkillIDBySlot(slot) or 0)
            if skill_id != 0:
                skills.append(BarSkill(skill_id=skill_id, kind=_action_kind(skill_id)))
        return skills

    def cast_watch(self, blocked_skill_ids: Iterable[int] = ()) -> list[CastRow]:
        """Every enemy cast in range with the interrupt that lands on it, read once (preview, list and key)."""
        self._sync_combat(blocked_skill_ids)
        return cast_rows(self._enemy_casts(), self._interrupt_slots(), self._is_feasible)

    def energy_status(self, mode: ReserveMode, fixed: int) -> EnergyStatus:
        """Energy, reserve and the "cannot interrupt" state for the window; call right after a sync (cast_watch)."""
        maximum_energy = float(Agent.GetMaxEnergy(Player.GetAgentID()))
        return make_energy_status(self._current_energy(), maximum_energy, mode, fixed, self._interrupt_costs())

    @staticmethod
    def agent_name(agent_id: int) -> str:
        return Agent.GetNameByID(agent_id) or f"agente {agent_id}"  # names decode asynchronously

    @staticmethod
    def skill_name(skill_id: int) -> str:
        return _skill_name(skill_id)

    @staticmethod
    def skill_icon_path(skill_id: int) -> str:
        """Relative icon path for ImGui.DrawTexture, or "" when the skill has no icon."""
        return GLOBAL_CACHE.Skill.ExtraData.GetTexturePath(skill_id)

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
