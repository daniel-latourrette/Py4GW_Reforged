# Auto Rota — Guarda contra hexes punitivos: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enquanto o jogador tiver em si um hex que castiga uma ação (spells, ataques, shouts/chants ou qualquer skill), as jogadas automáticas da Auto Rota deixam de usar as skills que esse hex castiga, e a janela mostra um aviso vermelho com o nome e os segundos.

**Architecture:**
- Um módulo puro novo, `hex_guard.py`, guarda o catálogo de 25 ids e as regras. É testado offline.
- O `GameAdapter` lê os hexes do jogador com `Effects.GetEffects`, classifica as skills da barra e passa os ids bloqueados ao mecanismo de bloqueio do `CombatClass`, que já existe. Esse mecanismo cobre os interrupts e a rotação.
- O widget lê a guarda uma vez por frame. Com a build afetada, pausa a passagem da build e joga a rotação genérica. Mostra também o aviso e a caixa "Guarda de hexes".

**Tech Stack:** Python 3.13 32 bits no jogo (testes offline com `python3.12`), Py4GWCoreLib (`Effects`, `GLOBAL_CACHE`, HeroAI `CombatClass`), PyImGui, `unittest`, Pyright (`npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows`), Black 120 (`/tmp/claude-501/bv/bin/black -l 120 -S`).

**Spec:** `docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md`

**Commits:** só com autorização explícita do utilizador (regra do repositório). Se ele autorizar, há um commit no fim de cada tarefa, no branch `feature/auto-rota`. Todas as mensagens terminam com a linha `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Sem autorização, os passos de commit são saltados e as alterações ficam por commitar.

**Regras a respeitar:**
- Os textos da interface são em português **sem acentos**, porque a fonte do ImGui não os tem (ex.: `Ressurreicao` em `priorities.py`).
- Os comentários no código são em inglês.
- Os imports seguem o isort `force_single_line`, com uma linha por nome.
- Os módulos em `auto_rota_src/` que são testados offline (`model.py` e `hex_guard.py`) nunca importam Py4GWCoreLib.

---

## Estrutura de ficheiros

| Ficheiro | Responsabilidade |
|---|---|
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py` | + `ActionKind`, `BarSkill`, `ActiveHex` |
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/hex_guard.py` | **Novo, puro.** `PunishingHex`, `PUNISHING_HEXES` (25 ids), `active_punishing_hexes`, `guarded_skill_ids`, `build_paused_by_guard`, `warning_text`, `history_text`, `guard_reason` |
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py` | + `_action_kind`, `punishing_hexes_on_player()`, `bar_skills()`; `blocked_skill_ids` em `next_decision` e `interrupt_decision` |
| `Widgets/Automation/Helpers/AutoRota/Auto Rota.py` | Leitura da guarda por frame, ligação a `_play_once`, `_finish_build_pass` e `_update_preview`, aviso, caixa, histórico e tooltip |
| `Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py` | **Novo.** 26 testes offline |
| `docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md` | Estado → implementado |
| `docs/superpowers/specs/2026-10-24-auto-rota-design.md` | Linha "Ver também" a apontar para a spec da guarda |

---

### Task 1: Núcleo puro — tipos, catálogo e regras (TDD)

**Files:**
- Create: `Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py`
- Modify: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py`
- Create: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/hex_guard.py`

- [ ] **Step 1: Escrever os testes (vão falhar)**

Cria `Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py` com:

```python
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
```

- [ ] **Step 2: Correr os testes e confirmar que falham**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py" -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard'`.

- [ ] **Step 3: Acrescentar os tipos a `model.py`**

Em `Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py`:

1. Acrescenta o import, a seguir a `from enum import IntEnum`:

```python
from typing import Optional
```

2. Acrescenta no fim do ficheiro, depois de `BuildCandidate`:

```python


class ActionKind(IntEnum):
    """What a skill on the player's own bar does, as far as punishing hexes are concerned."""

    SPELL = 0
    ATTACK = 1
    SHOUT_OR_CHANT = 2
    OTHER = 3  # signets, stances, glyphs, rituals, preparations, forms, pet attacks...


@dataclass(frozen=True)
class BarSkill:
    skill_id: int  # 0 = empty slot
    kind: ActionKind


@dataclass(frozen=True)
class ActiveHex:
    skill_id: int
    remaining_ms: Optional[int]  # None when the game reports an implausible time ("?" in the window)
```

- [ ] **Step 4: Criar `hex_guard.py`**

Cria `Widgets/Automation/Helpers/AutoRota/auto_rota_src/hex_guard.py` com:

```python
"""Punishing-hex guard: which of the player's own skills a hex on the player punishes.

This module must not import Py4GWCoreLib: it runs offline in unit tests. Hexes are keyed by skill id
(checked against Py4GWCoreLib/skill_descriptions.json), not by name: Skill.GetID(name) is native and the
repo spells some names two ways. Spec: docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

from .model import ActionKind
from .model import ActiveHex
from .model import BarSkill

_SPELLS: frozenset[ActionKind] = frozenset({ActionKind.SPELL})
_ATTACKS: frozenset[ActionKind] = frozenset({ActionKind.ATTACK})
_ANY_SKILL: frozenset[ActionKind] = frozenset(ActionKind)
_ATTACKS_AND_SPELLS: frozenset[ActionKind] = frozenset({ActionKind.ATTACK, ActionKind.SPELL})
_SHOUTS_AND_CHANTS: frozenset[ActionKind] = frozenset({ActionKind.SHOUT_OR_CHANT})

_PAUSED_TEXT: dict[frozenset[ActionKind], str] = {
    _SPELLS: "spells",
    _ATTACKS: "ataques",
    _ANY_SKILL: "todas as skills",
    _ATTACKS_AND_SPELLS: "ataques e spells",
    _SHOUTS_AND_CHANTS: "shouts e chants",
}

# A remaining time above the effect's own duration plus this slack is not trusted (e.g. an unsigned value
# that wrapped at expiry): the hex still blocks, the window just shows "?".
_TIME_SLACK_MS = 1000


@dataclass(frozen=True)
class PunishingHex:
    name: str
    punishes: frozenset[ActionKind]


# Never add Wastrel's Worry (50) or Wastrel's Demise (1335): using a skill ENDS them, so pausing makes them
# hit harder. The repeated names are the separate "(PvP)" skill ids, which follow the same rule.
PUNISHING_HEXES: dict[int, PunishingHex] = {
    # Spells. Guilt and Mistrust only punish spells on foes, Shame and Mark of Subversion only spells on
    # allies, but HeroAI's target data cannot tell them apart (unknown skills default to Enemy), so these
    # pause every spell, for at most 6 s.
    28: PunishingHex("Backfire", _SPELLS),
    128: PunishingHex("Soul Leech", _SPELLS),
    804: PunishingHex("Arcane Languor", _SPELLS),
    979: PunishingHex("Mistrust", _SPELLS),
    3191: PunishingHex("Mistrust", _SPELLS),
    46: PunishingHex("Guilt", _SPELLS),
    51: PunishingHex("Shame", _SPELLS),
    127: PunishingHex("Mark of Subversion", _SPELLS),
    # Attacks
    26: PunishingHex("Empathy", _ATTACKS),
    3151: PunishingHex("Empathy", _ATTACKS),
    123: PunishingHex("Insidious Parasite", _ATTACKS),
    66: PunishingHex("Spirit Shackles", _ATTACKS),
    43: PunishingHex("Clumsiness", _ATTACKS),
    47: PunishingHex("Ineptitude", _ATTACKS),
    2056: PunishingHex("Wandering Eye", _ATTACKS),
    3195: PunishingHex("Wandering Eye", _ATTACKS),
    227: PunishingHex("Glimmering Mark", _ATTACKS),
    # Any skill
    121: PunishingHex("Spiteful Spirit", _ANY_SKILL),
    878: PunishingHex("Visions of Regret", _ANY_SKILL),
    3234: PunishingHex("Visions of Regret", _ANY_SKILL),
    30: PunishingHex("Diversion", _ANY_SKILL),
    52: PunishingHex("Panic", _ANY_SKILL),
    # Attacks and spells
    1066: PunishingHex("Spoil Victor", _ATTACKS_AND_SPELLS),
    3233: PunishingHex("Spoil Victor", _ATTACKS_AND_SPELLS),
    # Shouts and chants
    1998: PunishingHex("Cacophony", _SHOUTS_AND_CHANTS),
}


def _plausible_ms(remaining_ms: int, duration_s: float) -> Optional[int]:
    if remaining_ms <= 0 or remaining_ms > duration_s * 1000.0 + _TIME_SLACK_MS:
        return None
    return remaining_ms


def _longer(candidate: Optional[int], current: Optional[int]) -> bool:
    if candidate is None:
        return False
    return current is None or candidate > current


def active_punishing_hexes(effects: Iterable[tuple[int, int, float]]) -> tuple[ActiveHex, ...]:
    """Punishing hexes among (skill_id, remaining_ms, duration_s) effects, one per id.

    Duplicates keep the longest known time. A hex counts while its effect exists, whatever its time.
    """
    best: dict[int, Optional[int]] = {}
    for skill_id, remaining_ms, duration_s in effects:
        if skill_id not in PUNISHING_HEXES:
            continue
        remaining = _plausible_ms(remaining_ms, duration_s)
        if skill_id not in best or _longer(remaining, best[skill_id]):
            best[skill_id] = remaining
    return tuple(ActiveHex(skill_id=skill_id, remaining_ms=remaining) for skill_id, remaining in best.items())


def guarded_skill_ids(bar: Sequence[BarSkill], hexes: Sequence[ActiveHex]) -> frozenset[int]:
    """Ids of the bar skills that an active punishing hex would punish (empty slots never count)."""
    punished: set[ActionKind] = set()
    for active in hexes:
        entry = PUNISHING_HEXES.get(active.skill_id)
        if entry is not None:
            punished |= entry.punishes
    return frozenset(skill.skill_id for skill in bar if skill.skill_id != 0 and skill.kind in punished)


def build_paused_by_guard(guarded: frozenset[int], build_skill_ids: Iterable[int]) -> bool:
    """A build pass cannot skip single skills: the whole build waits while the guard blocks one of them."""
    return not guarded.isdisjoint(build_skill_ids)


def warning_text(active: ActiveHex) -> str:
    entry = PUNISHING_HEXES[active.skill_id]
    seconds = "?" if active.remaining_ms is None else str(math.ceil(active.remaining_ms / 1000))
    return f"{entry.name} em ti: {_PAUSED_TEXT[entry.punishes]} em pausa ({seconds} s)"


def history_text(skill_id: int, started: bool) -> str:
    entry = PUNISHING_HEXES[skill_id]
    if started:
        return f"Guarda: {entry.name} - {_PAUSED_TEXT[entry.punishes]} em pausa"
    return f"Guarda: {entry.name} acabou"


def guard_reason(hexes: Sequence[ActiveHex]) -> str:
    """Names of the active punishing hexes, for the preview's "build em pausa (...)"."""
    return ", ".join(PUNISHING_HEXES[active.skill_id].name for active in hexes)
```

- [ ] **Step 5: Correr os testes novos**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py" -v`
Expected: `Ran 26 tests` … `OK`.

- [ ] **Step 6: Correr os testes antigos (não podem partir)**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v`
Expected: `Ran 35 tests` … `OK`.

- [ ] **Step 7: Pyright e Black**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows "Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py" "Widgets/Automation/Helpers/AutoRota/auto_rota_src/hex_guard.py" "Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py"`
Expected: `0 errors, 0 warnings, 0 informations`.

Run: `/tmp/claude-501/bv/bin/black -l 120 -S --check "Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py" "Widgets/Automation/Helpers/AutoRota/auto_rota_src/hex_guard.py" "Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py"`
Expected: `3 files would be left unchanged.` Se o Black quiser reformatar, corre o mesmo comando sem `--check`, revê o diff e volta a correr os passos 5 e 6.

Apaga os `__pycache__` criados pelos testes:
Run: `find Widgets/Automation/Helpers/AutoRota "Examples and tests/tests/auto_rota" -name __pycache__ -type d -prune -exec rm -rf {} +`

- [ ] **Step 8: Commit (só com autorização)**

```bash
git add "Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py" Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py Widgets/Automation/Helpers/AutoRota/auto_rota_src/hex_guard.py
git commit -m "$(cat <<'EOF'
feat(auto-rota): punishing-hex catalogue and guard rules (pure core)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `GameAdapter` — ler os hexes, classificar a barra e aceitar ids bloqueados

**Files:**
- Modify: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py`

Contexto:
- `CombatClass.ApplyBlockedSkillIDs` **substitui** o conjunto bloqueado de cada vez (`Py4GWCoreLib/HeroAI/combat.py:305-310`).
- `IsSkillReady` rejeita os ids bloqueados (`combat.py:506`).
- `_interrupt_slots` e `_rotation_decision` chamam ambos `IsSkillReady`, por isso basta passar os ids a `_sync_combat` em cada decisão.

- [ ] **Step 1: Imports**

Na secção de imports de `game_adapter.py`:

1. Acrescenta, imediatamente antes de `from typing import Optional`:

```python
from typing import Iterable
```

As linhas `from typing import Optional` e `from typing import Sequence` não mudam, e o bloco fica `Iterable`, `Optional`, `Sequence`, que é a ordem do isort do repositório.

2. Acrescenta, antes de `from Py4GWCoreLib.enums_src.GameData_enums import Attribute`:

```python
from Py4GWCoreLib.Effect import Effects
```

3. Substitui o bloco de imports locais:

```python
from .decide import choose_interrupt
from .model import CastKind
```

por:

```python
from .decide import choose_interrupt
from .hex_guard import active_punishing_hexes
from .model import ActionKind
from .model import ActiveHex
from .model import BarSkill
from .model import CastKind
```

- [ ] **Step 2: Classificação das skills da barra**

A seguir à função `_cast_kind` (antes de `_skill_name`), acrescenta:

```python
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
```

- [ ] **Step 3: `_sync_combat` aceita qualquer iterável**

Substitui:

```python
    def _sync_combat(self, blocked_skill_ids: Sequence[int] = ()) -> CombatClass:
```

por:

```python
    def _sync_combat(self, blocked_skill_ids: Iterable[int] = ()) -> CombatClass:
```

O corpo não muda: já faz `combat.ApplyBlockedSkillIDs(list(blocked_skill_ids))`.

- [ ] **Step 4: `next_decision` e `interrupt_decision` passam os ids bloqueados**

Substitui:

```python
    def next_decision(self, preview: bool = False, allow_buffs: bool = True) -> Optional[Decision]:
        self._sync_combat()
        interrupt = choose_interrupt(self._enemy_casts(), self._interrupt_slots(), self._is_feasible)
        if interrupt is not None:
            return interrupt
        return self._rotation_decision(preview, allow_buffs)

    def interrupt_decision(self, max_tier: Tier) -> Optional[Decision]:
        """Interrupt layer only (build mode): no rotation fallback, never reserves targets."""
        self._sync_combat()
        return choose_interrupt(self._enemy_casts(), self._interrupt_slots(), self._is_feasible, max_tier=max_tier)
```

por:

```python
    def next_decision(
        self, preview: bool = False, allow_buffs: bool = True, blocked_skill_ids: Iterable[int] = ()
    ) -> Optional[Decision]:
        # Blocked ids (the hex guard) must be passed on every call, the preview included:
        # ApplyBlockedSkillIDs replaces the set, so an omitted argument unblocks everything.
        self._sync_combat(blocked_skill_ids)
        interrupt = choose_interrupt(self._enemy_casts(), self._interrupt_slots(), self._is_feasible)
        if interrupt is not None:
            return interrupt
        return self._rotation_decision(preview, allow_buffs)

    def interrupt_decision(self, max_tier: Tier, blocked_skill_ids: Iterable[int] = ()) -> Optional[Decision]:
        """Interrupt layer only (build mode): no rotation fallback, never reserves targets."""
        self._sync_combat(blocked_skill_ids)
        return choose_interrupt(self._enemy_casts(), self._interrupt_slots(), self._is_feasible, max_tier=max_tier)
```

- [ ] **Step 5: Ler os hexes do jogador e a barra**

A seguir ao método `rotation_after_build` (antes de `note_external_cast`), acrescenta:

```python
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
```

- [ ] **Step 6: Verificar**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows "Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py"`
Expected: `0 errors, 0 warnings, 0 informations`.

Run: `/tmp/claude-501/bv/bin/black -l 120 -S --check "Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py"`
Expected: `1 file would be left unchanged.`

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v` e `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py" -v`
Expected: `Ran 35 tests … OK` e `Ran 26 tests … OK`. O adapter importa o Py4GWCoreLib, por isso não tem testes offline. Estes testes só confirmam que o núcleo continua a importar.

Apaga os `__pycache__` como na Task 1, Step 7.

- [ ] **Step 7: Commit (só com autorização)**

```bash
git add Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py
git commit -m "$(cat <<'EOF'
feat(auto-rota): read punishing hexes on the player and pass blocked skills to every decision

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Widget — guarda por frame, jogadas, pré-visualização, janela

**Files:**
- Modify: `Widgets/Automation/Helpers/AutoRota/Auto Rota.py`

- [ ] **Step 1: Imports, constante e estado**

1. Acrescenta a seguir a `from Widgets.Automation.Helpers.AutoRota.auto_rota_src.game_adapter import GameAdapter`:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import build_paused_by_guard
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import guard_reason
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import guarded_skill_ids
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import history_text
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.hex_guard import warning_text
```

2. Acrescenta antes de `from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import Decision`:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.model import ActiveHex
```

3. A seguir a `_SETTINGS_BUFF_HOTKEY = "buff_hotkey"`, acrescenta:

```python
_SETTINGS_HEX_GUARD = "hex_guard"
```

4. A seguir a `_buffs_on = False  # always starts off: buffs are an explicit opt-in per session`, acrescenta:

```python
_guard_on = True  # loaded from the settings together with the keys; on by default
_guard_hexes: tuple[ActiveHex, ...] = ()
_guard_ids: frozenset[int] = frozenset()
_guard_error = False
```

- [ ] **Step 2: `_update_guard`**

A seguir à função `_stop_reason` (antes de `_press_allowed`), acrescenta:

```python
def _update_guard() -> None:
    """Read the punishing hexes on the player once per frame and derive the skills the guard blocks."""
    global _guard_hexes, _guard_ids, _guard_error
    previous = {active.skill_id for active in _guard_hexes}
    if not _guard_on:
        _guard_hexes, _guard_ids, _guard_error = (), frozenset(), False
        return
    try:
        hexes = _adapter.punishing_hexes_on_player()
        guarded = guarded_skill_ids(_adapter.bar_skills(), hexes) if hexes else frozenset[int]()
    except Exception as exc:
        # Fail open: an unreadable effects list must not freeze the loop; the window says so.
        _guard_hexes, _guard_ids, _guard_error = (), frozenset(), True
        _log_error_once("hex guard", exc)
        return
    _guard_hexes, _guard_ids, _guard_error = hexes, guarded, False
    if _auto_on:
        current = {active.skill_id for active in hexes}
        for skill_id in sorted(current - previous):
            _push_history(history_text(skill_id, started=True))
        for skill_id in sorted(previous - current):
            _push_history(history_text(skill_id, started=False))
```

- [ ] **Step 3: `_play_once` respeita a guarda e pausa a build**

Substitui a função `_play_once` inteira por:

```python
def _play_once() -> None:
    """One play while the toggle is on; silent when busy or when there is nothing to do."""
    if _build_mode.busy or _adapter.blocker() is not None:
        return
    # A build pass cannot skip single skills: while the guard blocks one of the build's skills, play the
    # generic rotation (all interrupt tiers, then HeroAI) over the skills the guard still allows.
    if _build_mode.build_name is None or build_paused_by_guard(_guard_ids, _build_mode.blocked_skill_ids()):
        decision = _adapter.next_decision(allow_buffs=_buffs_on, blocked_skill_ids=_guard_ids)
        if decision is not None:
            _adapter.execute(decision)
            _push_history(_adapter.describe(decision))
        return
    interrupt = _adapter.interrupt_decision(BUILD_MODE_MAX_TIER, blocked_skill_ids=_guard_ids)
    if interrupt is not None:
        _adapter.execute(interrupt)
        _push_history(_adapter.describe(interrupt))
        return
    _build_mode.request_pass()  # main() drives the pass over the next frames
```

- [ ] **Step 4: `_finish_build_pass` junta os ids da guarda aos da build**

Em `_finish_build_pass`, substitui:

```python
    decision = _adapter.rotation_after_build(_build_mode.blocked_skill_ids(), allow_buffs=_buffs_on)
```

por:

```python
    blocked = set(_build_mode.blocked_skill_ids()) | _guard_ids
    decision = _adapter.rotation_after_build(sorted(blocked), allow_buffs=_buffs_on)
```

- [ ] **Step 5: `_update_preview` segue a mesma lógica**

Substitui a função `_update_preview` inteira por:

```python
def _update_preview() -> None:
    global _preview_text, _heroai_conflict
    _heroai_conflict = _adapter.heroai_conflict()
    reason = _adapter.blocker()
    if reason is not None and reason != REASON_BUSY:
        _preview_text = f"em pausa ({reason})"
        return
    build_ids = _build_mode.blocked_skill_ids()
    build_paused = _build_mode.build_name is not None and build_paused_by_guard(_guard_ids, build_ids)
    if _build_mode.build_name is None or build_paused:
        decision = _adapter.next_decision(preview=True, allow_buffs=_buffs_on, blocked_skill_ids=_guard_ids)
        text = _adapter.describe(decision) if decision is not None else "nada a fazer"
        _preview_text = f"build em pausa ({guard_reason(_guard_hexes)}): {text}" if build_paused else text
        return
    interrupt = _adapter.interrupt_decision(BUILD_MODE_MAX_TIER, blocked_skill_ids=_guard_ids)
    _preview_text = _adapter.describe(interrupt) if interrupt is not None else "jogada da build (decidida ao jogar)"
```

- [ ] **Step 6: Janela — aviso e caixa**

Em `_draw_window`:

1. Substitui a linha `global _key_index, _key_edge, _buff_key_index, _buff_key_edge` por:

```python
    global _key_index, _key_edge, _buff_key_index, _buff_key_edge, _guard_on
```

2. Logo a seguir ao bloco dos buffs:

```python
            if _buffs_on:
                PyImGui.text_colored(f"Buffs: LIGADOS  ({buff_label})", _ON_COLOR)
            else:
                PyImGui.text(f"Buffs: DESLIGADOS  ({buff_label})")
```

acrescenta:

```python
            if _guard_error:
                PyImGui.text_colored("Guarda: erro a ler efeitos (ver consola)", _WARNING_COLOR)
            for active in _guard_hexes:
                PyImGui.text_colored(warning_text(active), _WARNING_COLOR)
```

3. Logo a seguir a:

```python
            if _buff_key_index == _key_index:
                PyImGui.text_colored("As duas teclas sao iguais: a tecla dos buffs e ignorada", _WARNING_COLOR)
```

acrescenta:

```python
            new_guard_on = PyImGui.checkbox("Guarda de hexes", _guard_on)
            if new_guard_on != _guard_on:
                _guard_on = new_guard_on
                _settings.set_bool(_SETTINGS_SECTION, _SETTINGS_HEX_GUARD, new_guard_on)
                _push_history("Guarda de hexes LIGADA" if new_guard_on else "Guarda de hexes DESLIGADA")
```

- [ ] **Step 7: Tooltip**

Em `tooltip()`, antes de `PyImGui.end_tooltip()`, acrescenta:

```python
    PyImGui.text("Guarda de hexes: pausa as skills que um hex em ti castiga (ex.: Backfire -> spells).")
```

- [ ] **Step 8: `main()` — carregar a definição e correr a guarda em cada frame**

1. Substitui a linha `global _key_index, _buff_key_index, _key_loaded, _main_tick_s, _preview_text` por:

```python
    global _key_index, _buff_key_index, _key_loaded, _main_tick_s, _preview_text, _guard_on
```

2. No bloco `if not _key_loaded:`, antes de `_key_loaded = True`, acrescenta:

```python
            _guard_on = _settings.get_bool(_SETTINGS_SECTION, _SETTINGS_HEX_GUARD, True)
```

3. Logo a seguir a:

```python
        try:
            _build_mode.refresh()
        except Exception as exc:
            _log_error_once("build", exc)
```

acrescenta:

```python
        try:
            _update_guard()  # before the play and the preview, so a fresh hex is seen on the frame it lands
        except Exception as exc:
            _log_error_once("hex guard", exc)
```

- [ ] **Step 9: Verificar**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows "Widgets/Automation/Helpers/AutoRota"`
Expected: `0 errors, 0 warnings, 0 informations`.

Run: `/tmp/claude-501/bv/bin/black -l 120 -S --check "Widgets/Automation/Helpers/AutoRota/Auto Rota.py"`
Expected: `1 file would be left unchanged.`

Run: `python3.12 -m py_compile "Widgets/Automation/Helpers/AutoRota/Auto Rota.py"`
Expected: sem output.

Corre os dois ficheiros de testes: `Ran 35 tests … OK` e `Ran 26 tests … OK`. Depois apaga os `__pycache__` como na Task 1, Step 7.

Confirma com grep que todas as decisões levam a guarda. Nenhuma chamada a `next_decision(` ou `interrupt_decision(` no widget pode ficar sem `blocked_skill_ids=_guard_ids`:

Run: `grep -n "next_decision(\|interrupt_decision(\|rotation_after_build(" "Widgets/Automation/Helpers/AutoRota/Auto Rota.py"`
Expected: 5 linhas.
- `_play_once`: `next_decision` e `interrupt_decision`.
- `_finish_build_pass`: `rotation_after_build(sorted(blocked)`.
- `_update_preview`: `next_decision` e `interrupt_decision`.
- Todas as chamadas a `next_decision` e `interrupt_decision` levam `blocked_skill_ids=_guard_ids`.

- [ ] **Step 10: Commit (só com autorização)**

```bash
git add "Widgets/Automation/Helpers/AutoRota/Auto Rota.py"
git commit -m "$(cat <<'EOF'
feat(auto-rota): punishing-hex guard pauses punished plays, with a red warning and a toggle

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Documentação e verificação final

**Files:**
- Modify: `docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md:3`
- Modify: `docs/superpowers/specs/2026-10-24-auto-rota-design.md:3`

- [ ] **Step 1: Estado da spec da guarda**

Em `docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md`, substitui:

```markdown
Data: 2026-10-25 · Estado: aprovado, por implementar · Branch: `feature/auto-rota`
```

por:

```markdown
Data: 2026-10-25 · Estado: implementado, por validar no jogo · Branch: `feature/auto-rota`
```

- [ ] **Step 2: Ligação a partir da spec base**

Em `docs/superpowers/specs/2026-10-24-auto-rota-design.md`, a seguir à linha 3 (`Data: 2026-10-24 · Estado: implementado, por validar no jogo · Branch: \`feature/auto-rota\``), acrescenta uma linha em branco e:

```markdown
Ver também: `docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md` (guarda contra hexes punitivos).
```

- [ ] **Step 3: Verificação completa**

Run, um a um:

```bash
python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v
python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py" -v
npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows "Widgets/Automation/Helpers/AutoRota" "Examples and tests/tests/auto_rota"
/tmp/claude-501/bv/bin/black -l 120 -S --check "Widgets/Automation/Helpers/AutoRota/Auto Rota.py" Widgets/Automation/Helpers/AutoRota/auto_rota_src/model.py Widgets/Automation/Helpers/AutoRota/auto_rota_src/hex_guard.py Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py "Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py"
find Widgets/Automation/Helpers/AutoRota "Examples and tests/tests/auto_rota" -name __pycache__ -type d -prune -exec rm -rf {} +
git status --short
```

Expected:
- 35 e 26 testes OK.
- Pyright com `0 errors`.
- Black sem alterações nos cinco ficheiros do plano.

O Black só verifica os ficheiros deste plano. O `auto_rota_src/decide.py` já estava fora do formato antes deste trabalho (commit 1a57dd27), e reformatá-lo é uma alteração à parte, fora deste plano.
- O `git status` mostra só os ficheiros deste plano. Se os commits foram autorizados, mostra só os dois `.md` desta tarefa e o plano.

- [ ] **Step 4: Commit (só com autorização)**

```bash
git add docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md docs/superpowers/specs/2026-10-24-auto-rota-design.md docs/superpowers/plans/2026-10-25-auto-rota-hex-guard.md
git commit -m "$(cat <<'EOF'
docs(auto-rota): hex guard spec, plan and status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

## Validação no jogo (depois da implementação, pelo utilizador no Windows)

Copia de novo a pasta `Widgets/Automation/Helpers/AutoRota` a partir do zip do branch, e depois confirma:

1. **Backfire em ti:** as spells automáticas param e a linha vermelha `Backfire em ti: spells em pausa (N s)` conta para baixo cerca de 1 s por segundo.
2. **Fim do hex:** a Auto Rota volta a jogar sozinha e o histórico mostra `Guarda: Backfire acabou`.
3. **Empathy:** as skills de ataque param e as spells continuam.
4. **Build de Energy Surge com Backfire:** a pré-visualização mostra `build em pausa (Backfire): ...`.
5. **Caixa "Guarda de hexes" desligada:** sem aviso e sem bloqueio. O estado mantém-se depois de reiniciar o widget.
6. **Ataques normais:** com Empathy, ver se o boneco continua a atacar sozinho depois de uma skill de ataque. Isto é registado como limite, não como erro.
