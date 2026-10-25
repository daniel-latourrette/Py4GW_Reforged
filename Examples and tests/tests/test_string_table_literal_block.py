"""Offline tests for the string-table decoder's literal-text block (0x0108 0x0107 <text> 0x0001).

The defect: mercenary heroes carry their names as the game's literal-text block. The encoded name
read live from the Agent Info Viewer was ``\\x0108\\x0107Nefastus Necro\\x0001``. The decoder read
0x0108 as string-table index 8 (the bare template "%str1%") and every widget showed "%str1%"
instead of the name. string_table.py is loaded straight from source with its two runtime-only
imports stubbed, so this runs without the injected client.

Run: python3.12 "Examples and tests/tests/test_string_table_literal_block.py" -v
"""

from __future__ import annotations

import importlib.util
import struct
import sys
import types
import unittest
from pathlib import Path
from typing import Union

ROOT = Path(__file__).resolve().parents[2]
STRING_TABLE = ROOT / "Py4GWCoreLib" / "native_src" / "internals" / "string_table.py"
_STUBBED_IMPORTS = ("Py4GWCoreLib.native_src.context.TextContext", "Py4GWCoreLib.native_src.internals.helpers")


def _load_string_table() -> types.ModuleType:
    text_context = types.ModuleType(_STUBBED_IMPORTS[0])
    setattr(text_context, "TextParser", type("TextParser", (), {"get_context": staticmethod(lambda: None)}))
    helpers = types.ModuleType(_STUBBED_IMPORTS[1])
    setattr(helpers, "read_wstr", lambda address: "")
    saved = {name: sys.modules.get(name) for name in _STUBBED_IMPORTS}
    sys.modules[_STUBBED_IMPORTS[0]] = text_context
    sys.modules[_STUBBED_IMPORTS[1]] = helpers
    try:
        spec = importlib.util.spec_from_file_location("string_table_under_test", STRING_TABLE)
        assert spec is not None and spec.loader is not None, f"no module spec for {STRING_TABLE}"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


string_table = _load_string_table()

LITERAL = (0x0108, 0x0107)
PLAYER_NAME = (0x0BA9, 0x0107)
END = 0x0001
SEPARATOR = 0x0002


def encoded(*parts: Union[int, str]) -> bytes:
    """Raw wchar bytes as the client returns them: codepoints and literal text, null-terminated."""
    codepoints: list[int] = []
    for part in parts:
        codepoints.extend(ord(char) for char in part) if isinstance(part, str) else codepoints.append(part)
    return struct.pack(f"<{len(codepoints) + 1}H", *codepoints, 0)


class LiteralBlockDecodeTests(unittest.TestCase):
    def check(self, raw: bytes, expected: str) -> None:
        observed = string_table.decode(raw)
        self.assertEqual(observed, expected, f"raw={raw.hex(' ')} expected={expected!r} observed={observed!r}")

    def test_mercenary_hero_names_decode_to_their_text(self) -> None:
        # Exactly the encoded names read live from the Agent Info Viewer.
        self.check(encoded(*LITERAL, "Nefastus Necro", END), "Nefastus Necro")
        self.check(encoded(*LITERAL, "Sande Kuala", END), "Sande Kuala")

    def test_literal_text_needs_no_string_table_and_no_async_round(self) -> None:
        # The table is never loaded offline: the first call must already return the name.
        self.assertFalse(string_table._string_table, "the offline string table must stay empty")
        self.check(encoded(*LITERAL, "Nefastus Necro", END), "Nefastus Necro")

    def test_escaped_brackets_and_backslashes_are_restored(self) -> None:
        # GWUI._encode_text_literal escapes '\\' '[' ']' with a backslash; decoding restores them.
        self.check(encoded(*LITERAL, "\\[Tag\\] a\\\\b", END), "[Tag] a\\b")

    def test_literal_text_is_not_postprocessed_as_game_markup(self) -> None:
        # "[M]" is a grammar tag in table strings, but in a literal it is just the player's text.
        self.check(encoded(*LITERAL, "\\[M\\] Name", END), "[M] Name")

    def test_a_requested_language_does_not_change_literal_text(self) -> None:
        observed = string_table.decode(encoded(*LITERAL, "Sande Kuala", END), language=3)
        self.assertEqual(observed, "Sande Kuala", f"observed={observed!r}")

    def test_player_names_still_decode(self) -> None:
        self.check(encoded(*PLAYER_NAME, "Lilith Nefastus", END), "Lilith Nefastus")

    def test_with_the_live_table_loaded_the_name_is_not_the_bare_template(self) -> None:
        # In game the table maps index 8 to "%str1%": reading 0x0108 as that index produced "%str1%".
        template = "%str1%".encode("utf-16-le")
        entry = struct.pack("<HHBB", 6 + len(template), 0, 16, 0) + template  # raw UTF-16LE entry, no RC4 key
        saved_loaded = string_table._string_table_loaded
        string_table._string_table[8] = entry
        setattr(string_table, "_string_table_loaded", True)
        try:
            self.check(encoded(*LITERAL, "Nefastus Necro", END), "Nefastus Necro")
        finally:
            string_table._string_table.pop(8, None)
            setattr(string_table, "_string_table_loaded", saved_loaded)


class LiteralBlockShapeTests(unittest.TestCase):
    def check(self, raw: bytes, expected: object) -> None:
        observed = string_table._decode_literal_block(raw)
        self.assertEqual(observed, expected, f"raw={raw.hex(' ')} expected={expected!r} observed={observed!r}")

    def test_a_block_without_its_terminator_still_reads_to_the_end(self) -> None:
        self.check(encoded(*LITERAL, "Nefastus Necro"), "Nefastus Necro")

    def test_bytes_after_the_null_terminator_are_ignored(self) -> None:
        self.check(encoded(*LITERAL, "Nefastus Necro", END, 0, 0x4141), "Nefastus Necro")

    def test_surrogate_pairs_become_one_character(self) -> None:
        self.check(encoded(*LITERAL, "Hi ", 0xD83D, 0xDE00, END), "Hi \U0001f600")

    def test_more_data_after_the_block_is_left_to_the_general_decoder(self) -> None:
        self.check(encoded(*LITERAL, "Name", END, SEPARATOR, *LITERAL, "Suffix", END), None)

    def test_control_codepoints_inside_the_text_are_left_to_the_general_decoder(self) -> None:
        self.check(encoded(*LITERAL, "Na", SEPARATOR, "me", END), None)

    def test_other_strings_are_not_literal_blocks(self) -> None:
        self.check(encoded(*PLAYER_NAME, "Lilith Nefastus", END), None)
        self.check(encoded(0x2100, END), None)
        self.check(b"", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
