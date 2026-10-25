"""Offline unit tests for Auto Rota's interrupt energy reserve (no game runtime needed).

Run: python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_energy_reserve.py" -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import CANNOT_INTERRUPT_TEXT  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import DRAINS_ALL_ENERGY_SKILL_IDS  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import ENERGY_GAIN_SKILL_IDS  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import EnergyStatus  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import InterruptCost  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import ReserveMode  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import breaks_reserve  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import cannot_interrupt  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import cheapest_interrupt  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import effective_reserve  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import energy_line  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import make_energy_status  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import mode_from_setting  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import reserve_pause_text  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import reserve_skipped_suffix  # noqa: E402

ETHER_LORD = 41


def cost(skill_id: int, value: float, ready: bool = True) -> InterruptCost:
    return InterruptCost(skill_id=skill_id, cost=value, ready=ready)


class ModeFromSettingTests(unittest.TestCase):
    def test_known_texts_map_to_modes(self) -> None:
        for text, expected in (
            ("cheapest", ReserveMode.CHEAPEST),
            ("fixed", ReserveMode.FIXED),
            ("off", ReserveMode.OFF),
        ):
            observed = mode_from_setting(text)
            self.assertIs(observed, expected, f"mode_from_setting({text!r}) expected={expected} observed={observed}")

    def test_unknown_text_falls_back_to_cheapest(self) -> None:
        observed = mode_from_setting("garbage")
        self.assertIs(observed, ReserveMode.CHEAPEST, f"mode_from_setting('garbage') observed={observed}")


class EffectiveReserveTests(unittest.TestCase):
    def check(self, mode: ReserveMode, fixed: int, costs: list[InterruptCost], maximum: float, expected: float) -> None:
        observed = effective_reserve(mode, fixed, costs, maximum)
        self.assertEqual(
            observed,
            expected,
            f"effective_reserve({mode.name}, fixed={fixed}, costs={costs}, maximum={maximum}) "
            f"expected={expected} observed={observed}",
        )

    def test_off_is_zero(self) -> None:
        self.check(ReserveMode.OFF, 10, [cost(1, 10.0)], 50.0, 0.0)

    def test_fixed_uses_the_value(self) -> None:
        self.check(ReserveMode.FIXED, 10, [], 50.0, 10.0)

    def test_negative_fixed_is_zero(self) -> None:
        self.check(ReserveMode.FIXED, -5, [], 50.0, 0.0)

    def test_cheapest_takes_the_lowest_cost_ready_or_recharging(self) -> None:
        self.check(ReserveMode.CHEAPEST, 0, [cost(1, 10.0), cost(2, 5.0, ready=False), cost(3, 15.0)], 50.0, 5.0)

    def test_a_free_signet_makes_the_reserve_zero(self) -> None:
        self.check(ReserveMode.CHEAPEST, 0, [cost(1, 10.0), cost(2, 0.0)], 50.0, 0.0)

    def test_no_interrupts_means_no_reserve(self) -> None:
        self.check(ReserveMode.CHEAPEST, 0, [], 50.0, 0.0)

    def test_reserve_is_capped_at_half_the_maximum(self) -> None:
        self.check(ReserveMode.FIXED, 25, [], 40.0, 20.0)
        self.check(ReserveMode.CHEAPEST, 0, [cost(1, 15.0)], 20.0, 10.0)

    def test_unknown_maximum_means_no_reserve(self) -> None:
        self.check(ReserveMode.FIXED, 10, [], 0.0, 0.0)


class CheapestInterruptTests(unittest.TestCase):
    def test_ties_keep_the_first_in_priority_order(self) -> None:
        observed = cheapest_interrupt([cost(1, 10.0), cost(2, 10.0), cost(3, 15.0)])
        self.assertEqual(observed, cost(1, 10.0), f"cheapest with a tie observed={observed}")

    def test_no_interrupts_gives_none(self) -> None:
        observed = cheapest_interrupt([])
        self.assertIsNone(observed, f"cheapest of nothing observed={observed}")


class BreaksReserveTests(unittest.TestCase):
    def check(
        self,
        expected: bool,
        current: float = 30.0,
        skill_cost: float = 10.0,
        reserve: float = 10.0,
        maximum: float = 50.0,
        skill_id: int = 100,
        energy_buff: bool = False,
    ) -> None:
        observed = breaks_reserve(current, skill_cost, reserve, maximum, skill_id, energy_buff)
        self.assertEqual(
            observed,
            expected,
            f"breaks_reserve(current={current}, cost={skill_cost}, reserve={reserve}, maximum={maximum}, "
            f"skill_id={skill_id}, energy_buff={energy_buff}) expected={expected} observed={observed}",
        )

    def test_special_skill_ids_match_the_spec(self) -> None:
        # Drain Enchantment, Energy Drain, Energy Tap, Waste Not Want Not; Ether Lord (skill_descriptions.json).
        self.assertEqual(ENERGY_GAIN_SKILL_IDS, frozenset({68, 79, 80, 1995}), f"observed={ENERGY_GAIN_SKILL_IDS}")
        self.assertEqual(
            DRAINS_ALL_ENERGY_SKILL_IDS, frozenset({ETHER_LORD}), f"observed={DRAINS_ALL_ENERGY_SKILL_IDS}"
        )

    def test_zero_reserve_never_breaks(self) -> None:
        self.check(False, current=5.0, reserve=0.0)

    def test_ether_lord_breaks_even_on_a_full_bar(self) -> None:
        self.check(True, current=50.0, skill_cost=5.0, skill_id=ETHER_LORD)
        self.check(True, current=30.0, skill_cost=5.0, skill_id=ETHER_LORD)

    def test_free_skills_never_break(self) -> None:
        self.check(False, current=5.0, skill_cost=0.0)

    def test_energy_buff_skills_never_break(self) -> None:
        self.check(False, current=5.0, skill_cost=5.0, energy_buff=True)

    def test_energy_gain_skills_never_break(self) -> None:
        for skill_id in (68, 79, 80, 1995):
            self.check(False, current=12.0, skill_cost=5.0, skill_id=skill_id)

    def test_a_full_bar_never_breaks(self) -> None:
        # cost + reserve > maximum: without this the skill could never be cast.
        self.check(False, current=40.0, skill_cost=25.0, reserve=20.0, maximum=40.0)

    def test_below_the_reserve_after_paying_breaks(self) -> None:
        self.check(True, current=19.0, skill_cost=10.0, reserve=10.0)

    def test_exactly_the_reserve_after_paying_does_not_break(self) -> None:
        self.check(False, current=20.0, skill_cost=10.0, reserve=10.0)


class CannotInterruptTests(unittest.TestCase):
    def check(self, current: Optional[float], costs: list[InterruptCost], expected: bool) -> None:
        observed = cannot_interrupt(current, costs)
        self.assertEqual(
            observed, expected, f"cannot_interrupt({current}, {costs}) expected={expected} observed={observed}"
        )

    def test_no_ready_interrupt_is_not_a_warning(self) -> None:
        self.check(5.0, [cost(1, 10.0, ready=False)], False)

    def test_one_affordable_ready_interrupt_is_enough(self) -> None:
        self.check(10.0, [cost(1, 10.0), cost(2, 15.0)], False)

    def test_no_affordable_ready_interrupt_warns(self) -> None:
        self.check(9.0, [cost(1, 10.0), cost(2, 15.0), cost(3, 5.0, ready=False)], True)

    def test_unknown_energy_is_not_a_warning(self) -> None:
        self.check(None, [cost(1, 10.0)], False)


def status(
    current: Optional[float],
    mode: ReserveMode = ReserveMode.CHEAPEST,
    reserve: float = 10.0,
    skill_id: int = 500,
) -> EnergyStatus:
    return EnergyStatus(
        current=current, maximum=50.0, mode=mode, reserve=reserve, reserve_skill_id=skill_id, cannot_interrupt=False
    )


class TextTests(unittest.TestCase):
    def check(self, observed: str, expected: str) -> None:
        self.assertEqual(observed, expected, f"expected={expected!r} observed={observed!r}")

    def test_unknown_energy(self) -> None:
        self.check(energy_line(status(None), "Cry of Frustration"), "Energia: ?")

    def test_cheapest_mode_names_the_interrupt_and_rounds(self) -> None:
        self.check(
            energy_line(status(23.7, reserve=9.5), "Cry of Frustration"),
            "Energia: 23/50 - reserva 10 (Cry of Frustration)",
        )

    def test_fixed_mode(self) -> None:
        self.check(energy_line(status(23.0, ReserveMode.FIXED, 10.0, 0), ""), "Energia: 23/50 - reserva 10 (fixa)")

    def test_off_mode(self) -> None:
        self.check(energy_line(status(23.0, ReserveMode.OFF, 0.0, 0), ""), "Energia: 23/50 - reserva desligada")

    def test_cheapest_mode_without_interrupts(self) -> None:
        self.check(
            energy_line(status(23.0, reserve=0.0, skill_id=0), ""), "Energia: 23/50 - reserva 0 (sem interrupts)"
        )

    def test_warning_pause_and_skip_texts(self) -> None:
        self.check(CANNOT_INTERRUPT_TEXT, "sem energia para interromper")
        self.check(reserve_pause_text("Empathy"), "rotacao em pausa: reserva para interrupt (Empathy)")
        self.check(reserve_skipped_suffix("Empathy"), " (reserva: saltou Empathy)")


class MakeEnergyStatusTests(unittest.TestCase):
    def check(self, observed: EnergyStatus, expected: EnergyStatus) -> None:
        self.assertEqual(observed, expected, f"expected={expected} observed={observed}")

    def test_cheapest_status_names_the_cheapest_interrupt(self) -> None:
        observed = make_energy_status(30.0, 50.0, ReserveMode.CHEAPEST, 10, [cost(7, 10.0), cost(8, 5.0, ready=False)])
        expected = EnergyStatus(
            current=30.0,
            maximum=50.0,
            mode=ReserveMode.CHEAPEST,
            reserve=5.0,
            reserve_skill_id=8,
            cannot_interrupt=False,
        )
        self.check(observed, expected)

    def test_fixed_status_has_no_reserve_skill(self) -> None:
        observed = make_energy_status(4.0, 50.0, ReserveMode.FIXED, 10, [cost(7, 10.0)])
        expected = EnergyStatus(
            current=4.0, maximum=50.0, mode=ReserveMode.FIXED, reserve=10.0, reserve_skill_id=0, cannot_interrupt=True
        )
        self.check(observed, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
