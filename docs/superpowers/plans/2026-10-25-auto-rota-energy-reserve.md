# Auto Rota — Reserva de energia para interrupts: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Com a Auto Rota ligada, as skills da rotação deixam de ser lançadas quando a energia que sobra depois de as pagar fica abaixo de uma reserva para interrupts. A janela mostra a energia, a reserva e o aviso "sem energia para interromper".

**Architecture:**
- Um módulo puro novo, `energy_reserve.py`, testado offline, guarda:
  - os modos;
  - a reserva com o teto;
  - a regra por skill;
  - as listas de ids;
  - os textos da janela.
- O `GameAdapter` extrai a energia atual e o custo real para funções partilhadas com `_has_resources`. Lista o custo de todos os interrupts da barra, aplica a regra num único ponto de `_rotation_decision` e devolve um `EnergyStatus` para a janela.
- O widget guarda o modo e o valor fixo. Passa-os às decisões da rotação, mostra a linha da energia e os avisos, e explica na pré-visualização quando a reserva saltou uma skill.

**Tech Stack:**
- Python 3.13 32 bits no jogo; os testes offline correm com `python3.12`.
- Py4GWCoreLib: `Agent`, `Routines.Checks.Skills`, `GLOBAL_CACHE` e o `CombatClass` do HeroAI.
- PyImGui.
- `unittest`.
- Pyright: `npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows`.
- Black 120: `/tmp/claude-501/bv/bin/black -l 120 -S`.
- isort, com a configuração do repositório: `/private/tmp/claude-501/-Users-latourrette-Library-Application-Support-Claude-scratch-workspaces-49d8e2c2-9de2-440a-9235-e4cee5b6baeb-767a30bf-66a0-444c-a0b5-1a82626cfd89-scratch-2026-10-24-74fffe/414cdc62-7ecb-4cdd-a140-a5d6d12b8bcf/scratchpad/isortvenv/bin/isort --settings-path pyproject.toml --check-only`.

**Spec:** `docs/superpowers/specs/2026-10-25-auto-rota-energy-reserve-design.md`

**Commits:**
- Só com autorização explícita do utilizador, como manda a regra do repositório.
- Se forem autorizados, há um commit no fim de cada tarefa, no branch `feature/auto-rota`.
- Todas as mensagens terminam com a linha `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Sem autorização, os passos de commit são saltados.

**Ajustes à spec feitos durante o planeamento (a spec já está atualizada):**
- O `ReserveMode` e o `EnergyStatus` ficam no novo `energy_reserve.py` e não no `model.py`. No `model.py`, os dois módulos importar-se-iam um ao outro. É o mesmo padrão do `hex_guard.py`, que guarda o seu próprio `PunishingHex`.
- A regra da reserva corre depois dos filtros de alvo e de fora de combate, e antes do `IsReadyToCast`. A pré-visualização só culpa a reserva por uma skill que passou esses filtros e que se podia pagar sem a reserva. As condições de cast verificadas depois, como haver um aliado ferido, ainda não são conhecidas nesse ponto. Mudar isso obrigava a mexer na ordem do HeroAI, que é partilhado.
- O valor fixo é limitado a 0–25 também quando é escrito com Ctrl+clique no slider.

**Regras a respeitar:**
- **Textos da interface:** em português e **sem acentos**, porque a fonte do ImGui não os tem.
- **Comentários no código:** em inglês.
- **Imports:** uma linha por nome (isort `force_single_line`, com constantes, depois classes, depois funções).
- **Módulos testados offline:** o `energy_reserve.py` nunca importa Py4GWCoreLib.
- **`decide.py`:** não se mexe nele neste plano. A diferença do Black que já tem fica como está.

---

## Estrutura de ficheiros

| Ficheiro | Responsabilidade |
|---|---|
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/energy_reserve.py` | **Novo, puro.** `ReserveMode`, `InterruptCost`, `EnergyStatus`, constantes, `effective_reserve`, `breaks_reserve`, `cannot_interrupt`, `make_energy_status`, `energy_line` e os textos |
| `Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py` | `_current_energy`, `_energy_cost` (partilhadas com `_has_resources`), `_interrupt_costs`, a regra em `_rotation_decision`, `reserve_skip_skill_id`, `energy_status()`, argumentos da reserva em `next_decision` e `rotation_after_build` |
| `Widgets/Automation/Helpers/AutoRota/Auto Rota.py` | Definições, controlos, linha da energia, avisos, pré-visualização e tooltip |
| `Examples and tests/tests/auto_rota/test_auto_rota_energy_reserve.py` | **Novo.** 33 testes offline |
| `docs/superpowers/specs/2026-10-25-auto-rota-energy-reserve-design.md` | Estado → implementado |
| `docs/superpowers/specs/2026-10-24-auto-rota-design.md` | Linha "Ver também" |

---

### Task 1: `energy_reserve.py` — modos, reserva, regra e textos (TDD)

**Files:**
- Create: `Examples and tests/tests/auto_rota/test_auto_rota_energy_reserve.py`
- Create: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/energy_reserve.py`

- [ ] **Step 1: Escrever os testes (vão falhar)**

Cria `Examples and tests/tests/auto_rota/test_auto_rota_energy_reserve.py` com:

```python
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
```

- [ ] **Step 2: Correr os testes e confirmar que falham**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_energy_reserve.py" -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve'`.

- [ ] **Step 3: Criar `energy_reserve.py`**

Cria `Widgets/Automation/Helpers/AutoRota/auto_rota_src/energy_reserve.py` com:

```python
"""Interrupt energy reserve: how much energy the rotation must leave for an interrupt, and which skills that stops.

This module must not import Py4GWCoreLib: it runs offline in unit tests.
Spec: docs/superpowers/specs/2026-10-25-auto-rota-energy-reserve-design.md.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ReserveMode(Enum):
    CHEAPEST = "cheapest"  # the value is what auto_rota.ini stores
    FIXED = "fixed"
    OFF = "off"


MODE_CHOICES: tuple[ReserveMode, ...] = (ReserveMode.CHEAPEST, ReserveMode.FIXED, ReserveMode.OFF)
MODE_LABELS: dict[ReserveMode, str] = {
    ReserveMode.CHEAPEST: "Interrupt mais barato",
    ReserveMode.FIXED: "Fixa",
    ReserveMode.OFF: "Desligada",
}
RESERVE_FIXED_DEFAULT = 10
RESERVE_FIXED_MAX = 25

# HeroAI tags these Offensive although they give energy back (Drain Enchantment, Energy Drain, Energy Tap,
# Waste Not, Want Not; ids checked in Py4GWCoreLib/skill_descriptions.json): blocking them would cut the way out.
ENERGY_GAIN_SKILL_IDS: frozenset[int] = frozenset({68, 79, 80, 1995})
# Ether Lord: "You lose all Energy", so a cost-based check would let it empty the reserve.
DRAINS_ALL_ENERGY_SKILL_IDS: frozenset[int] = frozenset({41})

CANNOT_INTERRUPT_TEXT = "sem energia para interromper"


@dataclass(frozen=True)
class InterruptCost:
    skill_id: int
    cost: float  # effective energy cost (effects and Expertise included)
    ready: bool  # off recharge, with enough adrenaline


@dataclass(frozen=True)
class EnergyStatus:
    current: Optional[float]  # None: the energy could not be read
    maximum: float
    mode: ReserveMode
    reserve: float
    reserve_skill_id: int  # the interrupt that sets the reserve in CHEAPEST mode (0: none)
    cannot_interrupt: bool  # a ready interrupt exists and none of the ready ones is affordable


def mode_from_setting(text: str) -> ReserveMode:
    for mode in ReserveMode:
        if mode.value == text:
            return mode
    return ReserveMode.CHEAPEST


def cheapest_interrupt(costs: Sequence[InterruptCost]) -> Optional[InterruptCost]:
    """Cheapest interrupt on the bar, ready or recharging; a tie keeps the first (CombatClass priority order)."""
    best: Optional[InterruptCost] = None
    for item in costs:
        if best is None or item.cost < best.cost:
            best = item
    return best


def effective_reserve(mode: ReserveMode, fixed: int, costs: Sequence[InterruptCost], maximum: float) -> float:
    """The energy the rotation must leave, capped at half the maximum (0 when the maximum is unknown)."""
    if mode is ReserveMode.OFF or maximum <= 0:
        return 0.0
    if mode is ReserveMode.FIXED:
        raw = float(fixed)
    else:
        cheapest = cheapest_interrupt(costs)
        raw = cheapest.cost if cheapest is not None else 0.0
    return min(max(0.0, raw), maximum / 2.0)


def breaks_reserve(
    current: float, cost: float, reserve: float, maximum: float, skill_id: int, energy_buff: bool
) -> bool:
    """Would casting this rotation skill leave less than the reserve? The spec's rules, in order."""
    if reserve <= 0:
        return False
    if skill_id in DRAINS_ALL_ENERGY_SKILL_IDS:
        return True
    if cost <= 0 or energy_buff or skill_id in ENERGY_GAIN_SKILL_IDS:
        return False
    if current >= maximum:
        return False  # a full bar never blocks, so a skill costing more than maximum - reserve is never stuck
    return current - cost < reserve


def cannot_interrupt(current: Optional[float], costs: Sequence[InterruptCost]) -> bool:
    """A ready interrupt exists and the energy pays for none of the ready ones."""
    ready_costs = [item.cost for item in costs if item.ready]
    return current is not None and bool(ready_costs) and all(current < cost for cost in ready_costs)


def make_energy_status(
    current: Optional[float], maximum: float, mode: ReserveMode, fixed: int, costs: Sequence[InterruptCost]
) -> EnergyStatus:
    cheapest = cheapest_interrupt(costs) if mode is ReserveMode.CHEAPEST else None
    return EnergyStatus(
        current=current,
        maximum=maximum,
        mode=mode,
        reserve=effective_reserve(mode, fixed, costs, maximum),
        reserve_skill_id=cheapest.skill_id if cheapest is not None else 0,
        cannot_interrupt=cannot_interrupt(current, costs),
    )


def energy_line(status: EnergyStatus, reserve_skill_name: str) -> str:
    if status.current is None:
        return "Energia: ?"
    head = f"Energia: {math.floor(status.current)}/{math.floor(status.maximum)}"
    if status.mode is ReserveMode.OFF:
        return f"{head} - reserva desligada"
    reserve = math.ceil(status.reserve)
    if status.mode is ReserveMode.FIXED:
        return f"{head} - reserva {reserve} (fixa)"
    return f"{head} - reserva {reserve} ({reserve_skill_name or 'sem interrupts'})"


def reserve_pause_text(skill_name: str) -> str:
    return f"rotacao em pausa: reserva para interrupt ({skill_name})"


def reserve_skipped_suffix(skill_name: str) -> str:
    return f" (reserva: saltou {skill_name})"
```

- [ ] **Step 4: Correr os testes**

Run: `python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_energy_reserve.py" -v`
Expected: `Ran 33 tests` … `OK`.

- [ ] **Step 5: Pyright, Black e isort**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows Widgets/Automation/Helpers/AutoRota/auto_rota_src/energy_reserve.py "Examples and tests/tests/auto_rota/test_auto_rota_energy_reserve.py"`
Expected: `0 errors, 0 warnings, 0 informations`.

Run: o Black em modo `--check` sobre os dois ficheiros.
Expected: `2 files would be left unchanged.`

Run: o isort em modo `--check-only` sobre os dois ficheiros.
Expected: código de saída 0.

Apaga os `__pycache__`:
Run: `find Widgets/Automation/Helpers/AutoRota "Examples and tests/tests" -name __pycache__ -type d -prune -exec rm -rf {} +`

- [ ] **Step 6: Commit (só com autorização)**

```bash
git add Widgets/Automation/Helpers/AutoRota/auto_rota_src/energy_reserve.py "Examples and tests/tests/auto_rota/test_auto_rota_energy_reserve.py"
git commit -m "$(cat <<'EOF'
feat(auto-rota): interrupt energy reserve rules (pure core)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `GameAdapter` — energia e custo partilhados, custos dos interrupts e a regra na rotação

**Files:**
- Modify: `Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py`

- [ ] **Step 1: Imports**

Substitui:

```python
from .decide import interrupt_from_rows
from .hex_guard import active_punishing_hexes
```

por:

```python
from .decide import interrupt_from_rows
from .energy_reserve import EnergyStatus
from .energy_reserve import InterruptCost
from .energy_reserve import ReserveMode
from .energy_reserve import breaks_reserve
from .energy_reserve import effective_reserve
from .energy_reserve import make_energy_status
from .hex_guard import active_punishing_hexes
```

- [ ] **Step 2: Estado da última skill saltada**

1. Substitui:

```python
        self._logged_failures: set[tuple[int, int]] = set()
```

por:

```python
        self._logged_failures: set[tuple[int, int]] = set()
        # First rotation skill the energy reserve skipped in the last decision (0: none), for the preview line.
        self.reserve_skip_skill_id: int = 0
```

2. Substitui:

```python
        combat.is_targeting_enabled = True
        return combat
```

por:

```python
        combat.is_targeting_enabled = True
        self.reserve_skip_skill_id = 0
        return combat
```

- [ ] **Step 3: Energia e custo partilhados, e os custos dos interrupts**

Substitui o método `_has_resources` inteiro:

```python
    def _has_resources(self, skill_id: int, adrenaline_a: int) -> bool:
        # Mirrors the adrenaline/energy gates of CombatClass.IsReadyToCast,
        # which cannot be reused here because it also picks its own target.
        combat = self._combat
        player_id = Player.GetAgentID()
        adrenaline_required = GLOBAL_CACHE.Skill.Data.GetAdrenaline(skill_id)
        if adrenaline_required > 0 and adrenaline_a < adrenaline_required:
            return False
        energy_fraction = combat.GetEnergyValues(player_id)
        if energy_fraction < 0.0:
            return False
        current_energy = energy_fraction * Agent.GetMaxEnergy(player_id)
        energy_cost = Routines.Checks.Skills.GetEnergyCostWithEffects(skill_id, player_id)
        if combat.expertise_exists:
            energy_cost = Routines.Checks.Skills.apply_expertise_reduction(
                energy_cost, combat.expertise_level, skill_id
            )
        return current_energy >= energy_cost
```

por:

```python
    def _current_energy(self) -> Optional[float]:
        """Current energy in points, read like IsReadyToCast (HeroAI mirror); None when it cannot be read."""
        player_id = Player.GetAgentID()
        energy_fraction = self._combat.GetEnergyValues(player_id)
        if energy_fraction < 0.0:
            return None
        return energy_fraction * Agent.GetMaxEnergy(player_id)

    def _energy_cost(self, skill_id: int) -> float:
        """Effective energy cost (effects such as Primal Echoes, then Expertise), as IsReadyToCast computes it."""
        combat = self._combat
        energy_cost = Routines.Checks.Skills.GetEnergyCostWithEffects(skill_id, Player.GetAgentID())
        if combat.expertise_exists:
            energy_cost = Routines.Checks.Skills.apply_expertise_reduction(
                energy_cost, combat.expertise_level, skill_id
            )
        return float(energy_cost)

    def _has_resources(self, skill_id: int, adrenaline_a: int) -> bool:
        # Mirrors the adrenaline/energy gates of CombatClass.IsReadyToCast,
        # which cannot be reused here because it also picks its own target.
        adrenaline_required = GLOBAL_CACHE.Skill.Data.GetAdrenaline(skill_id)
        if adrenaline_required > 0 and adrenaline_a < adrenaline_required:
            return False
        current_energy = self._current_energy()
        return current_energy is not None and current_energy >= self._energy_cost(skill_id)

    def _interrupt_costs(self) -> list[InterruptCost]:
        """Every interrupt-layer skill on the bar, ready or recharging, with its effective cost.

        No energy filter (it would drop the reserve to 0 exactly when energy is low) and no blocked-id filter:
        build-owned interrupts and the ones the hex guard pauses still need energy when they come back.
        """
        costs: list[InterruptCost] = []
        for skill in self._combat.GetSkills():
            data = skill.custom_skill_data
            if skill.skill_id == 0 or data.Nature != SkillNature.Interrupt.value:
                continue
            if int(data.TargetAllegiance) not in _REACH_BY_ALLEGIANCE:
                continue
            adrenaline_required = GLOBAL_CACHE.Skill.Data.GetAdrenaline(skill.skill_id)
            recharged = skill.skillbar_data.recharge == 0
            ready = recharged and int(skill.skillbar_data.adrenaline_a) >= adrenaline_required
            costs.append(InterruptCost(skill_id=skill.skill_id, cost=self._energy_cost(skill.skill_id), ready=ready))
        return costs
```

- [ ] **Step 4: A regra em `_rotation_decision`**

1. Substitui:

```python
    def _rotation_decision(self, preview: bool = False, allow_buffs: bool = True) -> Optional[Decision]:
        combat = self._combat
        selected_enemy = self._selected_enemy()
        for index, skill in enumerate(combat.GetSkills()):
```

por:

```python
    def _rotation_decision(
        self,
        preview: bool = False,
        allow_buffs: bool = True,
        reserve_mode: ReserveMode = ReserveMode.OFF,
        reserve_fixed: int = 0,
    ) -> Optional[Decision]:
        combat = self._combat
        selected_enemy = self._selected_enemy()
        maximum_energy = float(Agent.GetMaxEnergy(Player.GetAgentID()))
        current_energy = self._current_energy()
        reserve = 0.0
        if reserve_mode is not ReserveMode.OFF and current_energy is not None:
            reserve = effective_reserve(reserve_mode, reserve_fixed, self._interrupt_costs(), maximum_energy)
        for index, skill in enumerate(combat.GetSkills()):
```

2. Mais abaixo, no mesmo ciclo, depois dos filtros de alvo e de fora de combate, substitui:

```python
                continue  # out of combat only out-of-combat skills, like HeroAI (no buff spam while walking)
            combat.is_targeting_enabled = not attacks_selected_target
```

por:

```python
                continue  # out of combat only out-of-combat skills, like HeroAI (no buff spam while walking)
            if reserve > 0 and current_energy is not None:
                energy_buff = data.Nature == SkillNature.EnergyBuff.value
                skill_cost = self._energy_cost(skill.skill_id)
                if breaks_reserve(current_energy, skill_cost, reserve, maximum_energy, skill.skill_id, energy_buff):
                    # Only an affordable skill is credited to the reserve: an unaffordable one would be refused
                    # anyway, so the preview must not blame the reserve for it.
                    if self.reserve_skip_skill_id == 0 and current_energy >= skill_cost:
                        self.reserve_skip_skill_id = skill.skill_id
                    # After the pure filters and before IsReadyToCast and the preview's target lookups,
                    # so a skipped skill never reserves a target lock.
                    continue
            combat.is_targeting_enabled = not attacks_selected_target
```

- [ ] **Step 5: `rotation_after_build` e `next_decision` passam a reserva**

1. Substitui:

```python
    def rotation_after_build(self, blocked_skill_ids: Sequence[int], allow_buffs: bool = True) -> Optional[Decision]:
        """Rotation over the skills the build does not own (actual plays only, never the preview)."""
        self._sync_combat(blocked_skill_ids)
        return self._rotation_decision(preview=False, allow_buffs=allow_buffs)
```

por:

```python
    def rotation_after_build(
        self,
        blocked_skill_ids: Sequence[int],
        allow_buffs: bool = True,
        reserve_mode: ReserveMode = ReserveMode.OFF,
        reserve_fixed: int = 0,
    ) -> Optional[Decision]:
        """Rotation over the skills the build does not own (actual plays only, never the preview)."""
        self._sync_combat(blocked_skill_ids)
        return self._rotation_decision(
            preview=False, allow_buffs=allow_buffs, reserve_mode=reserve_mode, reserve_fixed=reserve_fixed
        )
```

2. Substitui:

```python
        blocked_skill_ids: Iterable[int] = (),
        rows: Optional[Sequence[CastRow]] = None,
    ) -> Optional[Decision]:
```

por:

```python
        blocked_skill_ids: Iterable[int] = (),
        rows: Optional[Sequence[CastRow]] = None,
        reserve_mode: ReserveMode = ReserveMode.OFF,
        reserve_fixed: int = 0,
    ) -> Optional[Decision]:
```

3. Substitui, no fim de `next_decision`:

```python
        if interrupt is not None:
            return interrupt
        return self._rotation_decision(preview, allow_buffs)
```

por:

```python
        if interrupt is not None:
            return interrupt
        return self._rotation_decision(
            preview=preview, allow_buffs=allow_buffs, reserve_mode=reserve_mode, reserve_fixed=reserve_fixed
        )
```

- [ ] **Step 6: `energy_status()` para a janela**

A seguir ao método `cast_watch` (antes de `def agent_name`), acrescenta:

```python
    def energy_status(self, mode: ReserveMode, fixed: int) -> EnergyStatus:
        """Energy, reserve and the "cannot interrupt" state for the window; call right after a sync (cast_watch)."""
        maximum_energy = float(Agent.GetMaxEnergy(Player.GetAgentID()))
        return make_energy_status(self._current_energy(), maximum_energy, mode, fixed, self._interrupt_costs())
```

- [ ] **Step 7: Verificar**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py`
Expected: `0 errors, 0 warnings, 0 informations`.

Run: o Black em modo `--check` sobre `game_adapter.py`.
Expected: `1 file would be left unchanged.`

Run: o isort em modo `--check-only` sobre `game_adapter.py`.
Expected: código de saída 0.

Corre os quatro ficheiros de testes da Auto Rota: decide, hex guard, cast watch e energy reserve.
Expected: 43, 26, 13 e 33 testes, todos OK.

Apaga os `__pycache__`.

- [ ] **Step 8: Commit (só com autorização)**

```bash
git add Widgets/Automation/Helpers/AutoRota/auto_rota_src/game_adapter.py
git commit -m "$(cat <<'EOF'
feat(auto-rota): energy reserve in the rotation, sharing the energy and cost reads with the cast gate

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Widget — definições, jogadas, pré-visualização e janela

**Files:**
- Modify: `Widgets/Automation/Helpers/AutoRota/Auto Rota.py`

- [ ] **Step 1: Imports, constantes e estado**

1. Substitui:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import interrupt_from_rows
```

por:

```python
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.decide import interrupt_from_rows
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import CANNOT_INTERRUPT_TEXT
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import MODE_CHOICES
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import MODE_LABELS
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import RESERVE_FIXED_DEFAULT
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import RESERVE_FIXED_MAX
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import EnergyStatus
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import ReserveMode
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import energy_line
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import mode_from_setting
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import reserve_pause_text
from Widgets.Automation.Helpers.AutoRota.auto_rota_src.energy_reserve import reserve_skipped_suffix
```

2. Substitui:

```python
_SETTINGS_CAST_WATCH_OPEN = "cast_watch_open"
```

por:

```python
_SETTINGS_CAST_WATCH_OPEN = "cast_watch_open"
_SETTINGS_RESERVE_MODE = "energy_reserve_mode"
_SETTINGS_RESERVE_FIXED = "energy_reserve_fixed"
```

3. Substitui:

```python
_load_job: Optional[Generator[Any, Any, Any]] = None
```

por:

```python
_reserve_mode = ReserveMode.CHEAPEST  # loaded from the settings together with the keys
_reserve_fixed = RESERVE_FIXED_DEFAULT
_energy_status: Optional[EnergyStatus] = None
_energy_text = ""
_load_job: Optional[Generator[Any, Any, Any]] = None
```

- [ ] **Step 2: As jogadas passam a reserva**

1. Em `_play_once`, substitui:

```python
        decision = _adapter.next_decision(allow_buffs=_buffs_on, blocked_skill_ids=_guard_ids)
```

por:

```python
        decision = _adapter.next_decision(
            allow_buffs=_buffs_on,
            blocked_skill_ids=_guard_ids,
            reserve_mode=_reserve_mode,
            reserve_fixed=_reserve_fixed,
        )
```

2. Em `_finish_build_pass`, substitui:

```python
    decision = _adapter.rotation_after_build(sorted(blocked), allow_buffs=_buffs_on)
```

por:

```python
    decision = _adapter.rotation_after_build(
        sorted(blocked), allow_buffs=_buffs_on, reserve_mode=_reserve_mode, reserve_fixed=_reserve_fixed
    )
```

- [ ] **Step 3: Pré-visualização e estado da energia**

1. Substitui a função `_update_preview` inteira (de `def _update_preview() -> None:` até à linha `_preview_text = _adapter.describe(interrupt) if interrupt is not None else "jogada da build (decidida ao jogar)"`, inclusive) por:

```python
def _update_energy() -> None:
    """Energy line and the "cannot interrupt" state for both windows (needs the sync cast_watch just did)."""
    global _energy_status, _energy_text
    try:
        status = _adapter.energy_status(_reserve_mode, _reserve_fixed)
        name = _adapter.skill_name(status.reserve_skill_id) if status.reserve_skill_id else ""
        _energy_status, _energy_text = status, energy_line(status, name)
    except Exception as exc:
        _energy_status, _energy_text = None, "Energia: erro (ver consola)"
        _log_error_once("energy", exc)


def _preview_decision_text(decision: Optional[Decision]) -> str:
    """Preview text of a generic decision, saying when the energy reserve skipped a rotation skill."""
    skipped = _adapter.reserve_skip_skill_id
    if decision is None:
        return reserve_pause_text(_adapter.skill_name(skipped)) if skipped else "nada a fazer"
    text = _adapter.describe(decision)
    return text + reserve_skipped_suffix(_adapter.skill_name(skipped)) if skipped else text


def _update_preview() -> None:
    global _preview_text, _heroai_conflict, _watch_paused, _watch_error, _energy_status, _energy_text
    _heroai_conflict = _adapter.heroai_conflict()
    reason = _adapter.blocker()
    if reason is not None and reason != REASON_BUSY:
        _preview_text = f"em pausa ({reason})"
        _watch_paused = reason
        _store_watch([])
        _energy_status, _energy_text = None, ""
        return
    _watch_paused = ""
    rows: Optional[list[CastRow]] = None
    try:
        rows = _adapter.cast_watch(_guard_ids)  # one read per tick feeds the preview and the cast watch
        _watch_error = False
    except Exception as exc:
        _watch_error = True
        _log_error_once("cast watch", exc)
    _refresh_watch(rows or [])
    _update_energy()
    build_ids = _build_mode.blocked_skill_ids()
    build_paused = _build_mode.build_name is not None and build_paused_by_guard(_guard_ids, build_ids)
    if _build_mode.build_name is None or build_paused:
        decision = _adapter.next_decision(
            preview=True,
            allow_buffs=_buffs_on,
            blocked_skill_ids=_guard_ids,
            rows=rows,
            reserve_mode=_reserve_mode,
            reserve_fixed=_reserve_fixed,
        )
        text = _preview_decision_text(decision)
        _preview_text = f"build em pausa ({guard_reason(_guard_hexes)}): {text}" if build_paused else text
        return
    if rows is not None:
        interrupt = interrupt_from_rows(rows, BUILD_MODE_MAX_TIER)
    else:
        interrupt = _adapter.interrupt_decision(BUILD_MODE_MAX_TIER, blocked_skill_ids=_guard_ids)
    _preview_text = _adapter.describe(interrupt) if interrupt is not None else "jogada da build (decidida ao jogar)"
```

- [ ] **Step 4: Aviso na janela da vigia**

Substitui:

```python
        PyImGui.text_disabled("tecla em pausa: o ciclo esta ligado")
```

por:

```python
        PyImGui.text_disabled("tecla em pausa: o ciclo esta ligado")
    if _energy_status is not None and _energy_status.cannot_interrupt:
        PyImGui.text_colored(CANNOT_INTERRUPT_TEXT, _WARNING_COLOR)
```

- [ ] **Step 5: Janela principal — linha da energia, aviso e controlos**

1. Substitui:

```python
    global _interrupt_key_index, _interrupt_key_edge
```

por:

```python
    global _interrupt_key_index, _interrupt_key_edge, _reserve_mode, _reserve_fixed
```

2. Substitui:

```python
                PyImGui.text(f"Buffs: DESLIGADOS  ({buff_label})")
```

por:

```python
                PyImGui.text(f"Buffs: DESLIGADOS  ({buff_label})")
            if _energy_text:
                PyImGui.text(_energy_text)
            if _energy_status is not None and _energy_status.cannot_interrupt:
                PyImGui.text_colored(CANNOT_INTERRUPT_TEXT, _WARNING_COLOR)
```

3. Substitui:

```python
                _set_watch_open(new_watch_open)
```

por:

```python
                _set_watch_open(new_watch_open)
            mode_index = MODE_CHOICES.index(_reserve_mode)
            new_mode_index = PyImGui.combo("Reserva interrupt", mode_index, [MODE_LABELS[m] for m in MODE_CHOICES])
            if new_mode_index != mode_index:
                _reserve_mode = MODE_CHOICES[new_mode_index]
                _settings.set_str(_SETTINGS_SECTION, _SETTINGS_RESERVE_MODE, _reserve_mode.value)
                _push_history(f"Reserva interrupt: {MODE_LABELS[_reserve_mode]}")
            if _reserve_mode is ReserveMode.FIXED:
                new_fixed = PyImGui.slider_int("Reserva fixa", _reserve_fixed, 0, RESERVE_FIXED_MAX)
                new_fixed = min(RESERVE_FIXED_MAX, max(0, new_fixed))  # Ctrl+click typing is not clamped by ImGui
                if new_fixed != _reserve_fixed:
                    _reserve_fixed = new_fixed
                    _settings.set_int(_SETTINGS_SECTION, _SETTINGS_RESERVE_FIXED, new_fixed)
```

- [ ] **Step 6: Tooltip**

Substitui:

```python
    PyImGui.text("Vigia de casts: janela com os casts inimigos ao alcance e o interrupt que chega a tempo.")
```

por:

```python
    PyImGui.text("Vigia de casts: janela com os casts inimigos ao alcance e o interrupt que chega a tempo.")
    PyImGui.text("Reserva de energia: so na rotacao (a build gere a propria energia).")
```

- [ ] **Step 7: `main()` — carregar as definições**

1. Substitui:

```python
    global _interrupt_key_index, _watch_open
```

por:

```python
    global _interrupt_key_index, _watch_open, _reserve_mode, _reserve_fixed
```

2. Substitui:

```python
            _watch_open = _settings.get_bool(_SETTINGS_SECTION, _SETTINGS_CAST_WATCH_OPEN, True)
```

por:

```python
            _watch_open = _settings.get_bool(_SETTINGS_SECTION, _SETTINGS_CAST_WATCH_OPEN, True)
            saved_mode = _settings.get_str(_SETTINGS_SECTION, _SETTINGS_RESERVE_MODE, ReserveMode.CHEAPEST.value)
            _reserve_mode = mode_from_setting(saved_mode)
            saved_fixed = _settings.get_int(_SETTINGS_SECTION, _SETTINGS_RESERVE_FIXED, RESERVE_FIXED_DEFAULT)
            _reserve_fixed = min(RESERVE_FIXED_MAX, max(0, saved_fixed))
```

- [ ] **Step 8: Verificar**

Run: `npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows "Widgets/Automation/Helpers/AutoRota" "Examples and tests/tests/auto_rota"`
Expected: `0 errors, 0 warnings, 0 informations`.

Run: o Black em modo `--check` sobre `"Widgets/Automation/Helpers/AutoRota/Auto Rota.py"`.
Expected: `1 file would be left unchanged.`

Run: o isort em modo `--check-only` sobre o mesmo ficheiro.
Expected: código de saída 0.

Run: `python3.12 -B -m py_compile "Widgets/Automation/Helpers/AutoRota/Auto Rota.py"`
Expected: sem output.

Corre os quatro ficheiros de testes da Auto Rota.
Expected: 43, 26, 13 e 33 testes, todos OK.

Confirma que as jogadas da rotação levam a reserva:
Run: `grep -n "reserve_mode=_reserve_mode" "Widgets/Automation/Helpers/AutoRota/Auto Rota.py"`
Expected: 3 linhas: `_play_once`, `_finish_build_pass` e `_update_preview`.

Apaga os `__pycache__`.

- [ ] **Step 9: Commit (só com autorização)**

```bash
git add "Widgets/Automation/Helpers/AutoRota/Auto Rota.py"
git commit -m "$(cat <<'EOF'
feat(auto-rota): energy reserve mode, energy line and "sem energia para interromper" warning

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Documentação e verificação final

**Files:**
- Modify: `docs/superpowers/specs/2026-10-25-auto-rota-energy-reserve-design.md`
- Modify: `docs/superpowers/specs/2026-10-24-auto-rota-design.md`

- [ ] **Step 1: Estado da spec da reserva**

Os ajustes feitos durante o planeamento já estão na spec. Falta só o estado. Em `docs/superpowers/specs/2026-10-25-auto-rota-energy-reserve-design.md`, substitui:

```markdown
Data: 2026-10-25 · Estado: aprovado, por implementar · Branch: `feature/auto-rota`
```

por:

```markdown
Data: 2026-10-25 · Estado: implementado, por validar no jogo · Branch: `feature/auto-rota`
```

- [ ] **Step 2: Ligação a partir da spec base**

Em `docs/superpowers/specs/2026-10-24-auto-rota-design.md`, substitui:

```markdown
Ver também: `docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md` (guarda contra hexes punitivos)
e `docs/superpowers/specs/2026-10-25-auto-rota-cast-watch-design.md` (vigia de casts e interrupt de um toque).
```

por:

```markdown
Ver também: `docs/superpowers/specs/2026-10-25-auto-rota-hex-guard-design.md` (guarda contra hexes punitivos),
`docs/superpowers/specs/2026-10-25-auto-rota-cast-watch-design.md` (vigia de casts e interrupt de um toque)
e `docs/superpowers/specs/2026-10-25-auto-rota-energy-reserve-design.md` (reserva de energia para interrupts).
```

- [ ] **Step 3: Verificação completa**

Run, um a um:

```bash
python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_decide.py" -v
python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_hex_guard.py" -v
python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_cast_watch.py" -v
python3.12 "Examples and tests/tests/auto_rota/test_auto_rota_energy_reserve.py" -v
python3.12 "Examples and tests/tests/combat_meter/test_combat_meter.py" -v
npx -y pyright@1.1.390 --pythonversion 3.13 --pythonplatform Windows "Widgets/Automation/Helpers/AutoRota" "Examples and tests/tests/auto_rota"
find Widgets/Automation/Helpers/AutoRota "Examples and tests/tests" -name __pycache__ -type d -prune -exec rm -rf {} +
git status --short
```

Expected:
- **Testes:** 43, 26, 13, 33 e 11, todos OK.
- **Pyright:** `0 errors`.
- **`git status`:** só os ficheiros deste plano. Com os commits autorizados, ficam só os dois `.md` desta tarefa e o plano.

- [ ] **Step 4: Commit (só com autorização)**

```bash
git add docs/superpowers/specs/2026-10-25-auto-rota-energy-reserve-design.md docs/superpowers/specs/2026-10-24-auto-rota-design.md docs/superpowers/plans/2026-10-25-auto-rota-energy-reserve.md
git commit -m "$(cat <<'EOF'
docs(auto-rota): energy reserve spec, plan and status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
)"
```

---

## Validação no jogo (depois da implementação, pelo utilizador no Windows)

Copia de novo a pasta `Widgets/Automation/Helpers/AutoRota` a partir do zip do branch, e faz Reload no catálogo de widgets. Depois confirma:

1. **Linha da energia:** a linha `Energia: X/Y - reserva Z (...)` mostra valores certos. Com a barra cheia, X é igual a Y.
2. **Energia baixa, modo do mais barato:** a pré-visualização mostra `rotacao em pausa: reserva para interrupt (...)`, e os interrupts continuam a sair, pelo ciclo e pela F3.
3. **Aviso:** `sem energia para interromper` acende nas duas janelas quando nenhum interrupt pronto se pode pagar.
4. **Modo `Fixa` a 25:** a rotação guarda mais energia. Em `Desligada`, comporta-se como antes.
5. **Build Psychic Instability Wastrel's:** as jogadas da build não mudam.
6. **Skills de energia:** Ether Signet e Energy Tap continuam a sair com a energia baixa.
