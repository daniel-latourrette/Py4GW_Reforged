"""Pure helpers for the cast watch window: the estimated cast-progress bar and the row texts.

This module must not import Py4GWCoreLib: it runs offline in unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .model import CastRow
from .model import EnemyCast

WATCH_MAX_ROWS = 6

# A cast seen running this long past its base activation is slowed or recast: say so instead of a stuck 100%.
_OVERRUN_GRACE_MS = 300


@dataclass(frozen=True)
class CastProgress:
    fraction: Optional[float]  # None: no reading (empty bar)
    label: str


@dataclass(frozen=True)
class WatchLabels:
    """Display strings for one row, captured at read time so names are not looked up every frame."""

    enemy: str
    skill: str
    icon_path: str
    interrupt: str


def cast_progress(cast: EnemyCast, seconds_since_read: float) -> CastProgress:
    """Estimated progress: base activation and the observer's first sighting, not the game's own clock.

    Enemy Fast Casting and slowing hexes are not modelled, so this is an estimate.
    """
    if cast.elapsed_ms is None or cast.activation_ms <= 0:
        return CastProgress(fraction=None, label="?")
    elapsed_ms = cast.elapsed_ms + seconds_since_read * 1000.0
    if elapsed_ms > cast.activation_ms + _OVERRUN_GRACE_MS:
        return CastProgress(fraction=1.0, label="a terminar?")
    fraction = min(1.0, max(0.0, elapsed_ms / cast.activation_ms))
    left_s = max(0.0, cast.activation_ms - elapsed_ms) / 1000.0
    return CastProgress(fraction=fraction, label=f"{left_s:.1f}s")


def interrupt_text(row: CastRow, skill_name: str) -> str:
    return f"a tempo: {skill_name}" if row.slot is not None else "sem interrupt a tempo"
