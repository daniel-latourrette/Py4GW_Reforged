"""Offline unit tests for the Combat Meter core (no game runtime needed).

Run: python3.12 "Examples and tests/tests/combat_meter/test_combat_meter.py" -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from Widgets.Automation.Helpers.CombatMeter.combat_meter_src.meter import ARMOR_IGNORING  # noqa: E402
from Widgets.Automation.Helpers.CombatMeter.combat_meter_src.meter import CRITICAL  # noqa: E402
from Widgets.Automation.Helpers.CombatMeter.combat_meter_src.meter import DAMAGE  # noqa: E402
from Widgets.Automation.Helpers.CombatMeter.combat_meter_src.meter import HEALING  # noqa: E402
from Widgets.Automation.Helpers.CombatMeter.combat_meter_src.meter import Channel  # noqa: E402
from Widgets.Automation.Helpers.CombatMeter.combat_meter_src.meter import CombatMeter  # noqa: E402
from Widgets.Automation.Helpers.CombatMeter.combat_meter_src.meter import classify_event  # noqa: E402
from Widgets.Automation.Helpers.CombatMeter.combat_meter_src.meter import health_amount  # noqa: E402


class ClassifyEventTests(unittest.TestCase):
    def assert_classified(self, event_type: int, fraction: float, expected: object) -> None:
        observed = classify_event(event_type, fraction)
        self.assertEqual(
            observed, expected, f"classify_event({event_type}, {fraction}) expected={expected} observed={observed}"
        )

    def test_damage_and_critical_use_the_magnitude(self) -> None:
        self.assert_classified(DAMAGE, 0.25, (Channel.DAMAGE, 0.25))
        self.assert_classified(CRITICAL, -0.5, (Channel.DAMAGE, 0.5))

    def test_armor_ignoring_counts_either_sign(self) -> None:
        # The sign is unverified in-game; heals are filtered later by the receiver being an ally.
        self.assert_classified(ARMOR_IGNORING, 0.1, (Channel.DAMAGE, 0.1))
        self.assert_classified(ARMOR_IGNORING, -0.1, (Channel.DAMAGE, 0.1))

    def test_healing_uses_the_magnitude(self) -> None:
        self.assert_classified(HEALING, 0.2, (Channel.HEALING, 0.2))

    def test_other_events_and_zero_values_are_ignored(self) -> None:
        self.assert_classified(1, 0.5, None)
        self.assert_classified(DAMAGE, 0.0, None)


class HealthAmountTests(unittest.TestCase):
    def test_known_max_health_is_exact(self) -> None:
        self.assertEqual(health_amount(0.5, known_max_hp=600, level=20), (300.0, False))

    def test_unknown_max_health_is_estimated_from_level(self) -> None:
        # Most creatures: 80 + 20 * level health (level 20 -> 480).
        self.assertEqual(health_amount(0.5, known_max_hp=0, level=20), (240.0, True))


class CombatMeterTests(unittest.TestCase):
    def test_rows_are_sorted_with_per_second_and_share(self) -> None:
        meter = CombatMeter(fight_gap_ms=8000)
        meter.record(Channel.DAMAGE, "Mesmer", 300.0, False, 1000)
        meter.record(Channel.DAMAGE, "Hero", 100.0, True, 3000)
        rows = meter.summary(Channel.DAMAGE, current_fight=True)
        observed = [(r.name, r.total, r.per_second, r.share, r.estimated) for r in rows]
        expected = [("Mesmer", 300.0, 150.0, 0.75, False), ("Hero", 100.0, 50.0, 0.25, True)]
        self.assertEqual(observed, expected, f"rows expected={expected} observed={observed}")

    def test_gap_starts_a_new_fight_but_total_keeps_everything(self) -> None:
        meter = CombatMeter(fight_gap_ms=8000)
        meter.record(Channel.DAMAGE, "Mesmer", 100.0, False, 1000)
        meter.record(Channel.DAMAGE, "Mesmer", 100.0, False, 3000)
        meter.record(Channel.DAMAGE, "Mesmer", 50.0, False, 20000)
        current = meter.summary(Channel.DAMAGE, current_fight=True)
        total = meter.summary(Channel.DAMAGE, current_fight=False)
        self.assertEqual(current[0].total, 50.0, f"current fight should only hold the new event: {current}")
        self.assertEqual(total[0].total, 250.0, f"total should keep every event: {total}")

    def test_total_per_second_counts_only_combat_time(self) -> None:
        meter = CombatMeter(fight_gap_ms=8000)
        meter.record(Channel.DAMAGE, "Mesmer", 100.0, False, 0)
        meter.record(Channel.DAMAGE, "Mesmer", 100.0, False, 2000)  # first fight: 2 s
        meter.record(Channel.DAMAGE, "Mesmer", 100.0, False, 60000)
        meter.record(Channel.DAMAGE, "Mesmer", 100.0, False, 62000)  # second fight: 2 s
        total = meter.summary(Channel.DAMAGE, current_fight=False)
        self.assertEqual(total[0].per_second, 100.0, f"400 over 4 s of combat expected 100/s, got {total}")

    def test_single_event_fight_counts_as_one_second(self) -> None:
        meter = CombatMeter(fight_gap_ms=8000)
        meter.record(Channel.HEALING, "Monk", 80.0, False, 5000)
        rows = meter.summary(Channel.HEALING, current_fight=True)
        self.assertEqual(rows[0].per_second, 80.0, f"one-event fight should use 1 s, got {rows}")

    def test_channels_are_independent_and_reset_clears_all(self) -> None:
        meter = CombatMeter(fight_gap_ms=8000)
        meter.record(Channel.DAMAGE, "Mesmer", 100.0, False, 1000)
        self.assertEqual(meter.summary(Channel.HEALING, current_fight=True), [], "healing must stay empty")
        meter.reset()
        self.assertEqual(meter.summary(Channel.DAMAGE, current_fight=False), [], "reset must clear the total")


if __name__ == "__main__":
    unittest.main(verbosity=2)
