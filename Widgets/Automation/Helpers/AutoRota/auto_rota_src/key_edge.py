"""Edge detection for a polled key state, and the on/off rule of the Auto Rota toggle.

This module must not import Py4GWCoreLib: it runs offline in unit tests.
"""

from __future__ import annotations


class KeyEdge:
    """Turns a per-frame "is the key down" sample into one event per physical press."""

    def __init__(self) -> None:
        # Start as "down" so a key already held when the widget starts is not a new press.
        self._was_down = True

    def update(self, is_down: bool) -> bool:
        pressed = is_down and not self._was_down
        self._was_down = is_down
        return pressed


def next_auto_state(is_on: bool, toggle_pressed: bool, must_stop: bool) -> bool:
    """A press flips the toggle; a stop condition (death, map change, HeroAI combat) always wins."""
    if must_stop:
        return False
    if toggle_pressed:
        return not is_on
    return is_on
