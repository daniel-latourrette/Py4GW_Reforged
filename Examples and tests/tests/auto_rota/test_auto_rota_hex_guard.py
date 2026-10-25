"""Offline unit tests for Auto Rota's punishing-hex guard (no game runtime needed).

Run: python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py" -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import PUNISHING_HEXES  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import active_punishing_hexes  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import build_paused_by_guard  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import guard_reason  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import guarded_skill_ids  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import history_text  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import warning_text  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import ActionKind  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import ActiveHex  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import BarSkill  # noqa: E402

BACKFIRE = 28
EMPATHY = 26
SPITEFUL_SPIRIT = 121
SPOIL_VICTOR = 1066
CACOPHONY = 1998
NOT_PUNISHING = 5  # a skill id that is not in the table

# The catalogue of docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md, by category.
SPELL_IDS = frozenset({28, 128, 804, 979, 3191, 46, 51, 127})
ATTACK_IDS = frozenset({26, 3151, 123, 66, 43, 47, 2056, 3195, 227})
ANY_SKILL_IDS = frozenset({121, 878, 3234, 30, 52})
ATTACK_AND_SPELL_IDS = frozenset({1066, 3233})
SHOUT_OR_CHANT_IDS = frozenset({1998})
SPEC_IDS = SPELL_IDS | ATTACK_IDS | ANY_SKILL_IDS | ATTACK_AND_SPELL_IDS | SHOUT_OR_CHANT_IDS

SPELL = BarSkill(skill_id=1001, kind=ActionKind.SPELL)
ATTACK = BarSkill(skill_id=1002, kind=ActionKind.ATTACK)
SIGNET = BarSkill(skill_id=1003, kind=ActionKind.OTHER)
SHOUT = BarSkill(skill_id=1004, kind=ActionKind.SHOUT_OR_CHANT)
FULL_BAR = (SPELL, ATTACK, SIGNET, SHOUT)


class CatalogueTests(unittest.TestCase):
    def test_catalogue_holds_exactly_the_spec_ids(self) -> None:
        observed = frozenset(PUNISHING_HEXES)
        self.assertEqual(
            observed, SPEC_IDS, f"missing={sorted(SPEC_IDS - observed)} extra={sorted(observed - SPEC_IDS)}"
        )

    def test_categories_match_the_spec(self) -> None:
        expected: dict[int, frozenset[ActionKind]] = {}
        expected.update({skill_id: frozenset({ActionKind.SPELL}) for skill_id in SPELL_IDS})
        expected.update({skill_id: frozenset({ActionKind.ATTACK}) for skill_id in ATTACK_IDS})
        expected.update({skill_id: frozenset(ActionKind) for skill_id in ANY_SKILL_IDS})
        expected.update(
            {skill_id: frozenset({ActionKind.ATTACK, ActionKind.SPELL}) for skill_id in ATTACK_AND_SPELL_IDS}
        )
        expected.update({skill_id: frozenset({ActionKind.SHOUT_OR_CHANT}) for skill_id in SHOUT_OR_CHANT_IDS})
        for skill_id, punishes in expected.items():
            observed = PUNISHING_HEXES[skill_id].punishes
            self.assertEqual(
                observed,
                punishes,
                f"skill {skill_id} ({PUNISHING_HEXES[skill_id].name}) "
                f"expected={sorted(punishes)} observed={sorted(observed)}",
            )

    def test_hexes_that_end_on_skill_use_are_never_listed(self) -> None:
        # Wastrel's Worry and Wastrel's Demise end when the player uses a skill: pausing makes them hit harder.
        for skill_id in (50, 1335):
            self.assertNotIn(skill_id, PUNISHING_HEXES, f"skill {skill_id} must never be guarded")

    def test_every_entry_has_a_warning_text(self) -> None:
        for skill_id, entry in PUNISHING_HEXES.items():
            observed = warning_text(ActiveHex(skill_id=skill_id, remaining_ms=1000))
            self.assertTrue(observed.startswith(f"{entry.name} em ti: "), f"skill {skill_id}: observed={observed!r}")


class ActivePunishingHexesTests(unittest.TestCase):
    def check(self, effects: list[tuple[int, int, float]], expected: tuple[ActiveHex, ...]) -> None:
        observed = active_punishing_hexes(effects)
        self.assertEqual(observed, expected, f"effects={effects} expected={expected} observed={observed}")

    def test_ignores_effects_outside_the_table(self) -> None:
        self.check([(NOT_PUNISHING, 5000, 10.0), (BACKFIRE, 5000, 10.0)], (ActiveHex(BACKFIRE, 5000),))

    def test_duplicates_keep_the_longest_time(self) -> None:
        self.check(
            [(BACKFIRE, 3000, 10.0), (BACKFIRE, 7000, 10.0), (BACKFIRE, 5000, 10.0)], (ActiveHex(BACKFIRE, 7000),)
        )

    def test_implausible_or_zero_time_is_unknown_but_the_hex_still_counts(self) -> None:
        # Wrapped unsigned value, zero, and above duration + 1 s of slack.
        for remaining_ms in (4_294_967_000, 0, 11_001):
            self.check([(BACKFIRE, remaining_ms, 10.0)], (ActiveHex(BACKFIRE, None),))

    def test_slack_accepts_a_time_just_above_the_duration(self) -> None:
        self.check([(BACKFIRE, 10_500, 10.0)], (ActiveHex(BACKFIRE, 10_500),))
        self.check([(BACKFIRE, 11_000, 10.0)], (ActiveHex(BACKFIRE, 11_000),))  # the limit itself is plausible

    def test_a_known_time_wins_over_an_unknown_one(self) -> None:
        # Plausibility is decided per copy, before duplicates are compared: a wrapped copy never wins.
        for unknown_ms in (0, 4_294_967_000):
            self.check([(BACKFIRE, unknown_ms, 10.0), (BACKFIRE, 4000, 10.0)], (ActiveHex(BACKFIRE, 4000),))
            self.check([(BACKFIRE, 4000, 10.0), (BACKFIRE, unknown_ms, 10.0)], (ActiveHex(BACKFIRE, 4000),))


class GuardedSkillIdsTests(unittest.TestCase):
    def check(self, hex_ids: list[int], expected_ids: list[int], bar: Sequence[BarSkill] = FULL_BAR) -> None:
        hexes = [ActiveHex(skill_id=hex_id, remaining_ms=5000) for hex_id in hex_ids]
        observed = guarded_skill_ids(bar, hexes)
        self.assertEqual(
            observed,
            frozenset(expected_ids),
            f"hexes={hex_ids} bar={[(skill.skill_id, skill.kind.name) for skill in bar]} "
            f"expected={sorted(expected_ids)} observed={sorted(observed)}",
        )

    def test_no_hex_blocks_nothing(self) -> None:
        self.check([], [])

    def test_backfire_blocks_spells_but_not_signets_or_attacks(self) -> None:
        self.check([BACKFIRE], [SPELL.skill_id])

    def test_empathy_blocks_attacks_only(self) -> None:
        self.check([EMPATHY], [ATTACK.skill_id])

    def test_spiteful_spirit_blocks_every_skill(self) -> None:
        self.check([SPITEFUL_SPIRIT], [SPELL.skill_id, ATTACK.skill_id, SIGNET.skill_id, SHOUT.skill_id])

    def test_spoil_victor_blocks_attacks_and_spells(self) -> None:
        self.check([SPOIL_VICTOR], [SPELL.skill_id, ATTACK.skill_id])

    def test_cacophony_blocks_shouts_and_chants_only(self) -> None:
        self.check([CACOPHONY], [SHOUT.skill_id])

    def test_two_hexes_block_the_union(self) -> None:
        self.check([BACKFIRE, EMPATHY], [SPELL.skill_id, ATTACK.skill_id])

    def test_empty_slots_are_never_blocked(self) -> None:
        self.check([BACKFIRE], [SPELL.skill_id], bar=(BarSkill(skill_id=0, kind=ActionKind.SPELL), SPELL))

    def test_ids_outside_the_table_block_nothing(self) -> None:
        self.check([NOT_PUNISHING], [])


class BuildPausedByGuardTests(unittest.TestCase):
    def check(self, guarded: frozenset[int], build_ids: list[int], expected: bool) -> None:
        observed = build_paused_by_guard(guarded, build_ids)
        self.assertEqual(
            observed, expected, f"guarded={sorted(guarded)} build={build_ids} expected={expected} observed={observed}"
        )

    def test_pauses_when_the_guard_blocks_a_build_skill(self) -> None:
        self.check(frozenset({1001}), [1001, 1005], True)

    def test_keeps_the_build_when_the_guard_misses_it(self) -> None:
        self.check(frozenset({1002}), [1001, 1005], False)

    def test_never_pauses_without_a_guard(self) -> None:
        self.check(frozenset(), [1001], False)


class TextTests(unittest.TestCase):
    def check(self, observed: str, expected: str) -> None:
        self.assertEqual(observed, expected, f"expected={expected!r} observed={observed!r}")

    def test_warning_rounds_seconds_up(self) -> None:
        self.check(warning_text(ActiveHex(BACKFIRE, 6200)), "Backfire em ti: spells em pausa (7 s)")

    def test_warning_shows_a_question_mark_for_an_unknown_time(self) -> None:
        self.check(warning_text(ActiveHex(EMPATHY, None)), "Empathy em ti: ataques em pausa (? s)")

    def test_warning_names_every_kind_of_pause(self) -> None:
        self.check(
            warning_text(ActiveHex(SPITEFUL_SPIRIT, 2500)), "Spiteful Spirit em ti: todas as skills em pausa (3 s)"
        )
        self.check(warning_text(ActiveHex(SPOIL_VICTOR, 1000)), "Spoil Victor em ti: ataques e spells em pausa (1 s)")
        self.check(warning_text(ActiveHex(CACOPHONY, 900)), "Cacophony em ti: shouts e chants em pausa (1 s)")

    def test_history_lines(self) -> None:
        self.check(history_text(BACKFIRE, started=True), "Guarda: Backfire - spells em pausa")
        self.check(history_text(BACKFIRE, started=False), "Guarda: Backfire acabou")

    def test_guard_reason_joins_hex_names(self) -> None:
        self.check(guard_reason((ActiveHex(BACKFIRE, 1000), ActiveHex(EMPATHY, None))), "Backfire, Empathy")


if __name__ == "__main__":
    unittest.main(verbosity=2)
