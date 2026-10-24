"""Edge detection for a polled key state.

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
