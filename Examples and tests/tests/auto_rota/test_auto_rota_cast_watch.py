"""Offline unit tests for Auto Rota's cast watch helpers (no game runtime needed).

Run: python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_cast_watch.py" -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from Widgets.Automation.Helpers.AutoRota.auto_rota_src.cast_watch import CastProgress  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.cast_watch import cast_progress  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.cast_watch import interrupt_text  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import CastKind  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import CastRow  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import EnemyCast  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import InterruptReach  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import InterruptSlot  # noqa: E402
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.priorities import Tier  # noqa: E402


def make_cast(activation_ms: int = 2000, elapsed_ms: Optional[int] = 1000) -> EnemyCast:
    seen_ms = elapsed_ms or 0
    return EnemyCast(
        agent_id=1,
        skill_id=100,
        kind=CastKind.SPELL,
        is_resurrection=False,
        is_healing=False,
        is_elite=False,
        activation_ms=activation_ms,
        remaining_ms=max(0, activation_ms - seen_ms),
        elapsed_ms=elapsed_ms,
    )


class CastProgressTests(unittest.TestCase):
    def check(self, cast: EnemyCast, seconds_since_read: float, expected: CastProgress) -> None:
        observed = cast_progress(cast, seconds_since_read)
        self.assertEqual(
            observed,
            expected,
            f"cast_progress(activation={cast.activation_ms}, elapsed={cast.elapsed_ms}, "
            f"since_read={seconds_since_read}) expected={expected} observed={observed}",
        )

    def test_a_cast_not_seen_yet_has_no_reading(self) -> None:
        self.check(make_cast(elapsed_ms=None), 0.0, CastProgress(fraction=None, label="?"))

    def test_an_instant_cast_has_no_reading(self) -> None:
        self.check(make_cast(activation_ms=0, elapsed_ms=0), 0.0, CastProgress(fraction=None, label="?"))

    def test_half_way_shows_the_seconds_left(self) -> None:
        self.check(make_cast(elapsed_ms=1000), 0.0, CastProgress(fraction=0.5, label="1.0s"))

    def test_the_bar_advances_between_reads(self) -> None:
        self.check(make_cast(elapsed_ms=1000), 0.5, CastProgress(fraction=0.75, label="0.5s"))

    def test_a_fresh_cast_starts_empty(self) -> None:
        self.check(make_cast(elapsed_ms=0), 0.0, CastProgress(fraction=0.0, label="2.0s"))

    def test_slightly_past_the_end_is_full_without_the_warning(self) -> None:
        self.check(make_cast(elapsed_ms=2300), 0.0, CastProgress(fraction=1.0, label="0.0s"))

    def test_well_past_the_end_says_it_may_be_finishing(self) -> None:
        self.check(make_cast(elapsed_ms=2301), 0.0, CastProgress(fraction=1.0, label="a terminar?"))
        self.check(make_cast(elapsed_ms=2000), 0.4, CastProgress(fraction=1.0, label="a terminar?"))


class InterruptTextTests(unittest.TestCase):
    def test_a_row_with_a_slot_names_the_interrupt(self) -> None:
        slot = InterruptSlot(slot=0, bar_slot=1, skill_id=500, reach=InterruptReach.ANY_CAST)
        row = CastRow(cast=make_cast(), tier=Tier.OTHER, slot=slot)
        observed = interrupt_text(row, "Cry of Frustration")
        self.assertEqual(observed, "a tempo: Cry of Frustration", f"observed={observed!r}")

    def test_a_row_without_a_slot_says_so(self) -> None:
        row = CastRow(cast=make_cast(), tier=Tier.OTHER, slot=None)
        observed = interrupt_text(row, "")
        self.assertEqual(observed, "sem interrupt a tempo", f"observed={observed!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
