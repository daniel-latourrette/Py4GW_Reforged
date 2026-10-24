"""Offline unit tests for the Auto Rota decision core (no game runtime needed).

Run: python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import can_hit  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import choose_interrupt  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import classify  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import CastKind  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import Decision  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import EnemyCast  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import InterruptReach  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import InterruptSlot  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import TIER_LABELS  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import Tier  # noqa: E402


def make_cast(
    agent_id: int = 1,
    skill_id: int = 100,
    kind: CastKind = CastKind.SPELL,
    is_resurrection: bool = False,
    is_healing: bool = False,
    is_elite: bool = False,
    activation_ms: int = 1000,
    remaining_ms: int = 800,
) -> EnemyCast:
    return EnemyCast(
        agent_id=agent_id,
        skill_id=skill_id,
        kind=kind,
        is_resurrection=is_resurrection,
        is_healing=is_healing,
        is_elite=is_elite,
        activation_ms=activation_ms,
        remaining_ms=remaining_ms,
    )


class ClassifyTests(unittest.TestCase):
    def assert_tier(self, cast: EnemyCast, expected: Tier) -> None:
        observed = classify(cast)
        self.assertEqual(observed, expected, f"classify({cast}) expected={expected.name} observed={observed.name}")

    def test_resurrection_wins_over_every_other_flag(self) -> None:
        self.assert_tier(
            make_cast(is_resurrection=True, is_healing=True, is_elite=True, activation_ms=5000), Tier.RESURRECTION
        )

    def test_healing_wins_over_elite_and_long_cast(self) -> None:
        self.assert_tier(make_cast(is_healing=True, is_elite=True, activation_ms=5000), Tier.HEALING)

    def test_elite_wins_over_long_cast(self) -> None:
        self.assert_tier(make_cast(is_elite=True, activation_ms=5000), Tier.ELITE)

    def test_long_cast_boundary_is_inclusive(self) -> None:
        self.assert_tier(make_cast(activation_ms=2000), Tier.LONG_CAST)

    def test_just_below_long_cast_is_other(self) -> None:
        self.assert_tier(make_cast(activation_ms=1999), Tier.OTHER)

    def test_every_tier_has_a_label(self) -> None:
        missing = set(Tier) - set(TIER_LABELS)
        self.assertEqual(missing, set(), f"TIER_LABELS is missing labels for tiers: {sorted(t.name for t in missing)}")


class CanHitTests(unittest.TestCase):
    EXPECTED: dict[InterruptReach, set[CastKind]] = {
        InterruptReach.ANY_CAST: {CastKind.SPELL, CastKind.CHANT, CastKind.ATTACK, CastKind.OTHER},
        InterruptReach.SPELL: {CastKind.SPELL},
        InterruptReach.SPELL_OR_CHANT: {CastKind.SPELL, CastKind.CHANT},
        InterruptReach.ATTACK: {CastKind.ATTACK},
    }

    def test_full_reach_matrix(self) -> None:
        for reach, hittable in self.EXPECTED.items():
            for kind in CastKind:
                expected = kind in hittable
                observed = can_hit(reach, kind)
                with self.subTest(reach=reach.name, kind=kind.name):
                    self.assertEqual(
                        observed,
                        expected,
                        f"can_hit(reach={reach.name}, kind={kind.name}) expected={expected} observed={observed}",
                    )

    def test_expected_covers_every_reach(self) -> None:
        missing = set(InterruptReach) - set(self.EXPECTED)
        self.assertEqual(missing, set(), f"EXPECTED is missing reaches: {sorted(r.name for r in missing)}")


def make_slot(
    slot: int = 0, bar_slot: int = 1, skill_id: int = 500, reach: InterruptReach = InterruptReach.ANY_CAST
) -> InterruptSlot:
    return InterruptSlot(slot=slot, bar_slot=bar_slot, skill_id=skill_id, reach=reach)


def always(_slot: InterruptSlot, _cast: EnemyCast) -> bool:
    return True


class ChooseInterruptTests(unittest.TestCase):
    def assert_choice(
        self,
        observed: Optional[Decision],
        expected_target: Optional[int],
        expected_skill: Optional[int],
        context: str,
    ) -> None:
        if expected_target is None:
            self.assertIsNone(observed, f"{context}: expected no decision, observed={observed}")
            return
        self.assertIsNotNone(observed, f"{context}: expected target={expected_target}, observed=None")
        assert observed is not None
        self.assertEqual(
            (observed.target_id, observed.skill_id),
            (expected_target, expected_skill),
            f"{context}: expected (target, skill)=({expected_target}, {expected_skill}) observed={observed}",
        )

    def test_no_casts_returns_none(self) -> None:
        self.assert_choice(choose_interrupt([], [make_slot()], always), None, None, "no casts")

    def test_no_slots_returns_none(self) -> None:
        self.assert_choice(choose_interrupt([make_cast()], [], always), None, None, "no slots")

    def test_resurrection_beats_healing_listed_first(self) -> None:
        casts = [make_cast(agent_id=10, is_healing=True), make_cast(agent_id=20, is_resurrection=True)]
        observed = choose_interrupt(casts, [make_slot(skill_id=500)], always)
        self.assert_choice(observed, 20, 500, "resurrection vs healing")

    def test_same_tier_prefers_cast_finishing_first(self) -> None:
        casts = [
            make_cast(agent_id=10, is_healing=True, remaining_ms=900),
            make_cast(agent_id=20, is_healing=True, remaining_ms=400),
        ]
        observed = choose_interrupt(casts, [make_slot()], always)
        self.assert_choice(observed, 20, 500, "same tier, earlier finish")

    def test_spell_only_interrupt_ignores_attack(self) -> None:
        casts = [make_cast(agent_id=10, kind=CastKind.ATTACK, is_elite=True)]
        slots = [make_slot(skill_id=501, reach=InterruptReach.SPELL_OR_CHANT)]
        self.assert_choice(choose_interrupt(casts, slots, always), None, None, "power spike vs attack")

    def test_uses_first_feasible_slot_in_priority_order(self) -> None:
        slots = [make_slot(slot=0, bar_slot=1, skill_id=501), make_slot(slot=1, bar_slot=2, skill_id=502)]
        observed = choose_interrupt([make_cast(agent_id=10)], slots, always)
        self.assert_choice(observed, 10, 501, "both feasible, first slot wins")

    def test_skips_infeasible_slot(self) -> None:
        slots = [make_slot(slot=0, bar_slot=1, skill_id=501), make_slot(slot=1, bar_slot=2, skill_id=502)]

        def only_502(slot: InterruptSlot, _cast: EnemyCast) -> bool:
            return slot.skill_id == 502

        observed = choose_interrupt([make_cast(agent_id=10)], slots, only_502)
        self.assert_choice(observed, 10, 502, "first slot infeasible")

    def test_unreachable_high_tier_falls_back_to_lower_tier(self) -> None:
        casts = [make_cast(agent_id=10, is_resurrection=True), make_cast(agent_id=20, is_elite=True)]

        def not_agent_10(_slot: InterruptSlot, cast: EnemyCast) -> bool:
            return cast.agent_id != 10

        observed = choose_interrupt(casts, [make_slot()], not_agent_10)
        self.assert_choice(observed, 20, 500, "resurrection out of reach")

    def test_tier_outranks_remaining_time(self) -> None:
        casts = [
            make_cast(agent_id=10, is_healing=True, remaining_ms=200),
            make_cast(agent_id=20, is_resurrection=True, remaining_ms=1500),
        ]
        observed = choose_interrupt(casts, [make_slot()], always)
        self.assert_choice(observed, 20, 500, "higher tier finishing later still wins")

    def test_exact_tie_keeps_first_cast(self) -> None:
        casts = [make_cast(agent_id=10, is_elite=True), make_cast(agent_id=20, is_elite=True)]
        observed = choose_interrupt(casts, [make_slot()], always)
        self.assert_choice(observed, 10, 500, "same tier and remaining time")

    def test_feasibility_is_only_checked_when_needed(self) -> None:
        calls: list[tuple[int, int]] = []

        def spy(slot: InterruptSlot, cast: EnemyCast) -> bool:
            calls.append((slot.skill_id, cast.agent_id))
            return True

        casts = [make_cast(agent_id=20, is_elite=True), make_cast(agent_id=10, is_resurrection=True)]
        slots = [make_slot(skill_id=601, reach=InterruptReach.ATTACK), make_slot(skill_id=602)]
        choose_interrupt(casts, slots, spy)
        self.assertEqual(calls, [(602, 10)], f"feasibility calls expected=[(602, 10)] observed={calls}")

    def test_decision_carries_bar_slot_label_and_enemy_skill(self) -> None:
        cast = make_cast(agent_id=10, skill_id=777, is_healing=True)
        observed = choose_interrupt([cast], [make_slot(bar_slot=6, skill_id=501)], always)
        expected = Decision(bar_slot=6, skill_id=501, target_id=10, label="Interrupt: Cura", enemy_skill_id=777)
        self.assertEqual(observed, expected, f"full decision expected={expected} observed={observed}")

    def test_max_tier_skips_casts_below_the_limit(self) -> None:
        casts = [make_cast(agent_id=10, activation_ms=3000), make_cast(agent_id=20)]
        observed = choose_interrupt(casts, [make_slot()], always, max_tier=Tier.ELITE)
        self.assert_choice(observed, None, None, "only long-cast and other casts, limit ELITE")

    def test_max_tier_blocks_fall_through_to_lower_tiers(self) -> None:
        casts = [make_cast(agent_id=10, activation_ms=3000), make_cast(agent_id=20, is_healing=True)]

        def not_agent_20(_slot: InterruptSlot, cast: EnemyCast) -> bool:
            return cast.agent_id != 20

        observed = choose_interrupt(casts, [make_slot()], not_agent_20, max_tier=Tier.ELITE)
        self.assert_choice(observed, None, None, "healing infeasible, long cast above limit ELITE must not be picked")

    def test_max_tier_includes_casts_at_the_limit(self) -> None:
        casts = [make_cast(agent_id=20, remaining_ms=100), make_cast(agent_id=10, is_elite=True, remaining_ms=900)]
        observed = choose_interrupt(casts, [make_slot()], always, max_tier=Tier.ELITE)
        self.assert_choice(observed, 10, 500, "elite cast at limit ELITE beats an earlier-finishing OTHER cast")

    def test_default_max_tier_allows_every_tier(self) -> None:
        observed = choose_interrupt([make_cast(agent_id=10)], [make_slot()], always)
        self.assert_choice(observed, 10, 500, "OTHER cast with default limit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
